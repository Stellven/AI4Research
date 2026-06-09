import { existsSync } from "fs";
import { mkdtemp, rm, writeFile } from "fs/promises";
import { join } from "path";
import { tmpdir } from "os";
import { renderCoreRequestEnvelope } from "./markdown-envelope";
import {
  CORE_TO_HARNESS_SCHEMA_VERSION,
  type CoreToHarnessRequest,
  type CoreToHarnessResult,
  type HarnessCaptureResult,
  type HarnessClientOptions,
  type HarnessConsumeResult,
} from "./types";

function resolveDefaultHarnessDir(): string {
  if (process.env.SOLAR_HARNESS_DIR) return process.env.SOLAR_HARNESS_DIR;
  if (process.env.HARNESS_DIR) return process.env.HARNESS_DIR;

  const installedHarnessDir = process.env.HOME ? join(process.env.HOME, ".solar", "harness") : "";
  if (installedHarnessDir && existsSync(join(installedHarnessDir, "solar-harness.sh"))) {
    return installedHarnessDir;
  }

  return join(process.cwd(), "harness");
}

const DEFAULT_HARNESS_DIR = resolveDefaultHarnessDir();

function resolveDefaultPython(): string {
  if (process.env.SOLAR_PYTHON_BIN) return process.env.SOLAR_PYTHON_BIN;

  const repoVenvPython = join(process.cwd(), ".venv", "bin", "python3");
  if (existsSync(repoVenvPython)) return repoVenvPython;

  return "python3";
}

const DEFAULT_PYTHON = resolveDefaultPython();

function isPresent(value: string | undefined): value is string {
  const text = (value || "").trim();
  return Boolean(text) && text !== "N/A";
}

function requireString(value: string | undefined, field: string, errors: string[]): void {
  if (!isPresent(value)) errors.push(`${field} is required`);
}

export function validateCoreToHarnessRequest(request: CoreToHarnessRequest): string[] {
  const errors: string[] = [];
  if (request.schema_version !== CORE_TO_HARNESS_SCHEMA_VERSION) {
    errors.push(`schema_version must be ${CORE_TO_HARNESS_SCHEMA_VERSION}`);
  }
  requireString(request.request_id, "request_id", errors);
  requireString(request.source?.channel, "source.channel", errors);
  requireString(request.source?.actor, "source.actor", errors);
  requireString(request.source?.source_trust, "source.source_trust", errors);
  requireString(request.workspace?.repo, "workspace.repo", errors);
  requireString(request.routing?.mode, "routing.mode", errors);
  requireString(request.routing?.urgency, "routing.urgency", errors);
  requireString(request.raw_input?.text, "raw_input.text", errors);
  return errors;
}

export function buildCaptureArgs(
  request: CoreToHarnessRequest,
  envelopePath: string,
  harnessDir: string = DEFAULT_HARNESS_DIR,
): string[] {
  const args = [
    join(harnessDir, "lib", "intent_gateway.py"),
    "capture",
    "--intent-id",
    request.request_id,
    "--source-channel",
    request.source.channel,
    "--actor",
    request.source.actor,
    "--repo",
    request.workspace.repo,
    "--source-trust",
    request.source.source_trust,
    "--urgency",
    request.routing.urgency,
    "--mode",
    request.routing.mode,
    "--file",
    envelopePath,
    "--json",
  ];

  if (isPresent(request.source.device)) args.push("--device", request.source.device);
  if (isPresent(request.source.session_id)) args.push("--session-id", request.source.session_id);
  if (isPresent(request.source.thread_ref)) args.push("--thread-ref", request.source.thread_ref);
  if (isPresent(request.workspace.knowledge_query)) args.push("--knowledge-query", request.workspace.knowledge_query);
  if (!request.routing.allow_autodispatch) args.push("--no-autodispatch");
  if (request.routing.requires_human_confirm) args.push("--requires-human-confirm");
  if (request.routing.require_research_artifact) args.push("--require-research-artifact");

  const research = request.research || {};
  if (isPresent(research.artifact)) args.push("--research-artifact", research.artifact);
  if (isPresent(research.project_name)) args.push("--research-project-name", research.project_name);
  if (isPresent(research.conversation_id)) args.push("--research-conversation-id", research.conversation_id);
  if (isPresent(research.source_url)) args.push("--research-source-url", research.source_url);

  return args;
}

export function buildConsumeArgs(
  request: CoreToHarnessRequest,
  intentId: string,
  harnessDir: string = DEFAULT_HARNESS_DIR,
): string[] {
  const consume = request.consume || { enabled: true };
  const args = [
    join(harnessDir, "lib", "intent_consumer.py"),
    "consume",
    "--intent-id",
    intentId,
    "--json",
  ];

  if (isPresent(consume.sprint_id)) args.push("--sprint-id", consume.sprint_id);
  if (consume.dispatch_planner) args.push("--dispatch-planner");
  if (consume.auto_dispatch_planner === false) args.push("--no-auto-dispatch-planner");

  return args;
}

