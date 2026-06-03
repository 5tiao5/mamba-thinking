import { cleanDisplayText } from "../../lib/displayText";

type MessageMetric = {
  label: string;
  value: string;
};

type MessageSection = {
  key: "papers" | "priority" | "gaps" | "ideas" | "next" | "directions";
  title: string;
  items: string[];
};

type ParsedAssistantMessage = {
  raw: string;
  lead: string;
  metrics: MessageMetric[];
  sections: MessageSection[];
  structured: boolean;
};

const SECTION_LABEL_PATTERN =
  /(代表性论文|论文线索|优先关注|关键研究空白|研究空白|可继续推进的选题|建议选题|研究建议|下一步|建议动作|完整\s*研究方向图|研究方向图)\s*[-:：]/g;
const IDEA_LABEL_PATTERN = /\s+(选题[一二三四五六七八九十\d]+)\s*[:：]/g;
const SECTION_LINE_PATTERN =
  /^(代表性论文|论文线索|优先关注|关键研究空白|研究空白|可继续推进的选题|建议选题|研究建议|下一步|建议动作|完整\s*研究方向图|研究方向图)\s*[:：-]\s*(.*)$/;
const IDEA_LINE_PATTERN = /^(选题[一二三四五六七八九十\d]+)\s*[:：]\s*(.*)$/;

const sectionTitleMap: Record<MessageSection["key"], string> = {
  papers: "代表性论文",
  priority: "优先关注",
  gaps: "关键空白",
  ideas: "选题建议",
  next: "下一步",
  directions: "研究方向图",
};

function normalizeSectionKey(label: string): MessageSection["key"] {
  if (label.includes("论文")) return "papers";
  if (label.includes("优先关注")) return "priority";
  if (label.includes("空白")) return "gaps";
  if (label.includes("选题") || label.includes("建议选题") || label.includes("研究建议")) return "ideas";
  if (label.includes("方向图")) return "directions";
  return "next";
}

function cleanListItem(value: string) {
  return cleanDisplayText(value)
    .replace(/^[\s\-•·、:：]+/, "")
    .replace(/[\s\-:：]+$/, "")
    .trim();
}

function uniqueNonEmpty(items: string[]) {
  const seen = new Set<string>();
  const results: string[] = [];

  for (const item of items) {
    const cleaned = cleanListItem(item);
    if (!cleaned || seen.has(cleaned)) continue;
    seen.add(cleaned);
    results.push(cleaned);
  }

  return results;
}

function extractMetrics(text: string): MessageMetric[] {
  const metricCandidates: Array<[string, RegExp]> = [
    ["建议", /建议\s*[:：]?\s*(\d+)\s*条/],
    ["对齐分数", /对齐分数\s*[:：]?\s*([0-9.]+)/],
    ["匹配度", /匹配度\s*[:：]?\s*([0-9.]+)/],
    ["论文", /论文\s*[:：]?\s*(\d+)\s*(?:篇|空白|$)/],
    ["研究空白", /(?:空白|研究空白)\s*[:：]?\s*(\d+)\s*(?:条|项|个|建议|$)/],
  ];

  const metrics: MessageMetric[] = [];
  const usedLabels = new Set<string>();

  for (const [label, pattern] of metricCandidates) {
    const match = text.match(pattern);
    if (!match?.[1] || usedLabels.has(label)) continue;
    metrics.push({ label, value: match[1] });
    usedLabels.add(label);
  }

  return metrics;
}

function stripMetricText(text: string) {
  return cleanLeadText(
    text
      .replace(/建议\s*[:：]?\s*\d+\s*条/g, " ")
      .replace(/对齐分数\s*[:：]?\s*[0-9.]+/g, " ")
    .replace(/匹配度\s*[:：]?\s*[0-9.]+/g, " ")
    .replace(/论文\s*[:：]?\s*\d+\s*(?:篇)?/g, " ")
    .replace(/(?:空白|研究空白)\s*[:：]?\s*\d+\s*(?:条|项|个)?/g, " ")
    .replace(/\s+-\s+/g, " ")
  );
}

