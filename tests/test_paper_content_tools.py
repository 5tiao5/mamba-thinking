from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from product_agent.app_container import AppContainer
from product_agent.paper_content_tools import (
    FullTextUnavailableError,
    fetch_full_text,
    parse_pdf_bytes,
    resolve_paper,
)


class _Response:
    def __init__(
        self,
        payload: bytes,
        *,
        content_type: str = "application/json",
    ) -> None:
        self._payload = payload
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._payload if size < 0 else self._payload[:size]


class PaperContentToolTests(unittest.TestCase):
    @patch("product_agent.paper_content_tools.urllib.request.urlopen")
    def test_resolve_arxiv_id_returns_canonical_pdf_location(self, urlopen) -> None:
        urlopen.return_value = _Response(
            b"""<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <id>https://arxiv.org/abs/2501.01234v2</id>
                <published>2025-01-03T00:00:00Z</published>
                <title>Reliable Tool Use Agents</title>
                <summary>We evaluate failure recovery.</summary>
                <author><name>Ada Researcher</name></author>
              </entry>
            </feed>"""
        )

        result = resolve_paper("https://arxiv.org/abs/2501.01234v2")

        self.assertIsNotNone(result)
        self.assertEqual(result.paper_id, "2501.01234")
        self.assertEqual(result.arxiv_id, "2501.01234")
        self.assertEqual(result.pdf_url, "https://arxiv.org/pdf/2501.01234.pdf")
        self.assertEqual(result.resolution_method, "arxiv_id")

    @patch("product_agent.paper_content_tools.urllib.request.urlopen")
    def test_resolve_title_prefers_best_openalex_match(self, urlopen) -> None:
        payload = {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "display_name": "Unrelated Vision Paper",
                },
                {
                    "id": "https://openalex.org/W2",
                    "display_name": "Reliable Tool Use Agents",
                    "publication_date": "2025-02-01",
                    "best_oa_location": {
                        "landing_page_url": "https://example.org/paper",
                        "pdf_url": "https://example.org/paper.pdf",
                    },
                    "ids": {"doi": "https://doi.org/10.1000/tool-use"},
                    "authorships": [
                        {"author": {"display_name": "Ada Researcher"}}
                    ],
                    "abstract_inverted_index": {
                        "Tool": [0],
                        "agents": [1],
                        "recover": [2],
                    },
                },
            ]
        }
        urlopen.return_value = _Response(json.dumps(payload).encode("utf-8"))

        result = resolve_paper("Reliable Tool Use Agents")

        self.assertIsNotNone(result)
        self.assertEqual(result.paper_id, "10.1000/tool-use")
        self.assertEqual(result.pdf_url, "https://example.org/paper.pdf")
        self.assertEqual(result.abstract, "Tool agents recover")
        self.assertEqual(result.resolution_method, "title")

    @patch("product_agent.paper_content_tools.urllib.request.urlopen")
    def test_resolve_doi_uses_openalex_identity(self, urlopen) -> None:
        payload = {
            "id": "https://openalex.org/W3",
            "display_name": "Evidence-Grounded Research Agents",
            "publication_date": "2024-06-01",
            "best_oa_location": {
                "landing_page_url": "https://example.org/article",
                "pdf_url": "https://example.org/article.pdf",
            },
            "ids": {"doi": "https://doi.org/10.1000/research-agent"},
        }
        urlopen.return_value = _Response(json.dumps(payload).encode("utf-8"))

        result = resolve_paper("doi:10.1000/research-agent")

        self.assertIsNotNone(result)
        self.assertEqual(result.paper_id, "10.1000/research-agent")
        self.assertEqual(result.source, "openalex")
        self.assertEqual(result.resolution_method, "doi")
        requested_url = urlopen.call_args.args[0].full_url
        self.assertIn("https://doi.org/10.1000/research-agent", requested_url)

    @patch("product_agent.paper_content_tools.parse_pdf_bytes")
    @patch("product_agent.paper_content_tools.urllib.request.urlopen")
    def test_fetch_full_text_downloads_only_pdf_content(
        self,
        urlopen,
        parse_pdf,
    ) -> None:
        urlopen.return_value = _Response(
            b"%PDF-test",
            content_type="application/pdf",
        )

        fetch_full_text("https://arxiv.org/pdf/2501.01234.pdf")

        parse_pdf.assert_called_once_with(
            b"%PDF-test",
            source_url="https://arxiv.org/pdf/2501.01234.pdf",
            max_pages=40,
        )

    @patch("product_agent.paper_content_tools.urllib.request.urlopen")
    def test_fetch_full_text_rejects_non_pdf_response(self, urlopen) -> None:
        urlopen.return_value = _Response(
            b"<html>not a PDF</html>",
            content_type="text/html",
        )

        with self.assertRaisesRegex(FullTextUnavailableError, "did not return a PDF"):
            fetch_full_text("https://example.org/paper")

    def test_parse_pdf_preserves_page_and_section_provenance(self) -> None:
        try:
            import fitz
        except ModuleNotFoundError:
            self.skipTest("PyMuPDF is not installed.")

        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text(
            (72, 72),
            "Introduction\nThis paper studies tool recovery.\n"
            "Experiments\nOur method improves accuracy by 8 percent.",
        )
        payload = pdf.tobytes()
        pdf.close()

        result = parse_pdf_bytes(payload, source_url="https://example.org/paper.pdf")

        self.assertEqual(len(result.pages), 1)
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(result.pages[0].page_number, 1)
        self.assertEqual(
            [section.heading for section in result.sections],
            ["Introduction", "Experiments"],
        )
        self.assertIn("improves accuracy", result.sections[1].text)

    def test_new_tools_are_registered_for_product_configuration(self) -> None:
        container = AppContainer(storage_backend="memory")

        tools = {tool.tool_id: tool for tool in container.tool_service.list_tools()}

        self.assertIn("paper_resolver", tools)
        self.assertIn("fulltext_fetcher", tools)
        self.assertEqual(
            tools["fulltext_fetcher"].config["default_max_pages"],
            40,
        )


if __name__ == "__main__":
    unittest.main()
