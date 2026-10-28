"""段階5：答え合わせに合格した機種だけ、note 用の期待値表（article.md 用の Markdown と画像）を作る。

必ず書くこと：「独自試算」「算出条件」「期待値は長い目で見た平均で、1回の結果を保証しない」
標準ボーダー＝狙い目シートのゲーム数、強気ボーダー＝等価で期待値がプラスになり始めるゲーム数（config の note.borders）
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .model import MachineModel, Point, Variant, border

FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/msgothic.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
]

CAVEAT = "期待値は長い目で見た平均の目安で、1回ごとの結果を保証するものではありません。天井まで当たらずにハマることもあります。"


def conditions_text(m: MachineModel, ev_cfg: dict, calib_note: str) -> list[str]:
    ex = "・".join(e["label"] for e in ev_cfg.get("exchanges", []))
    rows = [
        "独自試算（自作のシミュレーター。他サイトの表の写しではありません）",
        f"設定{ev_cfg.get('setting', 1)}／{ex}",
        f"やめどき：{ev_cfg.get('stop_rule')}",
        f"時給：1時間{ev_cfg.get('games_per_hour')}G（AT中も同じ速さ）で計算",
        f"コイン持ち{m.coin_mochi:g}G/50枚・AT純増{m.net_gain:g}枚/G・機械割{m.rate * 100:.1f}%・初当たり1/{1 / m.p_hit:.1f}（いずれも公表値）",
        f"AT1回の獲得：{'公表値' if m.payout_spec else '機械割から逆算し、' + calib_note}",
    ]
    rows += list(ev_cfg.get("assumptions", []))
    rows += m.notes
    return rows


def _yen(v: float) -> str:
    s = f"{abs(round(v / 10) * 10):,}円"
    return ("+" if v >= 0 else "−") + s


def markdown_table(m: MachineModel, variant: Variant, points: list[Point], ev_cfg: dict, calib_note: str,
                   sheet_border: int | None) -> str:
    agg = border(points, "toka")
    lines = [f"### {m.name}：{variant.label}の期待値表（独自試算）", "",
             "| 打ち始め | 期待値（等価） | 期待値（5.6枚・現金） | 時給（等価） | 平均投資 | 投資の目安（10回に1回はこれ以上） | 天井到達率 | 線 |",
             "|---:|---:|---:|---:|---:|---:|---:|:---|"]
    for p in points:
        mark = []
        if sheet_border is not None and p.start <= sheet_border < p.start + int(ev_cfg.get("step", 50)):
            mark.append("標準ボーダー")
        if agg is not None and p.start == agg:
            mark.append("強気ボーダー")
        lines.append(f"| {p.start}G | {_yen(p.ev['toka'])} | {_yen(p.ev['5.6'])} | {_yen(p.hourly['toka'])} | "
                     f"{round(p.invest_yen, -2):,.0f}円 | {round(p.p90_invest_yen, -2):,.0f}円 | "
                     f"{p.ceiling_rate * 100:.0f}% | {'・'.join(mark)} |")
    lines += ["", f"- 標準ボーダー：{f'{sheet_border}G（狙い目シート）' if sheet_border is not None else 'シートに記載なし'}",
              f"- 強気ボーダー：{f'{agg}G（等価で期待値がプラスになり始める所）' if agg is not None else 'なし'}",
              f"- やめどき：{ev_cfg.get('stop_rule')}", "", "**算出条件**", ""]
    lines += [f"- {c}" for c in conditions_text(m, ev_cfg, calib_note)]
    lines += ["", f"※{CAVEAT}", ""]
    return "\n".join(lines)


def _font(size: int):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def _wrap(text: str, n: int) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def png_table(m: MachineModel, variant: Variant, points: list[Point], out: Path, sheet_border: int | None,
              ev_cfg: dict) -> Path:
    """note に貼る画像（幅1280）。表の下に「独自試算」「算出条件の要約」「保証しない」を必ず入れる。"""
    agg = border(points, "toka")
    cols = ["打ち始め", "期待値(等価)", "期待値(5.6枚)", "時給(等価)", "平均投資", "天井到達率"]
    widths = [160, 220, 220, 200, 200, 200]
    rh, top = 46, 150
    h = top + rh * (len(points) + 1) + 400
    img = Image.new("RGB", (1280, h), "#ffffff")
    d = ImageDraw.Draw(img)
    f_title, f_head, f_body, f_small = _font(40), _font(26), _font(26), _font(21)
    d.text((40, 30), f"{m.name}", font=f_title, fill="#222")
    d.text((40, 88), f"{variant.label}の期待値表（独自試算・設定1）", font=f_head, fill="#444")
    x0 = 40
    y = top
    d.rectangle((x0, y, x0 + sum(widths), y + rh), fill="#2b4c7e")
    x = x0
    for c, w in zip(cols, widths):
        d.text((x + 12, y + 9), c, font=f_head, fill="#fff")
        x += w
    for i, p in enumerate(points):
        y += rh
        fill = "#fff6d6" if (sheet_border is not None and p.start <= sheet_border < p.start + 50) else (
            "#e6f2ff" if p.start == agg else ("#f6f6f6" if i % 2 else "#ffffff"))
        d.rectangle((x0, y, x0 + sum(widths), y + rh), fill=fill)
        vals = [f"{p.start}G", _yen(p.ev["toka"]), _yen(p.ev["5.6"]), _yen(p.hourly["toka"]),
                f"{round(p.invest_yen, -2):,.0f}円", f"{p.ceiling_rate * 100:.0f}%"]
        x = x0
        for v, w in zip(vals, widths):
            color = "#c0392b" if v.startswith("−") else "#222"
            d.text((x + 12, y + 9), v, font=f_body, fill=color)
            x += w
    y += rh + 16
    notes = [
        f"黄色＝標準ボーダー（狙い目シート {sheet_border}G）" if sheet_border is not None else "",
        f"青＝強気ボーダー（等価で期待値がプラスになり始める {agg}G）" if agg is not None else "",
        f"算出条件：設定1・{ev_cfg.get('stop_rule')}・1時間{ev_cfg.get('games_per_hour')}G・5.6枚は現金投資・閉店は考えない",
        "独自試算。" + CAVEAT,
    ]
    for n in [n for n in notes if n]:
        for part in _wrap(n, 54):
            d.text((40, y), part, font=f_small, fill="#333")
            y += 32
    img = img.crop((0, 0, 1280, y + 20))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
