export interface RetryPolicy {
  baseDelayMs: number;
  maxDelayMs: number;
  maxAttempts: number;
  jitterRatio: number;
  retryableErrorPatterns: string[];
}

export const DEFAULT_RETRY_POLICY: RetryPolicy = {
  baseDelayMs: 1000,
  maxDelayMs: 60000,
  maxAttempts: 3,
  jitterRatio: 0.2,
  retryableErrorPatterns: [
    "timeout",
    "temporarily unavailable",
    "rate limit",
    "connection",
    "socket",
  ],
};

export function computeBackoffMs(policy: RetryPolicy, attempt: number): number {
  const boundedAttempt = Math.max(1, Math.floor(attempt || 1));
  const base = Math.max(1, policy.baseDelayMs);
  const max = Math.max(base, policy.maxDelayMs);
  const raw = Math.min(max, base * Math.pow(2, boundedAttempt - 1));
  const jitter = Math.max(0, Math.min(1, policy.jitterRatio || 0));
  if (jitter === 0) return raw;
  const spread = raw * jitter;
  return Math.max(1, Math.round(raw - spread + Math.random() * spread * 2));
}
