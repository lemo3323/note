"""note に手で貼るためのキット（note_kit.txt）と、承認の記録（review_log.md）。"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .article import KIND_LABEL, price_for
from .config import ROOT, Config


def write_kit(folder: Path, draft: dict, kind: str, cfg: Config, images: list[dict], tables: list[str]) -> Path:
    price = price_for(kind, cfg)
    tags = list(dict.fromkeys((draft.get("hashtags") or []) + list(cfg.get_path("note.hashtags_base", []) or [])))[:10]
    lines = [
        f"■ 種類\n{KIND_LABEL.get(kind, kind)}",
        f"■ タイトル\n{draft['title']}",
        "■ 値段\n" + (f"{price}円（有料記事）" if kind in ("machine", "special", "new_machine") else
                     (f"月額マガジン（{cfg.get_path('note.magazine_name')}）に入れる。マガジンの値段：創刊メンバー{cfg.get_path('note.price_monthly')}円／月"
                      if kind == "weekly" else "無料")),
        "■ ハッシュタグ（note の「ハッシュタグを追加」に1つずつ）\n" + " ".join(f"#{t}" for t in tags),
        "■ 無料／有料の区切り\n" + ("本文の「▼ ここから有料」の段落のすぐ下に、note の「有料エリア設定」の線を合わせる。"
                               "線より上（特徴・いちばん浅い狙い目・目次）は誰でも読める。"
                               if kind != "free" else "なし（無料記事）"),
        "■ 貼り方\n"
        "1. note で「投稿」→「テキスト」\n"
        "2. 見出し画像：images/header.png を「画像を追加」から（1280×670）\n"
        "3. 「> ひより：…」の一言は、目印のところの images/serif_N.png（ひより＋吹き出し）を画像として貼り、キャプションに同じセリフを書く\n"
        "4. article.md の本文を、見出し（## のつく行）ごとに貼る。note は「## 」で大見出し、「- 」で箇条書き、「> 」で引用、「---」で区切り線になる\n"
        "5. note は表（| で区切った行）を表示できない。表は下の「表の画像」を、その表の場所に画像として貼る\n"
        "6. 「<!-- auto: … -->」「<!-- /auto -->」の行は貼らない（コードが入れた部分の目印）\n"
        "7. 有料記事は「公開設定」で「有料」にして値段を入れ、「有料エリア設定」の線を区切りの位置に合わせる\n"
        "8. 公開前に review_log.md のチェック結果と、本文の数字・注意書きをもう一度確認する",
    ]
    if images:
        lines.append("■ 画像（ひより）\n" + "\n".join(f"- {i['file']}：{i.get('where', '')}（{i.get('emotion', '')}）"
                                               + ("" if i.get("rendered") else "　※仮の画像（ひよりは未描画）") for i in images)
                     + ("" if all(i.get("rendered") for i in images) else
                        f"\n仮の画像は PC で `python pipeline/note.py --render-images {folder.name}` を実行すると、ひよりを描いた画像に置き換わる"))
    if tables:
        lines.append("■ 表の画像\n" + "\n".join(f"- {t}" for t in tables))
    p = folder / "note_kit.txt"
    p.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return p


def append_review(folder: Path, kind: str, title: str, problems: list[str], mats: dict, unknown_urls: list[str],
                  attempts: int) -> Path:
    """フォルダの review_log.md と、全体の notes/review_log.md の両方に書く。"""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    conflicts = mats.get("conflicts") or []
    dropped = mats.get("dropped") or []
    status = "自動チェック合格・運営者の確認待ち（読んで問題なければ手動で公開）" if not problems else "自動チェック不合格（公開しない）"
    lines = [f"## {now} {KIND_LABEL.get(kind, kind)}：{title}", "",
             f"- フォルダ：{folder.name}", f"- 状態：**{status}**", f"- 作成の回数：{attempts}"]
    lines += [f"- 問題：{p}" for p in problems] or ["- 問題：なし"]
    for c in conflicts:
        lines.append(f"- メモと調べた情報の食い違い（記事はメモを優先）：{c.get('machine', '')}「{c.get('memo_line')}」⇔「{c.get('found')}」")
    if dropped:
        lines.append(f"- 不採用にした調べた情報：{len(dropped)}件（理由：{'、'.join(sorted({d.get('why', '') for d in dropped}))}）")
    for u in unknown_urls:
        lines.append(f"- 材料に無い出典を本文が挙げたので参考から外した：{u}")
    for n in mats.get("research_notes", []):
        lines.append(f"- 調査メモ：{n}")
    for w in mats.get("warnings", []):
        lines.append(f"- 注意：{w}")
    lines.append("- 運営者の承認：未（公開したら「承認：済 日付」を書き足す）")
    entry = "\n".join(lines) + "\n\n"
    local = folder / "review_log.md"
    local.write_text((local.read_text(encoding="utf-8") if local.exists() else "# 確認の記録\n\n") + entry, encoding="utf-8")
    glob_log = ROOT / "notes" / "review_log.md"
    glob_log.write_text((glob_log.read_text(encoding="utf-8") if glob_log.exists() else "# note 記事の確認の記録（全体）\n\n") + entry,
                        encoding="utf-8")
    return local
