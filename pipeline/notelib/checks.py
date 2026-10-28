"""記事の自動チェック（YouTube の qa と同じく、通らなければ作り直す）。

- 10以上の数字が、シート・採用済みの調べた情報・自作の期待値データのどれかにあるか
  （コードが入れた部分＝期待値表・注意書き・参考・案内は <!-- auto --> で囲み、チェックしない）
- 注意書き・「ここから有料」の位置・参考がそろっているか
- 実在のホール名・勝ちを保証する言い方・他サイトの写しの疑い（出典の文をそのまま含む）が無いか
"""
from __future__ import annotations

import re
import unicodedata

from .config import Config
from .sheet import numbers_in

PAYWALL = "ここから有料"
AUTO = re.compile(r"<!-- auto[^>]*-->.*?<!-- /auto -->", re.S)

BANNED_PHRASES = ["必ず勝てる", "絶対勝てる", "確実に勝てる", "勝ち確定", "必勝", "稼げる", "儲かる", "損しない", "負けない"]


def check_numbers(article: str, allowed: set[float], min_value: int = 10) -> list[str]:
    body = AUTO.sub("", article)
    body = re.sub(r"https?://\S+", "", body)
    bad = []
    for v in sorted(numbers_in(body)):
        if v < min_value or v in allowed:
            continue
        # 年月日（2026年10月28日 など）は数字チェックの対象外
        if re.search(rf"{int(v)}年|年{int(v)}月|月{int(v)}日", unicodedata.normalize("NFKC", body)):
            continue
        bad.append(f"{v:g}")
    return bad


def check_article(article: str, kind: str, mats: dict, allowed: set[float], cfg: Config) -> list[str]:
    problems = []
    bad = check_numbers(article, allowed, int(cfg.get_path("note.number_check_min", 10)))
    if bad:
        problems.append(f"数字の根拠が無い（シート・調べた情報・期待値データのどれにも無い）：{', '.join(bad)}")
    for d in cfg.get_path("note.disclaimers", []) or []:
        if d not in article:
            problems.append(f"注意書きが無い：{d[:20]}…")
    if kind != "free" and article.count(PAYWALL) != 1:
        problems.append("「ここから有料」の区切りが1つではない")
    if kind == "free" and PAYWALL in article:
        problems.append("無料記事に「ここから有料」がある")
    if "## 参考" not in article and mats.get("facts"):
        problems.append("「参考」が無い")
    for w in BANNED_PHRASES:
        if w in AUTO.sub("", article):
            problems.append(f"勝ちを保証するような言い方：{w}")
    for w in cfg.get_path("note.banned_words", []) or []:
        if w and w in article:
            problems.append(f"出してはいけない言葉（実在のホール名など）：{w}")
    # 出典の文をそのまま写していないか（調べた情報の text は自分の言葉の要約だが、念のため長い一致を見る）
    for f in mats.get("facts", []):
        for q in f.get("quotes", []) or []:
            if len(q) >= 25 and q in article:
                problems.append(f"出典の文をそのまま写している疑い：{q[:20]}…")
    return problems
