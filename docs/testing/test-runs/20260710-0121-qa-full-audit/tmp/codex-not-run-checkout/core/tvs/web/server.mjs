/**
 * TVS Email Search Server (Node.js)
 *
 * Usage:
 *   node server.mjs
 *
 * Endpoints:
 *   GET /              Web interface
 *   GET /search        Search emails
 *   GET /health        Health check
 */

import { createServer } from 'http';
import { readFileSync } from 'fs';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 3847;
const MAX_RESULTS = 3;

// Execute himalaya command
function execHimalaya(args) {
  return new Promise((resolve, reject) => {
    const proc = spawn('himalaya', args, {
      env: { ...process.env, TERM: 'dumb' }
    });
    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      // Combine all output and filter warning lines
      const allOutput = stdout + stderr;
      const cleanOutput = allOutput
        .split('\n')
        .filter(line => !line.includes('WARN') && !line.includes('[2m'))
        .join('\n');
      console.log('[TVS] himalaya output:', cleanOutput.slice(0, 200));
      resolve(cleanOutput);
    });

    proc.on('error', (err) => {
      console.error('[TVS] himalaya error:', err);
      reject(err);
    });
  });
}

// Search emails by keyword
async function searchEmails(keyword) {
  const query = `subject ${keyword} or body ${keyword}`;
  const output = await execHimalaya([
    'envelope', 'list',
    '--page-size', '10',
    '--output', 'json',
    query
  ]);

  try {
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
async function readEmail(id) {
  const output = await execHimalaya(['message', 'read', id]);

  let content = output
    .replace(/<#part[^>]*>/g, '')
    .replace(/<#\/part>/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\([^)]+\)/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  if (content.length > 2000) {
    content = content.slice(0, 2000) + '...';
  }

  return content;
}

// Generate summary from email content
function generateSummary(content, subject) {
  const sentences = content
    .split(/[.。！？!?]/)
    .map(s => s.trim())
    .filter(s => s.length > 20 && s.length < 200);

  const summaryPoints = sentences.slice(0, 5);

  if (summaryPoints.length === 0) {
    return `Email about: ${subject}`;
  }

  return summaryPoints.map(p => `• ${p}`).join('\n');
}

// Main search handler
async function handleSearch(keyword) {
  console.log(`[TVS] Searching for: ${keyword}`);

  const envelopes = await searchEmails(keyword);
  const total = envelopes.length;

  console.log(`[TVS] Found ${total} emails`);

  const topEmails = envelopes.slice(0, MAX_RESULTS);
  const emailsWithSummary = [];

  for (const envelope of topEmails) {
    console.log(`[TVS] Reading email ${envelope.id}: ${envelope.subject}`);

    const body = await readEmail(envelope.id);
    const summary = generateSummary(body, envelope.subject);

    emailsWithSummary.push({
      ...envelope,
      summary,
      body: body.slice(0, 500)
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
const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;

  // Set CORS headers
  Object.entries(corsHeaders).forEach(([key, value]) => {
    res.setHeader(key, value);
  });

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  // Health check
  if (path === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', version: 'TVS v0.3.0' }));
    return;
  }

  // Search endpoint
  if (path === '/search') {
    const keyword = url.searchParams.get('keyword');

    if (!keyword) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Missing keyword parameter' }));
      return;
    }

    try {
      const result = await handleSearch(keyword);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
    } catch (e) {
      console.error('[TVS] Search error:', e);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: `Search failed: ${e}` }));
    }
    return;
  }

  // Serve static files
  if (path === '/' || path === '/index.html') {
    try {
      const html = readFileSync(join(__dirname, 'index.html'), 'utf-8');
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    } catch (e) {
      res.writeHead(500);
      res.end('Failed to load index.html');
    }
    return;
  }

  res.writeHead(404);
  res.end('Not Found');
});

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

server.listen(PORT);
