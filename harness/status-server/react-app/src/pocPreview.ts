type JsonObject = Record<string, unknown>;

export type PocPreviewModel = {
  total: number;
  done: number;
  percent: number;
  failed: number;
  active: number;
  phase: string;
  terminal: boolean;
  resolvedIssues: string[];
};

function object(value: unknown): JsonObject {
  return value && typeof value === "object" ? (value as JsonObject) : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function count(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

export function buildPocPreviewModel(projection: unknown): PocPreviewModel {
  const response = object(projection);
  const data = object(response.data);
  const sprint = object(data.sprint);
  const summary = object(data.summary);
  const progress = object(summary.progress);
  const governance = object(data.plan_governance);
  const statusCounts = object(progress.status_counts);
  const graph = object(data.task_graph);
  const nodes = Array.isArray(graph.nodes)
    ? graph.nodes
    : Array.isArray(data.nodes)
      ? data.nodes
      : [];

  const total = count(progress.total_nodes) || nodes.length;
  const done =
    count(progress.passed_nodes ?? progress.completed_nodes) ||
    nodes.filter((node) => {
      const status = text(object(node).status).toLowerCase();
      return /^(passed|completed|done)$/.test(status);
    }).length;
  const rawPercent = Number(progress.percent_complete);
  const percent = Number.isFinite(rawPercent) && rawPercent > 0
    ? rawPercent <= 1
      ? Math.round(rawPercent * 100)
      : Math.round(rawPercent)
    : total > 0
      ? Math.round((done / total) * 100)
      : 0;
  const status = text(data.status || sprint.status).toLowerCase();
  const phase = text(data.phase || sprint.phase || data.status || sprint.status);
  const terminal = /^(passed|completed|done)$/.test(status) ||
    /^(passed|completed|done)$/.test(phase.toLowerCase());
  const compileCodes = Array.isArray(governance.compile_error_codes)
    ? governance.compile_error_codes.map(text).filter(Boolean)
    : [];
  const resolvedIssues =
    (terminal || text(governance.state) === "certified") &&
    count(governance.plan_compile_bounces) > 0
      ? Array.from(new Set(compileCodes))
      : [];

  return {
    total,
    done,
    percent: Math.min(100, Math.max(0, percent)),
    failed: count(progress.failed_nodes) || count(statusCounts.failed),
    active:
      count(progress.active_nodes ?? progress.running_nodes) ||
      count(statusCounts.running) ||
      count(statusCounts.reviewing) ||
      count(statusCounts.dispatched),
    phase,
    terminal,
    resolvedIssues,
  };
}

export function selectPocArtifact<
  T extends { name?: string; rel_path?: string; kind?: string; result?: boolean; primary?: boolean },
>(items: T[]): T | undefined {
  const ranked = [...items].sort((left, right) => {
    const score = (item: T): number => {
      const path = text(item.rel_path || item.name).toLowerCase();
      const kind = text(item.kind).toLowerCase();
      if (/(^|\/)poster\.html$/.test(path)) return 100;
      if (/(^|\/)index\.html$/.test(path)) return 90;
      if (kind === "html") return 80;
      if (item.result) return 70;
      if (item.primary) return 60;
      if (/(^|\/)report\.md$/.test(path)) return 50;
      return 0;
    };
    return score(right) - score(left);
  });
  return ranked.find((item) => {
    const path = text(item.rel_path || item.name).toLowerCase();
    return Boolean(item.result || item.primary || text(item.kind) === "html" || /report\.md$/.test(path));
  });
}
