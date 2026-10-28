"""設定の読み込み。

ai-vtuber の config/channel.yaml（YouTube と共有の設定）を先に読み、
このリポジトリの config/channel.note.yaml で足りない節（note・links・ev・paths、research が無ければ research）を補う。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


class Config(dict):
    def get_path(self, dotted: str, default=None):
        cur = self
        for key in dotted.split("."):
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur

    @property
    def ai_root(self) -> Path:
        p = Path(self.get_path("paths.ai_vtuber_root", "../ai-vtuber"))
        return p if p.is_absolute() else (ROOT / p).resolve()


def load_config(note_yaml: Path | None = None) -> Config:
    own = yaml.safe_load((note_yaml or CONFIG_DIR / "channel.note.yaml").read_text(encoding="utf-8")) or {}
    cfg = Config(own)
    shared = cfg.ai_root / "config" / "channel.yaml"
    if shared.exists():
        base = yaml.safe_load(shared.read_text(encoding="utf-8")) or {}
        merged = Config(base)
        for key, val in own.items():
            if key == "research" and "research" in base:
                continue  # 格付けは YouTube と同じものを使う
            if key not in base or key in ("paths", "ev"):
                merged[key] = val
        merged["_shared_config"] = str(shared)
        return merged
    return cfg


def today() -> dt.date:
    return dt.date.today()


def read_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p: Path, obj) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
