# -*- coding: utf-8 -*-
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def run_task():
    script_dir = Path(__file__).resolve().parent
    screenshots_dir = script_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    headless = os.environ.get("BROWSER_AGENT_HEADLESS", "true").lower() == "true"
    print(f"[Fallback Playwright] Launching browser (headless={headless})...", flush=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        target_url = "https://example.com"
        print(f"[Fallback Playwright] Navigating to {target_url}...", flush=True)
        await page.goto(target_url, wait_until="domcontentloaded")
        
        print("[Fallback Playwright] Waiting 5 seconds...", flush=True)
        await page.wait_for_timeout(5000)
        
        # Take screenshot
        screenshot_path = screenshots_dir / "page_screenshot.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"[Fallback Playwright] Screenshot saved to {screenshot_path}", flush=True)
        
        # Capture title
        title = await page.title()
        url_curr = page.url
        print(f"[Fallback Playwright] Title: {title}", flush=True)
        print(f"[Fallback Playwright] URL: {url_curr}", flush=True)
        
        await browser.close()
        print("[Fallback Playwright] Done.", flush=True)

if __name__ == "__main__":
    asyncio.run(run_task())
