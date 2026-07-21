#!/usr/bin/env bun
/**
 * Solar Metadata Index - Query API
 * 统一查询接口，替代 Grep/Glob
 */

import Database from 'bun:sqlite';

// ============================================================
// Types
// ============================================================

export interface SMIFile {
  file_id: string;
  file_path: string;
  abs_path: string;
  file_type: string;
  category: string;
  feature?: string;
  project?: string;
  title?: string;
  description?: string;
  tags?: string[];
  size_bytes: number;
  line_count: number;
  last_modified: string;
}

export interface SMIAgent {
  agent_id: string;
  name: string;
  emoji?: string;
  role?: string;
  phase?: string;
  capabilities?: string[];
  file_path?: string;
  description?: string;
}

export interface SMISkill {
  skill_id: string;
  command: string;
  name?: string;
  description?: string;
  category?: string;
  file_path?: string;
  impl_path?: string;
  usage_count: number;
}

export interface SMISearchResult {
  entity_type: string;
  id: string;
  title?: string;
  description?: string;
  path?: string;
  feature?: string;
  project?: string;
  tags?: string[];
}

// ============================================================
// SMI Query Class
// ============================================================

export class SMIQuery {
  private db: Database;

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`) {
    this.db = new Database(dbPath, { readonly: true });
  }

  // ============================================================
  // File Queries
  // ============================================================

  /**
   * 查询特性相关的所有文件
   */
  findFilesByFeature(feature: string): SMIFile[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_files
      WHERE feature = ?
      ORDER BY category, file_path
    `).all(feature) as any[];

    return rows.map(r => this.parseFile(r));
  }

  /**
   * 查询项目的所有文件
   */
  findFilesByProject(project: string): SMIFile[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_files
      WHERE project = ?
      ORDER BY category, file_path
    `).all(project) as any[];

    return rows.map(r => this.parseFile(r));
  }

  /**
   * 按分类查询文件
   */
  findFilesByCategory(category: string): SMIFile[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_files
      WHERE category = ?
      ORDER BY file_path
    `).all(category) as any[];

    return rows.map(r => this.parseFile(r));
  }

  /**
   * 按文件类型查询
   */
  findFilesByType(fileType: string): SMIFile[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_files
      WHERE file_type = ?
      ORDER BY file_path
    `).all(fileType) as any[];

    return rows.map(r => this.parseFile(r));
  }

  /**
   * 查询单个文件
   */
  findFile(filePath: string): SMIFile | null {
    const row = this.db.prepare(`
      SELECT * FROM smi_files
      WHERE file_path = ? OR abs_path = ?
    `).get(filePath, filePath) as any;

    return row ? this.parseFile(row) : null;
  }

  // ============================================================
  // Agent Queries
  // ============================================================

  /**
   * 查询所有 Agent
   */
  findAllAgents(): SMIAgent[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_agents
      ORDER BY agent_id
    `).all() as any[];

    return rows.map(r => this.parseAgent(r));
  }

  /**
   * 按阶段查询 Agent
   */
  findAgentsByPhase(phase: string): SMIAgent[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_agents
      WHERE phase = ?
      ORDER BY agent_id
    `).all(phase) as any[];

    return rows.map(r => this.parseAgent(r));
  }

  /**
   * 查询单个 Agent
   */
  findAgent(agentId: string): SMIAgent | null {
    const row = this.db.prepare(`
      SELECT * FROM smi_agents
      WHERE agent_id = ?
    `).get(agentId) as any;

    return row ? this.parseAgent(row) : null;
  }

  // ============================================================
  // Skill Queries
  // ============================================================

  /**
   * 查询所有 Skill
   */
  findAllSkills(): SMISkill[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_skills
      ORDER BY command
    `).all() as any[];

    return rows.map(r => this.parseSkill(r));
  }

  /**
   * 按分类查询 Skill
   */
  findSkillsByCategory(category: string): SMISkill[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_skills
      WHERE category = ?
      ORDER BY command
    `).all(category) as any[];

    return rows.map(r => this.parseSkill(r));
  }

  /**
   * 查询用户可调用的 Skill
   */
  findUserInvocableSkills(): SMISkill[] {
    const rows = this.db.prepare(`
      SELECT * FROM smi_skills
      WHERE user_invocable = true
      ORDER BY usage_count DESC, command
    `).all() as any[];

    return rows.map(r => this.parseSkill(r));
  }

  /**
   * 查询单个 Skill
   */
  findSkill(skillId: string): SMISkill | null {
    const row = this.db.prepare(`
      SELECT * FROM smi_skills
      WHERE skill_id = ? OR command = ?
    `).get(skillId, `/${skillId}`) as any;

    return row ? this.parseSkill(row) : null;
  }

  // ============================================================
  // Search Queries
  // ============================================================

  /**
   * 全文搜索 (跨所有实体)
   */
  search(query: string, options: {
    entityTypes?: string[];
    limit?: number;
  } = {}): SMISearchResult[] {
    const {
      entityTypes = ['file', 'agent', 'skill', 'rule'],
      limit = 50
    } = options;

    const pattern = `%${query}%`;
    const typeFilter = entityTypes.map(() => '?').join(',');

    const rows = this.db.prepare(`
      SELECT * FROM v_smi_search
      WHERE entity_type IN (${typeFilter})
        AND (
          title LIKE ? OR
          description LIKE ? OR
          path LIKE ?
        )
      LIMIT ?
    `).all(...entityTypes, pattern, pattern, pattern, limit) as any[];

    return rows.map(r => this.parseSearchResult(r));
  }

  /**
   * 按标签搜索
   */
  searchByTag(tag: string): SMISearchResult[] {
    const rows = this.db.prepare(`
      SELECT
        t.entity_type,
        t.entity_id as id,
        CASE
          WHEN t.entity_type = 'file' THEN f.title
          WHEN t.entity_type = 'agent' THEN a.name
          WHEN t.entity_type = 'skill' THEN s.name
        END as title,
        CASE
          WHEN t.entity_type = 'file' THEN f.file_path
          WHEN t.entity_type = 'agent' THEN a.file_path
          WHEN t.entity_type = 'skill' THEN s.file_path
        END as path
      FROM smi_tags t
      LEFT JOIN smi_files f ON t.entity_type = 'file' AND t.entity_id = f.file_id
      LEFT JOIN smi_agents a ON t.entity_type = 'agent' AND t.entity_id = a.agent_id
      LEFT JOIN smi_skills s ON t.entity_type = 'skill' AND t.entity_id = s.skill_id
      WHERE t.tag = ?
    `).all(tag) as any[];

    return rows.map(r => ({
      entity_type: r.entity_type,
      id: r.id,
      title: r.title,
      path: r.path
    }));
  }

  // ============================================================
  // Relationship Queries
  // ============================================================

  /**
   * 查询依赖关系
   */
  findDependencies(entityType: string, entityId: string): Array<{
    target_type: string;
    target_id: string;
    relation_type: string;
  }> {
    return this.db.prepare(`
      SELECT target_type, target_id, relation_type
      FROM smi_relationships
      WHERE source_type = ? AND source_id = ?
      ORDER BY weight DESC
    `).all(entityType, entityId) as any[];
  }

  /**
   * 查询反向依赖 (谁依赖我)
   */
  findReverseDependencies(entityType: string, entityId: string): Array<{
    source_type: string;
    source_id: string;
    relation_type: string;
  }> {
    return this.db.prepare(`
      SELECT source_type, source_id, relation_type
      FROM smi_relationships
      WHERE target_type = ? AND target_id = ?
      ORDER BY weight DESC
    `).all(entityType, entityId) as any[];
  }

  // ============================================================
  // Stats Queries
  // ============================================================

  /**
   * 获取统计信息
   */
  getStats(): {
    total_files: number;
    total_agents: number;
    total_skills: number;
    total_projects: number;
  } {
    const fileCount = this.db.prepare('SELECT COUNT(*) as count FROM smi_files').get() as { count: number };
    const agentCount = this.db.prepare('SELECT COUNT(*) as count FROM smi_agents').get() as { count: number };
    const skillCount = this.db.prepare('SELECT COUNT(*) as count FROM smi_skills').get() as { count: number };
    const projectCount = this.db.prepare('SELECT COUNT(*) as count FROM smi_projects').get() as { count: number };

    return {
      total_files: fileCount.count,
      total_agents: agentCount.count,
      total_skills: skillCount.count,
      total_projects: projectCount.count
    };
  }

  /**
   * 按特性统计文件数
   */
  getFeatureStats(): Array<{ feature: string; file_count: number }> {
    return this.db.prepare(`
      SELECT feature, COUNT(*) as file_count
      FROM smi_files
      WHERE feature IS NOT NULL
      GROUP BY feature
      ORDER BY file_count DESC
    `).all() as any[];
  }

  // ============================================================
  // Helper Methods
  // ============================================================

  private parseFile(row: any): SMIFile {
    return {
      ...row,
      tags: row.tags ? JSON.parse(row.tags) : undefined
    };
  }

  private parseAgent(row: any): SMIAgent {
    return {
      ...row,
      capabilities: row.capabilities ? JSON.parse(row.capabilities) : undefined
    };
  }

  private parseSkill(row: any): SMISkill {
    return {
      ...row,
      tags: row.tags ? JSON.parse(row.tags) : undefined
    };
  }

  private parseSearchResult(row: any): SMISearchResult {
    return {
      ...row,
      tags: row.tags ? JSON.parse(row.tags) : undefined
    };
  }

  close(): void {
    this.db.close();
  }
}

// ============================================================
// Convenience Functions
// ============================================================

/**
 * 快速查询: Capsule 相关的所有文件
 */
export function findCapsuleFiles(): SMIFile[] {
  const query = new SMIQuery();
  const files = query.findFilesByFeature('capsule');
  query.close();
  return files;
}

/**
 * 快速查询: 所有 Agent
 */
export function findAllAgents(): SMIAgent[] {
  const query = new SMIQuery();
  const agents = query.findAllAgents();
  query.close();
  return agents;
}

/**
 * 快速搜索
 */
export function quickSearch(term: string): SMISearchResult[] {
  const query = new SMIQuery();
  const results = query.search(term);
  query.close();
  return results;
}

// ============================================================
// CLI Support
// ============================================================

if (import.meta.main) {
  const args = process.argv.slice(2);
  const cmd = args[0];

  const query = new SMIQuery();

  switch (cmd) {
    case 'search':
      const results = query.search(args[1] || '');
      console.log(JSON.stringify(results, null, 2));
      break;

    case 'feature':
      const files = query.findFilesByFeature(args[1] || '');
      console.log(JSON.stringify(files, null, 2));
      break;

    case 'agents':
      const agents = query.findAllAgents();
      console.log(JSON.stringify(agents, null, 2));
      break;

    case 'skills':
      const skills = query.findAllSkills();
      console.log(JSON.stringify(skills, null, 2));
      break;

    case 'stats':
      const stats = query.getStats();
      console.log(JSON.stringify(stats, null, 2));
      break;

    default:
      console.log('Usage: query.ts <search|feature|agents|skills|stats> [args]');
  }

  query.close();
}
