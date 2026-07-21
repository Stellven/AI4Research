#!/usr/bin/env bun
/**
 * Claude Code Usage Data Extractor
 * 提取并分析所有会话数据
 */

import { readdir, readFile, stat } from 'fs/promises';
import { join, basename } from 'path';

interface UsageStats {
  inputTokens: number;
  outputTokens: number;
}

interface ToolCall {
  tool: string;
  count: number;
}

interface SessionData {
  sessionId: string;
  project: string;
  timestamp: string;
  messageCount: number;
  userMessages: number;
  assistantMessages: number;
  usage: UsageStats;
  tools: Record<string, number>;
  hasSubagents: boolean;
  subagentCount: number;
}

interface ProjectStats {
  name: string;
  sessions: number;
  subagents: number;
  totalMessages: number;
  avgDepth: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  toolCalls: Record<string, number>;
  writeEditCount: number;
}

interface HourlyActivity {
  hour: string;
  count: number;
}

interface ReportData {
  generatedAt: string;
  timeRange: { start: string; end: string };
  totals: {
    sessions: number;
    subagents: number;
    messages: number;
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    dataSize: string;
  };
  projects: ProjectStats[];
  toolUsage: ToolCall[];
  hourlyActivity: HourlyActivity[];
  sessionDepthDistribution: {
    short: number;    // <10
    medium: number;   // 10-50
    long: number;     // 50-200
    veryLong: number; // >200
  };
}

const CLAUDE_PROJECTS_DIR = join(process.env.HOME!, '.claude', 'projects');

async function findJsonlFiles(dir: string): Promise<string[]> {
  const files: string[] = [];

  async function walk(currentDir: string) {
    try {
      const entries = await readdir(currentDir, { withFileTypes: true });
      for (const entry of entries) {
        const fullPath = join(currentDir, entry.name);
        if (entry.isDirectory()) {
          await walk(fullPath);
        } else if (entry.name.endsWith('.jsonl')) {
          files.push(fullPath);
        }
      }
    } catch (e) {
      // Skip inaccessible directories
    }
  }

  await walk(dir);
  return files;
}

async function parseJsonlFile(filePath: string): Promise<SessionData | null> {
  try {
    const content = await readFile(filePath, 'utf-8');
    const lines = content.trim().split('\n').filter(l => l.trim());

    const project = basename(filePath.split('/projects/')[1]?.split('/')[0] || 'unknown');
    const isSubagent = filePath.includes('/subagents/');

    let userMessages = 0;
    let assistantMessages = 0;
    let inputTokens = 0;
    let outputTokens = 0;
    const tools: Record<string, number> = {};
    let firstTimestamp = '';

    for (const line of lines) {
      try {
        const record = JSON.parse(line);

        if (!firstTimestamp && record.timestamp) {
          firstTimestamp = record.timestamp;
        }

        if (record.type === 'user') {
          userMessages++;
        } else if (record.type === 'assistant') {
          assistantMessages++;
          if (record.message?.usage) {
            inputTokens += record.message.usage.input_tokens || 0;
            outputTokens += record.message.usage.output_tokens || 0;
          }
        } else if (record.type === 'progress' && record.data?.tool) {
          const tool = record.data.tool;
          tools[tool] = (tools[tool] || 0) + 1;
        }
      } catch (e) {
        // Skip malformed lines
      }
    }

    return {
      sessionId: basename(filePath, '.jsonl'),
      project,
      timestamp: firstTimestamp,
      messageCount: userMessages + assistantMessages,
      userMessages,
      assistantMessages,
      usage: { inputTokens, outputTokens },
      tools,
      hasSubagents: false,
      subagentCount: 0
    };
  } catch (e) {
    return null;
  }
}

async function getFileModTime(filePath: string): Promise<string> {
  try {
    const stats = await stat(filePath);
    return stats.mtime.toISOString().slice(0, 13) + ':00';
  } catch {
    return '';
  }
}

