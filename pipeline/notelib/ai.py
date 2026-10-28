"""Claude Code（`claude -p`）に JSON を書いてもらう。YouTube パイプラインの claude_cli と同じ考え方。

- プロンプトは prompts/ のテンプレートに材料を差し込んだもの
- 返ってきた文から ```json ブロックを取り出して読む。必須の項目が無ければ作り直しを頼む
- 下書きを人（または別のセッション）が書く場合は、note.py の --draft で JSON を渡せば AI を呼ばない
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import ROOT

PROMPTS = ROOT / "prompts"


def fill(template: str, values: dict) -> str:
    text = (PROMPTS / f"{template}.md").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
    return text


def extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(\{.*\})\s*```", text, re.S)
    return json.loads(m.group(1) if m else text)


def ask_json(prompt: str, log_dir: Path, name: str, tools: list[str] | None = None, timeout: int = 1800) -> dict:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude コマンドが見つからない（--draft で下書きを渡すか、Claude Code を入れる）")
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{name}_prompt.md").write_text(prompt, encoding="utf-8")
    cmd = [exe, "-p", "--output-format", "json"]
    if tools:
        cmd += ["--allowedTools", ",".join(tools)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    (log_dir / f"{name}_out.txt").write_text(r.stdout + "\n---stderr---\n" + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"claude が失敗しました（{r.returncode}）：{r.stderr[:300]}")
    res = json.loads(r.stdout)
    return extract_json(res.get("result", ""))
