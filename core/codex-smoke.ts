/**
 * Installed Solar Codex smoke behavior.
 *
 * Provides a minimal, real call-chain entry for a "say hi" smoke path.
 */

export const SMOKE_REQUEST_MARKER = "installed solar codex smoke: say hi";
export const SMOKE_RESPONSE = "Hi from Solar! Installed Codex smoke check passed.";
export const CALL_CHAIN = [
  "bun run core/codex-smoke.ts",
  "runCodexSmoke",
  "main",
] as const;

export interface CodexSmokeResult {
  ok: boolean;
  request: string;
  response: string;
  callChain: readonly string[];
}

export function normalizeInput(value: string): string {
  return value.toLowerCase().trim();
}

export function isSayHiSmoke(input: string): boolean {
  return normalizeInput(input) === SMOKE_REQUEST_MARKER;
}

export function runCodexSmoke(input: string): CodexSmokeResult {
  const normalized = normalizeInput(input);
  if (normalized === SMOKE_REQUEST_MARKER) {
    return {
      ok: true,
      request: input,
      response: SMOKE_RESPONSE,
      callChain: CALL_CHAIN,
    };
  }

  return {
    ok: false,
    request: input,
    response: `Unknown smoke request: ${input}`,
    callChain: CALL_CHAIN,
  };
}

function main(argv: string[]): void {
  const request = argv.length > 0 ? argv.join(" ") : SMOKE_REQUEST_MARKER;
  const result = runCodexSmoke(request);
  console.log(result.response);

  if (!result.ok) {
    console.error(`Invalid request: ${result.request}`);
    process.exit(1);
  }
}

if (import.meta.main) {
  main(process.argv.slice(2));
}
