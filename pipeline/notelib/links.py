"""YouTube の説明文に入れる、note 記事と月額マガジンへの案内。

ai-vtuber の pipeline/steps/metadata.py で説明文を組み立てるところ（「▼参考」を足している所の前）に
    from notelib.links import youtube_block   # sys.path に note の pipeline を足す
    block = youtube_block(cfg_note, machine_id, machine_name)
    if block: parts.append(block)
を入れる（docs/integration.md）。URL は config の links: に運営者が入れる。空なら何も出さない。
"""
from __future__ import annotations

from .config import Config
from .sheet import norm


def article_url(cfg: Config, machine_id: str = "", machine_name: str = "") -> str:
    arts = cfg.get_path("links.articles") or {}
    if machine_id and arts.get(machine_id):
        return arts[machine_id]
    for k, v in arts.items():
        if v and machine_name and norm(str(k)) == norm(machine_name):
            return v
    return ""


def youtube_block(cfg: Config, machine_id: str = "", machine_name: str = "") -> str:
    lines = []
    art = article_url(cfg, machine_id, machine_name)
    mag = cfg.get_path("links.paid_magazine") or ""
    if art:
        lines.append(cfg.get_path("links.youtube_article_line", "{article}").format(article=art, magazine=mag))
    if mag:
        lines.append(cfg.get_path("links.youtube_magazine_line", "{magazine}").format(article=art, magazine=mag))
    return "\n\n".join(lines)
