"""逆算した平均獲得枚数を「深いゲーム数から打つ人の獲得」に直す係数 k を推定する。

使うのはメーカー公表の状況別機械割（仕様の situational_rate。例：リコリコの「300Gから天井まで 100.3%」）だけ。
他サイトの期待値表は使わない（段階4の答え合わせが独立した確認にならなくなるため）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import MachineModel, from_spec, situational_rate


@dataclass
class Calibration:
    factor: float
    rows: list[dict]          # 機種・開始G・公表値・計算値
    sources: list[str]        # 使った機種
    names: list[str] = None   # 使った機種の名前

    @property
    def note(self) -> str:
        if not self.rows:
            return "状況別機械割のある機種が無いため係数1.0（補正なし）"
        mids = "、".join(sorted(set(self.names or self.sources)))
        return (f"係数{self.factor:.3f}（{mids}のメーカー公表の状況別機械割{len(self.rows)}点に合わせた。"
                f"最大のずれ{max(abs(r['model'] - r['published']) for r in self.rows):.1f}ポイント）")


def fit(specs: list[dict]) -> Calibration:
    targets = []
    for spec in specs:
        sr = spec["items"].get("situational_rate", {})
        if sr.get("confidence") not in ("high", "single"):
            continue
        m = from_spec(spec)
        for r in sr.get("value") or []:
            if r.get("when"):        # 上位CZ失敗後など、天井が特殊な状況は使わない
                continue
            if int(r["to_ceiling"]) != m.normal_ceiling:
                continue
            targets.append((spec["id"], m, int(r["from"]), float(r["rate"]) / 100.0))
    if not targets:
        return Calibration(1.0, [], [])
    best, best_err = 1.0, float("inf")
    for k in np.arange(0.80, 1.0501, 0.0025):
        err = 0.0
        for _id, m, start, pub in targets:
            m.payout_factor = float(k)
            err += (situational_rate(m, start, m.normal_ceiling, trials=200000) - pub) ** 2
        if err < best_err:
            best, best_err = float(k), err
    rows = []
    for mid, m, start, pub in targets:
        m.payout_factor = best
        rows.append({"machine": mid, "from": start, "published": pub * 100,
                     "model": situational_rate(m, start, m.normal_ceiling) * 100})
    return Calibration(round(best, 4), rows, [t[0] for t in targets], [t[1].name for t in targets])
