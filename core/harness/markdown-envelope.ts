import type { CoreToHarnessRequest } from "./types";

function clean(value: string | undefined): string {
  const text = (value || "").trim();
  return text && text !== "N/A" ? text : "N/A";
}

function renderList(items: string[] | undefined): string {
  const values = (items || []).map((item) => item.trim()).filter(Boolean);
  if (values.length === 0) return "- N/A";
  return values.map((item) => `- ${item}`).join("\n");
}

function renderJsonList(items: string[] | undefined): string {
  const values = (items || []).map((item) => item.trim()).filter(Boolean);
  if (values.length === 0) return "- N/A";
  return values.map((item) => `- ${JSON.stringify(item)}`).join("\n");
}

export function renderCoreRequestEnvelope(request: CoreToHarnessRequest): string {
  const analysis = request.core_analysis || {};
  const research = request.research || {};

  return [
    "# Solar Core Request",
    "",
    "## Request Metadata",
    "",
    `- schema_version: ${request.schema_version}`,
    `- request_id: ${request.request_id}`,
    `- created_at: ${clean(request.created_at)}`,
    `- source_channel: ${request.source.channel}`,
    `- source_actor: ${request.source.actor}`,
    `- source_trust: ${request.source.source_trust}`,
    `- thread_ref: ${clean(request.source.thread_ref)}`,
    "",
    "## Routing Hints",
    "",
    `- mode: ${request.routing.mode}`,
    `- urgency: ${request.routing.urgency}`,
    `- allow_autodispatch: ${request.routing.allow_autodispatch}`,
    `- requires_human_confirm: ${request.routing.requires_human_confirm}`,
    `- require_research_artifact: ${request.routing.require_research_artifact}`,
    "",
    "## Raw User Input",
    "",
    request.raw_input.text.trim(),
    "",
    "## Core Interpretation",
    "",
    `- title: ${clean(analysis.title)}`,
    `- objective: ${clean(analysis.objective)}`,
    `- problem: ${clean(analysis.problem)}`,
    `- outcome: ${clean(analysis.outcome)}`,
    "",
    "## Constraints",
    "",
    renderList(analysis.constraints),
    "",
    "## Non Goals",
    "",
    renderList(analysis.non_goals),
    "",
    "## Acceptance",
    "",
    renderList(analysis.acceptance),
    "",
    "## Suggested Logical Operators",
    "",
    renderList(analysis.suggested_logical_operators),
    "",
    "## Artifact References",
    "",
    "### Attachments",
    "",
    renderJsonList(request.raw_input.attachments),
    "",
    "### Quoted Context",
    "",
    renderJsonList(request.raw_input.quoted_context),
    "",
    "### Research",
    "",
    `- artifact: ${clean(research.artifact)}`,
    `- project_name: ${clean(research.project_name)}`,
    `- conversation_id: ${clean(research.conversation_id)}`,
    `- source_url: ${clean(research.source_url)}`,
    "",
  ].join("\n");
}

