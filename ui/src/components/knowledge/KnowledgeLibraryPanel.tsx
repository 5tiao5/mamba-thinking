import { useEffect, useMemo, useState } from "react";

import { api, toErrorMessage } from "../../lib/api";
import { cleanDisplayText } from "../../lib/displayText";
import { compactText } from "../../lib/productText";
import type { CreateKnowledgeDocumentPayload, KnowledgeDocumentItem } from "../../types/api";
import { StatusPill } from "../ui/StatusPill";

type KnowledgeLibraryPanelProps = {
  compact?: boolean;
};

type SearchMode = "keyword" | "tags";

function metadataString(document: KnowledgeDocumentItem, key: string) {
  const value = document.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function normalizeDraft(draft: CreateKnowledgeDocumentPayload): CreateKnowledgeDocumentPayload {
  return {
    title: draft.title.trim(),
    content: draft.content.trim(),
    tags: draft.tags?.map((tag) => tag.trim()).filter(Boolean) ?? [],
    source_url: draft.source_url?.trim() || null,
    notes: draft.notes?.trim() || null,
  };
}

export function KnowledgeLibraryPanel({ compact = false }: KnowledgeLibraryPanelProps) {
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("keyword");
  const [draft, setDraft] = useState<CreateKnowledgeDocumentPayload>({
    title: "",
    content: "",
    tags: [],
    source_url: "",
    notes: "",
  });
  const [status, setStatus] = useState("资料库会同步已导入的论文摘要、调研笔记和人工结论。");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void loadDocuments();
  }, []);

  const tagText = useMemo(() => draft.tags?.join(", ") ?? "", [draft.tags]);

  async function loadDocuments(nextQuery = query, nextMode = searchMode) {
    setLoading(true);
    setStatus(nextQuery.trim() ? "正在检索资料库..." : "正在同步资料库...");
    try {
      const response = nextQuery.trim()
        ? await api.searchKnowledge({ q: nextQuery.trim(), by: nextMode, limit: 30 })
        : await api.listKnowledgeDocuments();
      setDocuments(response.data.items);
      setStatus(nextQuery.trim() ? `找到 ${response.data.items.length} 条相关资料。` : "资料库已同步。");
    } catch (error) {
      setStatus(`资料库同步失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function createDocument() {
    const payload = normalizeDraft(draft);
    if (!payload.title || !payload.content) {
      setStatus("请先填写资料标题和正文。");
      return;
    }

    setLoading(true);
    setStatus("正在导入资料...");
    try {
      const response = await api.createKnowledgeDocument(payload);
      setDocuments((current) => [response.data, ...current]);
      setDraft({ title: "", content: "", tags: [], source_url: "", notes: "" });
      setStatus("资料已导入，后续研究会从资料库检索相关上下文。");
    } catch (error) {
      setStatus(`导入失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  async function deleteDocument(documentId: string) {
    setLoading(true);
    setStatus("正在删除资料...");
    try {
      await api.deleteKnowledgeDocument(documentId);
      setDocuments((current) => current.filter((document) => document.document_id !== documentId));
      setStatus("资料已删除。");
    } catch (error) {
      setStatus(`删除失败：${toErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className={compact ? "knowledge-panel knowledge-panel-compact" : "knowledge-panel"}>
      <div className="knowledge-panel-head">
        <div>
          <div className="section-eyebrow">资料管理</div>
          <h2>资料库</h2>
        </div>
        <StatusPill tone={loading ? "neutral" : "info"} compact>
          {loading ? "同步中" : `${documents.length} 条资料`}
        </StatusPill>
      </div>

      <div className="status-line">{status}</div>

      <div className="knowledge-library-layout">
        <section className="knowledge-import-panel">
          <div className="subsection-title">导入资料</div>
          <div className="knowledge-form">
            <input
              className="input"
              onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              placeholder="资料标题"
              value={draft.title}
            />
            <textarea
              className="input textarea"
              onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
              placeholder="粘贴论文摘要、调研笔记或已有结论"
              value={draft.content}
            />
            <div className="knowledge-form-grid">
              <input
                className="input"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    tags: event.target.value
                      .split(",")
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="标签，用逗号分隔"
                value={tagText}
              />
              <input
                className="input"
                onChange={(event) => setDraft((current) => ({ ...current, source_url: event.target.value }))}
                placeholder="来源链接，可选"
                value={draft.source_url ?? ""}
              />
            </div>
            <input
              className="input"
              onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
              placeholder="备注，可选"
              value={draft.notes ?? ""}
            />
            <button className="primary-button" disabled={loading} onClick={createDocument} type="button">
              导入资料
            </button>
          </div>
        </section>

        <section className="knowledge-search-panel">
          <div className="subsection-title">检索资料</div>
          <div className="knowledge-search-row">
            <input
              className="input"
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchMode === "tags" ? "输入标签，多个标签用逗号分隔" : "按关键词搜索资料"}
              value={query}
            />
            <select
              className="input knowledge-search-mode"
              onChange={(event) => setSearchMode(event.target.value as SearchMode)}
              value={searchMode}
            >
              <option value="keyword">关键词</option>
              <option value="tags">标签</option>
            </select>
            <button className="secondary-button" disabled={loading} onClick={() => loadDocuments()} type="button">
              搜索
            </button>
            <button
              className="ghost-button"
              disabled={loading}
              onClick={() => {
                setQuery("");
                void loadDocuments("", searchMode);
              }}
              type="button"
            >
              全部
            </button>
          </div>

          <div className="knowledge-doc-list">
            {documents.length ? (
              documents.map((document) => {
                const sourceUrl = metadataString(document, "source_url");
                const notes = metadataString(document, "notes");
                return (
                  <article className="knowledge-doc-card" key={document.document_id}>
                    <div>
                      <strong>{cleanDisplayText(document.title, 120)}</strong>
                      <p>{compactText(cleanDisplayText(document.content), compact ? 180 : 260)}</p>
                      <div className="knowledge-doc-meta">
                        {document.tags.length ? <span>{document.tags.join(" / ")}</span> : null}
                        {notes ? <span>{cleanDisplayText(notes, 120)}</span> : null}
                        {sourceUrl ? (
                          <a href={sourceUrl} rel="noreferrer" target="_blank">
                            来源
                          </a>
                        ) : null}
                      </div>
                    </div>
                    <button
                      aria-label="删除资料"
                      className="history-delete-button"
                      disabled={loading}
                      onClick={() => deleteDocument(document.document_id)}
                      title="删除资料"
                      type="button"
                    >
                      x
                    </button>
                  </article>
                );
              })
            ) : (
              <div className="empty-state">暂无资料。可以先导入论文摘要、调研笔记或已有结论。</div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
