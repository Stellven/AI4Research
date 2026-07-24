import assert from "node:assert/strict";
import test from "node:test";

import {
  collectHardwareInfo,
  createBenchmarkResult,
} from "../../../core/benchmark/reporter.ts";

test("benchmark framing records usable hardware metadata", () => {
  const hardware = collectHardwareInfo();
  assert.ok(hardware.cpuCores > 0);
  assert.ok(hardware.memoryGb > 0);
  assert.ok(hardware.cpuModel.length > 0);
});

test("benchmark evidence summarizes supplied measurements", () => {
  const result = createBenchmarkResult("phase22", "Phase 22 probe", [10, 11, 12, 13, 14], {
    unit: "ms",
    removeOutliers: false,
  });
  assert.equal(result.rawData.length, 5);
  assert.ok(result.stats.median.value > 0);
  assert.equal(result.stats.median.unit, "ms");
});