async function main() {
  console.log('📊 Claude Code Usage Data Extractor');
  console.log('====================================\n');

  console.log('🔍 Scanning JSONL files...');
  const allFiles = await findJsonlFiles(CLAUDE_PROJECTS_DIR);
  console.log(`   Found ${allFiles.length} files\n`);

  // Separate main sessions and subagents
  const mainSessionFiles = allFiles.filter(f => !f.includes('/subagents/'));
  const subagentFiles = allFiles.filter(f => f.includes('/subagents/'));

  console.log(`📁 Main sessions: ${mainSessionFiles.length}`);
  console.log(`🤖 Subagent sessions: ${subagentFiles.length}\n`);

  // Parse all files
  console.log('📖 Parsing session data...');
  const sessions: SessionData[] = [];
  const hourlyMap: Record<string, number> = {};

  let processed = 0;
  for (const file of allFiles) {
    const data = await parseJsonlFile(file);
    if (data) {
      sessions.push(data);

      // Track hourly activity
      const modTime = await getFileModTime(file);
      if (modTime) {
        hourlyMap[modTime] = (hourlyMap[modTime] || 0) + 1;
      }
    }
    processed++;
    if (processed % 50 === 0) {
      process.stdout.write(`   Processed ${processed}/${allFiles.length}\r`);
    }
  }
  console.log(`\n   Parsed ${sessions.length} sessions\n`);

  // Aggregate by project
  console.log('📊 Aggregating statistics...');
  const projectMap: Record<string, ProjectStats> = {};

  for (const session of sessions) {
    if (!projectMap[session.project]) {
      projectMap[session.project] = {
        name: session.project,
        sessions: 0,
        subagents: 0,
        totalMessages: 0,
        avgDepth: 0,
        inputTokens: 0,
        outputTokens: 0,
        totalTokens: 0,
        toolCalls: {},
        writeEditCount: 0
      };
    }

    const proj = projectMap[session.project];
    proj.sessions++;
    proj.totalMessages += session.messageCount;
    proj.inputTokens += session.usage.inputTokens;
    proj.outputTokens += session.usage.outputTokens;
    proj.totalTokens += session.usage.inputTokens + session.usage.outputTokens;

    for (const [tool, count] of Object.entries(session.tools)) {
      proj.toolCalls[tool] = (proj.toolCalls[tool] || 0) + count;
      if (tool === 'Write' || tool === 'Edit') {
        proj.writeEditCount += count;
      }
    }
  }

  // Calculate averages
  for (const proj of Object.values(projectMap)) {
    proj.avgDepth = proj.sessions > 0 ? Math.round(proj.totalMessages / proj.sessions) : 0;
  }

  // Count subagents per project
  for (const file of subagentFiles) {
    const project = basename(file.split('/projects/')[1]?.split('/')[0] || 'unknown');
    if (projectMap[project]) {
      projectMap[project].subagents++;
    }
  }

  // Aggregate tool usage
  const globalTools: Record<string, number> = {};
  for (const proj of Object.values(projectMap)) {
    for (const [tool, count] of Object.entries(proj.toolCalls)) {
      globalTools[tool] = (globalTools[tool] || 0) + count;
    }
  }

  const toolUsage: ToolCall[] = Object.entries(globalTools)
    .map(([tool, count]) => ({ tool, count }))
    .sort((a, b) => b.count - a.count);

  // Session depth distribution
  const depthDist = { short: 0, medium: 0, long: 0, veryLong: 0 };
  for (const session of sessions) {
    const depth = session.messageCount;
    if (depth < 10) depthDist.short++;
    else if (depth < 50) depthDist.medium++;
    else if (depth < 200) depthDist.long++;
    else depthDist.veryLong++;
  }

  // Hourly activity
  const hourlyActivity: HourlyActivity[] = Object.entries(hourlyMap)
    .map(([hour, count]) => ({ hour, count }))
    .sort((a, b) => a.hour.localeCompare(b.hour));

  // Time range
  const timestamps = hourlyActivity.map(h => h.hour).filter(Boolean);
  const timeRange = {
    start: timestamps[0] || 'unknown',
    end: timestamps[timestamps.length - 1] || 'unknown'
  };

  // Calculate totals
  const totals = {
    sessions: mainSessionFiles.length,
    subagents: subagentFiles.length,
    messages: sessions.reduce((sum, s) => sum + s.messageCount, 0),
    inputTokens: sessions.reduce((sum, s) => sum + s.usage.inputTokens, 0),
    outputTokens: sessions.reduce((sum, s) => sum + s.usage.outputTokens, 0),
    totalTokens: 0,
    dataSize: '2.3 GB'
  };
  totals.totalTokens = totals.inputTokens + totals.outputTokens;

  // Sort projects by token usage
  const projects = Object.values(projectMap)
    .sort((a, b) => b.totalTokens - a.totalTokens);

  // Build report data
  const reportData: ReportData = {
    generatedAt: new Date().toISOString(),
    timeRange,
    totals,
    projects,
    toolUsage,
    hourlyActivity,
    sessionDepthDistribution: depthDist
  };

  // Output JSON
  const outputPath = join(process.env.HOME!, 'Solar', 'data', 'usage-stats.json');
  await Bun.write(outputPath, JSON.stringify(reportData, null, 2));
  console.log(`\n✅ Statistics saved to: ${outputPath}`);

  // Print summary
  console.log('\n📈 SUMMARY');
  console.log('==========');
  console.log(`Sessions: ${totals.sessions} main + ${totals.subagents} subagents`);
  console.log(`Messages: ${totals.messages.toLocaleString()}`);
  console.log(`Tokens: ${totals.totalTokens.toLocaleString()} (Input: ${totals.inputTokens.toLocaleString()}, Output: ${totals.outputTokens.toLocaleString()})`);
  console.log(`\nTop Projects:`);
  for (const proj of projects.slice(0, 5)) {
    console.log(`  ${proj.name}: ${proj.totalTokens.toLocaleString()} tokens, ${proj.sessions} sessions`);
  }
  console.log(`\nTop Tools:`);
  for (const tool of toolUsage.slice(0, 10)) {
    console.log(`  ${tool.tool}: ${tool.count.toLocaleString()}`);
  }

  return reportData;
}

main().catch(console.error);
