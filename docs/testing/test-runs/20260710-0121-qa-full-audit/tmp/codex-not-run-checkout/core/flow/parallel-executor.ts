/**
 * Parallel Flow Executor
 *
 * Dependency-aware parallel task execution engine for Solar
 */

// ==================== Types ====================

export type TaskStatus = "pending" | "ready" | "running" | "completed" | "failed" | "blocked";

export interface FlowTask {
  id: string;
  name: string;
  agent: string;
  dependencies: string[];     // Task IDs this depends on
  execute: () => Promise<TaskResult>;
  timeout?: number;           // Max execution time in ms
  retries?: number;           // Max retry attempts
  priority?: number;          // Higher = more priority
}

export interface TaskResult {
  success: boolean;
  output?: unknown;
  error?: string;
  duration: number;
  metrics?: Record<string, number>;
}

export interface TaskState {
  task: FlowTask;
  status: TaskStatus;
  result?: TaskResult;
  startTime?: number;
  endTime?: number;
  attempts: number;
  blockedBy?: string[];       // IDs of failed dependencies
}

export interface ExecutorConfig {
  maxConcurrency?: number;    // Max parallel tasks
  globalTimeout?: number;     // Max total execution time
  onTaskStart?: (task: FlowTask) => void;
  onTaskComplete?: (task: FlowTask, result: TaskResult) => void;
  onTaskFailed?: (task: FlowTask, error: Error) => void;
  onProgress?: (progress: ExecutionProgress) => void;
}

export interface ExecutionProgress {
  total: number;
  completed: number;
  failed: number;
  running: number;
  pending: number;
  blocked: number;
  elapsedTime: number;
}

export interface ExecutionResult {
  success: boolean;
  tasks: Map<string, TaskState>;
  totalDuration: number;
  progress: ExecutionProgress;
  errors: Array<{ taskId: string; error: string }>;
}

// ==================== Dependency Graph ====================

class DependencyGraph {
  private nodes: Map<string, Set<string>> = new Map();      // task -> dependencies
  private dependents: Map<string, Set<string>> = new Map(); // task -> tasks that depend on it

  addTask(taskId: string, dependencies: string[]): void {
    this.nodes.set(taskId, new Set(dependencies));

    // Build reverse map
    for (const dep of dependencies) {
      if (!this.dependents.has(dep)) {
        this.dependents.set(dep, new Set());
      }
      this.dependents.get(dep)!.add(taskId);
    }
  }

  getDependencies(taskId: string): string[] {
    return Array.from(this.nodes.get(taskId) ?? []);
  }

  getDependents(taskId: string): string[] {
    return Array.from(this.dependents.get(taskId) ?? []);
  }

  hasDependencies(taskId: string): boolean {
    const deps = this.nodes.get(taskId);
    return deps !== undefined && deps.size > 0;
  }

  removeDependency(taskId: string, dependencyId: string): void {
    this.nodes.get(taskId)?.delete(dependencyId);
  }

  // Detect cycles using DFS
  hasCycle(): boolean {
    const visited = new Set<string>();
    const recursionStack = new Set<string>();

    const dfs = (nodeId: string): boolean => {
      visited.add(nodeId);
      recursionStack.add(nodeId);

      const deps = this.nodes.get(nodeId) ?? new Set();
      for (const dep of deps) {
        if (!visited.has(dep)) {
          if (dfs(dep)) return true;
        } else if (recursionStack.has(dep)) {
          return true; // Cycle detected
        }
      }

      recursionStack.delete(nodeId);
      return false;
    };

    for (const nodeId of this.nodes.keys()) {
      if (!visited.has(nodeId)) {
        if (dfs(nodeId)) return true;
      }
    }

    return false;
  }

  // Topological sort
  getExecutionOrder(): string[] {
    const inDegree = new Map<string, number>();
    const queue: string[] = [];
    const result: string[] = [];

    // Calculate in-degree for each node
    for (const [taskId, deps] of this.nodes) {
      inDegree.set(taskId, deps.size);
      if (deps.size === 0) {
        queue.push(taskId);
      }
    }

    while (queue.length > 0) {
      const taskId = queue.shift()!;
      result.push(taskId);

      // Reduce in-degree for dependents
      const dependents = this.dependents.get(taskId) ?? new Set();
      for (const dep of dependents) {
        const degree = (inDegree.get(dep) ?? 0) - 1;
        inDegree.set(dep, degree);
        if (degree === 0) {
          queue.push(dep);
        }
      }
    }

    return result;
  }
}

