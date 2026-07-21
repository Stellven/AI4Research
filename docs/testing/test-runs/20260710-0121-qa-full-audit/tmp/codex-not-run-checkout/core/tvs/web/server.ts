/**
 * TVS Email Search Server
 *
 * A simple Bun server that provides email search API using himalaya CLI.
 *
 * Usage:
 *   bun run server.ts
 *
 * Endpoints:
 *   GET /search?keyword=<keyword>  - Search emails and return summaries
 *   GET /health                    - Health check
 */

const PORT = 3847;
const MAX_RESULTS = 3;

interface EmailEnvelope {
  id: string;
  flags: string[];
  subject: string;
  from: { name: string | null; addr: string };
  to: { name: string | null; addr: string };
  date: string;
  has_attachment: boolean;
}

interface EmailWithSummary extends EmailEnvelope {
  summary?: string;
  body?: string;
}

interface SearchResult {
  total: number;
  keyword: string;
  emails: EmailWithSummary[];
}

// Execute himalaya command
async function execHimalaya(args: string[]): Promise<string> {
  const proc = Bun.spawn(['himalaya', ...args], {
    stdout: 'pipe',
    stderr: 'pipe',
  });

  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();

  await proc.exited;

  // Filter out warning messages
  const cleanOutput = stdout
    .split('\n')
    .filter(line => !line.startsWith('['))
    .join('\n');

  return cleanOutput;
}

// Search emails by keyword
async function searchEmails(keyword: string): Promise<EmailEnvelope[]> {
  const query = `subject ${keyword} or body ${keyword}`;
  const output = await execHimalaya([
    'envelope', 'list',
    '--page-size', '10',
    '--output', 'json',
    query
  ]);

  try {
    // Find JSON array in output
    const jsonMatch = output.match(/\[[\s\S]*\]/);
    if (jsonMatch) {
      return JSON.parse(jsonMatch[0]);
    }
    return [];
  } catch (e) {
    console.error('Failed to parse email list:', e);
    return [];
  }
}

// Read email content
async function readEmail(id: string): Promise<string> {
  const output = await execHimalaya(['message', 'read', id]);

  // Extract text content, skip HTML tags
  let content = output
    .replace(/<#part[^>]*>/g, '')
    .replace(/<#\/part>/g, '')
    .replace(/<[^>]+>/g, ' ')  // Remove HTML tags
    .replace(/\([^)]+\)/g, '') // Remove URLs in parentheses
    .replace(/\s+/g, ' ')      // Normalize whitespace
    .trim();

  // Limit content length
  if (content.length > 2000) {
    content = content.slice(0, 2000) + '...';
  }

  return content;
}

// Generate summary from email content
function generateSummary(content: string, subject: string): string {
  // Simple extractive summary - get key sentences
  const sentences = content
    .split(/[.。！？!?]/)
    .map(s => s.trim())
    .filter(s => s.length > 20 && s.length < 200);

  // Get first few meaningful sentences
  const summaryPoints = sentences.slice(0, 5);

  if (summaryPoints.length === 0) {
    return `Email about: ${subject}`;
  }

  return summaryPoints.map(p => `• ${p}`).join('\n');
}

// Main search handler
async function handleSearch(keyword: string): Promise<SearchResult> {
  console.log(`[TVS] Searching for: ${keyword}`);

  // Search emails
  const envelopes = await searchEmails(keyword);
  const total = envelopes.length;

  console.log(`[TVS] Found ${total} emails`);

  // Get top N emails with content
  const topEmails = envelopes.slice(0, MAX_RESULTS);
  const emailsWithSummary: EmailWithSummary[] = [];

  for (const envelope of topEmails) {
    console.log(`[TVS] Reading email ${envelope.id}: ${envelope.subject}`);

    const body = await readEmail(envelope.id);
    const summary = generateSummary(body, envelope.subject);

    emailsWithSummary.push({
      ...envelope,
      summary,
      body: body.slice(0, 500) // Include partial body
    });
  }

  return {
    total,
    keyword,
    emails: emailsWithSummary
  };
}

// CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

// Request handler
async function handleRequest(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const path = url.pathname;

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  // Health check
  if (path === '/health') {
    return Response.json({ status: 'ok', version: 'TVS v0.3.0' }, { headers: corsHeaders });
  }

  // Search endpoint
  if (path === '/search') {
    const keyword = url.searchParams.get('keyword');

    if (!keyword) {
      return Response.json(
        { error: 'Missing keyword parameter' },
        { status: 400, headers: corsHeaders }
      );
    }

    try {
      const result = await handleSearch(keyword);
      return Response.json(result, { headers: corsHeaders });
    } catch (e) {
      console.error('[TVS] Search error:', e);
      return Response.json(
        { error: `Search failed: ${e}` },
        { status: 500, headers: corsHeaders }
      );
    }
  }

  // Serve static files
  if (path === '/' || path === '/index.html') {
    const file = Bun.file(import.meta.dir + '/index.html');
    return new Response(file, {
      headers: { 'Content-Type': 'text/html' }
    });
  }

  return new Response('Not Found', { status: 404 });
}

// Start server
console.log(`
┌─────────────────────────────────────────────────────────────┐
│                 TVS EMAIL SEARCH SERVER                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Status     RUNNING                                         │
│  Port       ${PORT}                                            │
│  URL        http://localhost:${PORT}                           │
│                                                             │
│  Endpoints:                                                 │
│    GET /              Web interface                         │
│    GET /search        Search emails                         │
│    GET /health        Health check                          │
│                                                             │
└───────────────────────────── [solar-dark] Powered by TVS v0.3.0 ─┘
`);

Bun.serve({
  port: PORT,
  fetch: handleRequest,
});
