#!/usr/bin/env python3
"""
Solar Shortcut Search
从互联网搜索并下载 Apple Shortcuts
"""

import json
import subprocess
import sys
import re
import urllib.parse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class ShortcutResult:
    name: str
    description: str
    source: str
    url: str
    download_url: Optional[str] = None
    rating: Optional[float] = None
    downloads: Optional[int] = None
    author: Optional[str] = None
    updated: Optional[str] = None

def search_web(query: str, limit: int = 5) -> List[ShortcutResult]:
    """使用 Web 搜索查找 Shortcuts"""
    results = []

    # 构建搜索查询
    search_query = f'site:routinehub.co OR site:icloud.com/shortcuts "{query}" shortcut'

    # 使用 ddgr (DuckDuckGo CLI) 或 curl + 解析
    try:
        # 尝试使用 Web 搜索 API
        encoded_query = urllib.parse.quote(search_query)

        # 模拟搜索结果 (实际实现需要调用搜索 API)
        # 这里我们直接构造一些常见来源的搜索 URL

        search_urls = [
            f"https://routinehub.co/search/?q={urllib.parse.quote(query)}",
            f"https://shortcutsgallery.com/search/?q={urllib.parse.quote(query)}",
        ]

        print(f"[Solar] Searching for: {query}")
        print(f"[Solar] Search URLs: {search_urls[0]}")

    except Exception as e:
        print(f"[Solar] Search error: {e}")

    return results

