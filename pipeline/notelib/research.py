"""調べた情報の採否。YouTube の research 工程（ai-vtuber/pipeline/steps/research.py）と同じ決まり。

- 出典のドメインを research.sites で格付けし、次のどれかを満たす事実だけ採用する
    ・メーカー公式（official）
    ・信頼サイト（tier1）が2つ以上、または tier1 が1つ＋別サイト（tier2・一覧外）が1つ
    ・tier1 が1つだけ → allow_single_trusted が true なら「単独出典」（記事では「〜とされている」）
    ・一覧にないサイトだけなら2つ以上の一致で「単独出典」扱い
- 出典の URL を実際に開いて、ページが存在するか確かめる（開けない URL は数えない）

ai-vtuber が隣にあれば、その research.py の関数をそのまま使う（判定がずれないように）。
"""
from __future__ import annotations

import sys
from urllib.parse import urlparse

import requests

from .config import Config

_upstream = None


def _load_upstream(cfg: Config):
    """ai-vtuber の steps.research を読み込めれば使う。"""
    global _upstream
    if _upstream is not None:
        return _upstream or None
    pipe = cfg.ai_root / "pipeline"
    if (pipe / "steps" / "research.py").exists():
        sys.path.insert(0, str(pipe))
        try:
            from steps import research as up  # type: ignore
            _upstream = up
            return up
        except Exception:  # 依存が足りないなど。手元の写しを使う
            pass
    _upstream = False
    return None


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _site_match(url: str, entry: str) -> str | None:
    entry = entry.lower().strip().strip("/")
    host = domain(url)
    path = urlparse(url).path.lower()
    d, _, prefix = entry.partition("/")
    if not (host == d or host.endswith("." + d)):
        return None
    if prefix and not (path == "/" + prefix or path.startswith("/" + prefix + "/")):
        return None
    return entry


def _origin(site: str, cfg: Config) -> str:
    for group in cfg.get_path("research.not_independent", []) or []:
        names = [g.lower() for g in group]
        if site.split("/")[0] in names or site in names:
            return names[0]
    return site


def tier_of(url: str, cfg: Config) -> tuple[str, str]:
    """（格付け, どのサイトとして数えるか）。official / tier1 / tier2 / other / blocked"""
    up = _load_upstream(cfg)
    if up:
        return up.tier_of(url, cfg)
    for tier in ("official", "tier1", "tier2"):
        for entry in cfg.get_path(f"research.sites.{tier}", []) or []:
            hit = _site_match(url, entry)
            if hit:
                return tier, _origin(hit, cfg)
    for entry in cfg.get_path("research.blocked", []) or []:
        if _site_match(url, entry):
            return "blocked", domain(url)
    host = domain(url)
    for shared in cfg.get_path("research.shared_hosts", []) or []:
        if host == shared or host.endswith("." + shared):
            seg = urlparse(url).path.strip("/").split("/")[0].lower()
            return "other", f"{host}/{seg}" if host == shared else host
    return "other", _origin(host, cfg)


_page_cache: dict[str, str | None] = {}


def fetch_page(url: str) -> str | None:
    """ページの本文（HTML）。開けなければ None。取得対策の回避はしない。"""
    if url in _page_cache:
        return _page_cache[url]
    text = None
    try:
        r = requests.get(url, timeout=25, allow_redirects=True)
        if r.status_code < 400 and len(r.content) > 500:
            text = r.content.decode(r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8",
                                    errors="ignore")
    except requests.RequestException:
        text = None
    _page_cache[url] = text
    return text


def url_exists(url: str, cfg: Config | None = None) -> bool:
    up = _load_upstream(cfg) if cfg is not None else None
    if up:
        return up.url_exists(url)
    return fetch_page(url) is not None


def judge_urls(urls: list[str], cfg: Config) -> tuple[str | None, str]:
    """出典 URL（確認済みのもの）から採否を決める。戻り値：(high / single / None, 理由)"""
    by_tier: dict[str, set[str]] = {k: set() for k in ("official", "tier1", "tier2", "other", "blocked")}
    for u in urls:
        tier, origin = tier_of(u, cfg)
        by_tier[tier].add(origin)
    if by_tier["official"]:
        return "high", "メーカー公式"
    t1 = by_tier["tier1"]
    others = (by_tier["tier2"] | by_tier["other"]) - t1
    if len(t1) >= 2:
        return "high", "信頼サイト2つ以上"
    if len(t1) == 1 and others:
        return "high", "信頼サイト＋別サイトで一致"
    if len(t1) == 1 and cfg.get_path("research.allow_single_trusted", True):
        return "single", "信頼サイト1つだけ"
    if len(by_tier["other"]) >= 2:
        return "single", "一覧にないサイト2つ以上で一致"
    if by_tier["blocked"] and not (t1 or others):
        return None, "SNS・掲示板などだけ"
    return None, "1つのサイトでしか確認できない"


def judge(fact: dict, cfg: Config, check_urls: bool = True) -> tuple[str | None, str]:
    """research.json の facts と同じ形（sources: [{url, site}]）の事実を判定する。"""
    urls = [s["url"] for s in fact.get("sources", [])]
    if check_urls:
        urls = [u for u in urls if url_exists(u, cfg)]
        if not urls:
            return None, "出典のページが開けない"
    return judge_urls(urls, cfg)
