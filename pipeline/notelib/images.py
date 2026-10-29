"""記事の画像。見出し画像1枚（1280×670）＋ひよりのセリフ（各セクションの一言）ごとに1枚（1280×600）。

- ひよりの画像：ai-vtuber の Remotion の静止画（Thumbnail コンポジション。左に文言・右にひより）で描く。
  セリフの画像は文言を空にして描き、左半分に PIL で吹き出し（セリフ）を重ねる（ai-vtuber 側は変えない）
  表情（emotion）でポーズも決まる（happy→指さし、surprised→驚き、relaxed→首かしげ など。ai-vtuber の POSE_FOR）
- 機種画像・実機画像は使わない（Thumbnail の machineImage は渡さない）
- VRM のメタ情報：商用は個人の営利利用まで可（personalProfit）、作者は運営者本人（2026-10-28 確認）→ note に使ってよい
- 表の画像：note は表を表示できないので、PIL で画像にする（ai-vtuber が無くても作れる）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config, read_json

EMOTIONS = {"happy", "surprised", "neutral", "relaxed", "angry", "sad"}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/msgothic.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]


SERIF_SIZE = (1280, 600)
_AUTO_EMOTIONS = ["happy", "relaxed", "surprised", "neutral"]


def _auto_emotion(line: str, n: int) -> str:
    if "！" in line or "!" in line:
        return "happy"
    if "？" in line or "?" in line:
        return "relaxed"
    return _AUTO_EMOTIONS[n % len(_AUTO_EMOTIONS)]


def plan(draft: dict, cfg: Config) -> list[dict]:
    """見出し画像1枚＋ひよりのセリフ（各セクションの hiyori）ごとに1枚。"""
    if not cfg.get_path("note.images.enabled", True):
        return []
    hw = cfg.get_path("note.images.header", {"width": 1280, "height": 670})
    sw = cfg.get_path("note.images.serif", {"width": SERIF_SIZE[0], "height": SERIF_SIZE[1]})
    out = []
    head = next((im for im in draft.get("images", []) if im.get("slot") == "header"), None)
    if head:
        emo = head.get("emotion") if head.get("emotion") in EMOTIONS else "happy"
        out.append({"file": "images/header.png", "kind": "header", "where": "見出し画像", "emotion": emo,
                    "text": head.get("text", ""), "subtext": head.get("subtext", ""),
                    "width": hw["width"], "height": hw["height"]})
    n = 0
    for sec in list(draft.get("free_sections", [])) + list(draft.get("paid_sections", [])):
        line = (sec.get("hiyori") or "").strip()
        if not line:
            continue
        n += 1
        emo = sec.get("hiyori_emotion") if sec.get("hiyori_emotion") in EMOTIONS else _auto_emotion(line, n)
        out.append({"file": f"images/serif_{n}.png", "kind": "serif", "where": f"「{sec['heading']}」のひよりのセリフ",
                    "heading": sec["heading"], "line": line, "emotion": emo, "text": " ", "subtext": "",
                    "width": sw["width"], "height": sw["height"]})
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
    """ai-vtuber があれば Remotion（Thumbnail コンポジション）でひよりを描き、セリフの画像は吹き出しを重ねる。
    無ければ、配置を確かめるための仮の画像（ひよりの所は枠だけ）を作る（rendered: False）。"""
    pipe = cfg.ai_root / "pipeline"
    available = (pipe / "remotion.py").exists()
    done = []
    if available:
        sys.path.insert(0, str(pipe))
        from common import Episode, load_config  # type: ignore
        from remotion import render_still  # type: ignore
        ai_cfg = load_config()
        ep = Episode(id=f"note_{folder.name}", dir=folder, kind="long", format="long", date=folder.name[:10])
        bg = _background(cfg)
    for i in items:
        out = folder / i["file"]
        out.parent.mkdir(parents=True, exist_ok=True)
        if available:
            # Thumbnail は左に文言・右にひより。セリフの画像は文言を空にして、左に吹き出しを重ねる
            render_still(ai_cfg, ep, "Thumbnail", out, {"width": i["width"], "height": i["height"], "text": i["text"],
                                                         "subtext": i["subtext"], "emotion": i["emotion"], "background": bg})
            if i["kind"] == "serif" and out.exists():
                speech_bubble(Image.open(out).convert("RGB"), i["line"]).save(out)
            done.append({**i, "rendered": out.exists()})
        else:
            base = _placeholder(i["width"], i["height"], i["emotion"])
            img = speech_bubble(base, i["line"]) if i["kind"] == "serif" else _header_text(base, i["text"], i["subtext"])
            img.save(out)
            done.append({**i, "rendered": False})
    return done


_NO_LINE_START = set("ー」』）)、。，．！？!?・ぁぃぅぇぉっゃゅょァィゥェォッャュョ〜")


def _wrap_px(d: ImageDraw.ImageDraw, text: str, font, width: float) -> list[str]:
    """吹き出しの改行。文の終わり（！？。）で改行し、最後の行が1〜2文字だけにならないようにする。"""
    lines = []
    for part in re.split(r"(?<=[！？。!?])\s*", text):
        cur = ""
        for ch in part:
            # 行頭に来てはいけない文字（ー・」・。など）は、少しはみ出しても前の行に付ける
            if d.textlength(cur + ch, font=font) > width and cur and ch not in _NO_LINE_START:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
    # 最後の行が短すぎるときは、前の行の終わりの文字を送る
    while len(lines) >= 2 and len(lines[-1]) <= 2 and len(lines[-2]) > 3 and lines[-2][-1] not in "！？。!?":
        lines[-2], lines[-1] = lines[-2][:-1], lines[-2][-1] + lines[-1]
        while lines[-1][0] in _NO_LINE_START and len(lines[-2]) > 3:
            lines[-2], lines[-1] = lines[-2][:-1], lines[-2][-1] + lines[-1]
    return lines


def speech_bubble(img: Image.Image, line: str) -> Image.Image:
    """画像の左半分に、ひよりのセリフの吹き出しを描く（しっぽは右のひよりへ）。"""
    W, H = img.size
    u = H / 600
    d = ImageDraw.Draw(img)
    size = int(50 * u)
    font = _font(size)
    box_w = int(W * 0.47)
    lines = _wrap_px(d, line, font, box_w - 80 * u)
    while len(lines) > 4 and size > 28:
        size -= 4
        font = _font(size)
        lines = _wrap_px(d, line, font, box_w - 80 * u)
    lh = int(size * 1.45)
    box_h = int(lh * len(lines) + 80 * u)
    x0, y0 = int(40 * u), int((H - box_h) / 2)
    x1, y1 = x0 + box_w, y0 + box_h
    border, fill = "#3b3b58", "#ffffff"
    tail = [(x1 - 6, y0 + box_h * 0.38), (x1 + 70 * u, y0 + box_h * 0.5), (x1 - 6, y0 + box_h * 0.62)]
    d.rounded_rectangle((x0, y0, x1, y1), radius=int(40 * u), fill=fill, outline=border, width=int(6 * u))
    d.polygon(tail, fill=fill)
    d.line([tail[0], tail[1], tail[2]], fill=border, width=int(6 * u))
    name_font = _font(int(30 * u))
    nw = d.textlength("ひより", font=name_font)
    d.rounded_rectangle((x0 + 30 * u, y0 - 26 * u, x0 + 30 * u + nw + 40 * u, y0 + 26 * u), radius=int(26 * u),
                        fill="#ff6fa3")
    d.text((x0 + 50 * u, y0 - 18 * u), "ひより", font=name_font, fill="#ffffff")
    ty = y0 + 40 * u
    for ln in lines:
        d.text((x0 + 40 * u, ty), ln, font=font, fill="#2b2b3a")
        ty += lh
    return img


def _placeholder(w: int, h: int, emotion: str) -> Image.Image:
    """ai-vtuber が無い環境用の仮の背景。右側の枠がひよりの描かれる位置（Thumbnail と同じ右寄せ）。"""
    img = Image.new("RGB", (w, h), "#fde8f0")
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(253 - 30 * t), int(232 - 20 * t), int(240 - 5 * t)))
    x0, x1 = int(w * 0.6), int(w * 0.95)
    d.rounded_rectangle((x0, int(h * 0.08), x1, int(h * 0.95)), radius=30, outline="#b07090", width=4)
    f = _font(int(h / 20))
    d.text((x0 + 30, int(h * 0.45)), f"ひより（{emotion}）", font=f, fill="#b07090")
    d.text((x0 + 30, int(h * 0.45) + h / 14), "PC で描き直す", font=f, fill="#b07090")
    return img


def _header_text(img: Image.Image, text: str, subtext: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    W, H = img.size
    f = _font(int(H / 7))
    y = int(H * 0.3)
    for ln in _wrap_px(d, text, f, W * 0.55):
        d.text((48, y), ln, font=f, fill="#ffffff", stroke_width=10, stroke_fill="#3b3b58")
        y += int(H / 6)
    if subtext:
        d.text((48, y + 10), subtext, font=_font(int(H / 16)), fill="#3b3b58")
    return img


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
