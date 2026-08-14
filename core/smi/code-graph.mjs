#!/usr/bin/env node
/**
 * Durable, source-derived CodeGraph construction, query, and validation.
 *
 * This intentionally stays dependency-free so the graph can be built before
 * the wider Solar/Bun environment has been installed.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, extname, join, normalize, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SCHEMA_VERSION = "solar.code_graph.v1";
const SOURCE_EXTENSIONS = new Set([".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const DEFAULT_EXCLUDES = new Set([".git", "node_modules", "dist", "build", "coverage", ".venv", "venv", "__pycache__"]);

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const posix = (value) => value.split(sep).join("/");
const nodeId = (kind, key) => `${kind}:${key}`;

function canonicalGraph(graph) {
  return JSON.stringify({
    schema_version: graph.schema_version,
    root: graph.root,
    nodes: [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id)),
    edges: [...graph.edges].sort((a, b) => `${a.type}:${a.from}:${a.to}`.localeCompare(`${b.type}:${b.from}:${b.to}`)),
    source_file_count: graph.source_file_count,
  });
}

function walk(root) {
  const files = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isDirectory() && DEFAULT_EXCLUDES.has(entry.name)) continue;
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile() && (SOURCE_EXTENSIONS.has(extname(entry.name)) || entry.name === "package.json" || entry.name === "pyproject.toml")) files.push(path);
    }
  };
  visit(root);
  return files;
}

function moduleKey(path) {
  return path.replace(/\.(py|tsx?|jsx?|mjs|cjs)$/i, "").replace(/\/__init__$/, "");
}

function parsePython(content) {
  const imports = [];
  const functions = [];
  const apis = [];
  const tests = [];
  for (const match of content.matchAll(/^from\s+([\w.]+)\s+import\s+([^\n#]+)/gm)) {
    imports.push({ source: match[1], names: match[2].split(",").map((name) => name.trim().split(/\s+as\s+/)[0]).filter(Boolean) });
  }
  for (const match of content.matchAll(/^import\s+([\w.]+)/gm)) imports.push({ source: match[1], names: [] });
  for (const match of content.matchAll(/^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(/gm)) {
    const name = match[1];
    functions.push(name);
    if (!name.startsWith("_")) apis.push(name);
    if (name.startsWith("test_")) tests.push(name);
  }
  for (const match of content.matchAll(/^class\s+([A-Za-z_]\w*)\b/gm)) if (!match[1].startsWith("_")) apis.push(match[1]);
  return { imports, functions, apis, tests };
}

function parseJavaScript(content) {
  const imports = [];
  const functions = [];
  const apis = [];
  const tests = [];
  for (const match of content.matchAll(/import\s+(?:\{([^}]+)\}|([\w$]+)|\*\s+as\s+([\w$]+))?\s*from\s*["']([^"']+)["']/g)) {
    const names = (match[1] || match[2] || match[3] || "").split(",").map((name) => name.trim().split(/\s+as\s+/)[0]).filter(Boolean);
    imports.push({ source: match[4], names });
  }
  for (const match of content.matchAll(/(?:require\s*\(\s*)["']([^"']+)["']\s*\)/g)) imports.push({ source: match[1], names: [] });
  for (const match of content.matchAll(/^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/gm)) functions.push(match[1]);
  for (const match of content.matchAll(/^export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type)\s+([A-Za-z_$][\w$]*)/gm)) apis.push(match[1]);
  for (const match of content.matchAll(/\b(?:test|it)\s*\(\s*["'`]([^"'`]+)["'`]/g)) tests.push(match[1]);
  return { imports, functions, apis, tests };
}

function resolveImport(source, importer, modulePaths, language) {
  let candidate;
  if (language === "python") {
    candidate = source.replaceAll(".", "/");
  } else if (source.startsWith(".")) {
    candidate = posix(normalize(join(dirname(importer), source)));
  } else {
    return null;
  }
  const variants = [candidate, `${candidate}/index`, `${candidate}/__init__`];
  return variants.find((item) => modulePaths.has(item)) || null;
}

export function buildCodeGraph(rootPath, runtimeCommands = []) {
  const root = resolve(rootPath);
  if (!existsSync(root) || !statSync(root).isDirectory()) throw new Error(`Root is not a directory: ${root}`);
  const paths = walk(root);
  const sourceFiles = paths.filter((path) => SOURCE_EXTENSIONS.has(extname(path)));
  const nodes = [];
  const edges = [];
  const seenNodes = new Set();
  const seenEdges = new Set();
  const analyses = new Map();
  const modulePaths = new Set(sourceFiles.map((path) => moduleKey(posix(relative(root, path)))));
  const addNode = (node) => { if (!seenNodes.has(node.id)) { seenNodes.add(node.id); nodes.push(node); } };
  const addEdge = (edge) => { const key = `${edge.type}:${edge.from}:${edge.to}`; if (!seenEdges.has(key)) { seenEdges.add(key); edges.push(edge); } };

  for (const absolutePath of sourceFiles) {
    const path = posix(relative(root, absolutePath));
    const content = readFileSync(absolutePath, "utf8");
    const contentHash = sha256(content);
    const language = extname(path) === ".py" ? "python" : "javascript";
    const analysis = language === "python" ? parsePython(content) : parseJavaScript(content);
    const module = moduleKey(path);
    analyses.set(module, { ...analysis, path, language, contentHash });
    addNode({ id: nodeId("file", path), kind: "file", path, content_sha256: contentHash });
    addNode({ id: nodeId("module", module), kind: "module", name: module, path, source_sha256: contentHash });
    addEdge({ type: "file_defines_module", from: nodeId("file", path), to: nodeId("module", module) });
    for (const name of analysis.functions) {
      addNode({ id: nodeId("function", `${module}#${name}`), kind: "function", name, path, source_sha256: contentHash });
      addEdge({ type: "module_declares_function", from: nodeId("module", module), to: nodeId("function", `${module}#${name}`) });
    }
    for (const name of analysis.apis) {
      addNode({ id: nodeId("api", `${module}#${name}`), kind: "api", name, path, source_sha256: contentHash });
      addEdge({ type: "module_declares_api", from: nodeId("module", module), to: nodeId("api", `${module}#${name}`) });
      if (analysis.functions.includes(name)) addEdge({ type: "api_implemented_by_function", from: nodeId("api", `${module}#${name}`), to: nodeId("function", `${module}#${name}`) });
    }
    for (const name of analysis.tests) {
      addNode({ id: nodeId("test", `${module}#${name}`), kind: "test", name, path, source_sha256: contentHash });
      addEdge({ type: "module_declares_test", from: nodeId("module", module), to: nodeId("test", `${module}#${name}`) });
    }
  }

  for (const [module, analysis] of analyses) {
    for (const imported of analysis.imports) {
      const target = resolveImport(imported.source, analysis.path, modulePaths, analysis.language);
      if (!target) continue;
      addEdge({ type: "module_imports_module", from: nodeId("module", module), to: nodeId("module", target) });
      for (const test of analysis.tests) addEdge({ type: "test_targets_module", from: nodeId("test", `${module}#${test}`), to: nodeId("module", target) });
      for (const name of imported.names) {
        if (analyses.get(target)?.apis.includes(name)) {
          for (const test of analysis.tests) addEdge({ type: "test_covers_api", from: nodeId("test", `${module}#${test}`), to: nodeId("api", `${target}#${name}`) });
        }
      }
    }
  }

  const packagePath = join(root, "package.json");
  const packageScripts = existsSync(packagePath) ? (JSON.parse(readFileSync(packagePath, "utf8")).scripts || {}) : {};
  const runtimes = [...Object.entries(packageScripts).map(([name, command]) => ({ name: `package:${name}`, command: String(command) })), ...runtimeCommands.map((command, index) => ({ name: `observed:${index + 1}`, command }))];
  for (const runtime of runtimes) {
    const id = nodeId("runtime", runtime.name);
    addNode({ id, kind: "runtime", name: runtime.name, command: runtime.command, command_sha256: sha256(runtime.command) });
    for (const [module, analysis] of analyses) {
      const basename = analysis.path.split("/").at(-1);
      if (runtime.command.includes(analysis.path) || runtime.command.includes(basename)) addEdge({ type: "runtime_executes_module", from: id, to: nodeId("module", module) });
    }
  }

  const graph = {
    schema_version: SCHEMA_VERSION,
    generated_at: new Date().toISOString(),
    root: posix(root),
    source_file_count: sourceFiles.length,
    nodes,
    edges,
  };
  graph.graph_sha256 = sha256(canonicalGraph(graph));
  return graph;
}

export function queryCodeGraph(graph, filters = {}) {
  const nodes = graph.nodes.filter((node) => (!filters.kind || node.kind === filters.kind) && (!filters.name || node.name?.includes(filters.name)) && (!filters.path || node.path?.includes(filters.path)));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter((edge) => (!filters.relation || edge.type === filters.relation) && (!filters.kind && !filters.name && !filters.path || nodeIds.has(edge.from) || nodeIds.has(edge.to)));
  return { nodes, edges, match_count: nodes.length + edges.length };
}

export function validateCodeGraph(graph, rootPath, requiredRelations = []) {
  const errors = [];
  if (graph.schema_version !== SCHEMA_VERSION) errors.push(`Unsupported schema_version: ${graph.schema_version}`);
  const ids = new Set();
  for (const node of graph.nodes || []) {
    if (!node.id || ids.has(node.id)) errors.push(`Duplicate or missing node id: ${node.id}`);
    ids.add(node.id);
  }
  for (const edge of graph.edges || []) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) errors.push(`Dangling edge: ${edge.type}:${edge.from}->${edge.to}`);
  }
  const relationTypes = new Set((graph.edges || []).map((edge) => edge.type));
  for (const relation of requiredRelations) if (!relationTypes.has(relation)) errors.push(`Missing required relation: ${relation}`);
  if (graph.graph_sha256 !== sha256(canonicalGraph(graph))) errors.push("graph_sha256 does not match graph content");
  if (rootPath) {
    const root = resolve(rootPath);
    for (const node of (graph.nodes || []).filter((item) => item.kind === "file")) {
      const path = resolve(root, node.path);
      if (!path.startsWith(`${root}${sep}`) && path !== root) errors.push(`File escapes root: ${node.path}`);
      else if (!existsSync(path)) errors.push(`Source file missing: ${node.path}`);
      else if (sha256(readFileSync(path)) !== node.content_sha256) errors.push(`Source hash mismatch: ${node.path}`);
    }
  }
  return { valid: errors.length === 0, errors, checked_nodes: (graph.nodes || []).length, checked_edges: (graph.edges || []).length, graph_sha256: graph.graph_sha256 };
}

function parseArgs(argv) {
  const values = { _: [], runtimeCommands: [], requiredRelations: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) values._.push(arg);
    else {
      const key = arg.slice(2).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
      const value = argv[++index];
      if (key === "runtimeCommand") values.runtimeCommands.push(value);
      else if (key === "requireRelation") values.requiredRelations.push(value);
      else values[key] = value;
    }
  }
  return values;
}

function writeJson(path, value) {
  const payload = `${JSON.stringify(value, null, 2)}\n`;
  if (path) writeFileSync(resolve(path), payload, "utf8");
  else process.stdout.write(payload);
}

async function main() {
  const [command, ...argv] = process.argv.slice(2);
  const args = parseArgs(argv);
  if (command === "build") {
    if (!args.root || !args.out) throw new Error("Usage: code-graph.mjs build --root <dir> --out <graph.json> [--runtime-command <command>]");
    writeJson(args.out, buildCodeGraph(args.root, args.runtimeCommands));
  } else if (command === "query") {
    if (!args.graph) throw new Error("Usage: code-graph.mjs query --graph <graph.json> [--kind <kind>] [--relation <type>] [--out <result.json>]");
    writeJson(args.out, queryCodeGraph(JSON.parse(readFileSync(resolve(args.graph), "utf8")), args));
  } else if (command === "validate") {
    if (!args.graph) throw new Error("Usage: code-graph.mjs validate --graph <graph.json> [--root <dir>] [--require-relation <type>] [--out <result.json>]");
    const result = validateCodeGraph(JSON.parse(readFileSync(resolve(args.graph), "utf8")), args.root, args.requiredRelations);
    writeJson(args.out, result);
    if (!result.valid) process.exitCode = 2;
  } else {
    throw new Error("Usage: code-graph.mjs <build|query|validate> ...");
  }
}

if (resolve(process.argv[1] || "") === resolve(fileURLToPath(import.meta.url))) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}
