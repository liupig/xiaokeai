"""带浏览器请求头，合并必应、360、谷歌的目录，再打开排在前面的一页。

不查百度，不查搜狗。检索词用模型写在 [lookup:] 里的原词，这里不改写。
"""
from __future__ import annotations

import base64
import html
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

import httpx

_TIMEOUT = 8.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-CH-UA": '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
}
_BARE = {
    "还有", "吗", "呢", "啊", "呀", "最新", "状况", "情况", "进展", "动态",
    "这个", "那个", "什么", "一下", "钉住", "然后", "继续", "看看", "知道",
}
_SKIP_HOST = (
    "bing.com",
    "microsoft.com",
    "baidu.com",
    "sogou.com",
    "google.",
    "gstatic.com",
    "googleusercontent.com",
    "wikipedia.org",
    "wiktionary.org",
    "baike.com",
    "360tres.com",
    "schema.org",
    "w3.org",
)


def _clean(text: str, limit: int) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _public(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False
    host = parts.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _skip(url: str) -> bool:
    if not _public(url):
        return True
    host = _host(url)
    if host == "www.so.com" and not urlsplit(url).path.startswith("/link"):
        return True
    return any(piece in host for piece in _SKIP_HOST)


def _unwrap(url: str) -> str:
    """必应的跳转链接把真实地址放在 u= 里。"""
    parts = urlsplit(html.unescape(url))
    if "bing.com" not in (parts.hostname or "") or "/ck/" not in parts.path:
        return url
    raw = (parse_qs(parts.query).get("u") or [""])[0]
    if raw.startswith("a1"):
        raw = raw[2:]
    pad = "=" * (-len(raw) % 4)
    try:
        decoded = base64.b64decode(raw + pad).decode("utf-8", "replace")
    except (ValueError, UnicodeError):
        return url
    return decoded if decoded.startswith("http") else url


def _google_target(url: str) -> str:
    parts = urlsplit(url)
    if "google." not in (parts.hostname or ""):
        return url
    target = (parse_qs(parts.query).get("q") or [""])[0]
    return unquote(target) if target.startswith("http") else url


def _get(url: str, *, params: dict | None = None, referer: str = "") -> str:
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin" if _host(referer) == _host(url) else "cross-site"
    response = httpx.get(
        url,
        params=params,
        headers=headers,
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _rows(page: str, pattern: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for href, title_html in re.findall(pattern, page, re.I | re.S):
        url = _google_target(_unwrap(html.unescape(href)))
        title = _clean(title_html, 80)
        if not title or _skip(url):
            continue
        found.append((title, url))
        if len(found) >= 4:
            break
    return found


def _card(page: str) -> str:
    """搜索页上已经写明的温度、现价。打开的网站若是脚本壳，就靠这些数字。"""
    text = re.sub(r"<script[\s\S]*?</script>", " ", page, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = _clean(text, 12000)
    hits = re.findall(r".{0,36}\d+(?:\.\d+)?\s*(?:℃|度|元|%).{0,36}", text)
    kept: list[str] = []
    for hit in hits:
        piece = hit.strip()
        if piece and piece not in kept:
            kept.append(piece)
        if len(kept) >= 4:
            break
    return "；".join(kept)


def _bing(query: str) -> tuple[list[tuple[str, str]], str]:
    page = _get(
        "https://cn.bing.com/search",
        params={"q": query, "ensearch": "0"},
        referer="https://cn.bing.com/",
    )
    return _rows(page, r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'), _card(page)


def _so(query: str) -> tuple[list[tuple[str, str]], str]:
    page = _get(
        "https://www.so.com/s",
        params={"q": query},
        referer="https://www.so.com/",
    )
    return _rows(page, r'class="res-title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'), _card(page)


def _google(query: str) -> tuple[list[tuple[str, str]], str]:
    page = _get(
        "https://www.google.com/search",
        params={"q": query, "hl": "zh-CN", "gbv": "1"},
        referer="https://www.google.com/",
    )
    return _rows(page, r'href="(?:/url\?q=)?(https?://[^"]+)"[^>]*>(.*?)</a>'), _card(page)


def merge_rows(groups: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """按名次轮流取，同一条链接只留一次。"""
    pools = [list(group) for group in groups]
    seen: set[str] = set()
    merged: list[tuple[str, str]] = []
    while any(pools) and len(merged) < 6:
        for pool in pools:
            if not pool:
                continue
            title, url = pool.pop(0)
            key = urlunsplit(urlsplit(url)._replace(query="", fragment="")).rstrip("/")
            if key in seen or _skip(url):
                continue
            seen.add(key)
            merged.append((title, url))
            if len(merged) >= 6:
                break
    return merged


def _usable(text: str) -> bool:
    if not text or len(text) < 40:
        return False
    has_unit = bool(re.search(r"\d+(?:\.\d+)?\s*(?:℃|度|元|%)", text))
    if "加载" in text and not has_unit:
        return False
    if text.count("|") > 12 and not has_unit:
        return False
    return True


def _off_title(title: str) -> bool:
    return bool(re.search(r"词典|拼音|笔顺|的意思|的解释|国学|国家概况|汉语", title or ""))


def _focus_terms(query: str) -> list[str]:
    """从检索词里留下能对上标题的对象，去掉「最新情况」这类空话。"""
    q = re.sub(r"\s+", "", query or "")
    q = re.sub(r"最新情况|最新状况|最新动态|最新进展|最新消息|怎么样|吗", "", q)
    terms: list[str] = []
    for piece in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", q):
        piece = re.sub(r"(股价|股票|价格|行情|天气|新闻|战场|战争)$", "", piece)
        if piece and piece not in {"最新", "情况", "状况", "进展"} and piece not in terms:
            terms.append(piece)
    if "俄乌" in q and "俄乌" not in terms:
        terms.append("俄乌")
    if "茅台" in q and not any("茅台" in term for term in terms):
        terms.append("茅台")
    return terms


def _matches(title: str, terms: list[str]) -> bool:
    if not terms:
        return True
    flat = re.sub(r"\s+", "", title or "")
    return any(term in flat for term in terms)


def _rescue_query(query: str) -> str:
    """第一页全是词典或国家概况时，用同一个对象再查一次进展。股价天气不改。"""
    if re.search(r"股价|股票|价格|天气|金价|汇率|气温", query or ""):
        return ""
    q = re.sub(r"\s+", "", query or "")
    q = re.sub(r"最新情况|最新状况|最新动态|最新消息|的情况", "", q)
    q = q.replace("战场", "战争")
    q = q.strip("的")
    if not q or q == re.sub(r"\s+", "", query or ""):
        return ""
    if "最新进展" not in q:
        q += "最新进展"
    return q


def _stock_code(url: str) -> str:
    host = _host(url)
    if not any(piece in host for piece in ("eastmoney.com", "sina.com", "xueqiu.com")):
        return ""
    matched = re.search(r"(?i)(?:/S/)?(sh|sz)(\d{6})", url)
    if matched:
        return matched.group(1).lower() + matched.group(2)
    matched = re.search(r"/(\d{6})\.html", url)
    if not matched or "eastmoney.com" not in host:
        return ""
    code = matched.group(1)
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def _signed(num: str) -> str:
    if not num or num[0] in "+-":
        return num
    try:
        value = float(num)
    except ValueError:
        return num
    return f"+{num}" if value > 0 else num


def _quote(code: str) -> str:
    """行情网页是脚本壳，现价从腾讯的文本接口读。"""
    try:
        raw = httpx.get(
            f"https://qt.gtimg.cn/q={code}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        ).content.decode("gbk", "replace")
    except httpx.HTTPError:
        return ""
    found = re.search(r'="([^"]+)"', raw)
    if not found:
        return ""
    parts = found.group(1).split("~")
    if len(parts) < 5 or not re.match(r"\d+(?:\.\d+)?$", parts[3] or ""):
        return ""
    name, price, prev = parts[1], parts[3], parts[4]
    stamp = re.search(r"~(\d{14})~([-\d.]+)~([-\d.]+)~([-\d.]+)~([-\d.]+)", found.group(1))
    extra = ""
    if stamp:
        change, pct, high, low = stamp.group(2), stamp.group(3), stamp.group(4), stamp.group(5)
        extra = f"，涨跌 {_signed(change)}（{_signed(pct)}%），最高 {high}，最低 {low}"
    return f"{name} 现价 {price}{extra}。昨收 {prev}。就念这一组，不要说还在加载。"


def _page_text(url: str) -> str:
    if not _public(url):
        return ""
    if _skip(url) and not (_host(url) == "www.so.com" and urlsplit(url).path.startswith("/link")):
        return ""
    page = _get(url, referer="https://cn.bing.com/")
    page = re.sub(r"<script[\s\S]*?</script>", " ", page, flags=re.I)
    page = re.sub(r"<style[\s\S]*?</style>", " ", page, flags=re.I)
    page = re.sub(r"<noscript[\s\S]*?</noscript>", " ", page, flags=re.I)
    return _clean(page, 2400)


def accept_query(text: str) -> str:
    """模型写在 [lookup:] 里的词，原样拿去查。虚词不查，也不另改成别的词。"""
    query = re.sub(r"\s+", " ", text or "").strip()
    if not query or query in _BARE:
        return ""
    return query



def _search(query: str) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    engines = (("必应", _bing), ("360", _so), ("谷歌", _google))
    groups: list[list[tuple[str, str]]] = []
    names: list[str] = []
    cards: list[str] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(name, pool.submit(fetch, query)) for name, fetch in engines]
        for name, future in futures:
            try:
                rows, card = future.result()
            except (httpx.HTTPError, ValueError):
                rows, card = [], ""
            if rows or card:
                names.append(name)
            if card:
                cards.append(f"{name}：{card}")
            groups.append(rows)
    merged = [(title, url) for title, url in merge_rows(groups) if not _off_title(title)]
    print(f"[websearch] {query} {'+'.join(names) or 'none'} {len(merged)}")
    return merged, cards, names


def lookup_note(query: str) -> str:
    """给模型的合并目录和打开的那一页。检索词为空或只是虚词时返回空。"""
    query = accept_query(query)
    if not query:
        return ""
    merged, cards, names = _search(query)
    terms = _focus_terms(query)
    quote = ""
    for _title, url in merged:
        code = _stock_code(url)
        if not code:
            continue
        quote = _quote(code)
        if quote:
            break
    kept = [(title, url) for title, url in merged if _matches(title, terms)]
    if not kept and not quote:
        rescued = _rescue_query(query)
        if rescued:
            merged, cards, names = _search(rescued)
            terms = _focus_terms(rescued)
            kept = [(title, url) for title, url in merged if _matches(title, terms)]
    if not kept and not cards and not quote:
        body = "网上查到的：没查到。跟对方说没查到，不要编。不要拿词典或国家概况来充数。"
    else:
        lines = [f"{index}. {title}" for index, (title, _url) in enumerate(kept or merged, start=1)]
        opened = ""
        opened_title = ""
        if not quote:
            for title, url in (kept or merged)[:3]:
                try:
                    text = _page_text(url)
                except (httpx.HTTPError, ValueError):
                    text = ""
                if not _usable(text) or not _matches(title + text[:400], terms):
                    continue
                opened, opened_title = text, title
                break
        body = "合并后的目录（" + "、".join(names) + "）：\n" + ("\n".join(lines) if lines else "（没有外链）")
        if quote:
            body += "\n现价（以此为准，不要说还在加载，不要另念一个价钱）：\n" + quote
        elif cards:
            body += (
                "\n搜索页上的数字。现价、温度用每条最前面那一组。"
                "打开的页面如果对不上，以搜索页为准：\n"
                + "\n".join(cards)
            )
        if opened:
            body += f"\n打开的页面：{opened_title}\n正文：{opened}"
        elif not quote:
            body += "\n打开的页面和要查的事对不上。说没查到，不要编，不要念国家概况或词典。"
        body = (
            "网上查到的，必须用里面和这句有关的事实回答。"
            "温度、晴雨、涨跌、标题里的事都要说出来。不要念网址。"
            "对不上的页面，尤其是国家概况、人口面积、词典解释，一个字都不要说。\n"
            + body
        )
    return (
        "铺垫已经说了：我去查一下。不要重复。不要再写 [lookup:]。不要调用 web_fetch。"
        "会话里以前说过的温度、价钱、新闻都作废，只按下面这次查到的说。\n"
        + body
    )
