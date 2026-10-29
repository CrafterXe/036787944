"""联网搜索。后端：必应（requests 解析 HTML，国内可访问，零额外依赖）。
任何失败返回 []，自动降级为仅用原文，不影响生成。

如要切换其他后端（SearXNG/ddgs），只需改 web_search 内部，保持返回格式不变。
"""
import re
import urllib.parse
import logging
import requests
import config

_log = logging.getLogger("app.core.search")

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _bing_search(query, max_results):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({
        "q": query, "setlang": "zh-CN", "ensearch": "0",
    })
    resp = requests.get(url, headers=_HEADERS, timeout=config.SEARCH_TIMEOUT)
    resp.raise_for_status()
    html = resp.text

    results = []
    # 必应结果块：<li class="b_algo"> ... <h2><a href="URL">TITLE</a></h2> ... <p>SNIPPET</p>
    for block in re.findall(r'<li class="b_algo"[\s\S]*?</li>', html):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', block)
        if not m:
            continue
        link = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        sm = re.search(r'<p[^>]*>([\s\S]*?)</p>', block)
        snippet = re.sub(r"<[^>]+>", "", sm.group(1)).strip() if sm else ""
        if link and title:
            results.append({"title": title, "url": link, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def web_search(query, max_results=None):
    """联网搜索，返回 [{title,url,snippet}]。任何失败返回 []。"""
    if not config.ENABLE_WEB_SEARCH:
        return []
    max_results = max_results or config.SEARCH_MAX_RESULTS
    try:
        return _bing_search(query, max_results)
    except Exception:
        _log.exception("搜索失败，降级仅用原文")
        return []


def format_web_block(results):
    """把搜索结果格式化为注入 prompt 的文本块。"""
    if not results:
        return ""
    lines = ["【网络参考资料】（联网补充，仅供参考，以课程内容为准）："]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']} — {r['snippet']}")
    return "\n".join(lines)
