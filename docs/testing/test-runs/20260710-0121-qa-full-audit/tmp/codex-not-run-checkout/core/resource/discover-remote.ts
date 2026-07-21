/**
 * Solar Resource Discovery: 远程资源搜索
 * 搜索 API、MCP、云服务等远程资源
 */

import Database from 'bun:sqlite';

const DB_PATH = process.env.SOLAR_DB_PATH || `${process.env.HOME}/.solar/db/solar.db`;

interface DiscoveredResource {
  name: string;
  description: string;
  category: string;
  sourceType: string;
  sourceUrl: string;
  relevanceScore: number;
  costEstimate: string;
}

interface SearchSource {
  name: string;
  type: string;
  searchFn: (query: string) => Promise<DiscoveredResource[]>;
}

//------------------------------------------------------------------------------
// 搜索源定义
//------------------------------------------------------------------------------

const SEARCH_SOURCES: SearchSource[] = [
  {
    name: 'Public APIs',
    type: 'api_directory',
    searchFn: searchPublicAPIs,
  },
  {
    name: 'MCP Registry',
    type: 'mcp_registry',
    searchFn: searchMCPRegistry,
  },
  {
    name: 'GitHub',
    type: 'github',
    searchFn: searchGitHub,
  },
  {
    name: 'Web Search',
    type: 'web_search',
    searchFn: searchWeb,
  },
];

//------------------------------------------------------------------------------
// Public APIs 搜索 (api.publicapis.org)
//------------------------------------------------------------------------------

async function searchPublicAPIs(query: string): Promise<DiscoveredResource[]> {
  try {
    const resp = await fetch(
      `https://api.publicapis.org/entries?title=${encodeURIComponent(query)}&https=true`,
      { signal: AbortSignal.timeout(5000) }
    );

    if (!resp.ok) return [];

    const data = await resp.json();
    const entries = data.entries || [];

    return entries.slice(0, 10).map((entry: any) => ({
      name: entry.API,
      description: entry.Description,
      category: 'api',
      sourceType: 'api_directory',
      sourceUrl: entry.Link,
      relevanceScore: 0.8,
      costEstimate: entry.Auth ? 'freemium' : 'free',
    }));
  } catch (e) {
    console.error('Public APIs search failed:', e);
    return [];
  }
}

//------------------------------------------------------------------------------
// MCP Registry 搜索
//------------------------------------------------------------------------------

async function searchMCPRegistry(query: string): Promise<DiscoveredResource[]> {
  // MCP 官方和社区资源
  const MCP_SOURCES = [
    {
      name: 'modelcontextprotocol/servers',
      url: 'https://api.github.com/repos/modelcontextprotocol/servers/contents/src',
    },
  ];

  const results: DiscoveredResource[] = [];

  for (const source of MCP_SOURCES) {
    try {
      const resp = await fetch(source.url, {
        headers: { Accept: 'application/vnd.github.v3+json' },
        signal: AbortSignal.timeout(5000),
      });

      if (!resp.ok) continue;

      const items = await resp.json();
      const queryLower = query.toLowerCase();

      for (const item of items) {
        if (item.type === 'dir' && item.name.toLowerCase().includes(queryLower)) {
          results.push({
            name: `mcp-${item.name}`,
            description: `MCP Server: ${item.name}`,
            category: 'mcp',
            sourceType: 'mcp_registry',
            sourceUrl: item.html_url,
            relevanceScore: 0.9,
            costEstimate: 'free',
          });
        }
      }
    } catch (e) {
      console.error('MCP Registry search failed:', e);
    }
  }

  return results;
}

//------------------------------------------------------------------------------
// GitHub 搜索
//------------------------------------------------------------------------------

async function searchGitHub(query: string): Promise<DiscoveredResource[]> {
  try {
    // 搜索相关工具和库
    const searchQuery = `${query} tool OR api OR cli in:name,description`;
    const resp = await fetch(
      `https://api.github.com/search/repositories?q=${encodeURIComponent(searchQuery)}&sort=stars&per_page=10`,
      {
        headers: { Accept: 'application/vnd.github.v3+json' },
        signal: AbortSignal.timeout(5000),
      }
    );

    if (!resp.ok) return [];

    const data = await resp.json();
    const items = data.items || [];

    return items.map((repo: any) => ({
      name: repo.name,
      description: repo.description || `GitHub: ${repo.full_name}`,
      category: 'tool',
      sourceType: 'github',
      sourceUrl: repo.html_url,
      relevanceScore: Math.min(0.5 + repo.stargazers_count / 10000, 0.95),
      costEstimate: 'free',
    }));
  } catch (e) {
    console.error('GitHub search failed:', e);
    return [];
  }
}

//------------------------------------------------------------------------------
// Web 搜索 (使用 DuckDuckGo)
//------------------------------------------------------------------------------

async function searchWeb(query: string): Promise<DiscoveredResource[]> {
  try {
    // DuckDuckGo Instant Answer API
    const resp = await fetch(
      `https://api.duckduckgo.com/?q=${encodeURIComponent(query + ' API')}&format=json&no_html=1`,
      { signal: AbortSignal.timeout(5000) }
    );

    if (!resp.ok) return [];

    const data = await resp.json();
    const results: DiscoveredResource[] = [];

    // Related topics
    for (const topic of data.RelatedTopics?.slice(0, 5) || []) {
      if (topic.FirstURL && topic.Text) {
        results.push({
          name: topic.Text.slice(0, 50),
          description: topic.Text,
          category: 'unknown',
          sourceType: 'web_search',
          sourceUrl: topic.FirstURL,
          relevanceScore: 0.6,
          costEstimate: 'unknown',
        });
      }
    }

    return results;
  } catch (e) {
    console.error('Web search failed:', e);
    return [];
  }
}

