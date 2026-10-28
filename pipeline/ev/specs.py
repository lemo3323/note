"""段階1：機種の仕様（data/specs/<ID>.yaml）を読み、出典を確かめて信頼度を付ける。

仕様ファイルは人（または調査の工程）が書く。1項目ごとに
    value:    値（見つからなければ null。推測で埋めない）
    sources:  [{url, site, evidence: [ページに書いてあるはずの文字列, ...]}]
を持つ。このスクリプトは、各出典について
    1. ページが開けるか（取得対策の回避はしない。開けなければその出典は数えない）
    2. evidence の文字列が本当にページにあるか（無ければその出典は数えない）
を確かめ、残った出典で research と同じ判定（notelib.research.judge_urls）をして
    confidence: high / single / none、why、checked_sources
を書き込む。

使い方：python pipeline/ev/specs.py [--offline] [ID ...]
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notelib.config import DATA_DIR, Config, load_config, today  # noqa: E402
from notelib.research import fetch_page, judge_urls  # noqa: E402

SPEC_DIR = DATA_DIR / "specs"

# 仕様の項目（表示順）。段階1で集める項目
ITEMS = [
    ("ceiling", "天井（ゲーム数・CZ間・スルー・ポイント）"),
    ("ceiling_benefit", "天井の恩恵"),
    ("ceiling_short", "天井の短縮"),
    ("first_hit", "設定1の初当たり確率（AT・CZ・ボーナス）"),
    ("cz_success", "CZ成功率"),
    ("payout_rate", "設定1の機械割"),
    ("avg_payout", "平均獲得枚数"),
    ("coin_mochi", "コイン持ち（50枚あたりのゲーム数）"),
    ("net_gain", "AT純増（枚/G）"),
    ("yuuri", "有利区間"),
    ("reset", "リセット時の仕様"),
    ("special", "特殊狙い・優遇の条件"),
]


def page_text(raw: str) -> str:
    s = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", raw)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return norm(s)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s)


def check_item(item: dict, cfg: Config, offline: bool) -> dict:
    srcs = item.get("sources") or []
    if item.get("value") in (None, "", []):
        item["confidence"] = "none"
        item["why"] = "見つからない（空のまま。推測で埋めない）"
        item["checked_sources"] = []
        return item
    ok_urls, notes = [], []
    for s in srcs:
        url = s["url"]
        if offline:
            ok_urls.append(url)
            continue
        raw = fetch_page(url)
        if raw is None:
            notes.append(f"開けない: {url}")
            continue
        text = page_text(raw)
        missing = [e for e in (s.get("evidence") or []) if norm(str(e)) not in text]
        if missing:
            notes.append(f"値が見つからない {missing}: {url}")
            continue
        ok_urls.append(url)
    conf, why = judge_urls(ok_urls, cfg) if ok_urls else (None, "確認できた出典なし")
    item["confidence"] = conf or "none"
    item["why"] = why
    item["checked_sources"] = ok_urls
    if notes:
        item["check_notes"] = notes
    return item


def load_spec(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save_spec(path: Path, spec: dict) -> None:
    head = ("# 段階1の仕様。value は出典で確認できた値だけ（見つからなければ null）。\n"
            "# confidence / why / checked_sources は pipeline/ev/specs.py が書き込む（手で書かない）。\n")
    path.write_text(head + yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


def verify(path: Path, cfg: Config, offline: bool = False) -> dict:
    spec = load_spec(path)
    for key, _label in ITEMS:
        if key in spec.get("items", {}):
            spec["items"][key] = check_item(spec["items"][key], cfg, offline)
    spec["checked"] = today().isoformat()
    save_spec(path, spec)
    return spec


def summary(spec: dict) -> str:
    rows = [f"■ {spec['name']}（{spec['id']}）"]
    for key, label in ITEMS:
        it = spec.get("items", {}).get(key)
        if not it:
            rows.append(f"  - {label}: （項目なし）")
            continue
        v = it.get("value")
        if v in (None, "", []):
            vs = "空"
        elif isinstance(v, (str, int, float)):
            vs = str(v)
        else:
            vs = yaml.safe_dump(v, allow_unicode=True, default_flow_style=True, width=1000).strip()
        rows.append(f"  - {label}: {vs} ［{it.get('confidence')}：{it.get('why')}］")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--offline", action="store_true", help="ページを開かずに判定だけ（試験用）")
    a = ap.parse_args()
    cfg = load_config()
    paths = sorted(SPEC_DIR.glob("*.yaml"))
    if a.ids:
        paths = [p for p in paths if p.stem in a.ids]
    for p in paths:
        print(summary(verify(p, cfg, a.offline)))


if __name__ == "__main__":
    main()
