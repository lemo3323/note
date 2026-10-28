"""記事の材料を集める。優先順位：①狙い目シート ②調べた情報（research）③自作の期待値データ。

調べた情報は2か所から読む。
- <ai_vtuber_root>/data/research/<ID>.json：YouTube の research 工程の結果（採用済みの facts だけ使う）
- data/research_note/<slug>.json：note 用に追加で調べたもの（特殊狙い・優遇狙い・無料記事のテーマなど）。
  形は research.schema.json と同じ（facts: [{category, text, sources: [{url, site}], provisional}]）に machine を足したもの。
  ここで notelib.research.judge（格付け＋URL確認）を通し、結果を <slug>.judged.json に書く
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

from . import sheet as sheet_mod
from .config import DATA_DIR, ROOT, Config, read_json, today, write_json
from .research import judge

NOTE_RESEARCH = DATA_DIR / "research_note"
SPEC_DIR = DATA_DIR / "specs"
EV_DIR = DATA_DIR / "ev"

SPEC_LABELS = {
    "ceiling": "天井", "ceiling_benefit": "天井の恩恵", "ceiling_short": "天井の短縮", "first_hit": "設定1の初当たり確率",
    "payout_rate": "設定1の機械割", "coin_mochi": "コイン持ち（50枚あたり）", "net_gain": "AT純増", "yuuri": "有利区間",
    "reset": "リセット時", "special": "特殊な条件",
}


def strategy_notes() -> list[str]:
    """config/strategy_notes.md の、運営者が書いた行（見出し・コメント・空行を除く）。見出しごとに返す。"""
    p = ROOT / "config" / "strategy_notes.md"
    text = re.sub(r"<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S)
    out, head = [], ""
    for ln in text.splitlines():
        if ln.startswith("## "):
            head = ln[3:].strip()
        elif ln.strip().startswith("- ") and head:
            out.append(f"[{head}] {ln.strip()[2:].strip()}")
    return out


def judged_note_research(slug: str, cfg: Config, recheck: bool = False) -> dict | None:
    raw_p = NOTE_RESEARCH / f"{slug}.json"
    out_p = NOTE_RESEARCH / f"{slug}.judged.json"
    if not raw_p.exists():
        return None
    if out_p.exists() and not recheck and out_p.stat().st_mtime >= raw_p.stat().st_mtime:
        return read_json(out_p)
    raw = read_json(raw_p)
    acc, drop = [], []
    for f in raw.get("facts", []):
        f = _keep_sources_with_evidence(f)
        conf, why = judge(f, cfg, check_urls=True) if f["sources"] else (None, "出典に値が見つからない")
        (acc if conf else drop).append({**f, "confidence": conf, "why": why})
    res = {**{k: v for k, v in raw.items() if k != "facts"}, "date": today().isoformat(), "facts": acc, "dropped": drop}
    write_json(out_p, res)
    return res


def _keep_sources_with_evidence(fact: dict) -> dict:
    """出典に evidence（ページに書いてあるはずの短い文字列）があれば、ページを開いて本当にあるか確かめ、無い出典は外す。"""
    from ev.specs import norm as _n, page_text
    from .research import fetch_page
    kept, notes = [], []
    for s in fact.get("sources", []):
        ev = s.get("evidence") or []
        if not ev:
            kept.append(s)
            continue
        raw = fetch_page(s["url"])
        if raw is None:
            notes.append(f"開けない: {s['url']}")
            continue
        text = page_text(raw)
        missing = [e for e in ev if _n(e) not in text]
        if missing:
            notes.append(f"値が見つからない {missing}: {s['url']}")
            continue
        kept.append(s)
    out = {**fact, "sources": kept}
    if notes:
        out["check_notes"] = notes
    return out


def youtube_research(mid: str, cfg: Config) -> dict | None:
    if not mid:
        return None
    p = cfg.ai_root / "data" / "research" / f"{mid}.json"
    return read_json(p) if p.exists() else None


def spec_for(name: str, mid: str) -> dict | None:
    for p in SPEC_DIR.glob("*.yaml"):
        s = yaml.safe_load(p.read_text(encoding="utf-8"))
        if (mid and s.get("sheet_id") == mid) or sheet_mod.norm(s.get("sheet_name", "")) == sheet_mod.norm(name):
            return s
    return None


def spec_facts(spec: dict) -> list[dict]:
    """仕様（段階1）のうち信頼度 high/single の項目を、調べた情報と同じ形にする。"""
    out = []
    for key, label in SPEC_LABELS.items():
        it = spec["items"].get(key) or {}
        if it.get("confidence") not in ("high", "single") or it.get("value") in (None, "", []):
            continue
        v = it["value"]
        text = v if isinstance(v, str) else yaml.safe_dump(v, allow_unicode=True, default_flow_style=True, width=1000).strip()
        out.append({"category": "spec", "text": f"{label}：{text}", "confidence": it["confidence"], "why": it.get("why"),
                    "sources": [{"url": u, "site": ""} for u in it.get("checked_sources", [])], "origin": "spec",
                    "provisional": False})
    return out


def ev_for(spec: dict | None) -> dict | None:
    if not spec:
        return None
    p = EV_DIR / f"{spec['id']}.json"
    if not p.exists():
        return None
    ev = read_json(p)
    tables = {}
    for key, ok in (ev.get("verdicts") or {}).items():
        md = EV_DIR / "tables" / f"{spec['id']}_{key}.md"
        if ok and md.exists():
            tables[key] = {"label": ev["variants"][key]["label"], "md": md.read_text(encoding="utf-8"),
                           "png": str(EV_DIR / "tables" / f"{spec['id']}_{key}.png"),
                           "border_toka": ev["variants"][key]["border_toka"]}
    return {"spec_id": spec["id"], "tables": tables, "verdicts": ev.get("verdicts", {}), "params": ev.get("params")}


def collect(kind: str, target: str, cfg: Config, slug: str, machine_names: list[str] | None = None) -> dict:
    machines = sheet_mod.load(cfg)
    mats: dict = {"kind": kind, "target": target, "slug": slug, "date": today().isoformat(), "machines": [],
                  "facts": [], "conflicts": [], "ev": {}, "strategy_notes": strategy_notes(), "warnings": []}
    names = machine_names or ([target] if kind in ("machine", "new_machine") else [])
    for nm in names:
        m, cands = sheet_mod.find(machines, nm)
        if not m:
            mats["warnings"].append(f"シートに「{nm}」が見つからない（候補：{', '.join(c.name for c in cands[:5]) or 'なし'}）")
            continue
        entry = {"id": m.id, "name": m.name, "aliases": m.aliases, "updated": m.updated, "lines": m.lines}
        mats["machines"].append(entry)
        yr = youtube_research(m.id, cfg)
        if yr:
            for f in yr.get("facts", []):
                mats["facts"].append({**f, "machine": m.name, "origin": "youtube_research"})
            for c in yr.get("memo_conflicts", []):
                mats["conflicts"].append({**c, "machine": m.name})
        # note 用に機種ごとに調べたもの（data/research_note/<ID>.json）。テーマの記事でも使う
        if m.id and m.id != slug:
            mr = judged_note_research(m.id, cfg)
            if mr:
                if mr.get("notes"):
                    mats.setdefault("research_notes", []).append(f"{m.name}：{mr['notes']}")
                mats["facts"] += [{**f, "origin": "note_research"} for f in mr.get("facts", [])]
                for c in mr.get("memo_conflicts", []):
                    mats["conflicts"].append({**c, "machine": m.name})
        spec = spec_for(m.name, m.id)
        if spec:
            mats["facts"] += [{**f, "machine": m.name} for f in spec_facts(spec)]
            ev = ev_for(spec)
            if ev:
                mats["ev"][m.name] = ev
    nr = judged_note_research(slug, cfg)
    if nr:
        if nr.get("notes"):
            mats.setdefault("research_notes", []).append(nr["notes"])
        mats["facts"] += [{**f, "origin": "note_research"} for f in nr.get("facts", [])]
        mats["dropped"] = nr.get("dropped", [])
        for c in nr.get("memo_conflicts", []):
            mats["conflicts"].append(c)
    elif kind in ("special", "free", "new_machine"):
        mats["warnings"].append(f"note 用の調べた情報（data/research_note/{slug}.json）が無い")
    if kind == "weekly":
        mats["weekly"] = weekly_changes(machines)
    return mats


STATE = DATA_DIR / "note_state.json"


def weekly_changes(machines: list[sheet_mod.Machine], days: int = 7) -> dict:
    """今週（更新日が7日以内）の台と、前回の週刊記事から本文が変わった台。"""
    import hashlib
    state = read_json(STATE) if STATE.exists() else {}
    since = today() - dt.timedelta(days=days)
    recent, changed = [], []
    for m in machines:
        h = hashlib.sha1(m.text.encode("utf-8")).hexdigest()[:16]
        try:
            upd = dt.date.fromisoformat(m.updated)
        except ValueError:
            upd = None
        if upd and upd >= since:
            recent.append(m.name)
        prev = state.get(m.name)
        if prev and prev != h:
            changed.append(m.name)
    return {"since": since.isoformat(), "recent": recent, "changed": changed,
            "hashes": {m.name: hashlib.sha1(m.text.encode("utf-8")).hexdigest()[:16] for m in machines}}


def save_weekly_state(mats: dict) -> None:
    write_json(STATE, mats.get("weekly", {}).get("hashes", {}))


def allowed_numbers(mats: dict, cfg: Config) -> set[float]:
    """記事に出してよい数（10以上のチェック用）：シート・採用済みの調べた情報・自作の期待値データ・設定の値。"""
    nums: set[float] = set(float(x) for x in cfg.get_path("note.allowed_numbers", []) or [])
    for k in ("price_single", "price_monthly", "price_monthly_after", "price_premium", "monthly_raise_at"):
        v = cfg.get_path(f"note.{k}")
        if v:
            nums.add(float(v))
    for m in mats["machines"]:
        nums |= sheet_mod.numbers_in("\n".join(m["lines"]))
    for f in mats["facts"]:
        nums |= sheet_mod.numbers_in(f.get("text", ""))
    for ev in mats.get("ev", {}).values():
        for t in ev.get("tables", {}).values():
            nums |= sheet_mod.numbers_in(t["md"])
    return nums
