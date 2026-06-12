from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from product_agent.domain import ConversationResearchPaper, KnowledgeDocument
from product_agent.paper_content_tools import (
    FullTextDocument,
    FullTextUnavailableError,
    parse_pdf_bytes,
)

from .knowledge_service import KnowledgeService
from .research_paper_service import ResearchPaperService


MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_FILES_PER_BATCH = 10
DEFAULT_MAX_PDF_PAGES = 80


@dataclass(frozen=True)
class PdfUploadInput:
    filename: str
    content_type: str
    payload: bytes


@dataclass
class PdfImportResult:
    filename: str
    success: bool
    document: KnowledgeDocument | None = None
    research_paper: ConversationResearchPaper | None = None
    parsed_pages: int = 0
    total_pages: int = 0
    duplicate_replaced: bool = False
    warnings: list[str] | None = None
    error_code: str = ""
    error_message: str = ""


class PdfImportService:
    """Turn uploaded PDFs into scoped knowledge and conversation paper assets."""

    def __init__(
        self,
        *,
        knowledge_service: KnowledgeService,
        research_paper_service: ResearchPaperService,
        parser: Callable[..., FullTextDocument] = parse_pdf_bytes,
    ) -> None:
        self.knowledge_service = knowledge_service
        self.research_paper_service = research_paper_service
        self.parser = parser

    def import_batch(
        self,
        *,
        conversation_id: str,
        uploads: list[PdfUploadInput],
        status: str = "candidate",
    ) -> list[PdfImportResult]:
        self.research_paper_service.validate_status(status)
        return [
            self._import_one(
                conversation_id=conversation_id,
                upload=upload,
                status=status,
            )
            for upload in uploads
        ]

    def _import_one(
        self,
        *,
        conversation_id: str,
        upload: PdfUploadInput,
        status: str,
    ) -> PdfImportResult:
        filename = Path(upload.filename or "uploaded-paper.pdf").name
        validation_error = self._validate_upload(upload)
        if validation_error:
            return PdfImportResult(
                filename=filename,
                success=False,
                error_code=validation_error[0],
                error_message=validation_error[1],
            )

        try:
            parsed = self.parser(
                upload.payload,
                source_url="",
                max_pages=DEFAULT_MAX_PDF_PAGES,
            )
        except FullTextUnavailableError as error:
            return PdfImportResult(
                filename=filename,
                success=False,
                error_code="pdf_parse_failed",
                error_message=str(error),
            )
        except Exception as error:
            return PdfImportResult(
                filename=filename,
                success=False,
                error_code="pdf_parse_failed",
                error_message=f"Unable to parse PDF content: {error}",
            )

        if not parsed.text.strip():
            return PdfImportResult(
                filename=filename,
                success=False,
                parsed_pages=len(parsed.pages),
                total_pages=parsed.total_pages,
                warnings=list(parsed.warnings),
                error_code="pdf_text_unavailable",
                error_message="The PDF contains no extractable text and may require OCR.",
            )

        title = self._infer_title(parsed, filename)
        metadata = {
            "source_type": "paper_import",
            "import_method": "pdf_upload",
            "paper_source": "user_upload",
            "original_filename": filename,
            "content_type": upload.content_type or "application/pdf",
            "file_size": len(upload.payload),
            "parser": parsed.parser,
            "page_count": parsed.total_pages or len(parsed.pages),
            "parsed_page_count": len(parsed.pages),
            "truncated": parsed.truncated,
            "parse_warnings": list(parsed.warnings),
            "pdf_metadata": dict(parsed.metadata),
        }
        content = self._build_page_aware_content(parsed)
        try:
            document = self.knowledge_service.import_document(
                title=title,
                content=content,
                tags=["paper", "pdf", "user-upload"],
                conversation_id=conversation_id,
                metadata_extra=metadata,
                index_immediately=True,
            )
            previous = self.research_paper_service.find_matching_document(
                conversation_id=conversation_id,
                document=document,
            )
            paper = self.research_paper_service.add_document(
                conversation_id=conversation_id,
                document=document,
                origin="user_upload",
                status=status,
            )
        except Exception as error:
            if "document" in locals():
                self.knowledge_service.delete_document(document.document_id)
            return PdfImportResult(
                filename=filename,
                success=False,
                parsed_pages=len(parsed.pages),
                total_pages=parsed.total_pages or len(parsed.pages),
                warnings=list(parsed.warnings),
                error_code="pdf_import_failed",
                error_message=f"Unable to store imported PDF: {error}",
            )

        replaced = bool(previous and previous.document_id != document.document_id)
        if replaced:
            self.knowledge_service.delete_document(previous.document_id)

        return PdfImportResult(
            filename=filename,
            success=True,
            document=document,
            research_paper=paper,
            parsed_pages=len(parsed.pages),
            total_pages=parsed.total_pages or len(parsed.pages),
            duplicate_replaced=replaced,
            warnings=list(parsed.warnings),
        )

    @staticmethod
    def _validate_upload(upload: PdfUploadInput) -> tuple[str, str] | None:
        filename = upload.filename or ""
        if not filename.lower().endswith(".pdf"):
            return "unsupported_file_type", "Only PDF files can be imported."
        if not upload.payload:
            return "empty_file", "The uploaded PDF is empty."
        if len(upload.payload) > MAX_PDF_BYTES:
            return "file_too_large", "Each PDF must be 20 MB or smaller."
        if not upload.payload.startswith(b"%PDF"):
            return "invalid_pdf", "The uploaded file is not a valid PDF."
        return None

    @classmethod
    def _infer_title(cls, parsed: FullTextDocument, filename: str) -> str:
        metadata_title = cls._clean_title(parsed.metadata.get("title", ""))
        if metadata_title:
            return metadata_title

        first_page = parsed.pages[0].text if parsed.pages else ""
        candidates = [line.strip() for line in first_page.splitlines() if line.strip()]
        for index, line in enumerate(candidates[:8]):
            if cls._looks_like_title(line):
                title = line
                if index + 1 < len(candidates) and len(title) < 70:
                    continuation = candidates[index + 1]
                    if cls._looks_like_title(continuation) and not continuation.lower().startswith("abstract"):
                        title = f"{title} {continuation}"
                return cls._clean_title(title) or Path(filename).stem

        return cls._clean_title(Path(filename).stem) or "Uploaded paper"

    @staticmethod
    def _clean_title(value: str) -> str:
        title = " ".join(str(value or "").split()).strip(" -_:")
        if title.casefold() in {"", "untitled", "microsoft word"}:
            return ""
        return title[:300]

    @staticmethod
    def _looks_like_title(value: str) -> bool:
        normalized = " ".join(value.split()).strip()
        if not 8 <= len(normalized) <= 240:
            return False
        lowered = normalized.casefold()
        if lowered.startswith(("arxiv:", "doi:", "abstract", "http://", "https://")):
            return False
        if re.fullmatch(r"[\W\d_]+", normalized):
            return False
        return True

    @staticmethod
    def _build_page_aware_content(parsed: FullTextDocument) -> str:
        return "\n\n".join(
            f"[Page {page.page_number}]\n{page.text}"
            for page in parsed.pages
            if page.text.strip()
        )
