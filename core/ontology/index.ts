/**
 * Solar Ontology System
 * 本体 = 记忆库 + 个性 (不是大脑，大脑是 Claude)
 *
 * 使用方式:
 *
 * ```typescript
 * import { getOntologyManager, getPreferenceObserver } from './ontology';
 *
 * // 初始化 (需要数据库实例)
 * const ontology = getOntologyManager(db);
 *
 * // 会话开始时加载本体
 * const snapshot = await ontology.onSessionStart(sessionId);
 *
 * // 获取 Agent 上下文
 * const context = ontology.getAgentContext('coder');
 * const prompt = context.toPrompt(); // 注入到 Agent prompt
 *
 * // 会话结束时学习
 * const observer = getPreferenceObserver();
 * const signals = observer.extractSignals(sessionData);
 * await ontology.onSessionEnd(sessionId, signals);
 * ```
 */

export * from "./types";
export * from "./manager";
export * from "./observer";
export * from "./timeline";
export * from "./reflection";
export * from "./scheduler";
export * from "./agent-integration";

// Re-export convenience functions
export { getOntologyManager } from "./manager";
export { getPreferenceObserver } from "./observer";
export { getOntologyTimeline } from "./timeline";
export { getOntologyReflector, getOntologyUsageVerifier } from "./reflection";
export { getOntologyScheduler } from "./scheduler";
export {
  getAgentOntologyContext,
  applyOntologyPreferences,
  recordAgentTaskCompletion,
  generateOntologyGuidedPrompt,
  verifyAgentOntologyUsage,
  quickGetContext,
  quickRecordTask,
} from "./agent-integration";

// ==================== Quick Start ====================

import { Database } from "bun:sqlite";
import { getOntologyManager } from "./manager";
import { getPreferenceObserver, SessionData } from "./observer";

/**
 * 快速初始化本体系统
 */
export function initOntology(dbPath?: string) {
  const path = dbPath ?? process.env.SOLAR_DB_PATH ?? `${process.env.HOME}/.solar/db/solar.db`;
  const db = new Database(path);
  const ontology = getOntologyManager(db);
  const observer = getPreferenceObserver();

  return { db, ontology, observer };
}

/**
 * 快速创建会话生命周期 hooks
 */
export function createSessionHooks(dbPath?: string) {
  const { ontology, observer } = initOntology(dbPath);

  return {
    /**
     * 会话开始时调用
     */
    async onStart(sessionId: string) {
      return ontology.onSessionStart(sessionId);
    },

    /**
     * 获取 Agent 上下文
     */
    getAgentContext(agentId: string) {
      return ontology.getAgentContext(agentId);
    },

    /**
     * 从用户反馈中学习
     */
    learnFromFeedback(feedback: string) {
      return observer.extractFromExplicitFeedback(feedback);
    },

    /**
     * 会话结束时调用
     */
    async onEnd(sessionId: string, sessionData: SessionData, feedback?: string) {
      const signals = observer.extractSignals(sessionData);

      // 添加显式反馈的信号
      if (feedback) {
        signals.push(...observer.extractFromExplicitFeedback(feedback));
      }

      await ontology.onSessionEnd(sessionId, signals);
    },
  };
}
