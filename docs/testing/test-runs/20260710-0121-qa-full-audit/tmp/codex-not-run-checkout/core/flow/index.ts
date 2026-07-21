/**
 * Solar Flow Engine
 *
 * Five-phase flow controller with parallel execution
 *
 * @example
 * ```typescript
 * import { createExecutor, FlowTask } from 'solar/core/flow';
 *
 * const executor = createExecutor({ maxConcurrency: 4 });
 *
 * // Add tasks with dependencies
 * executor.addTasks([
 *   {
 *     id: 'research',
 *     name: 'Research APIs',
 *     agent: 'researcher',
 *     dependencies: [],
 *     execute: async () => ({ success: true, output: 'API docs...' }),
 *   },
 *   {
 *     id: 'design',
 *     name: 'Design Architecture',
 *     agent: 'architect',
 *     dependencies: ['research'],
 *     execute: async () => ({ success: true, output: 'Design doc...' }),
 *   },
 *   {
 *     id: 'implement-frontend',
 *     name: 'Implement Frontend',
 *     agent: 'coder',
 *     dependencies: ['design'],
 *     execute: async () => ({ success: true, output: 'Frontend code...' }),
 *   },
 *   {
 *     id: 'implement-backend',
 *     name: 'Implement Backend',
 *     agent: 'coder',
 *     dependencies: ['design'],
 *     execute: async () => ({ success: true, output: 'Backend code...' }),
 *   },
 *   {
 *     id: 'test',
 *     name: 'Run Tests',
 *     agent: 'tester',
 *     dependencies: ['implement-frontend', 'implement-backend'],
 *     execute: async () => ({ success: true, output: 'All tests passed' }),
 *   },
 * ]);
 *
 * // Execute with progress tracking
 * const result = await executor.execute();
 * console.log('Success:', result.success);
 * console.log('Duration:', result.totalDuration, 'ms');
 * ```
 */

// ==================== Parallel Executor ====================

export type {
  TaskStatus,
  FlowTask,
  TaskResult,
  TaskState,
  ExecutorConfig,
  ExecutionProgress,
  ExecutionResult,
} from "./parallel-executor";

export { ParallelExecutor, createExecutor } from "./parallel-executor";

// ==================== Flow Phases ====================

export type Phase = "P1" | "P2" | "P3" | "P4" | "P5";

export const PHASES: Record<Phase, { name: string; emoji: string; agent: string }> = {
  P1: { name: "研究", emoji: "🔬", agent: "researcher" },
  P2: { name: "设计", emoji: "🏗️", agent: "architect" },
  P3: { name: "实现", emoji: "💻", agent: "coder" },
  P4: { name: "验证", emoji: "🧪", agent: "tester" },
  P5: { name: "收尾", emoji: "⚙️", agent: "ops" },
};

export const PHASE_ORDER: Phase[] = ["P1", "P2", "P3", "P4", "P5"];

export function getNextPhase(current: Phase): Phase | null {
  const idx = PHASE_ORDER.indexOf(current);
  return idx < PHASE_ORDER.length - 1 ? PHASE_ORDER[idx + 1] : null;
}

export function getPrevPhase(current: Phase): Phase | null {
  const idx = PHASE_ORDER.indexOf(current);
  return idx > 0 ? PHASE_ORDER[idx - 1] : null;
}

// ==================== Gate Checks ====================

export interface GateResult {
  passed: boolean;
  message: string;
  details?: string[];
}

export type GateChecker = () => Promise<GateResult>;

export const GATES: Record<string, { from: Phase; to: Phase; description: string }> = {
  G1: { from: "P2", to: "P3", description: "设计文档完成" },
  G2: { from: "P4", to: "P5", description: "测试通过" },
};

// ==================== Flow State ====================

export interface FlowState {
  phase: Phase;
  task: string;
  startTime: number;
  checkpoints: Checkpoint[];
  gateAttempts: Record<string, number>;
}

export interface Checkpoint {
  phase: Phase;
  timestamp: number;
  task: string;
  status: "completed" | "skipped" | "failed";
  artifacts?: string[];
}

// ==================== Helpers ====================

/**
 * Create a simple task for the parallel executor
 */
export function createSimpleTask(
  id: string,
  name: string,
  agent: string,
  fn: () => Promise<unknown>,
  deps: string[] = []
): import("./parallel-executor").FlowTask {
  return {
    id,
    name,
    agent,
    dependencies: deps,
    execute: async () => {
      try {
        const output = await fn();
        return { success: true, output, duration: 0 };
      } catch (error) {
        return {
          success: false,
          error: error instanceof Error ? error.message : String(error),
          duration: 0,
        };
      }
    },
  };
}
