#!/usr/bin/env python3
"""
TVS Email Search Server (Python)

Usage:
  python3 server.py

Open: http://localhost:3847
"""

import http.server
import json
import subprocess
import re
import os
from urllib.parse import urlparse, parse_qs

PORT = 3847
MAX_RESULTS = 3

def exec_himalaya(args):
    """Execute himalaya command and return output."""
    try:
        result = subprocess.run(
            ['himalaya'] + args,
            capture_output=True,
            text=True,
            timeout=60
        )
        # Use stdout directly (JSON output goes to stdout)
        output = result.stdout
        print(f"[TVS] himalaya output length: {len(output)}")
        return output
    except Exception as e:
        print(f"[TVS] Error: {e}")
        return ""

def search_emails(keyword):
    """Search emails by keyword."""
    query = f"subject {keyword}"
    output = exec_himalaya([
        'envelope', 'list',
        '--page-size', '10',
        '--output', 'json',
        query
    ])

    # Extract JSON array
    match = re.search(r'\[[\s\S]*\]', output)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    return []

def read_email(email_id):
    """Read email content."""
    output = exec_himalaya(['message', 'read', email_id])

    # Clean up content
    content = re.sub(r'<#part[^>]*>', '', output)
    content = re.sub(r'<#/part>', '', content)
    content = re.sub(r'<[^>]+>', ' ', content)
    content = re.sub(r'\([^)]+\)', '', content)
    content = re.sub(r'\s+', ' ', content).strip()

    return content[:2000]

def generate_summary(content, subject):
    """Generate simple summary from content."""
    sentences = re.split(r'[.。！？!?]', content)
    sentences = [s.strip() for s in sentences if 20 < len(s.strip()) < 200]

    if not sentences:
        return f"Email about: {subject}"

    return '\n'.join([f"• {s}" for s in sentences[:5]])

def handle_search(keyword):
    """Main search handler."""
    print(f"[TVS] Searching: {keyword}")

    envelopes = search_emails(keyword)
    total = len(envelopes)
    print(f"[TVS] Found: {total} emails")

    emails_with_summary = []
    for envelope in envelopes[:MAX_RESULTS]:
        print(f"[TVS] Reading: {envelope.get('id')} - {envelope.get('subject', '')[:40]}")

        body = read_email(envelope['id'])
        summary = generate_summary(body, envelope.get('subject', ''))

        emails_with_summary.append({
            **envelope,
            'summary': summary,
            'body': body[:500]
        })

    return {
        'total': total,
        'keyword': keyword,
        'emails': emails_with_summary
    }

class TVSHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == '/health':
            self.send_json({'status': 'ok', 'version': 'TVS v0.3.0'})

        elif path == '/search':
            keyword = query.get('keyword', [''])[0]
            if not keyword:
                self.send_json({'error': 'Missing keyword'}, 400)
            else:
                try:
                    result = handle_search(keyword)
                    self.send_json(result)
                except Exception as e:
                    self.send_json({'error': str(e)}, 500)

        elif path == '/' or path == '/index.html':
            self.serve_file('index.html', 'text/html')

        else:
            self.send_error(404)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def serve_file(self, filename, content_type):
        try:
            filepath = os.path.join(os.path.dirname(__file__), filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            self.wfile.write(content.encode())
        except:
            self.send_error(500)

    def log_message(self, format, *args):
        print(f"[TVS] {args[0]}")

def main():
    print(f"""
┌─────────────────────────────────────────────────────────────┐
│                 TVS EMAIL SEARCH SERVER                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Status     RUNNING                                         │
│  Port       {PORT}                                            │
│  URL        http://localhost:{PORT}                           │
│                                                             │
│  Endpoints:                                                 │
│    GET /              Web interface                         │
│    GET /search        Search emails                         │
│    GET /health        Health check                          │
│                                                             │
└───────────────────────────── [solar-dark] Powered by TVS v0.3.0 ─┘
""")

    server = http.server.HTTPServer(('', PORT), TVSHandler)
    server.serve_forever()

if __name__ == '__main__':
    main()
