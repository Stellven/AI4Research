import assert from "node:assert/strict";
import test from "node:test";

import { CapabilityMatcher, NodeRegistry } from "../../../core/hive/node.ts";

const capability = {
  agentId: "builder",
  version: "1.0.0",
  description: "Phase 22 cluster probe",
  latencyMs: 20,
  successRate: 0.95,
};

test("cluster registry registers and discovers an online capable node", () => {
  const registry = new NodeRegistry({ maxNodes: 2 });
  const node = registry.register({
    name: "phase22-local",
    owner: "test",
    tier: "local",
    capabilities: [capability],
  });
  assert.equal(registry.get(node.nodeId)?.name, "phase22-local");
  assert.equal(registry.findByCapability("builder").length, 1);
  assert.equal(registry.getStats().onlineNodes, 1);
});

test("cluster matcher returns a node satisfying the required agent", () => {
  const registry = new NodeRegistry();
  registry.register({
    name: "phase22-cloud",
    owner: "test",
    tier: "cloud",
    capabilities: [capability],
  });
  const matches = new CapabilityMatcher(registry).findBestNodes({
    requiredAgents: ["builder"],
    minTier: "local",
  });
  assert.equal(matches.length, 1);
  assert.equal(matches[0].matchedCapabilities[0].agentId, "builder");
});
