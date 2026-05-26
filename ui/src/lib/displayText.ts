const INTERNAL_MARKER_PATTERN =
  /\[(?:Prior research knowledge|prior knowledge|Knowledge)[^\]]*\]\s*/gi;
const TASK_TAG_PATTERN = /\[task:[^\]]+\]\s*/gi;
const AUTO_TAG_PATTERN = /\[Auto\]\s*/gi;
const INTERNAL_PHRASE_PATTERN =
  /(?:Prior research knowledge\s*-?\s*use this to reduce fallback and improve search relevance|prior knowledge)\s*:?/gi;
const TRUNCATED_TASK_TAG_PATTERN = /\[t(?:ask)?\.{2,}.*?(?=\s|$)/gi;
const FOLLOW_UP_LABEL_PATTERN = /\s+-\s+(?:follow\s*up|focus\s*on)\s*:\s*/gi;
const INFORMED_BY_SUFFIX_PATTERN = /\s+-\s+informed\s+by\s+.*$/gi;

const RESULT_ANCHORS = [
  "\u7814\u7a76\u5ba1\u8ba1\u6982\u89c8",
  "\u672c\u8f6e\u5206\u6790",
  "\u5efa\u8bae\uff1a",
  "\u4f18\u5148\u5173\u6ce8\uff1a",
  "Research Overview",
  "Summary",
];

export function cleanDisplayText(value: unknown, maxLength?: number) {
  if (value == null) return "";

  let text = String(value);
  if (!text.trim()) return "";

  const anchorIndexes = RESULT_ANCHORS
    .map((anchor) => text.indexOf(anchor))
    .filter((index) => index > 0)
    .sort((left, right) => left - right);

  if (anchorIndexes.length) {
    text = text.slice(anchorIndexes[0]);
  }

  text = text
    .replace(INTERNAL_MARKER_PATTERN, " ")
    .replace(TASK_TAG_PATTERN, " ")
    .replace(AUTO_TAG_PATTERN, " ")
    .replace(INTERNAL_PHRASE_PATTERN, " ")
    .replace(TRUNCATED_TASK_TAG_PATTERN, " ")
    .replace(FOLLOW_UP_LABEL_PATTERN, " - ")
    .replace(INFORMED_BY_SUFFIX_PATTERN, "")
    .replace(/\[\s*\]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[\s:;,-]+|[\s:;,-]+$/g, "");

  if (maxLength && text.length > maxLength) {
    return `${text.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
  }

  return text;
}
