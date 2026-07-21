#!/usr/bin/env python3
"""
Playwright-based DOM extractor for Twitter profiles.
Extracts the innerText, published date, status URLs, and pinned hint from
directly visible <article> elements. Output is already recency-sorted to bias
towards the latest profile activity instead of historical highlights.
"""

import sys
import json
import asyncio
from playwright.async_api import async_playwright
from datetime import datetime, timezone
from urllib.parse import quote


def build_live_search_url(handle: str, since_date: str) -> str:
    query = f"(from:{handle}) since:{since_date}"
    return f"https://x.com/search?q={quote(query)}&src=typed_query&f=live"


async def extract_articles(page):
    tweets = await page.evaluate(r'''() => {
        return Array.from(document.querySelectorAll('article')).map(article => {
            const text = article.innerText;
            const statusLinks = Array.from(article.querySelectorAll('a'))
                .map(a => a.href)
                .filter(href => href.includes('/status/'));
            const url = statusLinks.length > 0 ? statusLinks[0] : "";

            const timeEl = article.querySelector('time');
            const published_at = timeEl ? timeEl.getAttribute('datetime') : "";
            const socialContext = article.querySelector('[data-testid="socialContext"]');
            const socialContextText = socialContext ? (socialContext.innerText || "") : "";
            const isPinned = /^\s*pinned\b/i.test(text) || /\bpinned\b/i.test(socialContextText);

            const allLinks = Array.from(article.querySelectorAll('a')).map(a => a.href);
            const externalLinks = Array.from(new Set(allLinks.filter(href => {
                if (!href.startsWith('http')) return false;
                try {
                    const urlObj = new URL(href);
                    return !urlObj.hostname.includes('twitter.com') && !urlObj.hostname.includes('x.com');
                } catch (e) {
                    return false;
                }
            })));

            return { text: text, tweet_url: url, published_at: published_at, external_links: externalLinks, is_pinned: isPinned };
        });
    }''')

    now_iso = datetime.now(timezone.utc).isoformat()
    for t in tweets:
        if not t["published_at"]:
            t["published_at"] = now_iso
    tweets.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return tweets


async def load_recent_search(page, handle: str, since_date: str, max_scrolls: int):
    url = build_live_search_url(handle, since_date)
    await page.goto(url, timeout=25000)
    await page.wait_for_selector("article", timeout=15000)
    await page.wait_for_timeout(2000)
    for _ in range(max_scrolls):
        await page.keyboard.press("PageDown")
        await page.wait_for_timeout(1500)
    return await extract_articles(page)


async def load_profile_fallback(page, handle: str, max_scrolls: int):
    await page.goto(f"https://x.com/{handle}", timeout=20000)
    await page.wait_for_selector("article", timeout=15000)
    await page.wait_for_timeout(2000)
    for _ in range(max_scrolls):
        await page.keyboard.press("PageDown")
        await page.keyboard.press("PageDown")
        await page.wait_for_timeout(2000)
    return await extract_articles(page)

async def run(handle: str, max_scrolls: int, since_date: str | None = None, limit: int = 8):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            tweets = []
            search_error = None
            if since_date:
                try:
                    tweets = await load_recent_search(page, handle, since_date, max_scrolls)
                except Exception as exc:
                    search_error = str(exc)
            if not tweets:
                tweets = await load_profile_fallback(page, handle, max_scrolls)
        except Exception as e:
            await browser.close()
            extra = f" | recent_search={search_error}" if 'search_error' in locals() and search_error else ""
            print(json.dumps({"error": f"Failed to load or find articles: {e}{extra}"}))
            return

        await browser.close()
        print(json.dumps({"result": tweets[:max(1, limit)]}))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("handle", help="Twitter handle")
    parser.add_argument("--scrolls", type=int, default=0, help="Number of times to scroll down")
    parser.add_argument("--since-date", default=None, help="Prefer tweets newer than YYYY-MM-DD via Live search")
    parser.add_argument("--limit", type=int, default=8, help="Maximum number of tweets to return")
    args = parser.parse_args()

    asyncio.run(run(args.handle, args.scrolls, since_date=args.since_date, limit=args.limit))