async function runJsonCommand<T>(
  pythonBin: string,
  args: string[],
  env: Record<string, string>,
): Promise<T & { stdout?: string; stderr?: string }> {
  const proc = Bun.spawn([pythonBin, ...args], {
    stdout: "pipe",
    stderr: "pipe",
    env,
  });
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);

  if (exitCode !== 0) {
    throw new Error(`command failed exit=${exitCode}: ${(stderr || stdout).trim()}`);
  }

  try {
    return { ...JSON.parse(stdout), stdout, stderr };
  } catch (error) {
    throw new Error(`command returned invalid JSON: ${(stdout || stderr).trim()}`);
  }
}

function buildHarnessEnv(harnessDir: string, extra: Record<string, string> = {}): Record<string, string> {
  const repoVenvBin = join(process.cwd(), ".venv", "bin");
  const path = existsSync(repoVenvBin)
    ? `${repoVenvBin}:${process.env.PATH || ""}`
    : process.env.PATH;
  const sprintsDir = process.env.SOLAR_HARNESS_SPRINTS_DIR || extra.SOLAR_HARNESS_SPRINTS_DIR || join(harnessDir, "sprints");
  const intentsDir = process.env.SOLAR_INTENT_GATEWAY_DIR || extra.SOLAR_INTENT_GATEWAY_DIR || join(harnessDir, "intents");

  return {
    ...process.env,
    ...extra,
    PATH: path || "",
    HARNESS_DIR: harnessDir,
    SOLAR_HARNESS_DIR: harnessDir,
    SOLAR_HARNESS_SPRINTS_DIR: sprintsDir,
    SOLAR_INTENT_GATEWAY_DIR: intentsDir,
  } as Record<string, string>;
}

export async function submitCoreToHarness(
  request: CoreToHarnessRequest,
  options: HarnessClientOptions = {},
): Promise<CoreToHarnessResult> {
  const errors = validateCoreToHarnessRequest(request);
  if (errors.length > 0) {
    return {
      ok: false,
      request_id: request.request_id,
      error: errors.join("; "),
    };
  }

  const harnessDir = options.harnessDir || DEFAULT_HARNESS_DIR;
  const pythonBin = options.pythonBin || DEFAULT_PYTHON;
  const tempRoot = options.tempDir || tmpdir();
  const runDir = await mkdtemp(join(tempRoot, "solar-core-harness-"));
  const envelopePath = join(runDir, `${request.request_id}.core-request.md`);
  const envelope = renderCoreRequestEnvelope(request);
  await writeFile(envelopePath, envelope, "utf-8");

  const captureArgs = buildCaptureArgs(request, envelopePath, harnessDir);
  const consumeEnabled = request.consume?.enabled !== false;

  try {
    if (options.dryRun) {
      return {
        ok: true,
        request_id: request.request_id,
        envelope_path: options.keepEnvelope ? envelopePath : undefined,
        capture: {
          ok: true,
          stdout: JSON.stringify({
            dry_run: true,
            capture_args: captureArgs,
            consume_args: consumeEnabled ? buildConsumeArgs(request, request.request_id, harnessDir) : [],
          }),
        },
      };
    }

    const env = buildHarnessEnv(harnessDir, options.env);
    const capture = await runJsonCommand<HarnessCaptureResult>(pythonBin, captureArgs, env);
    const intentId = capture.intent_id || request.request_id;

    if (!consumeEnabled) {
      return {
        ok: true,
        request_id: request.request_id,
        intent_id: intentId,
        envelope_path: options.keepEnvelope ? envelopePath : undefined,
        capture,
      };
    }

    try {
      const consumeArgs = buildConsumeArgs(request, intentId, harnessDir);
      const consume = await runJsonCommand<HarnessConsumeResult>(pythonBin, consumeArgs, env);
      return {
        ok: Boolean(capture.ok && consume.ok),
        request_id: request.request_id,
        intent_id: intentId,
        envelope_path: options.keepEnvelope ? envelopePath : undefined,
        capture,
        consume,
      };
    } catch (error) {
      return {
        ok: false,
        request_id: request.request_id,
        intent_id: intentId,
        envelope_path: options.keepEnvelope ? envelopePath : undefined,
        capture,
        consume: {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        },
        warnings: ["capture succeeded but consume failed"],
      };
    }
  } catch (error) {
    return {
      ok: false,
      request_id: request.request_id,
      envelope_path: options.keepEnvelope ? envelopePath : undefined,
      capture: {
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      },
      error: error instanceof Error ? error.message : String(error),
    };
  } finally {
    if (!options.keepEnvelope) {
      await rm(runDir, { recursive: true, force: true });
    }
  }
}
