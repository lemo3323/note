"""段階4：自作の期待値と、信頼サイトで公開されている期待値表の答え合わせ。

- 比べる相手の表は data/compare/raw/<ID>_<site>.txt（取得したページの表を行に分けたもの）。
  ここにある他サイトの数値は比べるためだけに使い、成果物（記事・表・docs）には載せない（data/compare/ は git に入れない）
- 何と何を比べるかは REFERENCES に書く（表の見出し → 自分の状況（variant）と列）
- 合否の基準は config の ev.compare（結果を見る前に決めたもの）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from notelib.config import DATA_DIR

from .model import Point, border

RAW_DIR = DATA_DIR / "compare" / "raw"

# 機種 → [(ファイル, 表の見出しに含まれる文字, [(自分の状況, 列番号→交換率)])]
#   列番号は「開始G」の次から 0,1,2,...
REFERENCES = {
    "godeater_r": {
        "site": "なな徹",
        "url": "https://nana-press.com/kaiseki/machine/767/22716/",
        "tables": [
            ("天井短縮なし時の天井期待値", {"normal": {0: "toka", 1: "5.6"}}),
            ("天井短縮あり時の天井期待値", {"reset": {0: "toka", 1: "5.6"}}),
        ],
    },
    "otome5": {
        "site": "なな徹",
        "url": "https://nana-press.com/kaiseki/machine/1160/37315/",
        "tables": [("天井期待値", {"normal": {0: "toka", 1: "5.6"}, "reset": {2: "toka", 3: "5.6"}})],
    },
    "kabaneri_unato": {
        "site": "なな徹",
        "url": "https://nana-press.com/kaiseki/machine/1097/35403/",
        "tables": [("通常条件・天井短縮時の期待値", {"normal": {0: "toka", 1: "5.6"}, "reset": {2: "toka", 3: "5.6"}})],
    },
    "milliongod_kiseki": {
        "site": "なな徹",
        "url": "https://nana-press.com/kaiseki/machine/1112/35715/",
        "tables": [("通常条件・リセット時の期待値", {"normal": {0: "toka", 1: "5.6"}, "reset": {2: "toka", 3: "5.6"}})],
    },
    # リコリコは状況別機械割を係数の推定に使ったので、独立した比べる相手が無い
}


def _num(s: str) -> float | None:
    s = s.replace(",", "").replace("円", "").replace("G", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_raw(path: Path) -> list[tuple[str, list[list[str]]]]:
    """[(見出し, 行)]。同じ見出しの表が複数あっても別々に持つ。"""
    tables: list[tuple[str, list[list[str]]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"--- table \d+ \[(.*)\]", line)
        if m:
            tables.append((m.group(1), []))
            continue
        if tables and line.startswith("  "):
            tables[-1][1].append([c.strip() for c in line.strip().split("|")])
    return tables


def _is_ev_table(rows: list[list[str]]) -> bool:
    """期待値の表か（開始Gの次の列が「〜円」で、%の列が無い）。"""
    body = [r for r in rows if r and _num(r[0]) is not None and len(r) >= 2]
    return bool(body) and all(c.endswith("円") for c in body[0][1:]) and not any("%" in c for c in body[0])


def load_reference(mid: str) -> dict[str, dict[str, dict[int, float]]]:
    """{状況: {交換率: {開始G: 円}}}"""
    ref = REFERENCES.get(mid)
    if not ref:
        return {}
    raw = RAW_DIR / f"{mid}_nana.txt"
    if not raw.exists():
        return {}
    tables = parse_raw(raw)
    out: dict[str, dict[str, dict[int, float]]] = {}
    for title_part, mapping in ref["tables"]:
        rows = next((rows for t, rows in tables if title_part in t and _is_ev_table(rows)), None)
        if not rows:
            continue
        for row in rows:
            g = _num(row[0]) if row else None
            if g is None or len(row) < 2:
                continue
            vals = [_num(c) for c in row[1:]]
            for variant, cols in mapping.items():
                for ci, key in cols.items():
                    if ci < len(vals) and vals[ci] is not None:
                        out.setdefault(variant, {}).setdefault(key, {})[int(g)] = vals[ci]
    return out


@dataclass
class VariantResult:
    variant: str
    n: int = 0
    n_ok: int = 0
    max_abs: float = 0.0
    mean_diff: float = 0.0
    border_mine: int | None = None
    border_ref: int | None = None
    rows: list[dict] = field(default_factory=list)   # 開始G・交換率・自分・相手・差（内部用。成果物に載せない）

    def passed(self, c: dict) -> bool:
        if self.n == 0:
            return False
        share_ok = self.n_ok / self.n >= float(c.get("min_pass_share", 0.8))
        b_ok = (self.border_mine is not None and self.border_ref is not None
                and abs(self.border_mine - self.border_ref) <= int(c.get("max_border_diff_g", 50)))
        return share_ok and b_ok


def compare_variant(variant: str, points: list[Point], ref: dict[str, dict[int, float]], c: dict) -> VariantResult:
    r = VariantResult(variant)
    diffs = []
    by_start = {p.start: p for p in points}
    for key, table in ref.items():
        for g, theirs in sorted(table.items()):
            p = by_start.get(g)
            if p is None:
                continue
            mine = p.ev[key]
            d = mine - theirs
            tol = max(float(c.get("max_diff_yen", 600)), float(c.get("max_diff_ratio", 0.25)) * abs(theirs))
            r.n += 1
            r.n_ok += abs(d) <= tol
            diffs.append(d)
            r.rows.append({"start": g, "exchange": key, "mine": round(mine), "ref": round(theirs), "diff": round(d),
                           "ok": abs(d) <= tol})
    if diffs:
        r.max_abs = max(abs(d) for d in diffs)
        r.mean_diff = sum(diffs) / len(diffs)
    r.border_mine = border(points, "toka")
    toka = ref.get("toka", {})
    first = None
    for g in sorted(toka):
        if toka[g] >= 0:
            first = g if first is None else first
        else:
            first = None
    r.border_ref = first
    return r
