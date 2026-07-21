/**
 * Solar Task Queue Widget
 *
 * 显示当前任务队列和进度
 */

import { card, kv, bar, list } from "tvs/termplane/sdk/widget";
import type { CardLayout } from "tvs/termplane/render/types";

// ==================== Types ====================

export interface TaskQueueData {
  tasks: Task[];
  completed: number;
  total: number;
  timestamp: number;
}

export interface Task {
  id: string;
  agent: string;
  description: string;
  progress: number;
  status: "running" | "pending" | "completed" | "blocked";
  priority?: "high" | "normal" | "low";
}

// ==================== Widget ====================

export class TaskQueueWidget {
  readonly id = "solar.task.queue";
  readonly title = "Task Queue";

  /**
   * 生成模拟数据
   */
  mockData(): TaskQueueData {
    return {
      tasks: [
        {
          id: "1",
          agent: "Coder",
          description: "实现 HashJoin v10",
          progress: 0.7,
          status: "running",
          priority: "high",
        },
        {
          id: "2",
          agent: "Tester",
          description: "TPC-H 基准测试",
          progress: 0.45,
          status: "running",
        },
        {
          id: "3",
          agent: "Architect",
          description: "设计评审",
          progress: 0.85,
          status: "running",
        },
        {
          id: "4",
          agent: "Ops",
          description: "Release Build",
          progress: 0.3,
          status: "pending",
        },
        {
          id: "5",
          agent: "Guard",
          description: "规范检查",
          progress: 0,
          status: "pending",
        },
      ],
      completed: 12,
      total: 17,
      timestamp: Date.now(),
    };
  }

  /**
   * 渲染 Widget
   */
  render(data: TaskQueueData): CardLayout {
    const runningTasks = data.tasks.filter((t) => t.status === "running");

    const items = runningTasks.map((task) => ({
      key: task.agent,
      bar: task.progress,
    }));

    return card("📋 TASK QUEUE", [
      { type: "kv", items },
      { type: "divider" },
      {
        type: "text",
        content: `进行中: ${runningTasks.length} | 完成: ${data.completed}/${data.total}`,
        align: "center",
      },
    ]);
  }

  /**
   * 渲染详细任务列表
   */
  renderDetailed(data: TaskQueueData): CardLayout {
    const taskItems = data.tasks.slice(0, 6).map((task) => {
      const statusIcon =
        task.status === "running"
          ? "🔄"
          : task.status === "completed"
            ? "✅"
            : task.status === "blocked"
              ? "🚫"
              : "⏳";
      const progress = Math.round(task.progress * 100);
      return `${statusIcon} [${task.agent}] ${task.description} (${progress}%)`;
    });

    return card("📋 TASK DETAILS", [
      { type: "list", items: taskItems, variant: "bullet" },
      { type: "divider" },
      { type: "bar", value: data.completed / data.total, label: "Overall" },
    ]);
  }
}

export const taskQueueWidget = new TaskQueueWidget();
