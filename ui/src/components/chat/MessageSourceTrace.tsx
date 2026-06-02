import { cleanDisplayText } from "../../lib/displayText";
import {
  formatRetrievalMessage,
  formatRetrievalPlan,
  knowledgeScopeLabel,
  retrievalStatusLabel,
} from "../../lib/groundingText";
import type { WorkspaceInheritedContext, WorkspaceSourceTrace } from "../../types/api";

type MessageSourceTraceProps = {
  sourceTrace?: WorkspaceSourceTrace | null;
  inheritedContext?: WorkspaceInheritedContext | null;
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

export function MessageSourceTrace({ sourceTrace, inheritedContext }: MessageSourceTraceProps) {
  const knowledgeTitles = uniqueTexts(
    (sourceTrace?.knowledge_hits ?? []).map((item) => item.title),
    2,
    36
  );
  const knowledgeSnippets = uniqueTexts(
    (sourceTrace?.knowledge_hits ?? []).map((item) => item.snippet),
    1,
    120
  );
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
  const knowledgeHitCount = sourceTrace?.knowledge_hit_count ?? 0;
  const workspaceHintCount = sourceTrace?.workspace_hint_count ?? 0;
  const recentTurnCount = sourceTrace?.recent_turn_count ?? 0;
  const knowledgeScope = sourceTrace?.knowledge_scope;
  const retrievalStatus = retrievalStatusLabel(sourceTrace?.retrieval_status);
  const retrievalPlan = formatRetrievalPlan(sourceTrace?.retrieval_plan, 120);
  const retrievalMessage = formatRetrievalMessage(sourceTrace, 160);
  const filteredOutCount = sourceTrace?.filtered_out_count ?? 0;
  const fallbackUsed = sourceTrace?.fallback_used ?? false;

  const hasMetrics =
    Boolean(sourceTrace) &&
    (knowledgeHitCount > 0 ||
      workspaceHintCount > 0 ||
      recentTurnCount > 0 ||
      filteredOutCount > 0 ||
      Boolean(retrievalStatus) ||
      fallbackUsed ||
      knowledgeScope === "none");
  const hasContext =
    knowledgeTitles.length > 0 ||
    knowledgeSnippets.length > 0 ||
    workspaceHints.length > 0 ||
    recentTurns.length > 0 ||
    Boolean(retrievalPlan) ||
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
          {knowledgeHitCount > 0 ? (
            <span className="message-source-trace-chip">知识命中 {knowledgeHitCount}</span>
          ) : null}
          {workspaceHintCount > 0 ? (
            <span className="message-source-trace-chip">历史结论 {workspaceHintCount}</span>
          ) : null}
          {filteredOutCount > 0 ? (
            <span className="message-source-trace-chip">过滤越界 {filteredOutCount}</span>
          ) : null}
          {recentTurnCount > 0 ? (
            <span className="message-source-trace-chip">近期追问 {recentTurnCount}</span>
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

      {retrievalPlan ? (
        <div className="message-source-trace-copy">
          <strong>检索策略</strong>
          <span>{retrievalPlan}</span>
        </div>
      ) : null}

      {knowledgeTitles.length ? (
        <div className="message-source-trace-copy">
          <strong>参考资料</strong>
          <span>{knowledgeTitles.join(" / ")}</span>
        </div>
      ) : null}

      {knowledgeSnippets.length ? (
        <div className="message-source-trace-copy">
          <strong>命中片段</strong>
          <span>{knowledgeSnippets[0]}</span>
        </div>
      ) : null}

      {workspaceHints.length ? (
        <div className="message-source-trace-copy">
          <strong>继承线索</strong>
          <span>{workspaceHints.join(" / ")}</span>
        </div>
      ) : null}

      {!workspaceHints.length && workspaceSummary ? (
        <div className="message-source-trace-copy">
          <strong>继承结论</strong>
          <span>{workspaceSummary}</span>
        </div>
      ) : null}

      {recentTurns.length ? (
        <div className="message-source-trace-copy">
          <strong>承接追问</strong>
          <span>{recentTurns[0]}</span>
        </div>
      ) : null}

      {!recentTurns.length && topic ? (
        <div className="message-source-trace-copy">
          <strong>研究主题</strong>
          <span>{topic}</span>
        </div>
      ) : null}
    </div>
  );
}
