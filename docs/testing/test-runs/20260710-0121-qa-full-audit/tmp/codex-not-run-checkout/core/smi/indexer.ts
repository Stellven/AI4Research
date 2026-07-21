#!/usr/bin/env bun
/**
 * Solar Metadata Index - File Indexer
 * 扫描文件系统并提取元数据索引到 ThunderDuck
 */

import { readdirSync, statSync, readFileSync } from 'fs';
import { join, relative, extname, basename, dirname } from 'path';
import { createHash } from 'crypto';
import Database from 'bun:sqlite';

// ============================================================
// Types
// ============================================================

export interface FileMetadata {
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
  last_modified: Date;
  content_hash: string;
}

export interface IndexStats {
  total_files: number;
  indexed: number;
  updated: number;
  skipped: number;
  errors: number;
  duration_ms: number;
}

// ============================================================
// File Indexer Class
// ============================================================

export class FileIndexer {
  private db: Database;
  private rootPath: string;
  private stats: IndexStats;

  constructor(dbPath: string = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`, rootPath: string = process.cwd()) {
    this.db = new Database(dbPath);
    this.rootPath = rootPath;
    this.stats = {
      total_files: 0,
      indexed: 0,
      updated: 0,
      skipped: 0,
      errors: 0,
      duration_ms: 0
    };
  }

  /**
   * 扫描目录并索引所有文件
   */
  async scanDirectory(dir: string, options: {
    recursive?: boolean;
    extensions?: string[];
    exclude?: string[];
  } = {}): Promise<IndexStats> {
    const startTime = Date.now();
    const {
      recursive = true,
      extensions = ['.md', '.ts', '.sql', '.json', '.txt', '.sh'],
      exclude = ['node_modules', '.git', 'dist', 'build', '.next', 'coverage']
    } = options;

    try {
      await this.scanDirectoryRecursive(dir, recursive, extensions, exclude);
    } catch (error) {
      console.error(`Error scanning directory ${dir}:`, error);
      this.stats.errors++;
    }

    this.stats.duration_ms = Date.now() - startTime;
    return this.stats;
  }

  private async scanDirectoryRecursive(
    dir: string,
    recursive: boolean,
    extensions: string[],
    exclude: string[]
  ): Promise<void> {
    const entries = readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = join(dir, entry.name);

      // 跳过排除目录
      if (exclude.includes(entry.name)) {
        continue;
      }

      if (entry.isDirectory() && recursive) {
        await this.scanDirectoryRecursive(fullPath, recursive, extensions, exclude);
      } else if (entry.isFile()) {
        const ext = extname(entry.name);
        if (extensions.includes(ext)) {
          this.stats.total_files++;
          await this.indexFile(fullPath);
        }
      }
    }
  }

  /**
   * 索引单个文件
   */
  async indexFile(filePath: string): Promise<boolean> {
    try {
      const metadata = await this.extractMetadata(filePath);

      // 检查是否需要更新
      const existing = this.db.prepare(
        'SELECT content_hash FROM smi_files WHERE file_path = ?'
      ).get(metadata.file_path) as { content_hash: string } | undefined;

      if (existing && existing.content_hash === metadata.content_hash) {
        this.stats.skipped++;
        return false;
      }

      // 插入或更新
      const stmt = this.db.prepare(`
        INSERT INTO smi_files (
          file_id, file_path, abs_path, file_type, category, feature, project,
          title, description, tags, size_bytes, line_count, last_modified, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_path) DO UPDATE SET
          abs_path = excluded.abs_path,
          file_type = excluded.file_type,
          category = excluded.category,
          feature = excluded.feature,
          project = excluded.project,
          title = excluded.title,
          description = excluded.description,
          tags = excluded.tags,
          size_bytes = excluded.size_bytes,
          line_count = excluded.line_count,
          last_modified = excluded.last_modified,
          content_hash = excluded.content_hash,
          indexed_at = CURRENT_TIMESTAMP
      `);

      stmt.run(
        metadata.file_id,
        metadata.file_path,
        metadata.abs_path,
        metadata.file_type,
        metadata.category,
        metadata.feature || null,
        metadata.project || null,
        metadata.title || null,
        metadata.description || null,
        metadata.tags ? JSON.stringify(metadata.tags) : null,
        metadata.size_bytes,
        metadata.line_count,
        metadata.last_modified.toISOString(),
        metadata.content_hash
      );

      if (existing) {
        this.stats.updated++;
      } else {
        this.stats.indexed++;
      }

      return true;
    } catch (error) {
      console.error(`Error indexing file ${filePath}:`, error);
      this.stats.errors++;
      return false;
    }
  }

  /**
   * 提取文件元数据
   */
  private async extractMetadata(filePath: string): Promise<FileMetadata> {
    const stat = statSync(filePath);
    const content = readFileSync(filePath, 'utf-8');
    const relPath = relative(this.rootPath, filePath);
    const fileType = extname(filePath).slice(1);

    const metadata: FileMetadata = {
      file_id: this.generateFileId(relPath),
      file_path: relPath,
      abs_path: filePath,
      file_type: fileType,
      category: this.detectCategory(filePath),
      size_bytes: stat.size,
      line_count: content.split('\n').length,
      last_modified: stat.mtime,
      content_hash: this.computeHash(content)
    };

    // 根据文件类型提取特定元数据
    if (fileType === 'md') {
      Object.assign(metadata, this.extractMarkdownMetadata(content, relPath));
    } else if (fileType === 'ts' || fileType === 'js') {
      Object.assign(metadata, this.extractCodeMetadata(content, relPath));
    }

    return metadata;
  }

  /**
   * 提取 Markdown 元数据
   */
  private extractMarkdownMetadata(content: string, filePath: string): Partial<FileMetadata> {
    const result: Partial<FileMetadata> = {};

    // 提取 YAML frontmatter
    const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
    if (frontmatterMatch) {
      const frontmatter = frontmatterMatch[1];
      const nameMatch = frontmatter.match(/name:\s*(.+)/);
      const descMatch = frontmatter.match(/description:\s*(.+)/);

      if (nameMatch) result.title = nameMatch[1].trim();
      if (descMatch) result.description = descMatch[1].trim();
    }

    // 提取第一个 # 标题作为 title
    if (!result.title) {
      const titleMatch = content.match(/^#\s+(.+)/m);
      if (titleMatch) {
        result.title = titleMatch[1].trim();
      }
    }

    // 提取摘要 (第一段文字)
    if (!result.description) {
      const paraMatch = content.match(/^[^#\n>-].+$/m);
      if (paraMatch) {
        result.description = paraMatch[0].trim().slice(0, 200);
      }
    }

    // 检测特性
    result.feature = this.detectFeature(filePath, content);

    // 提取标签
    result.tags = this.extractTags(content);

    return result;
  }

  /**
   * 提取代码文件元数据
   */
  private extractCodeMetadata(content: string, filePath: string): Partial<FileMetadata> {
    const result: Partial<FileMetadata> = {};

    // 提取文件顶部注释作为描述
    const commentMatch = content.match(/^\/\*\*\n([\s\S]*?)\*\//);
    if (commentMatch) {
      const comment = commentMatch[1]
        .split('\n')
        .map(line => line.replace(/^\s*\*\s?/, ''))
        .join(' ')
        .trim();
      result.description = comment.slice(0, 200);
    }

    // 提取 title (从文件路径推断)
    result.title = basename(filePath, extname(filePath));

    // 检测特性
    result.feature = this.detectFeature(filePath, content);

    return result;
  }

  /**
   * 检测文件所属分类
   */
  private detectCategory(filePath: string): string {
    if (filePath.includes('/agents/')) return 'agent';
    if (filePath.includes('/skills/')) return 'skill';
    if (filePath.includes('/rules/')) return 'rule';
    if (filePath.includes('/docs/')) return 'doc';
    if (filePath.includes('/core/')) return 'core';
    if (filePath.includes('/test/') || filePath.includes('.test.')) return 'test';
    if (filePath.includes('/hooks/')) return 'hook';
    return 'unknown';
  }

  /**
   * 检测文件关联的特性
   */
  private detectFeature(filePath: string, content: string): string | undefined {
    // 从路径检测
    const pathFeatures = [
      'capsule', 'backlog', 'ontology', 'smi', 'ree', 'tvs',
      'monitor', 'agent', 'skill', 'benchmark'
    ];

    for (const feature of pathFeatures) {
      if (filePath.toLowerCase().includes(feature)) {
        return feature;
      }
    }

    // 从内容检测
    for (const feature of pathFeatures) {
      const regex = new RegExp(`\\b${feature}\\b`, 'i');
      if (regex.test(content.slice(0, 500))) {
        return feature;
      }
    }

    return undefined;
  }

  /**
   * 提取标签
   */
  private extractTags(content: string): string[] {
    const tags: Set<string> = new Set();

    // 从内容提取关键词
    const keywords = [
      'agent', 'skill', 'rule', 'core', 'test', 'doc',
      'typescript', 'sql', 'markdown', 'performance', 'security'
    ];

    for (const keyword of keywords) {
      if (content.toLowerCase().includes(keyword)) {
        tags.add(keyword);
      }
    }

    return Array.from(tags);
  }

  /**
   * 生成文件 ID
   */
  private generateFileId(filePath: string): string {
    return this.computeHash(filePath).slice(0, 16);
  }

  /**
   * 计算内容哈希
   */
  private computeHash(content: string): string {
    return createHash('sha256').update(content).digest('hex');
  }

  /**
   * 获取统计信息
   */
  getStats(): IndexStats {
    return { ...this.stats };
  }

  /**
   * 关闭数据库
   */
  close(): void {
    this.db.close();
  }
}

// ============================================================
// CLI Support
// ============================================================

if (import.meta.main) {
  const args = process.argv.slice(2);
  const dir = args[0] || process.cwd();

  console.log(`🔍 Scanning directory: ${dir}\n`);

  const indexer = new FileIndexer();
  const stats = await indexer.scanDirectory(dir);

  console.log('\n📊 Indexing Stats:');
  console.log(`  Total files:   ${stats.total_files}`);
  console.log(`  Indexed:       ${stats.indexed}`);
  console.log(`  Updated:       ${stats.updated}`);
  console.log(`  Skipped:       ${stats.skipped}`);
  console.log(`  Errors:        ${stats.errors}`);
  console.log(`  Duration:      ${stats.duration_ms}ms`);

  indexer.close();
}
