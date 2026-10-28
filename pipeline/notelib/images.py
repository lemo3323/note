"""記事の画像。見出し画像1枚（1280×670）＋本文1〜2枚。入れすぎない。

- ひよりの画像：ai-vtuber の Remotion の静止画（Thumbnail コンポジション。ひより＋大きな文言）で描く。
  表情（emotion）でポーズも決まる（happy→指さし、surprised→驚き、relaxed→首かしげ など。ai-vtuber の POSE_FOR）
- 機種画像・実機画像は使わない（Thumbnail の machineImage は渡さない）
- VRM のメタ情報：商用は個人の営利利用まで可（personalProfit）、作者は運営者本人（2026-10-28 確認）→ note に使ってよい
- 表の画像：note は表を表示できないので、PIL で画像にする（ai-vtuber が無くても作れる）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config, read_json

EMOTIONS = {"happy", "surprised", "neutral", "relaxed", "angry", "sad"}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/msgothic.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]


def plan(draft: dict, cfg: Config) -> list[dict]:
    if not cfg.get_path("note.images.enabled", True):
        return []
    hw = cfg.get_path("note.images.header", {"width": 1280, "height": 670})
    bw = cfg.get_path("note.images.body", {"width": 1280, "height": 720, "max": 2})
    out, n_body = [], 0
    for im in draft.get("images", []):
        emo = im.get("emotion") if im.get("emotion") in EMOTIONS else "happy"
        if im.get("slot") == "header" and not any(o["file"] == "images/header.png" for o in out):
            out.append({"file": "images/header.png", "where": "見出し画像", "emotion": emo, "text": im.get("text", ""),
                        "subtext": im.get("subtext", ""), "width": hw["width"], "height": hw["height"]})
        elif im.get("slot", "").startswith("after:") and n_body < int(bw.get("max", 2)):
            n_body += 1
            out.append({"file": f"images/body{n_body}.png", "where": f"「{im['slot'][6:]}」の見出しの下",
                        "emotion": emo, "text": im.get("text", ""), "subtext": im.get("subtext", ""),
                        "width": bw["width"], "height": bw["height"]})
    return out


def _background(cfg: Config) -> str:
    bg = cfg.get_path("note.images.background")
    if bg:
        return bg
    # 直近の動画のサムネと同じ背景を使う
    for p in sorted((cfg.ai_root / "episodes").glob("*/_Thumbnail_props.json"), reverse=True):
        try:
            return read_json(p).get("background", "")
        except Exception:
            continue
    return ""


def render(folder: Path, items: list[dict], cfg: Config) -> list[dict]:
    """ai-vtuber があれば Remotion で描く。無ければ描かずに戻る（rendered: False）。"""
    pipe = cfg.ai_root / "pipeline"
    if not (pipe / "remotion.py").exists():
        return [{**i, "rendered": False} for i in items]
    sys.path.insert(0, str(pipe))
    from common import Episode, load_config  # type: ignore
    from remotion import render_still  # type: ignore
    ai_cfg = load_config()
    ep = Episode(id=f"note_{folder.name}", dir=folder, kind="long", format="long", date=folder.name[:10])
    bg = _background(cfg)
    done = []
    for i in items:
        out = folder / i["file"]
        out.parent.mkdir(parents=True, exist_ok=True)
        render_still(ai_cfg, ep, "Thumbnail", out, {"width": i["width"], "height": i["height"], "text": i["text"],
                                                     "subtext": i["subtext"], "emotion": i["emotion"], "background": bg})
        done.append({**i, "rendered": out.exists()})
    return done


def _font(size: int):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def table_png(title: str, columns: list[str], rows: list[list[str]], notes: list[str], out: Path) -> Path:
    """まとめ表などを画像にする（幅1280）。列幅は文字数から決める。"""
    f_t, f_h, f_b, f_s = _font(36), _font(25), _font(25), _font(21)
    d0 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    widths = []
    for ci, c in enumerate(columns):
        w = max([d0.textlength(c, font=f_h)] + [d0.textlength(str(r[ci]), font=f_b) for r in rows if ci < len(r)])
        widths.append(w + 28)
    scale = min(1.0, 1200 / sum(widths))
    widths = [w * scale for w in widths]

    def wrap(text: str, width: float, font) -> list[str]:
        lines, cur = [], ""
        for ch in str(text):
            if d0.textlength(cur + ch, font=font) > width - 24 and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        return lines + [cur]

    body = [[wrap(c, w, f_b) for c, w in zip(r, widths)] for r in rows]
    heights = [max(len(c) for c in r) * 34 + 14 for r in body]
    h = 110 + 50 + sum(heights) + 40 + 32 * sum(len(wrap(n, 1200, f_s)) for n in notes) + 30
    img = Image.new("RGB", (1280, int(h)), "#ffffff")
    d = ImageDraw.Draw(img)
    d.text((40, 30), title, font=f_t, fill="#222")
    y, x0 = 110, 40
    d.rectangle((x0, y, x0 + sum(widths), y + 50), fill="#2b4c7e")
    x = x0
    for c, w in zip(columns, widths):
        d.text((x + 12, y + 11), c, font=f_h, fill="#fff")
        x += w
    y += 50
    for i, (r, rh) in enumerate(zip(body, heights)):
        d.rectangle((x0, y, x0 + sum(widths), y + rh), fill="#f6f6f6" if i % 2 else "#ffffff")
        x = x0
        for cell, w in zip(r, widths):
            for k, ln in enumerate(cell):
                d.text((x + 12, y + 8 + k * 34), ln, font=f_b, fill="#222")
            x += w
        y += rh
    y += 20
    for n in notes:
        for ln in wrap(n, 1200, f_s):
            d.text((40, y), ln, font=f_s, fill="#333")
            y += 32
    out.parent.mkdir(parents=True, exist_ok=True)
    img.crop((0, 0, 1280, int(y + 20))).save(out)
    return out
