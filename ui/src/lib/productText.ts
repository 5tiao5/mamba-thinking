export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

export function taskStatusLabel(status?: string) {
  if (status === "completed") return "已完成";
  if (status === "degraded") return "已完成";
  if (status === "step_limit_reached") return "未完成（步数耗尽）";
  if (status === "running") return "生成中";
  if (status === "failed") return "生成失败";
  if (status === "created" || status === "pending") return "待生成";
  if (status === "active") return "进行中";
  return status ? "待更新" : "未生成";
}

export function taskStatusTone(status?: string): StatusTone {
  if (status === "completed" || status === "degraded") return "success";
  if (status === "step_limit_reached") return "warning";
  if (status === "running") return "info";
  if (status === "failed") return "danger";
  if (status === "created" || status === "pending") return "warning";
  return "neutral";
}

export function formatShortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function formatReadableTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function compactText(value: string, maxLength = 260) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
}
