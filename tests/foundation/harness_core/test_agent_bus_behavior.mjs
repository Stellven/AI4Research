import assert from "node:assert/strict";
import test from "node:test";

import { AgentBus } from "../../../core/agent/bus.ts";

function message(overrides = {}) {
  return {
    id: "phase22-message",
    type: "task",
    from: "planner",
    to: "builder",
    priority: "normal",
    timestamp: new Date().toISOString(),
    payload: { task: "probe durable queue behavior" },
    ...overrides,
  };
}

test("agent message bus queues and delivers a valid task", async () => {
  const delivered = [];
  const bus = new AgentBus({ processingInterval: 1 });
  bus.subscribe("builder", (item) => delivered.push(item));
  assert.equal(bus.publish(message()), true);
  bus.start();
  await new Promise((resolve) => setTimeout(resolve, 25));
  bus.stop();
  assert.equal(delivered.length, 1);
  assert.equal(delivered[0].id, "phase22-message");
  assert.equal(bus.getStats().messagesDelivered, 1);
});

test("agent message bus rejects malformed messages", () => {
  const bus = new AgentBus();
  assert.equal(bus.publish(message({ id: "" })), false);
  assert.equal(bus.getStats().messagesReceived, 0);
});