//------------------------------------------------------------------------------
// 主搜索函数
//------------------------------------------------------------------------------

export async function discoverResources(
  intent: string,
  options: { sources?: string[]; maxResults?: number } = {}
): Promise<DiscoveredResource[]> {
  const { sources = ['api_directory', 'mcp_registry', 'github'], maxResults = 20 } = options;

  const db = new Database(DB_PATH);
  const allResults: DiscoveredResource[] = [];

  console.log(`🔍 搜索资源: "${intent}"`);

  // 记录搜索
  const searchId = Date.now();

  // 并行搜索所有源
  const searchPromises = SEARCH_SOURCES
    .filter(s => sources.includes(s.type))
    .map(async source => {
      console.log(`  → 搜索 ${source.name}...`);
      try {
        const results = await source.searchFn(intent);
        console.log(`    ✓ ${source.name}: ${results.length} 结果`);
        return results;
      } catch (e) {
        console.log(`    ✗ ${source.name}: 失败`);
        return [];
      }
    });

  const searchResults = await Promise.all(searchPromises);

  // 合并结果
  for (const results of searchResults) {
    allResults.push(...results);
  }

  // 按相关度排序
  allResults.sort((a, b) => b.relevanceScore - a.relevanceScore);

  // 取前 N 个
  const topResults = allResults.slice(0, maxResults);

  // 写入发现表
  for (const result of topResults) {
    db.run(
      `INSERT INTO sys_resource_discoveries (
        search_query, source_type, source_url, name, description, category,
        relevance_score, cost_estimate, status
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'discovered')`,
      [
        intent,
        result.sourceType,
        result.sourceUrl,
        result.name,
        result.description,
        result.category,
        result.relevanceScore,
        result.costEstimate,
      ]
    );
  }

  // 记录搜索日志
  db.run(
    `INSERT INTO sys_resource_search_log (
      user_intent, search_query, search_source, results_count, action_taken
    ) VALUES (?, ?, ?, ?, ?)`,
    [
      intent,
      intent,
      sources.join(','),
      topResults.length,
      topResults.length > 0 ? 'discovered_new' : 'no_match',
    ]
  );

  db.close();

  console.log(`\n✅ 发现 ${topResults.length} 个资源`);

  return topResults;
}

//------------------------------------------------------------------------------
// 采纳资源
//------------------------------------------------------------------------------

export function adoptResource(discoveryId: number, resourceId: string): void {
  const db = new Database(DB_PATH);

  // 获取发现的资源信息
  const discovery = db.query(
    `SELECT * FROM sys_resource_discoveries WHERE id = ?`
  ).get(discoveryId) as any;

  if (!discovery) {
    console.error('Discovery not found:', discoveryId);
    db.close();
    return;
  }

  // 添加到正式资源表
  db.run(
    `INSERT OR REPLACE INTO sys_resources (
      resource_id, layer, category, name, description,
      executor, cost_type, availability, source, last_verified
    ) VALUES (?, 'remote', ?, ?, ?, 'shell', ?, 'needs_setup', 'search', datetime('now'))`,
    [
      resourceId,
      discovery.category,
      discovery.name,
      discovery.description,
      discovery.cost_estimate,
    ]
  );

  // 更新发现记录状态
  db.run(
    `UPDATE sys_resource_discoveries SET status = 'adopted', adopted_as = ?, evaluated_at = datetime('now') WHERE id = ?`,
    [resourceId, discoveryId]
  );

  console.log(`✅ 已采纳资源: ${resourceId}`);

  db.close();
}

//------------------------------------------------------------------------------
// CLI
//------------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  switch (command) {
    case 'search':
      const query = args.slice(1).join(' ');
      if (!query) {
        console.log('Usage: discover-remote.ts search <query>');
        process.exit(1);
      }
      const results = await discoverResources(query);
      console.log('\n📋 发现的资源:');
      for (const r of results) {
        console.log(`  [${r.category}] ${r.name}`);
        console.log(`    ${r.description}`);
        console.log(`    源: ${r.sourceType} | 成本: ${r.costEstimate}`);
        console.log('');
      }
      break;

    case 'adopt':
      const id = parseInt(args[1]);
      const resId = args[2];
      if (!id || !resId) {
        console.log('Usage: discover-remote.ts adopt <discovery_id> <resource_id>');
        process.exit(1);
      }
      adoptResource(id, resId);
      break;

    case 'gaps':
      const db = new Database(DB_PATH);
      const gaps = db.query(`SELECT * FROM v_capability_gaps LIMIT 10`).all();
      console.log('📊 能力缺口 (用户需要但没有的):');
      for (const gap of gaps as any[]) {
        console.log(`  • "${gap.user_intent}" - 请求 ${gap.request_count} 次`);
      }
      db.close();
      break;

    default:
      console.log('Solar Remote Resource Discovery');
      console.log('');
      console.log('Commands:');
      console.log('  search <query>               搜索远程资源');
      console.log('  adopt <id> <resource_id>     采纳发现的资源');
      console.log('  gaps                         查看能力缺口');
  }
}

main().catch(console.error);
