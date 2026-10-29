"""AI が書いた下書き（draft.json）と材料から article.md を組み立てる。

AI が書くのは本文の言葉だけ。次はコードが決まった形で入れる（<!-- auto --> で囲む）：
- 「ここから有料」の区切り（値段つき）
- 運営者の考え方（標準ボーダー・強気ボーダー。根拠は狙い目シートと config/strategy_notes.md だけ）
- 自作期待値表（段階4に合格した状況だけ）
- 参考（材料にある出典だけ）、注意書き、有料記事・月額への案内
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml

from .checks import PAYWALL
from .config import DATA_DIR, Config

SITE_NAMES = {
    "chonborista.com": "ちょんぼりすた", "p-town.dmm.com": "DMMぱちタウン", "nana-press.com": "なな徹",
    "1geki.jp": "一撃", "altema.jp": "アルテマ", "haienakun.com": "ハイエナくん", "p-world.co.jp": "P-WORLD",
    "note.com/g1slotapple": "たられば（note）", "note.com/kitaitilabo": "シオン＠期待値研究所（note）",
    "wosaruslot.wpcomstaging.com": "ヲ猿", "ameblo.jp/wosarusan": "ヲ猿（アメブロ）",
}

KIND_LABEL = {"machine": "単発記事", "special": "特殊狙い・優遇狙い", "new_machine": "新台初週速報",
              "weekly": "月額マガジン", "free": "無料記事"}


def site_name(url: str) -> str:
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    seg = p.path.strip("/").split("/")[0]
    return SITE_NAMES.get(f"{host}/{seg}") or SITE_NAMES.get(host) or host


def price_for(kind: str, cfg: Config) -> int | None:
    if kind in ("machine", "special", "new_machine"):
        return int(cfg.get_path("note.price_single", 200))
    if kind == "weekly":
        return int(cfg.get_path("note.price_monthly", 590))
    return None


def _auto(tag: str, body: str) -> str:
    return f"<!-- auto:{tag} -->\n{body.rstrip()}\n<!-- /auto -->"


def borders_for(machine: dict) -> dict:
    p = DATA_DIR / "sheet" / "_borders.yaml"
    if not p.exists():
        return {}
    allb = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    for mid, b in allb.items():
        if any(v.get("sheet") == machine["name"] for v in b.values()):
            return b
    return {}


def operator_view(mats: dict, cfg: Config, kind: str = "machine") -> str:
    """運営者の考え方。狙い目シートと strategy_notes.md に書いてあることだけ。"""
    notes = mats.get("strategy_notes") or []
    lines = ["## 運営者の考え方（標準ボーダーと強気ボーダー）", ""]
    if notes:
        lines.append("運営者のメモ（立ち回りの考え方）から：")
        lines += [f"- {n.split('] ', 1)[-1]}" for n in notes]
        lines.append("")
    if kind != "machine":
        with_ev = [m["name"] for m in mats.get("machines", []) if ((mats.get("ev") or {}).get(m["name"]) or {}).get("tables")]
        lines.append("- 標準ボーダー：各機種のところに書いた打ち始め（狙い目シートの値）")
        lines.append("- 強気ボーダー：" + (f"自作期待値表がある機種（{'、'.join(with_ev)}）は下の表のとおり" if with_ev else
                                       "自作期待値表がある機種だけ出します（この記事の機種は、まだ準備中です）"))
        return _auto("operator", "\n".join(lines))
    for m in mats.get("machines", []):
        ev = (mats.get("ev") or {}).get(m["name"]) or {}
        b = borders_for(m)
        lines.append(f"**{m['name']}**")
        if b:
            for key, v in b.items():
                label = "通常" if key == "normal" else "設定変更時・短縮時"
                lines.append(f"- 標準ボーダー・{label}：{v['games']}G〜（狙い目シートの値）")
        else:
            lines.append("- 標準ボーダー：上の「条件別の狙い目」のゲーム数（狙い目シートの値）")
        tables = ev.get("tables") or {}
        if tables:
            for key, t in tables.items():
                if t.get("border_toka") is not None:
                    lines.append(f"- 強気ボーダー・{t['label']}：{t['border_toka']}G〜（自作期待値表で、等価なら期待値がプラスになり始める所）")
        else:
            lines.append("- 強気ボーダー：この機種の自作期待値表はまだ準備中のため、出していません（答え合わせに合格したら追記します）")
        lines.append("")
    if not notes:
        lines.append("（運営者の立ち回りメモはまだありません）")
    return _auto("operator", "\n".join(lines))


def ev_section(mats: dict) -> str:
    parts = []
    for name, ev in (mats.get("ev") or {}).items():
        for key, t in (ev.get("tables") or {}).items():
            md = t["md"]
            first, _, rest = md.partition("\n")
            # note は表を表示できないので、表の画像（note.py が images/ に写す）を貼る場所の目印を入れる
            parts.append(f"{first}\n\n［この表は画像 images/table_ev_{ev['spec_id']}_{key}.png を貼る］\n{rest}")
    if not parts:
        return ""
    return _auto("ev", "## 自作の期待値表（独自試算）\n\n" + "\n".join(parts))


def references(urls: list[str]) -> str:
    seen, rows = set(), []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        rows.append(f"- {site_name(u)}：{u}")
    body = "## 参考\n\n他サイトの情報は、事実（数値・条件・仕様）だけを自分の言葉でまとめています。\n\n" + "\n".join(rows)
    return _auto("refs", body)


def disclaimers(cfg: Config) -> str:
    return _auto("disclaimer", "---\n\n" + "\n".join(f"※{d}" for d in cfg.get_path("note.disclaimers", []) or []))


def guide_to_paid(cfg: Config, mats: dict) -> str:
    """無料記事の最後：有料記事と月額への案内。URL が空なら「準備中」。"""
    mag = cfg.get_path("links.paid_magazine") or ""
    arts = cfg.get_path("links.articles") or {}
    lines = ["## もっと詳しく知りたい方へ", ""]
    # 機種ガイド（機種が1つ）ならその機種の完全版を先に案内する。機種が多いテーマの記事は、URL がある機種だけ
    ms = mats.get("machines", [])
    for m in ms:
        url = arts.get(m["id"]) or arts.get(m["name"])
        if not url and len(ms) > 1:
            continue
        url = url or "（記事の URL はここに入ります）"
        has_ev = bool(((mats.get("ev") or {}).get(m["name"]) or {}).get("tables"))
        lines.append(f"- **{m['name']}の天井・狙い目・やめどき完全版（単発記事・{cfg.get_path('note.price_single')}円）**："
                     "何ゲームから打つか（条件別の狙い目）・やめどき・特殊狙い・運営者のボーダー"
                     f"{'・自作の期待値表' if has_ev else ''}をまとめています。{url}")
    lines.append(f"- **機種ごとの完全版（単発記事・{cfg.get_path('note.price_single')}円）**：天井・条件別の狙い目・やめどき・特殊狙い・運営者のボーダーまで1機種ずつまとめています。")
    named = {m["id"] for m in ms} | {m["name"] for m in ms}
    listed = [f"  - {k}：{v}" for k, v in arts.items() if v and k not in named]
    lines += listed or ["  - （記事の URL はここに入ります）"]
    lines.append(f"- **月額マガジン（{cfg.get_path('note.magazine_name')}・創刊メンバー{cfg.get_path('note.price_monthly')}円／月）**："
                 "毎週の狙い目まとめと、狙い目が変わった台のお知らせ。単発記事も読めます。"
                 f"{mag or '（マガジンの URL はここに入ります）'}")
    lines.append(f"  - 会員が{cfg.get_path('note.monthly_raise_at')}人を超えたら{cfg.get_path('note.price_monthly_after')}円／月になります")
    return _auto("guide", "\n".join(lines))


def build(draft: dict, mats: dict, cfg: Config, kind: str) -> tuple[str, list[str]]:
    """(article.md, 使った出典URL)"""
    known = {s["url"] for f in mats.get("facts", []) for s in f.get("sources", [])}
    used, unknown = [], []
    out = [f"# {draft['title']}", ""]
    for ln in draft.get("lead", []):
        out.append(ln)
    out.append("")
    if draft.get("shallowest"):
        out += [f"**いちばん浅い狙い目：** {draft['shallowest']}", ""]
    for sec in draft.get("free_sections", []):
        out += [f"## {sec['heading']}", ""]
        if sec.get("hiyori"):
            out += [f"> ひより：{sec['hiyori']}", ""]
        out += [sec["body"].rstrip(), ""]
        for u in sec.get("sources", []):
            (used if u in known else unknown).append(u)
    price = price_for(kind, cfg)
    paid = draft.get("paid_sections", [])
    if price is not None:
        toc = [s["heading"] for s in paid] + ["運営者の考え方（標準ボーダーと強気ボーダー）"]
        if ev_section(mats):
            toc.append("自作の期待値表（独自試算）")
        toc += ["注意点", "まとめ", "参考"]
        out += ["## 目次（有料部分）", ""] + [f"{i}. {h}" for i, h in enumerate(toc, 1)] + [""]
        out += [_auto("paywall", f"---\n\n**▼ {PAYWALL}（{price}円）**\n\n---"), ""]
    for sec in paid:
        out += [f"## {sec['heading']}", ""]
        if sec.get("hiyori"):
            out += [f"> ひより：{sec['hiyori']}", ""]
        out += [sec["body"].rstrip(), ""]
        for u in sec.get("sources", []):
            (used if u in known else unknown).append(u)
    if price is not None:
        out += [operator_view(mats, cfg, kind), ""]
        evs = ev_section(mats)
        if evs:
            out += [evs, ""]
    if draft.get("cautions"):
        out += ["## 注意点", ""] + [f"- {c}" for c in draft["cautions"]] + [""]
    out += ["## まとめ", ""]
    st = draft.get("summary_table")
    if st and st.get("rows"):
        out.append("| " + " | ".join(st["columns"]) + " |")
        out.append("|" + "|".join("---" for _ in st["columns"]) + "|")
        out += ["| " + " | ".join(str(c) for c in r) + " |" for r in st["rows"]]
        out.append("")
    if draft.get("closing"):
        out += [draft["closing"].rstrip(), ""]
    if kind == "free":
        out += [guide_to_paid(cfg, mats), ""]
    if used:
        out += [references(used), ""]
    out += [disclaimers(cfg), ""]
    return "\n".join(out), unknown
