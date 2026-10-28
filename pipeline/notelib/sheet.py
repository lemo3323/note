"""狙い目シートの読み込みと機種の検索。

読む順番：
1. <ai_vtuber_root>/data/nerai_latest.csv（YouTube パイプラインがシートから取り込んだ最新の写し。列：ID・機種名・別名・更新日・本文）
2. data/sheet/*.txt（lemo3323/slot の nerai と同じ1機種1ファイル。ID はファイルに無いので空）

本文は運営者が書いたもの。読むだけで、追加・修正・言い換えはしない。
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR, Config


@dataclass
class Machine:
    id: str
    name: str
    aliases: list[str]
    updated: str
    lines: list[str]
    source: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


_SYMBOLS = re.compile(r"[\s・！？!?、。,.，．「」『』（）()\[\]【】〜~:：;；/／\-＿_]")


def norm(s: str) -> str:
    """検索用：NFKC、カタカナ→ひらがな、小文字、空白と記号を無視（長音「ー」は残す）。"""
    s = unicodedata.normalize("NFKC", s).lower()
    s = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)
    return _SYMBOLS.sub("", s)


def _split_aliases(raw: str) -> list[str]:
    raw = raw.strip().strip("[]")
    return [a.strip() for a in re.split(r"[,，]", raw) if a.strip()]


def _from_csv(path: Path) -> list[Machine]:
    out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.reader(f):
            if not r or not re.match(r"m\d+", r[0] or ""):
                continue
            out.append(Machine(id=r[0], name=r[1], aliases=_split_aliases(r[2] if len(r) > 2 else ""),
                               updated=r[3] if len(r) > 3 else "", lines=(r[4] if len(r) > 4 else "").split("\n"),
                               source=str(path)))
    return out


def _from_txt(d: Path) -> list[Machine]:
    ids_p = d / "_ids.yaml"
    ids = {}
    if ids_p.exists():
        import yaml
        ids = yaml.safe_load(ids_p.read_text(encoding="utf-8")) or {}
    out = []
    for p in sorted(d.glob("*.txt")):
        if p.name.startswith("_"):
            continue
        t = p.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n?(.*)", t, re.S)
        if not m:
            continue
        head, body = m.group(1), m.group(2)
        meta = dict(re.findall(r"^(\w+):\s*(.*)$", head, re.M))
        name = meta.get("name", p.stem)
        out.append(Machine(id=meta.get("id") or ids.get(name, ""), name=name,
                           aliases=_split_aliases(meta.get("aliases", "")), updated=meta.get("updated", ""),
                           lines=body.rstrip("\n").split("\n"), source=str(p)))
    return out


def load(cfg: Config) -> list[Machine]:
    csv_path = cfg.ai_root / "data" / "nerai_latest.csv"
    if csv_path.exists():
        return _from_csv(csv_path)
    d = Path(cfg.get_path("paths.sheet_txt_dir", "data/sheet"))
    d = d if d.is_absolute() else DATA_DIR.parent / d
    return _from_txt(d)


def find(machines: list[Machine], query: str) -> tuple[Machine | None, list[Machine]]:
    """（いちばん合う機種, 他の候補）。①完全一致 ②前方一致 ③部分一致。"""
    q = norm(query)
    keys = [(m, [norm(m.name)] + [norm(a) for a in m.aliases]) for m in machines]
    exact = [m for m, ks in keys if q in ks]
    if exact:
        return exact[0], [m for m, ks in keys if m is not exact[0] and any(k.startswith(q) or q in k for k in ks)]
    pre = [m for m, ks in keys if any(k.startswith(q) for k in ks)]
    part = [m for m, ks in keys if m not in pre and any(q in k for k in ks)]
    cands = pre + part
    return (cands[0] if len(cands) == 1 else None), cands


def numbers_in(text: str) -> set[float]:
    """文中の数（1,000 の区切りを外す。全角も読む）。"""
    t = unicodedata.normalize("NFKC", text).replace(",", "")
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)}
