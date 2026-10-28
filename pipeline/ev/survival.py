"""段階3：当たり履歴から「〇Gから打ったとき何Gで当たるか」の分布を作る（生存時間分析）。

- 1件 ＝ （打ち始めのゲーム数, 打ったゲーム数, 当たったか）。閉店で当たらずに終わったものは「打ち切り」として扱う
  （打ち切りを「当たらなかった」と数えると当たりにくく見え、捨てると当たりやすく見えるため）
- Kaplan-Meier 法で「t G 回しても当たっていない割合」S(t) を出し、シミュレーション（設定1）と比べる
- 実データには高設定や据え置きが混ざるので、差は「実際のホールではこう」という参考値としてだけ出す

使ってよいデータは docs/data_sources.md で「よい」のサイトだけ（2026-10-28 時点で 0 件）。
運営者の実戦記録は使わない（2026-10-28 決定）。今はテスト（合成データ）だけで動かす。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Record:
    start: int        # 打ち始めのゲーム数（天井までのカウンター）
    played: int       # 打ったゲーム数
    hit: bool         # 当たって終わったか（False＝閉店などで打ち切り）


def kaplan_meier(records: list[Record], horizon: int) -> np.ndarray:
    """S[t]（t=0..horizon）：t G 回しても当たっていない割合。"""
    played = np.array([r.played for r in records])
    hit = np.array([r.hit for r in records], dtype=bool)
    surv = np.ones(horizon + 1)
    s = 1.0
    for t in range(1, horizon + 1):
        at_risk = np.sum(played >= t)
        if at_risk == 0:
            surv[t:] = s
            break
        events = np.sum((played == t) & hit)
        s *= 1.0 - events / at_risk
        surv[t] = s
    return surv


def from_start(records: list[Record], start: int, width: int = 25) -> list[Record]:
    """打ち始めが start±width の記録だけ。"""
    return [r for r in records if abs(r.start - start) <= width]


def compare_to_model(records: list[Record], start: int, ceiling: int, hazard: float) -> dict:
    """実データの S(t) とモデル（一定の当たりやすさ・天井）の S(t) の差。"""
    horizon = ceiling - start
    km = kaplan_meier(records, horizon)
    t = np.arange(horizon + 1)
    model = (1 - hazard) ** t
    model[-1] = 0.0  # 天井で必ず当たる
    real_mean = float(np.sum(km[:-1]))   # 平均ゲーム数 ＝ ΣS(t)
    model_mean = float(np.sum(model[:-1]))
    return {"start": start, "n": len(records), "n_censored": sum(not r.hit for r in records),
            "mean_games_real": real_mean, "mean_games_model": model_mean,
            "diff_games": real_mean - model_mean}
