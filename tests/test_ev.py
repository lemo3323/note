"""期待値シミュレーターと生存時間分析のテスト（標準ライブラリの unittest）。"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from ev.model import MachineModel, Variant, border, hazard_for_mean, implied_payout, simulate, situational_rate  # noqa: E402
from ev.survival import Record, compare_to_model, kaplan_meier  # noqa: E402

EV_CFG = {"trials": 100000, "games_per_hour": 840, "coin_price_yen": 20, "step": 50,
          "exchanges": [{"key": "toka", "yen_per_coin": 20.0}, {"key": "5.6", "yen_per_coin": 17.857}],
          "uncertainty": {"payout_pct": 5, "coin_mochi_g": 0.5}}


def machine(**kw):
    base = dict(id="t", name="試験機", ceiling_type="game", p_hit=1 / 350, normal_ceiling=1000, rate=0.979,
                coin_mochi=31.0, net_gain=9.0)
    base.update(kw)
    return MachineModel(**base)


class TestModel(unittest.TestCase):
    def test_hazard_matches_mean(self):
        h = hazard_for_mean(350, 1000)
        self.assertAlmostEqual((1 - (1 - h) ** 1000) / h, 350, places=3)

    def test_identity_reproduces_payout_rate(self):
        # 逆算した獲得枚数（係数なし）で 0G から天井まで打つと、全体の機械割に戻る
        m = machine()
        self.assertAlmostEqual(situational_rate(m, 0, 1000, trials=400000), 0.979, places=3)

    def test_implied_payout_formula(self):
        a = implied_payout(350, 31.0, 0.979, 9.0)
        loss = 350 * 50 / 31.0
        self.assertAlmostEqual(a - loss, (0.979 - 1) * 3 * (350 + a / 9.0), places=6)

    def test_ev_increases_with_start(self):
        pts = simulate(machine(payout_factor=0.93), Variant("normal", "通常", [(1000, 1.0)]), EV_CFG)
        evs = [p.ev["toka"] for p in pts]
        self.assertTrue(all(b > a for a, b in zip(evs, evs[1:])))
        self.assertTrue(all(p.ev["5.6"] < p.ev["toka"] for p in pts))
        self.assertIsNotNone(border(pts))

    def test_short_ceiling_is_shifted_normal(self):
        # 一定の当たりやすさなら、天井600Gの0Gは天井1000Gの400Gと同じ
        m = machine(payout_factor=0.93)
        n = {p.start: p.ev["toka"] for p in simulate(m, Variant("n", "", [(1000, 1.0)]), EV_CFG)}
        s = {p.start: p.ev["toka"] for p in simulate(m, Variant("s", "", [(600, 1.0)]), EV_CFG)}
        self.assertAlmostEqual(s[0], n[400], delta=120)

    def test_ceiling_choice_posterior(self):
        # 天井の振り分けがあるとき、短い天井を過ぎたら長い天井だけが残る
        m = machine(normal_ceiling=1480, p_hit=1 / 530)
        v = Variant("r", "", [(510, 0.152), (1000, 0.203), (1480, 0.645)])
        pts = {p.start: p for p in simulate(m, v, EV_CFG, starts=[500, 600])}
        # 500G：510G天井（15.2%）はほぼ到達、1000G・1480G天井は当たらなければ到達 → 約35%
        self.assertAlmostEqual(pts[500].ceiling_rate, 0.35, delta=0.03)
        # 600G：510G天井は否定され、1000G・1480Gだけ → 約28%
        self.assertAlmostEqual(pts[600].ceiling_rate, 0.285, delta=0.03)


class TestSurvival(unittest.TestCase):
    def test_km_handles_censoring(self):
        # 当たりやすさ一定（1/300）の合成データ。3割を途中で打ち切っても平均ゲーム数を当てられる
        rng = np.random.default_rng(3)
        h, ceiling, start = 1 / 300, 1000, 400
        recs = []
        for _ in range(20000):
            g = min(int(rng.geometric(h)), ceiling - start)
            if rng.random() < 0.3:
                cut = int(rng.integers(1, ceiling - start))
                if cut < g:
                    recs.append(Record(start, cut, False))
                    continue
            recs.append(Record(start, g, True))
        res = compare_to_model(recs, start, ceiling, h)
        self.assertLess(abs(res["diff_games"]), 8)
        # 打ち切りを「当たり」と数えると明らかにずれる（打ち切りの扱いが効いていることの確認）
        naive = kaplan_meier([Record(r.start, r.played, True) for r in recs], ceiling - start)
        self.assertGreater(abs(float(np.sum(naive[:-1])) - res["mean_games_model"]), 20)


if __name__ == "__main__":
    unittest.main()
