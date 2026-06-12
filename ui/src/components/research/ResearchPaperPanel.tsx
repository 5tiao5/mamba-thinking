import { useEffect, useRef, useState } from "react";

import { api, toErrorMessage } from "../../lib/api";
import { cleanDisplayText } from "../../lib/displayText";
import type {
  PdfImportItem,
  ResearchPaperItem,
  ResearchPaperStatus,
} from "../../types/api";
import { StatusPill } from "../ui/StatusPill";

type ResearchPaperPanelProps = {
  conversationId: string;
  onStatusChange?: (message: string) => void;
};

const statusLabels: Record<ResearchPaperStatus, string> = {
  candidate: "候选",
  core: "核心",
  excluded: "已排除",
};

function statusTone(status: ResearchPaperStatus) {
  if (status === "core") return "success";
  if (status === "excluded") return "danger";
  return "info";
}

function importResultMessage(items: PdfImportItem[]) {
  const imported = items.filter((item) => item.success);
  const failed = items.filter((item) => !item.success);
  if (!failed.length) {
    const replaced = imported.filter((item) => item.duplicate_replaced).length;
    return replaced
      ? `已导入 ${imported.length} 篇，其中 ${replaced} 篇替换了重复版本。`
      : `已导入 ${imported.length} 篇论文，可用于下一轮生成或追问。`;
  }
  return `已导入 ${imported.length} 篇，${failed.length} 篇失败：${failed
    .map((item) => `${item.filename}（${item.error_message}）`)
    .join("；")}`;
}

export function ResearchPaperPanel({
  conversationId,
  onStatusChange,
}: ResearchPaperPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [papers, setPapers] = useState<ResearchPaperItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState("");
  const [message, setMessage] = useState("上传的论文会进入当前研究，不会自动开始生成。");

  async function loadPapers() {
    if (!conversationId) {
      setPapers([]);
      return;
    }
    const response = await api.listResearchPapers(conversationId);
    setPapers(response.data.items);
  }

  useEffect(() => {
    let cancelled = false;
    if (!conversationId) {
      setPapers([]);
      return () => {
        cancelled = true;
      };
    }
    api
      .listResearchPapers(conversationId)
      .then((response) => {
        if (!cancelled) setPapers(response.data.items);
      })
      .catch((error) => {
        if (!cancelled) setMessage(`论文池加载失败：${toErrorMessage(error)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  async function uploadFiles(files: File[]) {
    if (!files.length || !conversationId) return;
    setLoading(true);
    setMessage(`正在解析并导入 ${files.length} 篇 PDF...`);
    try {
      const response = await api.importResearchPdfs(conversationId, files);
      const nextMessage = importResultMessage(response.data.items);
      setMessage(nextMessage);
      onStatusChange?.(nextMessage);
      await loadPapers();
    } catch (error) {
      const nextMessage = `PDF 导入失败：${toErrorMessage(error)}`;
      setMessage(nextMessage);
      onStatusChange?.(nextMessage);
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function updateStatus(paper: ResearchPaperItem, status: ResearchPaperStatus) {
    setUpdatingId(paper.paper_entry_id);
    try {
      const response = await api.updateResearchPaper(
        conversationId,
        paper.paper_entry_id,
        status
      );
      setPapers((current) =>
        current.map((item) =>
          item.paper_entry_id === paper.paper_entry_id ? response.data : item
        )
      );
      setMessage(`《${paper.title}》已设为${statusLabels[status]}论文。`);
    } catch (error) {
      setMessage(`状态更新失败：${toErrorMessage(error)}`);
    } finally {
      setUpdatingId("");
    }
  }

  const coreCount = papers.filter((paper) => paper.status === "core").length;
  const candidateCount = papers.filter((paper) => paper.status === "candidate").length;

  return (
    <section className="research-paper-panel" aria-label="本研究论文">
      <div className="research-paper-panel-head">
        <div>
          <span className="section-eyebrow">本研究论文</span>
          <strong>{papers.length ? `${papers.length} 篇已就绪` : "先加入你的论文"}</strong>
          <p>论文正文会进入当前研究知识范围，后续生成与追问可以继续引用。</p>
        </div>
        <div className="research-paper-panel-actions">
          <StatusPill tone={coreCount ? "success" : "neutral"} compact>
            核心 {coreCount}
          </StatusPill>
          <StatusPill tone={candidateCount ? "info" : "neutral"} compact>
            候选 {candidateCount}
          </StatusPill>
          <input
            accept="application/pdf,.pdf"
            hidden
            multiple
            onChange={(event) => void uploadFiles(Array.from(event.target.files ?? []))}
            ref={fileInputRef}
            type="file"
          />
          <button
            className="primary-button"
            disabled={loading}
            onClick={() => fileInputRef.current?.click()}
            type="button"
          >
            {loading ? "导入中" : "批量导入 PDF"}
          </button>
        </div>
      </div>

      <div className="research-paper-panel-status" role="status">
        {message}
      </div>

      {papers.length ? (
        <div className="research-paper-list">
          {papers.map((paper) => (
            <article className="research-paper-row" key={paper.paper_entry_id}>
              <div>
                <strong>{cleanDisplayText(paper.title, 160)}</strong>
                <span>
                  {paper.origin === "user_upload" ? "PDF 上传" : "论文导入"}
                  {typeof paper.metadata.page_count === "number"
                    ? ` · ${paper.metadata.page_count} 页`
                    : ""}
                </span>
              </div>
              <div className="research-paper-row-actions">
                <StatusPill tone={statusTone(paper.status)} compact>
                  {statusLabels[paper.status]}
                </StatusPill>
                {paper.status !== "core" ? (
                  <button
                    className="ghost-button"
                    disabled={updatingId === paper.paper_entry_id}
                    onClick={() => void updateStatus(paper, "core")}
                    type="button"
                  >
                    设为核心
                  </button>
                ) : (
                  <button
                    className="ghost-button"
                    disabled={updatingId === paper.paper_entry_id}
                    onClick={() => void updateStatus(paper, "candidate")}
                    type="button"
                  >
                    改为候选
                  </button>
                )}
                {paper.status !== "excluded" ? (
                  <button
                    className="ghost-button research-paper-exclude"
                    disabled={updatingId === paper.paper_entry_id}
                    onClick={() => void updateStatus(paper, "excluded")}
                    type="button"
                  >
                    排除
                  </button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="research-paper-empty">
          可一次选择多篇 PDF。系统会逐篇解析，某一篇失败不会影响其他论文。
        </div>
      )}
    </section>
  );
}