def search_routinehub(query: str, limit: int = 5) -> List[ShortcutResult]:
    """搜索 RoutineHub"""
    results = []

    try:
        # RoutineHub 搜索页面
        url = f"https://routinehub.co/search/?q={urllib.parse.quote(query)}"

        # 使用 curl 获取页面
        result = subprocess.run(
            ["curl", "-s", "-L", url,
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             "-H", "Accept: text/html"],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0:
            html = result.stdout

            # 尝试多种模式匹配
            # 模式1: href="/shortcut/123/..."
            pattern1 = r'href="(/shortcut/\d+[^"]*)"[^>]*>\s*([^<]+)'
            matches = re.findall(pattern1, html)

            # 模式2: 查找标题
            pattern2 = r'class="[^"]*title[^"]*"[^>]*>([^<]+)</'
            titles = re.findall(pattern2, html)

            for i, (path, name) in enumerate(matches[:limit]):
                clean_name = name.strip()
                if clean_name and len(clean_name) > 2 and not clean_name.startswith(('<', '{')):
                    base_path = path.split('/')[0:3]
                    clean_path = '/'.join(base_path) if len(base_path) >= 3 else path
                    results.append(ShortcutResult(
                        name=clean_name[:50],
                        description="",
                        source="RoutineHub",
                        url=f"https://routinehub.co{clean_path}",
                        download_url=f"https://routinehub.co{clean_path}"
                    ))

        # 如果没找到结果，添加直接搜索链接
        if not results:
            results.append(ShortcutResult(
                name=f"Search '{query}' on RoutineHub",
                description="Open RoutineHub to search manually",
                source="RoutineHub",
                url=url,
                download_url=None
            ))

    except Exception as e:
        print(f"[Solar] RoutineHub search error: {e}")

    return results

def search_icloud_links(query: str) -> List[ShortcutResult]:
    """搜索 iCloud Shortcuts 链接"""
    results = []

    # 使用 DuckDuckGo 搜索 iCloud 链接
    search_url = f"https://duckduckgo.com/html/?q=site:icloud.com/shortcuts+{urllib.parse.quote(query)}"

    try:
        result = subprocess.run(
            ["curl", "-s", "-L", search_url, "-A", "Mozilla/5.0"],
            capture_output=True,
            text=True,
            timeout=15
        )

        if result.returncode == 0:
            # 提取 iCloud 链接
            pattern = r'https://www\.icloud\.com/shortcuts/[a-f0-9]+'
            matches = re.findall(pattern, result.stdout)

            for url in list(set(matches))[:5]:
                results.append(ShortcutResult(
                    name=f"iCloud Shortcut",
                    description="Direct iCloud link",
                    source="iCloud",
                    url=url,
                    download_url=url
                ))

    except Exception as e:
        print(f"[Solar] iCloud search error: {e}")

    return results

def format_results(results: List[ShortcutResult], query: str) -> str:
    """格式化搜索结果"""
    output = []
    output.append("┌─────────────────────────────────────────────────────────────┐")
    output.append(f"│              🔍 SHORTCUT SEARCH: \"{query[:30]}\"" + " " * (25 - len(query[:30])) + "│")
    output.append("├─────────────────────────────────────────────────────────────┤")
    output.append("│                                                             │")

    if not results:
        output.append("│  No shortcuts found. Try different keywords.               │")
        output.append("│                                                             │")
        output.append("│  Suggestions:                                               │")
        output.append("│  • Use English keywords                                     │")
        output.append("│  • Try broader terms                                        │")
        output.append("│  • Check routinehub.co manually                             │")
    else:
        output.append(f"│  Found {len(results)} shortcuts                                          │")
        output.append("│                                                             │")

        for i, r in enumerate(results, 1):
            name_display = r.name[:45] if len(r.name) > 45 else r.name
            output.append(f"│  {i}. {name_display:<53} │")
            output.append(f"│     Source: {r.source:<45} │")
            if r.rating:
                stars = "⭐" * int(r.rating)
                output.append(f"│     Rating: {stars} ({r.rating})                              │")
            if r.downloads:
                output.append(f"│     Downloads: {r.downloads:,}                                    │")
            output.append(f"│     URL: {r.url[:48]:<48} │")
            output.append("│                                                             │")

    output.append("│  Commands:                                                  │")
    output.append("│  • Enter number (1-5) to install                            │")
    output.append("│  • 'o <n>' to open in browser                               │")
    output.append("│  • 'q' to quit                                              │")
    output.append("│                                                             │")
    output.append("└───────────────────────────── [solar-dark] Powered by Solar ─┘")

    return "\n".join(output)

def install_shortcut(result: ShortcutResult) -> bool:
    """安装快捷指令"""
    url = result.download_url or result.url

    print(f"\n📥 Installing: {result.name}")
    print(f"   Source: {result.source}")
    print(f"   URL: {url}")

    # 如果是 iCloud 链接，直接打开
    if "icloud.com/shortcuts" in url:
        print("\n   Opening iCloud link in Shortcuts.app...")
        subprocess.run(["open", url])
        return True

    # 如果是 RoutineHub，打开下载页面
    if "routinehub.co" in url:
        print("\n   Opening RoutineHub page...")
        # 打开页面让用户点击下载
        subprocess.run(["open", result.url])
        return True

    # 其他情况尝试直接打开
    subprocess.run(["open", url])
    return True

def open_in_browser(result: ShortcutResult):
    """在浏览器中打开"""
    subprocess.run(["open", result.url])

def main():
    if len(sys.argv) < 2:
        print("Usage: shortcut-search.py <query> [--limit N] [--source SOURCE]")
        print("")
        print("Examples:")
        print("  shortcut-search.py weather")
        print("  shortcut-search.py 'morning routine' --limit 10")
        print("  shortcut-search.py productivity --source routinehub")
        sys.exit(1)

    query = sys.argv[1]
    limit = 5

    # 解析参数
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    print(f"\n🔍 Searching for shortcuts: \"{query}\"...\n")

    # 并行搜索多个来源
    all_results = []

    # 搜索 RoutineHub
    routinehub_results = search_routinehub(query, limit)
    all_results.extend(routinehub_results)

    # 搜索 iCloud 链接
    icloud_results = search_icloud_links(query)
    all_results.extend(icloud_results)

    # 去重
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            unique_results.append(r)

    # 限制结果数量
    unique_results = unique_results[:limit]

    # 显示结果
    print(format_results(unique_results, query))

    # 交互式选择
    if unique_results:
        while True:
            try:
                choice = input("\n> ").strip().lower()

                if choice == 'q':
                    print("Bye!")
                    break

                if choice.startswith('o '):
                    # 在浏览器中打开
                    num = int(choice[2:]) - 1
                    if 0 <= num < len(unique_results):
                        open_in_browser(unique_results[num])
                    continue

                # 安装
                num = int(choice) - 1
                if 0 <= num < len(unique_results):
                    install_shortcut(unique_results[num])
                    break
                else:
                    print("Invalid number. Try again.")

            except ValueError:
                print("Enter a number or 'q' to quit.")
            except KeyboardInterrupt:
                print("\nBye!")
                break

if __name__ == "__main__":
    main()
