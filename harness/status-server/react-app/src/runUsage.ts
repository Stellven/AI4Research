import type { UsagePayload } from "./types";

export function perRunUsageLabel(usage?: UsagePayload): string {
  if (!usage || usage.availability === "unavailable") {
    return "unavailable per run";
  }
  if (usage.not_per_sprint) {
    return "not reported per run";
  }
  return usage.total_used_tokens_label || "available";
}
