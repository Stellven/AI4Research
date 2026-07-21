#!/usr/bin/env bun
import { existsSync } from "fs";
import { homedir } from "os";
import { dirname, join, resolve } from "path";
import { fileURLToPath, pathToFileURL } from "url";

type Mode = "auto" | "v1" | "v2";
type ColorMode = "auto" | "on" | "off";

type Options = {
  mode: Mode;
  style: string;
  width: number;
  colors: ColorMode;
  footer: boolean;
  footerVersion: string;
};

const DEFAULT_OPTIONS: Options = {
  mode: "auto",
  style: "solar_default",
  width: 80,
  colors: "auto",
  footer: true,
  footerVersion: process.env.SOLAR_TVS_FOOTER_VERSION || "v0.4.0",
};

function usage(): string {
  return [
    "Usage:",
    "  solar-harness tvs render [--mode auto|v1|v2] [--style NAME] [--width N] [--colors auto|on|off] [--no-footer] < input.json",
    "",
    "Input:",
    "  v1 SemanticIR: {\"canvas\":{\"width\":80},\"style\":\"solar_default\",\"root\":{...}}",
    "  v2 LayoutDSL:   {\"canvas\":{\"width\":80},\"style\":\"enterprise_minimal\",\"layout\":{...}}",
    "  component:      {\"type\":\"card\",\"header\":\"Status\",\"sections\":[...]}",
  ].join("\n");
}

function parseArgs(argv: string[]): Options {
  const args = argv[0] === "render" ? argv.slice(1) : argv.slice();
  const opts = { ...DEFAULT_OPTIONS };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--help" || arg === "-h") {
      console.log(usage());
      process.exit(0);
    }
    if (arg === "--no-footer") {
      opts.footer = false;
      continue;
    }
    if (arg === "--mode") {
      const value = args[++i] as Mode;
      if (!["auto", "v1", "v2"].includes(value)) {
        throw new Error("--mode must be auto, v1, or v2");
      }
      opts.mode = value;
      continue;
    }
    if (arg === "--style") {
      opts.style = args[++i] || "";
      if (!opts.style) throw new Error("--style requires a value");
      continue;
    }
    if (arg === "--width") {
      const width = Number(args[++i]);
      if (!Number.isInteger(width) || width < 20 || width > 240) {
        throw new Error("--width must be an integer between 20 and 240");
      }
      opts.width = width;
      continue;
    }
    if (arg === "--colors") {
      const value = args[++i] as ColorMode;
      if (!["auto", "on", "off"].includes(value)) {
        throw new Error("--colors must be auto, on, or off");
      }
      opts.colors = value;
      continue;
    }
    throw new Error(`Unknown option: ${arg}`);
  }

  return opts;
}

async function readStdin(): Promise<string> {
  const chunks: Uint8Array[] = [];
  for await (const chunk of Bun.stdin.stream()) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8").trim();
}

function candidateTvsRoots(): string[] {
  const here = dirname(fileURLToPath(import.meta.url));
  const roots = [
    process.env.SOLAR_TVS_ROOT,
    process.env.SOLAR_ROOT ? join(process.env.SOLAR_ROOT, "..", "TVS") : undefined,
    join(here, "..", "..", "..", "TVS"),
    join(homedir(), "TVS"),
    join(homedir(), "Solar", "..", "TVS"),
  ].filter(Boolean) as string[];
  return [...new Set(roots.map((p) => resolve(p)))];
}

async function importFromRoot(root: string, subpath: string): Promise<any | null> {
  const path = join(root, subpath);
  if (!existsSync(path)) return null;
  return import(pathToFileURL(path).href);
}

async function importTvs(mode: "v1" | "v2"): Promise<any> {
  const subpath = mode === "v2" ? "v2/index.ts" : "index.ts";
  for (const root of candidateTvsRoots()) {
    const mod = await importFromRoot(root, subpath);
    if (mod) return mod;
  }

  try {
    return mode === "v2" ? await import("tvs/v2") : await import("tvs");
  } catch (error) {
    const roots = candidateTvsRoots().join(", ");
    throw new Error(`Unable to import TVS ${mode}. Checked roots: ${roots}. Set SOLAR_TVS_ROOT to the TVS package directory.`);
  }
}

function parsePayload(raw: string): any {
  if (!raw) throw new Error("stdin is empty; expected TVS JSON payload");
  try {
    return JSON.parse(raw);
  } catch (error: any) {
    throw new Error(`invalid JSON: ${error?.message || String(error)}`);
  }
}

function normalizeV1(payload: any, opts: Options): any {
  if (payload && typeof payload === "object" && payload.root) {
    return {
      ...payload,
      canvas: { width: opts.width, ...(payload.canvas || {}) },
      style: payload.style || opts.style,
    };
  }

  if (payload && typeof payload === "object" && payload.type) {
    return {
      canvas: { width: opts.width },
      style: opts.style,
      root: payload,
    };
  }

  throw new Error("v1 payload must contain root or be a TVS component with type");
}

function normalizeV2(payload: any, opts: Options): any {
  if (payload && typeof payload === "object" && payload.layout) {
    return {
      ...payload,
      canvas: { width: opts.width, ...(payload.canvas || {}) },
      style: payload.style || opts.style,
    };
  }

  if (payload && typeof payload === "object" && payload.sections) {
    return {
      canvas: { width: opts.width },
      style: opts.style,
      layout: {
        type: "card",
        sections: payload.sections,
      },
    };
  }

  throw new Error("v2 payload must contain layout or sections");
}

function resolveMode(payload: any, opts: Options): "v1" | "v2" {
  if (opts.mode === "v1" || opts.mode === "v2") return opts.mode;
  if (payload?.mode === "v1" || payload?.mode === "v2") return payload.mode;
  return payload?.layout ? "v2" : "v1";
}

function shouldUseColors(opts: Options): boolean {
  if (opts.colors === "on") return true;
  if (opts.colors === "off") return false;
  return Boolean(process.stdout.isTTY && process.env.NO_COLOR !== "1");
}

function appendFooter(output: string, opts: Options): string {
  if (!opts.footer) return output;
  const width = Math.max(20, opts.width);
  const text = `Powered by TVS ${opts.footerVersion} · Style: ${opts.style}`;
  const line = text.length <= width ? text : text.slice(0, Math.max(0, width - 1));
  return `${output.replace(/\s+$/u, "")}\n${line}`;
}

async function main(): Promise<void> {
  const opts = parseArgs(process.argv.slice(2));
  const raw = await readStdin();
  const payload = parsePayload(raw);
  const mode = resolveMode(payload, opts);

  let output = "";
  let renderedStyle = opts.style;
  if (mode === "v2") {
    const dsl = normalizeV2(payload, opts);
    renderedStyle = dsl.style || opts.style;
    const tvsV2 = await importTvs("v2");
    output = tvsV2.render(dsl);
  } else {
    const ir = normalizeV1(payload, opts);
    renderedStyle = ir.style || opts.style;
    const tvsV1 = await importTvs("v1");
    output = tvsV1.tvs.render(ir, { colors: shouldUseColors(opts) });
  }

  process.stdout.write(appendFooter(output, { ...opts, style: renderedStyle }));
  process.stdout.write("\n");
}

main().catch((error) => {
  console.error(`tvs-render error: ${error?.message || String(error)}`);
  process.exit(1);
});