// ==================== Parallel Executor ====================

export class ParallelExecutor {
  private config: Required<ExecutorConfig>;
  private taskStates: Map<string, TaskState> = new Map();
  private graph: DependencyGraph = new DependencyGraph();
  private completedTasks: Set<string> = new Set();
  private failedTasks: Set<string> = new Set();
  private runningTasks: Set<string> = new Set();
  private startTime = 0;

  constructor(config: ExecutorConfig = {}) {
    this.config = {
      maxConcurrency: config.maxConcurrency ?? 4,
      globalTimeout: config.globalTimeout ?? 600000, // 10 minutes
      onTaskStart: config.onTaskStart ?? (() => {}),
      onTaskComplete: config.onTaskComplete ?? (() => {}),
      onTaskFailed: config.onTaskFailed ?? (() => {}),
      onProgress: config.onProgress ?? (() => {}),
    };
  }

  // ==================== Task Registration ====================

  addTask(task: FlowTask): void {
    this.taskStates.set(task.id, {
      task,
      status: "pending",
      attempts: 0,
    });
    this.graph.addTask(task.id, task.dependencies);
  }

  addTasks(tasks: FlowTask[]): void {
    for (const task of tasks) {
      this.addTask(task);
    }
  }

  // ==================== Execution ====================

  async execute(): Promise<ExecutionResult> {
    this.startTime = Date.now();

    // Validate graph
    if (this.graph.hasCycle()) {
      throw new Error("Circular dependency detected in task graph");
    }

    // Initialize ready tasks
    this.updateTaskStatuses();

    // Execute until all done or timeout
    while (!this.isComplete()) {
      // Check global timeout
      if (Date.now() - this.startTime > this.config.globalTimeout) {
        this.cancelRunningTasks("Global timeout exceeded");
        break;
      }

      // Get ready tasks
      const readyTasks = this.getReadyTasks();

      // Execute ready tasks up to concurrency limit
      const slotsAvailable = this.config.maxConcurrency - this.runningTasks.size;
      const tasksToRun = readyTasks.slice(0, slotsAvailable);

      if (tasksToRun.length > 0) {
        // Start tasks in parallel (don't await)
        for (const task of tasksToRun) {
          this.executeTask(task);
        }
      }

      // Wait a bit before next iteration
      await this.sleep(10);
    }

    return this.buildResult();
  }

  private async executeTask(task: FlowTask): Promise<void> {
    const state = this.taskStates.get(task.id)!;
    state.status = "running";
    state.startTime = Date.now();
    state.attempts++;
    this.runningTasks.add(task.id);

    this.config.onTaskStart(task);
    this.emitProgress();

    try {
      // Execute with timeout
      const result = await this.executeWithTimeout(task);

      state.result = result;
      state.endTime = Date.now();

      if (result.success) {
        state.status = "completed";
        this.completedTasks.add(task.id);
        this.config.onTaskComplete(task, result);
      } else {
        // Check retries
        if (state.attempts < (task.retries ?? 1)) {
          state.status = "ready"; // Retry
        } else {
          state.status = "failed";
          this.failedTasks.add(task.id);
          this.config.onTaskFailed(task, new Error(result.error ?? "Unknown error"));
        }
      }
    } catch (error) {
      state.endTime = Date.now();
      state.result = {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        duration: Date.now() - (state.startTime ?? Date.now()),
      };

      // Check retries
      if (state.attempts < (task.retries ?? 1)) {
        state.status = "ready"; // Retry
      } else {
        state.status = "failed";
        this.failedTasks.add(task.id);
        this.config.onTaskFailed(task, error as Error);
      }
    } finally {
      this.runningTasks.delete(task.id);
      this.updateTaskStatuses();
      this.emitProgress();
    }
  }

  private async executeWithTimeout(task: FlowTask): Promise<TaskResult> {
    const timeout = task.timeout ?? 60000; // 1 minute default
    const startTime = Date.now();

    return new Promise(async (resolve, reject) => {
      const timeoutId = setTimeout(() => {
        reject(new Error(`Task ${task.id} timed out after ${timeout}ms`));
      }, timeout);

      try {
        const result = await task.execute();
        clearTimeout(timeoutId);
        resolve({
          ...result,
          duration: Date.now() - startTime,
        });
      } catch (error) {
        clearTimeout(timeoutId);
        reject(error);
      }
    });
  }

  // ==================== Status Management ====================