function cleanLeadText(text: string) {
  return text
    .replace(/^(已完成本轮研究任务[:：].*?)\s*/g, "")
    .replace(/^(研究分析完成)\s*/g, "")
    .replace(/^(研究主题[:：].*?)\s*/g, "")
    .replace(/^(本轮概览)\s*/g, "")
    .replace(/本轮分析共得到\s*[，,；;：:]*/g, "")
    .replace(/([，,；;：:])(?:\s*[，,；;：:])+/g, "$1")
    .replace(/([。！？!?])(?:\s*[。！？!?])+/g, "$1")
    .replace(/[，,；;：:]\s*(?=[。！？!?]|$)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitSectionItems(key: MessageSection["key"], content: string) {
  if (!content.trim()) return [];

  if (key === "ideas") {
    const normalizedIdeas = content.replace(IDEA_LABEL_PATTERN, "\n$1：");
    return uniqueNonEmpty(
      normalizedIdeas
        .split(/\n+|\s+-\s+(?=选题[一二三四五六七八九十\d]+[:：])/)
        .map((item) => item.replace(IDEA_LINE_PATTERN, "$1：$2"))
    );
  }

  if (key === "papers") {
    return uniqueNonEmpty(content.split(/\s+-\s+|[；;]/));
  }

  if (key === "priority") {
    return uniqueNonEmpty(content.split(/\s+-\s+|[；;。]/));
  }

  return uniqueNonEmpty(content.split(/\s+-\s+|[；;。]/));
}

function upsertSection(sections: MessageSection[], key: MessageSection["key"], items: string[]) {
  if (!items.length) return;

  const existing = sections.find((section) => section.key === key);
  if (existing) {
    existing.items = uniqueNonEmpty([...existing.items, ...items]);
    return;
  }

  sections.push({
    key,
    title: sectionTitleMap[key],
    items,
  });
}

function addSection(sections: MessageSection[], key: MessageSection["key"], content: string) {
  const items = splitSectionItems(key, content);
  if (!items.length) return;

  if (key === "directions") {
    return;
  }

  if (key === "next") {
    const directionItems = items.filter((item) => /^完整\s*研究方向图/.test(item) || item.includes("工作台查看"));
    const nextItems = items.filter((item) => !directionItems.includes(item));
    upsertSection(sections, key, nextItems);
    return;
  }

  upsertSection(sections, key, items);
}

function parseAssistantMessage(content: unknown): ParsedAssistantMessage {
  const raw = cleanDisplayText(content);
  if (!raw) {
    return { raw: "", lead: "", metrics: [], sections: [], structured: false };
  }

  const metrics = extractMetrics(raw);
  const normalized = raw
    .replace(SECTION_LABEL_PATTERN, "\n$1：")
    .replace(IDEA_LABEL_PATTERN, "\n$1：")
    .replace(/\n{2,}/g, "\n")
    .trim();
  const lines = normalized.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const sections: MessageSection[] = [];
  const leadParts: string[] = [];

  for (const line of lines) {
    const sectionMatch = line.match(SECTION_LINE_PATTERN);
    if (sectionMatch) {
      addSection(sections, normalizeSectionKey(sectionMatch[1]), sectionMatch[2] ?? "");
      continue;
    }

    const ideaMatch = line.match(IDEA_LINE_PATTERN);
    if (ideaMatch) {
      addSection(sections, "ideas", `${ideaMatch[1]}：${ideaMatch[2] ?? ""}`);
      continue;
    }

    leadParts.push(line);
  }

  const lead = stripMetricText(leadParts.join(" "));
  const structured = metrics.length > 0 || sections.length > 0;

  return {
    raw,
    lead,
    metrics,
    sections,
    structured,
  };
}

export function AssistantMessageContent({ content }: { content: unknown }) {
  const parsed = parseAssistantMessage(content);

  if (!parsed.structured) {
    return <p>{parsed.raw}</p>;
  }

  return (
    <div className="assistant-structured-message">
      {parsed.lead ? <p className="assistant-message-lead">{parsed.lead}</p> : null}

      {parsed.metrics.length ? (
        <div className="assistant-message-metrics" aria-label="本轮研究指标">
          {parsed.metrics.map((metric) => (
            <span className="assistant-message-metric" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </span>
          ))}
        </div>
      ) : null}

      {parsed.sections.length ? (
        <div className="assistant-message-sections">
          {parsed.sections.map((section) => (
            <section className={`assistant-message-section assistant-message-section-${section.key}`} key={section.key}>
              <div className="assistant-message-section-title">{section.title}</div>
              <ol className="assistant-message-list">
                {section.items.slice(0, 6).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      ) : null}
    </div>
  );
}
