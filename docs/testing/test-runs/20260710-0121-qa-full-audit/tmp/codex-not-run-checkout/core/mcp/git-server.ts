/**
 * MCP Git Server
 *
 * Git operations exposed through Model Context Protocol
 *
 * Operations:
 * - status: Get repository status
 * - log: Get commit history
 * - diff: Get changes diff
 * - commit: Create a commit
 * - branch: Branch operations
 * - stash: Stash operations
 * - remote: Remote operations
 */

import { execSync, exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

// ==================== Types ====================

export interface GitStatus {
  branch: string;
  ahead: number;
  behind: number;
  staged: FileChange[];
  unstaged: FileChange[];
  untracked: string[];
  conflicts: string[];
}

export interface FileChange {
  path: string;
  status: "modified" | "added" | "deleted" | "renamed" | "copied";
  oldPath?: string; // For renamed files
}

export interface GitCommit {
  hash: string;
  shortHash: string;
  author: string;
  email: string;
  date: string;
  message: string;
  body?: string;
}

export interface GitBranch {
  name: string;
  current: boolean;
  upstream?: string;
  ahead?: number;
  behind?: number;
  lastCommit?: string;
}

export interface GitDiff {
  files: DiffFile[];
  stats: {
    insertions: number;
    deletions: number;
    filesChanged: number;
  };
}

export interface DiffFile {
  path: string;
  status: string;
  insertions: number;
  deletions: number;
  hunks: string;
}

export interface GitRemote {
  name: string;
  fetchUrl: string;
  pushUrl: string;
}

// ==================== Git Server ====================

export class GitServer {
  private cwd: string;

  constructor(workingDirectory?: string) {
    this.cwd = workingDirectory ?? process.cwd();
  }

  // ==================== Status ====================

  async status(): Promise<GitStatus> {
    const branch = await this.getCurrentBranch();
    const { ahead, behind } = await this.getTrackingStatus();
    const porcelain = await this.exec("git status --porcelain=v2 --branch");

    const staged: FileChange[] = [];
    const unstaged: FileChange[] = [];
    const untracked: string[] = [];
    const conflicts: string[] = [];

    for (const line of porcelain.split("\n")) {
      if (!line) continue;

      if (line.startsWith("1 ") || line.startsWith("2 ")) {
        // Changed entries
        const parts = line.split(" ");
        const xy = parts[1]; // XY status
        const path = parts.slice(8).join(" ");

        // X = staged status, Y = unstaged status
        const stagedStatus = xy[0];
        const unstagedStatus = xy[1];

        if (stagedStatus !== ".") {
          staged.push({
            path,
            status: this.parseStatus(stagedStatus),
          });
        }

        if (unstagedStatus !== ".") {
          unstaged.push({
            path,
            status: this.parseStatus(unstagedStatus),
          });
        }

        // Check for conflicts
        if (xy === "UU" || xy === "AA" || xy === "DD") {
          conflicts.push(path);
        }
      } else if (line.startsWith("? ")) {
        // Untracked
        untracked.push(line.slice(2));
      } else if (line.startsWith("u ")) {
        // Unmerged (conflict)
        const path = line.split(" ").slice(10).join(" ");
        conflicts.push(path);
      }
    }

    return { branch, ahead, behind, staged, unstaged, untracked, conflicts };
  }

  private parseStatus(s: string): FileChange["status"] {
    switch (s) {
      case "M":
        return "modified";
      case "A":
        return "added";
      case "D":
        return "deleted";
      case "R":
        return "renamed";
      case "C":
        return "copied";
      default:
        return "modified";
    }
  }

  async getCurrentBranch(): Promise<string> {
    try {
      return (await this.exec("git branch --show-current")).trim();
    } catch {
      // Detached HEAD
      const hash = (await this.exec("git rev-parse --short HEAD")).trim();
      return `(HEAD detached at ${hash})`;
    }
  }

  private async getTrackingStatus(): Promise<{ ahead: number; behind: number }> {
    try {
      const output = await this.exec("git rev-list --left-right --count @{u}...HEAD");
      const [behind, ahead] = output.trim().split("\t").map(Number);
      return { ahead: ahead ?? 0, behind: behind ?? 0 };
    } catch {
      return { ahead: 0, behind: 0 };
    }
  }

  // ==================== Log ====================

  async log(options?: {
    count?: number;
    branch?: string;
    since?: string;
    author?: string;
    grep?: string;
  }): Promise<GitCommit[]> {
    // Use single quotes to prevent shell interpretation of %
    let cmd = "git log --format='%H|%h|%an|%ae|%aI|%s'";

    if (options?.count) cmd += ` -n${options.count}`;
    if (options?.branch) cmd += ` ${options.branch}`;
    if (options?.since) cmd += ` --since="${options.since}"`;
    if (options?.author) cmd += ` --author="${options.author}"`;
    if (options?.grep) cmd += ` --grep="${options.grep}"`;

    const output = await this.exec(cmd);
    const commits: GitCommit[] = [];

    for (const line of output.split("\n")) {
      if (!line.trim()) continue;

      const parts = line.split("|");
      if (parts.length >= 6) {
        commits.push({
          hash: parts[0],
          shortHash: parts[1],
          author: parts[2],
          email: parts[3],
          date: parts[4],
          message: parts[5],
        });
      }
    }

    return commits;
  }

  async getCommit(hash: string): Promise<GitCommit | null> {
    try {
      const output = await this.exec(
        `git show --format='%H|%h|%an|%ae|%aI|%s' -s ${hash}`
      );
      const parts = output.trim().split("|");
      if (parts.length >= 6) {
        return {
          hash: parts[0],
          shortHash: parts[1],
          author: parts[2],
          email: parts[3],
          date: parts[4],
          message: parts[5],
        };
      }
    } catch {
      return null;
    }
    return null;
  }

  // ==================== Diff ====================

  async diff(options?: {
    staged?: boolean;
    commit?: string;
    file?: string;
  }): Promise<GitDiff> {
    let cmd = "git diff";

    if (options?.staged) cmd += " --staged";
    if (options?.commit) cmd += ` ${options.commit}`;
    if (options?.file) cmd += ` -- "${options.file}"`;

    const diffOutput = await this.exec(cmd);

    // Get stats
    const statsCmd = cmd + " --stat";
    const statsOutput = await this.exec(statsCmd);

    const files: DiffFile[] = [];
    let currentFile: DiffFile | null = null;

    for (const line of diffOutput.split("\n")) {
      if (line.startsWith("diff --git")) {
        if (currentFile) files.push(currentFile);
        const match = line.match(/diff --git a\/(.*) b\/(.*)/);
        currentFile = {
          path: match?.[2] ?? "",
          status: "modified",
          insertions: 0,
          deletions: 0,
          hunks: "",
        };
      } else if (currentFile) {
        if (line.startsWith("+") && !line.startsWith("+++")) {
          currentFile.insertions++;
        } else if (line.startsWith("-") && !line.startsWith("---")) {
          currentFile.deletions++;
        }
        currentFile.hunks += line + "\n";
      }
    }

    if (currentFile) files.push(currentFile);

    // Parse stats
    let insertions = 0;
    let deletions = 0;
    const statsMatch = statsOutput.match(/(\d+) insertions?\(\+\), (\d+) deletions?\(-\)/);
    if (statsMatch) {
      insertions = parseInt(statsMatch[1], 10);
      deletions = parseInt(statsMatch[2], 10);
    }

    return {
      files,
      stats: {
        insertions,
        deletions,
        filesChanged: files.length,
      },
    };
  }

  // ==================== Commit ====================

  async commit(message: string, options?: {
    amend?: boolean;
    author?: string;
    allowEmpty?: boolean;
  }): Promise<{ hash: string; message: string }> {
    let cmd = `git commit -m "${message.replace(/"/g, '\\"')}"`;

    if (options?.amend) cmd += " --amend";
    if (options?.author) cmd += ` --author="${options.author}"`;
    if (options?.allowEmpty) cmd += " --allow-empty";

    await this.exec(cmd);

    // Get the new commit hash
    const hash = (await this.exec("git rev-parse HEAD")).trim();

    return { hash, message };
  }

  async add(paths: string | string[]): Promise<void> {
    const pathList = Array.isArray(paths) ? paths : [paths];
    await this.exec(`git add ${pathList.map((p) => `"${p}"`).join(" ")}`);
  }

  async addAll(): Promise<void> {
    await this.exec("git add -A");
  }

  async reset(paths?: string | string[], options?: { hard?: boolean; soft?: boolean }): Promise<void> {
    let cmd = "git reset";

    if (options?.hard) cmd += " --hard";
    if (options?.soft) cmd += " --soft";

    if (paths) {
      const pathList = Array.isArray(paths) ? paths : [paths];
      cmd += ` -- ${pathList.map((p) => `"${p}"`).join(" ")}`;
    }

    await this.exec(cmd);
  }

  // ==================== Branch ====================

  async branches(options?: { all?: boolean; remote?: boolean }): Promise<GitBranch[]> {
    let cmd = "git branch -vv";
    if (options?.all) cmd += " -a";
    if (options?.remote) cmd += " -r";

    const output = await this.exec(cmd);
    const branches: GitBranch[] = [];

    for (const line of output.split("\n")) {
      if (!line.trim()) continue;

      const current = line.startsWith("*");
      const parts = line.slice(2).trim().split(/\s+/);
      const name = parts[0];
      const hash = parts[1];

      // Parse tracking info [origin/main: ahead 2, behind 1]
      let upstream: string | undefined;
      let ahead: number | undefined;
      let behind: number | undefined;

      const trackMatch = line.match(/\[([^\]]+)\]/);
      if (trackMatch) {
        const trackInfo = trackMatch[1];
        const upstreamMatch = trackInfo.match(/^([^:]+)/);
        if (upstreamMatch) upstream = upstreamMatch[1];

        const aheadMatch = trackInfo.match(/ahead (\d+)/);
        if (aheadMatch) ahead = parseInt(aheadMatch[1], 10);

        const behindMatch = trackInfo.match(/behind (\d+)/);
        if (behindMatch) behind = parseInt(behindMatch[1], 10);
      }

      branches.push({
        name,
        current,
        upstream,
        ahead,
        behind,
        lastCommit: hash,
      });
    }

    return branches;
  }

  async createBranch(name: string, startPoint?: string): Promise<void> {
    let cmd = `git branch "${name}"`;
    if (startPoint) cmd += ` "${startPoint}"`;
    await this.exec(cmd);
  }

  async checkout(branchOrPath: string, options?: { create?: boolean; force?: boolean }): Promise<void> {
    let cmd = `git checkout`;
    if (options?.create) cmd += " -b";
    if (options?.force) cmd += " -f";
    cmd += ` "${branchOrPath}"`;
    await this.exec(cmd);
  }

  async deleteBranch(name: string, options?: { force?: boolean }): Promise<void> {
    const flag = options?.force ? "-D" : "-d";
    await this.exec(`git branch ${flag} "${name}"`);
  }

  // ==================== Stash ====================

  async stash(message?: string): Promise<void> {
    let cmd = "git stash push";
    if (message) cmd += ` -m "${message}"`;
    await this.exec(cmd);
  }

  async stashPop(index?: number): Promise<void> {
    const stashRef = index !== undefined ? `stash@{${index}}` : "";
    await this.exec(`git stash pop ${stashRef}`);
  }

  async stashList(): Promise<Array<{ index: number; message: string; branch: string }>> {
    const output = await this.exec("git stash list");
    const stashes: Array<{ index: number; message: string; branch: string }> = [];

    for (const line of output.split("\n")) {
      if (!line.trim()) continue;

      const match = line.match(/stash@\{(\d+)\}: On ([^:]+): (.+)/);
      if (match) {
        stashes.push({
          index: parseInt(match[1], 10),
          branch: match[2],
          message: match[3],
        });
      }
    }

    return stashes;
  }

  async stashDrop(index?: number): Promise<void> {
    const stashRef = index !== undefined ? `stash@{${index}}` : "";
    await this.exec(`git stash drop ${stashRef}`);
  }

  // ==================== Remote ====================

  async remotes(): Promise<GitRemote[]> {
    const output = await this.exec("git remote -v");
    const remoteMap: Map<string, GitRemote> = new Map();

    for (const line of output.split("\n")) {
      if (!line.trim()) continue;

      const match = line.match(/^(\S+)\s+(\S+)\s+\((fetch|push)\)$/);
      if (match) {
        const [, name, url, type] = match;

        if (!remoteMap.has(name)) {
          remoteMap.set(name, { name, fetchUrl: "", pushUrl: "" });
        }

        const remote = remoteMap.get(name)!;
        if (type === "fetch") {
          remote.fetchUrl = url;
        } else {
          remote.pushUrl = url;
        }
      }
    }

    return Array.from(remoteMap.values());
  }

  async fetch(remote?: string, options?: { prune?: boolean; all?: boolean }): Promise<void> {
    let cmd = "git fetch";
    if (options?.all) cmd += " --all";
    if (options?.prune) cmd += " --prune";
    if (remote) cmd += ` "${remote}"`;
    await this.exec(cmd);
  }

  async pull(remote?: string, branch?: string, options?: { rebase?: boolean }): Promise<void> {
    let cmd = "git pull";
    if (options?.rebase) cmd += " --rebase";
    if (remote) cmd += ` "${remote}"`;
    if (branch) cmd += ` "${branch}"`;
    await this.exec(cmd);
  }

  async push(remote?: string, branch?: string, options?: {
    force?: boolean;
    setUpstream?: boolean;
    tags?: boolean;
  }): Promise<void> {
    let cmd = "git push";
    if (options?.force) cmd += " --force";
    if (options?.setUpstream) cmd += " -u";
    if (options?.tags) cmd += " --tags";
    if (remote) cmd += ` "${remote}"`;
    if (branch) cmd += ` "${branch}"`;
    await this.exec(cmd);
  }

  // ==================== Utilities ====================

  async isRepo(): Promise<boolean> {
    try {
      await this.exec("git rev-parse --git-dir");
      return true;
    } catch {
      return false;
    }
  }

  async getRoot(): Promise<string> {
    return (await this.exec("git rev-parse --show-toplevel")).trim();
  }

  private async exec(command: string): Promise<string> {
    const { stdout } = await execAsync(command, { cwd: this.cwd });
    return stdout;
  }
}