  private updateTaskStatuses(): void {
    for (const [taskId, state] of this.taskStates) {
      if (state.status === "pending" || state.status === "ready") {
        const deps = this.graph.getDependencies(taskId);

        // Check if all dependencies are completed
        const allDepsCompleted = deps.every((dep) => this.completedTasks.has(dep));

        // Check if any dependency failed
        const failedDeps = deps.filter((dep) => this.failedTasks.has(dep));

        if (failedDeps.length > 0) {
          state.status = "blocked";
          state.blockedBy = failedDeps;
        } else if (allDepsCompleted) {
          state.status = "ready";
        }
      }
    }
  }

  private getReadyTasks(): FlowTask[] {
    const ready: FlowTask[] = [];

    for (const [_, state] of this.taskStates) {
      if (state.status === "ready") {
        ready.push(state.task);
      }
    }

    // Sort by priority (higher first)
    ready.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));

    return ready;
  }

  private isComplete(): boolean {
    for (const [_, state] of this.taskStates) {
      if (
        state.status !== "completed" &&
        state.status !== "failed" &&
        state.status !== "blocked"
      ) {
        return false;
      }
    }
    return true;
  }

  private cancelRunningTasks(reason: string): void {
    for (const taskId of this.runningTasks) {
      const state = this.taskStates.get(taskId);
      if (state) {
        state.status = "failed";
        state.result = {
          success: false,
          error: reason,
          duration: Date.now() - (state.startTime ?? Date.now()),
        };
        this.failedTasks.add(taskId);
      }
    }
    this.runningTasks.clear();
  }

  // ==================== Progress ====================

  private emitProgress(): void {
    this.config.onProgress(this.getProgress());
  }

  getProgress(): ExecutionProgress {
    let completed = 0;
    let failed = 0;
    let running = 0;
    let pending = 0;
    let blocked = 0;

    for (const [_, state] of this.taskStates) {
      switch (state.status) {
        case "completed":
          completed++;
          break;
        case "failed":
          failed++;
          break;
        case "running":
          running++;
          break;
        case "pending":
        case "ready":
          pending++;
          break;
        case "blocked":
          blocked++;
          break;
      }
    }

    return {
      total: this.taskStates.size,
      completed,
      failed,
      running,
      pending,
      blocked,
      elapsedTime: Date.now() - this.startTime,
    };
  }

  // ==================== Result ====================

  private buildResult(): ExecutionResult {
    const errors: Array<{ taskId: string; error: string }> = [];

    for (const [taskId, state] of this.taskStates) {
      if (state.status === "failed" && state.result?.error) {
        errors.push({ taskId, error: state.result.error });
      }
    }

    const progress = this.getProgress();
    const success = progress.failed === 0 && progress.blocked === 0;

    return {
      success,
      tasks: this.taskStates,
      totalDuration: Date.now() - this.startTime,
      progress,
      errors,
    };
  }

  // ==================== Utilities ====================

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // ==================== Visualization ====================

  /**
   * Generate execution plan visualization
   */
  getExecutionPlan(): string[] {
    const lines: string[] = [];
    const order = this.graph.getExecutionOrder();

    lines.push("═══ Execution Plan ═══");
    lines.push("");

    // Group by dependency level
    const levels: Map<string, number> = new Map();
    for (const taskId of order) {
      const deps = this.graph.getDependencies(taskId);
      const level = deps.length === 0 ? 0 : Math.max(...deps.map((d) => levels.get(d) ?? 0)) + 1;
      levels.set(taskId, level);
    }

    // Group tasks by level
    const byLevel: Map<number, string[]> = new Map();
    for (const [taskId, level] of levels) {
      if (!byLevel.has(level)) {
        byLevel.set(level, []);
      }
      byLevel.get(level)!.push(taskId);
    }

    // Print each level
    for (const [level, tasks] of Array.from(byLevel.entries()).sort((a, b) => a[0] - b[0])) {
      lines.push(`Level ${level}: [${tasks.length} tasks, parallel]`);
      for (const taskId of tasks) {
        const state = this.taskStates.get(taskId);
        const task = state?.task;
        const deps = this.graph.getDependencies(taskId);
        const depsStr = deps.length > 0 ? ` ← [${deps.join(", ")}]` : "";
        lines.push(`  ├── ${task?.agent ?? "?"}: ${task?.name ?? taskId}${depsStr}`);
      }
      lines.push("");
    }

    return lines;
  }
}

// ==================== Factory ====================

export function createExecutor(config?: ExecutorConfig): ParallelExecutor {
  return new ParallelExecutor(config);
}
