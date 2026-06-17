import { Link } from "react-router-dom";

import { cleanDisplayText } from "../../lib/displayText";
import {
  formatRetrievalMessage,
  knowledgeScopeLabel,
  retrievalStatusLabel,
} from "../../lib/groundingText";
import type { WorkspaceInheritedContext, WorkspaceSourceTrace } from "../../types/api";

type MessageSourceTraceProps = {
  sourceTrace?: WorkspaceSourceTrace | null;
  inheritedContext?: WorkspaceInheritedContext | null;
  detailsHref?: string;
};

function uniqueTexts(items: string[], maxItems: number, maxLength = 40) {
  const seen = new Set<string>();
  const values: string[] = [];

  for (const item of items) {
    const cleaned = cleanDisplayText(item, maxLength);
    if (!cleaned || seen.has(cleaned)) {
      continue;
    }
    seen.add(cleaned);
    values.push(cleaned);
    if (values.length >= maxItems) {
      break;
    }
  }

  return values;
}

export function MessageSourceTrace({
  sourceTrace,
  inheritedContext,
  detailsHref,
}: MessageSourceTraceProps) {
  const knowledgeHits = sourceTrace?.knowledge_hits ?? [];
  const sharedKnowledgeCount = knowledgeHits.filter(
    (item) => (item.scope || "").toLowerCase() === "shared"
  ).length;
  const researchKnowledgeCount = knowledgeHits.length - sharedKnowledgeCount;
  const workspaceHints = uniqueTexts(
    [...(sourceTrace?.workspace_hints ?? []), ...(inheritedContext?.workspace_hints ?? [])],
    2,
    48
  );
  const recentTurns = uniqueTexts(
    inheritedContext?.recent_turns?.length
      ? inheritedContext.recent_turns
      : (sourceTrace?.recent_user_turns ?? []),
    1,
    68
  );
  const workspaceSummary = cleanDisplayText(inheritedContext?.workspace_summary ?? "", 120);
  const topic = cleanDisplayText(inheritedContext?.conversation_topic ?? "", 48);
  const workspaceHintCount = sourceTrace?.workspace_hint_count ?? 0;
  const recentTurnCount = sourceTrace?.recent_turn_count ?? 0;
  const displayedWorkspaceHintCount = Math.max(workspaceHintCount, workspaceHints.length);
  const displayedRecentTurnCount = Math.max(recentTurnCount, recentTurns.length);
  const knowledgeScope = sourceTrace?.knowledge_scope;
  const retrievalStatus = retrievalStatusLabel(sourceTrace?.retrieval_status);
  const retrievalMessage = formatRetrievalMessage(sourceTrace, 160);
  const fallbackUsed = sourceTrace?.fallback_used ?? false;

  const hasMetrics =
    Boolean(sourceTrace) &&
    (knowledgeHits.length > 0 ||
      displayedWorkspaceHintCount > 0 ||
      displayedRecentTurnCount > 0 ||
      Boolean(retrievalStatus) ||
      fallbackUsed ||
      knowledgeScope === "none");
  const hasContext =
    workspaceHints.length > 0 ||
    recentTurns.length > 0 ||
    Boolean(retrievalMessage) ||
    Boolean(workspaceSummary) ||
    Boolean(topic);

  if (!hasMetrics && !hasContext) {
    return null;
  }

  return (
    <div className="message-source-trace" aria-label="回答依据摘要">
      {hasMetrics ? (
        <div className="message-source-trace-metrics">
          <span className="message-source-trace-chip message-source-trace-chip-scope">
            {knowledgeScopeLabel(knowledgeScope)}
          </span>
          {retrievalStatus ? (
            <span className="message-source-trace-chip message-source-trace-chip-info">
              {retrievalStatus}
            </span>
          ) : null}
          {fallbackUsed ? (
            <span className="message-source-trace-chip message-source-trace-chip-warning">
              背景参考
            </span>
          ) : null}
        </div>
      ) : null}

      {retrievalMessage ? (
        <div className="message-source-trace-copy message-source-trace-copy-note">
          <strong>结果说明</strong>
          <span>{retrievalMessage}</span>
        </div>
      ) : null}

      {researchKnowledgeCount ||
      sharedKnowledgeCount ||
      displayedWorkspaceHintCount ||
      displayedRecentTurnCount ? (
        <div className="message-source-context-summary">
          <strong>本轮上下文</strong>
          <div className="message-source-context-items">
            {researchKnowledgeCount > 0 ? <span>当前研究资料 {researchKnowledgeCount}</span> : null}
            {sharedKnowledgeCount > 0 ? <span>全局共享知识 {sharedKnowledgeCount}</span> : null}
            {displayedWorkspaceHintCount > 0 ? (
              <span>沿用研究历史 {displayedWorkspaceHintCount}</span>
            ) : null}
            {displayedRecentTurnCount > 0 ? (
              <span>承接近期追问 {displayedRecentTurnCount}</span>
            ) : null}
          </div>
          <small>这些内容用于辅助理解本轮问题，不会自动被视为论文证据。</small>
        </div>
      ) : null}

      {!displayedWorkspaceHintCount && !displayedRecentTurnCount && (workspaceSummary || topic) ? (
        <div className="message-source-trace-copy">
          <strong>研究上下文</strong>
          <span>{workspaceSummary || topic}</span>
        </div>
      ) : null}

      {detailsHref ? (
        <Link className="message-source-details-link" to={detailsHref}>
          查看证据与上下文
        </Link>
      ) : null}
    </div>
  );
}
