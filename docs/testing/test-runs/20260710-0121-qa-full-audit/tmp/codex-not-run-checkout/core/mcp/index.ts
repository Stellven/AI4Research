/**
 * Solar MCP Servers
 *
 * Model Context Protocol servers for tool integration
 *
 * @example
 * ```typescript
 * import { createGitServer } from 'solar/core/mcp';
 *
 * const git = createGitServer();
 *
 * // Get status
 * const status = await git.status();
 * console.log('Branch:', status.branch);
 * console.log('Changed files:', status.unstaged.length);
 *
 * // Stage and commit
 * await git.addAll();
 * await git.commit('feat: Add new feature');
 *
 * // Push
 * await git.push('origin', 'main');
 * ```
 */

// ==================== Git Server ====================

export {
  GitServer,
  createGitServer,
  GIT_TOOLS,
} from "./git-server";

export type {
  GitStatus,
  FileChange,
  GitCommit,
  GitBranch,
  GitDiff,
  DiffFile,
  GitRemote,
} from "./git-server";
