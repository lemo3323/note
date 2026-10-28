"""note 有料記事を作る。

    python pipeline/note.py --machine モンキー                 # 単発記事（有料）
    python pipeline/note.py --special 優遇狙い --machines ヴ2,モンキー,北斗,戦コレ6
    python pipeline/note.py --new-machine <機種>               # 新台の初週速報
    python pipeline/note.py --weekly                          # 月額：今週の狙い目まとめ＋狙い目が変わった台
    python pipeline/note.py --free ホールでの探し方             # 無料記事（最後に有料記事・月額へ案内）

    --research        先に note 用の調査（claude -p ＋ WebSearch）をして data/research_note/<slug>.json に保存する
    --draft <json>    AI を呼ばずに、この下書き JSON で組み立てる（人や別のセッションが書いた下書き）
    --slug <名前>     フォルダ名・調べた情報のファイル名に使う短い英字（テーマの記事）
    --no-images       画像を作らない
    --render-images <フォルダ名>  あとから画像だけ描く（ai-vtuber のある PC で）

出力：notes/<日付>_<種類>_<ID>/ に article.md・images/・note_kit.txt・review_log.md。
材料と下書きは notes/_work/<同じ名前>/（公開リポジトリのあいだ git に入れない）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notelib import ai, article, checks, images, kit, materials  # noqa: E402
from notelib.config import ROOT, load_config, read_json, today, write_json  # noqa: E402

KIND_DIR = {"machine": "machine", "special": "special", "new_machine": "new", "weekly": "weekly", "free": "free"}
TEMPLATE = {"machine": "note_machine", "special": "note_special", "new_machine": "note_new_machine",
            "weekly": "note_weekly", "free": "note_free"}
SLUGS = {"優遇狙い": "yuuguu", "リセット狙い": "reset", "ホールでの探し方": "hall_guide", "初心者向け機種ガイド": "beginner_guide"}


def slug_for(target: str) -> str:
    return SLUGS.get(target) or "t" + hashlib.sha1(target.encode("utf-8")).hexdigest()[:6]


def fmt_sheet(mats: dict) -> str:
    out = []
    for m in mats["machines"]:
        out.append(f"### {m['name']}（ID {m['id'] or 'なし'}・更新 {m['updated']}）\n```\n" + "\n".join(m["lines"]) + "\n```")
    return "\n\n".join(out) or "（なし）"


def fmt_facts(mats: dict) -> str:
    rows = []
    for f in mats["facts"]:
        src = " ".join(s["url"] for s in f.get("sources", []))
        flag = f"confidence={f.get('confidence')}" + (" provisional" if f.get("provisional") else "")
        rows.append(f"- [{f.get('machine', '')}][{f.get('category', '')}] {f['text']} （{flag}）{src}")
    return "\n".join(rows) or "（なし）"


def fmt_ev(mats: dict) -> str:
    parts = []
    for name, ev in (mats.get("ev") or {}).items():
        for key, t in ev.get("tables", {}).items():
            parts.append(f"{name}・{t['label']}：等価でプラスになり始めるのは {t['border_toka']}G（表はコードが入れる）")
        for key, ok in ev.get("verdicts", {}).items():
            if not ok:
                parts.append(f"{name}・{key}：答え合わせに不合格のため準備中（数字は使わない）")
    return "\n".join(parts) or "（この機種の自作期待値表はまだ無い。期待値の数字は書かない）"


def markdown_tables(md: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """article.md の表（<!-- auto --> の中を除く）を [(直前の見出し, 列, 行)] で返す。"""
    body = checks.AUTO.sub("", md)
    out, heading, block = [], "", []
    for ln in body.splitlines() + [""]:
        if ln.startswith("#"):
            heading = ln.lstrip("#").strip()
        if ln.startswith("|"):
            block.append(ln)
            continue
        if len(block) >= 3:
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in block]
            out.append((heading, cells[0], [r for r in cells[2:]]))
        block = []
    return out


def place_markers(md: str, img_items: list[dict]) -> str:
    """貼る場所が分かるように、本文に画像の目印を入れる（表の前・ひよりの画像の見出しの下）。"""
    lines, out, n_table, in_auto, prev_table = md.splitlines(), [], 0, False, False
    body_imgs = {i["where"].split("「")[1].split("」")[0]: i["file"] for i in img_items if "「" in i.get("where", "")}
    for ln in lines:
        if ln.startswith("<!-- auto"):
            in_auto = True
        if ln.startswith("<!-- /auto"):
            in_auto = False
        is_table = ln.startswith("|") and not in_auto
        if is_table and not prev_table:
            n_table += 1
            out.append(f"［この表は画像 images/table_{n_table}.png を貼る］")
        prev_table = is_table
        out.append(ln)
        if ln.startswith("## ") and ln[3:].strip() in body_imgs:
            out += ["", f"［ここに画像 {body_imgs[ln[3:].strip()]} を貼る（ひより）］"]
    return "\n".join(out) + "\n"


def make_prompt(kind: str, target: str, mats: dict, cfg) -> str:
    schema = (ROOT / "schemas" / "note_draft.schema.json").read_text(encoding="utf-8")
    rules = ai.fill("note_rules", {"schema": schema})
    conflicts = "\n".join(f"- {c.get('machine', '')}：メモ「{c.get('memo_line')}」⇔ 調査「{c.get('found')}」"
                          for c in mats["conflicts"]) or "（なし）"
    return ai.fill(TEMPLATE[kind], {
        "target": target, "price": str(article.price_for(kind, cfg) or 0), "rules": rules, "sheet": fmt_sheet(mats),
        "conflicts": conflicts, "facts": fmt_facts(mats), "ev": fmt_ev(mats), "date": today().isoformat(),
        "weekly": json.dumps({k: v for k, v in (mats.get("weekly") or {}).items() if k != "hashes"}, ensure_ascii=False),
    })


def run_research(kind: str, target: str, slug: str, mats: dict, cfg, work: Path) -> None:
    sites = cfg.get_path("research.sites", {}) or {}
    trusted = "、".join(list(sites.get("tier1") or []) + list(sites.get("tier2") or []))
    names = "、".join(m["name"] for m in mats["machines"]) or target
    questions = {
        "special": f"{names} のそれぞれについて、「{target}」の条件・見分け方・打ち始め・やめどき・恩恵",
        "new_machine": f"{target} の天井（ゲーム数・恩恵）・リセット時・やめどき・狙い目・導入日（判明していない項目は notes に「調査中」と書く）",
        "free": f"「{target}」のために、ホールで見る場所（液晶・データカウンター・メニュー画面など）と、天井・有利区間・リセットの一般的なしくみ",
        "machine": f"{target} のやめどき・天井恩恵・リセット時・有利区間・特殊狙い・優遇の条件",
    }.get(kind, target)
    prompt = ai.fill("note_research", {"target": target, "kind": kind, "questions": questions,
                                       "trusted_sites": trusted, "sheet": fmt_sheet(mats)})
    raw = ai.ask_json(prompt, work, "research", tools=["WebSearch", "WebFetch"])
    raw["topic"] = target
    write_json(materials.NOTE_RESEARCH / f"{slug}.json", raw)


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--machine")
    g.add_argument("--special")
    g.add_argument("--new-machine")
    g.add_argument("--weekly", action="store_true")
    g.add_argument("--free")
    g.add_argument("--render-images")
    ap.add_argument("--machines", default="", help="特殊狙いの記事で取り上げる機種（カンマ区切り）")
    ap.add_argument("--slug")
    ap.add_argument("--draft")
    ap.add_argument("--research", action="store_true")
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--prompt-only", action="store_true", help="材料とプロンプトを notes/_work/ に書いて終わる（下書きを別に書くとき）")
    a = ap.parse_args()
    cfg = load_config()

    if a.render_images:
        folder = ROOT / cfg.get_path("note.out_dir", "notes") / a.render_images
        plan = read_json(ROOT / "notes" / "_work" / folder.name / "images_plan.json")
        done = images.render(folder, plan, cfg)
        print("\n".join(f"{d['file']}: {'描きました' if d['rendered'] else '描けませんでした'}" for d in done))
        return

    if a.machine:
        kind, target = "machine", a.machine
    elif a.special:
        kind, target = "special", a.special
    elif a.new_machine:
        kind, target = "new_machine", a.new_machine
    elif a.weekly:
        kind, target = "weekly", "今週の狙い目"
    else:
        kind, target = "free", a.free
    names = [n.strip() for n in a.machines.split(",") if n.strip()] or None
    if kind == "weekly":
        names = None

    # ID：機種の記事はシートの ID（無ければテーマと同じ短い英字）
    slug = a.slug or (slug_for(target) if kind in ("special", "free") else "")
    mats = materials.collect(kind, target, cfg, slug or "_", names)
    if kind == "weekly":
        names = mats["weekly"]["recent"] + [n for n in mats["weekly"]["changed"] if n not in mats["weekly"]["recent"]]
        mats = materials.collect(kind, target, cfg, "_", names)
    if kind in ("machine", "new_machine"):
        mid = mats["machines"][0]["id"] if mats["machines"] and mats["machines"][0]["id"] else ""
        slug = a.slug or mid or slug_for(target)
        mats = materials.collect(kind, target, cfg, slug, names)
    if kind == "weekly":
        slug = today().strftime("%Y%m%d")
    name = f"{today().isoformat()}_{KIND_DIR[kind]}_{slug}"
    folder = ROOT / cfg.get_path("note.out_dir", "notes") / name
    work = ROOT / "notes" / "_work" / name
    folder.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    if a.research:
        run_research(kind, target, slug, mats, cfg, work)
        mats = materials.collect(kind, target, cfg, slug, names)
    write_json(work / "materials.json", mats)
    allowed = materials.allowed_numbers(mats, cfg)

    attempts, problems, unknown = 0, ["未作成"], []
    prompt = make_prompt(kind, target, mats, cfg)
    if a.prompt_only:
        (work / "prompt.md").write_text(prompt, encoding="utf-8")
        print(f"{work / 'prompt.md'}（材料 {work / 'materials.json'}）")
        return
    draft = None
    while problems and attempts <= int(cfg.get_path("note.max_retries", 2)):
        attempts += 1
        if a.draft:
            draft = read_json(Path(a.draft))
        else:
            p = prompt if attempts == 1 else prompt + "\n\n# 前回の下書きの問題（直して書き直す）\n" + "\n".join(f"- {x}" for x in problems)
            draft = ai.ask_json(p, work, f"draft_{attempts}")
        md, unknown = article.build(draft, mats, cfg, kind)
        problems = checks.check_article(md, kind, mats, allowed, cfg)
        if a.draft:
            break
    write_json(work / "draft.json", draft)
    (folder / "article.md").write_text(md, encoding="utf-8")

    # 画像：ひより（見出し＋本文1〜2枚）と、表の画像（note は表を表示できない）
    img_items, tables = [], []
    if not a.no_images:
        img_items = images.plan(draft, cfg)
        write_json(work / "images_plan.json", img_items)
        img_items = images.render(folder, img_items, cfg)
    # 本文中の表（コードが入れた期待値表を除く）も画像にする。note は表を表示できないため
    for i, (heading, cols, rows) in enumerate(markdown_tables(md), 1):
        name = f"table_{i}.png"
        images.table_png(heading, cols, rows, ["※note では表を表示できないため画像にしています。"], folder / "images" / name)
        tables.append(f"images/{name}（「{heading}」の表）")
    for nm, ev in (mats.get("ev") or {}).items():
        for key, t in ev.get("tables", {}).items():
            dst = folder / "images" / f"table_ev_{ev['spec_id']}_{key}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(t["png"], dst)
            tables.append(f"images/{dst.name}（自作の期待値表・{t['label']}）")
    md = place_markers(md, img_items)
    (folder / "article.md").write_text(md, encoding="utf-8")
    kit.write_kit(folder, draft, kind, cfg, img_items, tables)
    kit.append_review(folder, kind, draft["title"], problems, mats, unknown, attempts)
    if kind == "weekly" and not problems:
        materials.save_weekly_state(mats)
    print(f"{folder}\n  タイトル：{draft['title']}\n  チェック：{'合格' if not problems else '不合格'}")
    for p in problems:
        print("  -", p)
    for c in mats["conflicts"]:
        print(f"  ! メモと調べた情報の食い違い：{c.get('machine', '')}「{c.get('memo_line')}」⇔「{c.get('found')}」（記事はメモ優先）")


if __name__ == "__main__":
    main()