// ==================== Factory ====================

export function createGitServer(workingDirectory?: string): GitServer {
  return new GitServer(workingDirectory);
}

// ==================== MCP Tool Definitions ====================

export const GIT_TOOLS = [
  {
    name: "git_status",
    description: "Get the current git repository status",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "git_log",
    description: "Get commit history",
    inputSchema: {
      type: "object",
      properties: {
        count: { type: "number", description: "Number of commits to show" },
        branch: { type: "string", description: "Branch to show history for" },
        since: { type: "string", description: "Show commits since date" },
        author: { type: "string", description: "Filter by author" },
      },
    },
  },
  {
    name: "git_diff",
    description: "Show changes between commits or working tree",
    inputSchema: {
      type: "object",
      properties: {
        staged: { type: "boolean", description: "Show staged changes" },
        commit: { type: "string", description: "Compare with commit" },
        file: { type: "string", description: "Show diff for specific file" },
      },
    },
  },
  {
    name: "git_commit",
    description: "Create a new commit",
    inputSchema: {
      type: "object",
      properties: {
        message: { type: "string", description: "Commit message" },
        amend: { type: "boolean", description: "Amend the last commit" },
      },
      required: ["message"],
    },
  },
  {
    name: "git_add",
    description: "Stage files for commit",
    inputSchema: {
      type: "object",
      properties: {
        paths: {
          oneOf: [
            { type: "string" },
            { type: "array", items: { type: "string" } },
          ],
          description: "File paths to stage",
        },
        all: { type: "boolean", description: "Stage all changes" },
      },
    },
  },
  {
    name: "git_branches",
    description: "List branches",
    inputSchema: {
      type: "object",
      properties: {
        all: { type: "boolean", description: "Include remote branches" },
      },
    },
  },
  {
    name: "git_checkout",
    description: "Switch branches or restore files",
    inputSchema: {
      type: "object",
      properties: {
        target: { type: "string", description: "Branch or path to checkout" },
        create: { type: "boolean", description: "Create new branch" },
      },
      required: ["target"],
    },
  },
  {
    name: "git_push",
    description: "Push commits to remote",
    inputSchema: {
      type: "object",
      properties: {
        remote: { type: "string", description: "Remote name" },
        branch: { type: "string", description: "Branch to push" },
        setUpstream: { type: "boolean", description: "Set upstream for branch" },
      },
    },
  },
  {
    name: "git_pull",
    description: "Pull changes from remote",
    inputSchema: {
      type: "object",
      properties: {
        remote: { type: "string", description: "Remote name" },
        rebase: { type: "boolean", description: "Rebase instead of merge" },
      },
    },
  },
];
