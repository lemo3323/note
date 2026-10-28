"""段階4の比べる相手：信頼サイトの期待値表のページから <table> を取り出して data/compare/raw/<ID>_<site>.txt に保存する。

    python pipeline/ev/fetch_reference.py <ID> <URL> [--site nana]

保存したものは比べるためだけに使う（data/compare/ は git に入れない。記事・表に載せない）。
取得対策の回避はしない（開けなければ止まる）。
"""
from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notelib.config import DATA_DIR  # noqa: E402


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.stack, self.heading, self.in_h, self.buf, self.cell = [], [], "", False, "", None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "h4"):
            self.in_h, self.buf = True, ""
        if tag == "table":
            self.stack.append({"heading": self.heading, "rows": []})
        if tag == "tr" and self.stack:
            self.stack[-1]["rows"].append([])
        if tag in ("td", "th") and self.stack:
            self.cell = ""
        if tag == "br" and self.cell is not None:
            self.cell += " "

    def handle_endtag(self, tag):
        if tag in ("h2", "h3", "h4") and self.in_h:
            self.in_h, self.heading = False, re.sub(r"\s+", " ", self.buf).strip()
        if tag in ("td", "th") and self.stack and self.cell is not None:
            if not self.stack[-1]["rows"]:
                self.stack[-1]["rows"].append([])
            self.stack[-1]["rows"][-1].append(re.sub(r"\s+", " ", self.cell).strip())
            self.cell = None
        if tag == "table" and self.stack:
            self.tables.append(self.stack.pop())

    def handle_data(self, data):
        if self.in_h:
            self.buf += data
        if self.cell is not None:
            self.cell += data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("url")
    ap.add_argument("--site", default="nana")
    a = ap.parse_args()
    r = requests.get(a.url, timeout=30)
    r.raise_for_status()
    p = _Tables()
    p.feed(r.content.decode("utf-8", "ignore"))
    lines = [f"# source: {a.url}"]
    for i, t in enumerate(p.tables):
        lines.append(f"--- table {i} [{t['heading']}]")
        lines += ["  " + " | ".join(row) for row in t["rows"]]
    out = DATA_DIR / "compare" / "raw" / f"{a.id}_{a.site}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out}（表 {len(p.tables)} 個）")


if __name__ == "__main__":
    main()
