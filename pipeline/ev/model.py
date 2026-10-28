"""段階2：天井の種類ごとの型を持つ期待値シミュレーター。

型（ceiling_type）
- game        ：ゲーム数天井（AT間・GG間など）。天井でAT
- game_cycle  ：ゲーム数天井＋周期天井。周期の長さが公開されていないので、ゲーム数天井だけで計算する（周期は考えない）
- cz_st       ：CZ間天井（CZに当選するだけ）＋ST間天井（STに当選）。CZ成功率が公開されていないので、ST間天井で計算する
- through     ：CZスルー回数の天井（N回失敗の次でAT）。今回の5機種には無い。CZ確率・成功率が要る
- point       ：ポイント天井（1Gあたり平均 rate pt 貯まり、規定ptでAT）。ゲーム数に直して game と同じに扱う

どの型も「天井までのあいだ当たりやすさは一定」とし、その値は
    天井込みの平均初当たりゲーム数 ＝ 公表の初当たり確率の逆数
になるように決める（天井到達率と平均投資が初当たり確率と矛盾しない）。

AT1回あたりの平均獲得枚数 A は、公開値があればそれを使い、無ければ機械割から逆算する：
    1回の初当たりまでの収支 ＝ A − N×50/C ＝ (R−1)×3×(N＋A/j)
    → A ＝ N×(50/C＋3(R−1)) ／ (1−3(R−1)/j)
  N：平均初当たりゲーム数（＝1/初当たり確率）、C：コイン持ち（G/50枚）、R：機械割、j：AT純増（枚/G）
逆算した A には、AT後の引き戻しや浅いゲーム数での当たりやすさの分も入っているので、
深いゲーム数から打つ人の獲得に直す係数 k を掛ける（calibrate.py でメーカー公表の状況別機械割から推定）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def prob(text: str | float | None) -> float | None:
    """'1/351.9' → 1/351.9"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    a, _, b = str(text).partition("/")
    return float(a) / float(b)


def hazard_for_mean(mean_games: float, ceiling: int) -> float:
    """天井 ceiling まで一定の当たりやすさ h で、平均初当たりゲーム数が mean_games になる h。"""
    if mean_games >= ceiling:
        raise ValueError("平均初当たりゲーム数が天井以上")

    def mean_of(h: float) -> float:
        return (1 - (1 - h) ** ceiling) / h

    lo, hi = 1e-7, 0.5
    for _ in range(200):
        mid = (lo + hi) / 2
        if mean_of(mid) > mean_games:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def implied_payout(n_games: float, coin_mochi: float, rate: float, net_gain: float) -> float:
    """機械割から逆算した、AT1回あたりの平均獲得枚数（純増）。"""
    loss = 50.0 / coin_mochi
    d = 3.0 * (rate - 1.0)
    return n_games * (loss + d) / (1.0 - d / net_gain)


@dataclass
class Variant:
    """状況ごとの天井（通常・設定変更時・短縮時など）。ceilings は [(天井G, 確率)]"""
    key: str
    label: str
    ceilings: list[tuple[int, float]]


@dataclass
class MachineModel:
    id: str
    name: str
    ceiling_type: str
    p_hit: float               # 初当たり確率（設定1、天井込みの平均）
    normal_ceiling: int
    rate: float                # 機械割（設定1、1.0＝100%）
    coin_mochi: float
    net_gain: float
    payout_spec: float | None = None
    payout_factor: float = 1.0
    payout_factor_note: str = ""
    variants: list[Variant] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def hazard(self) -> float:
        return hazard_for_mean(1.0 / self.p_hit, self.normal_ceiling)

    @property
    def payout_raw(self) -> float:
        if self.payout_spec:
            return self.payout_spec
        return implied_payout(1.0 / self.p_hit, self.coin_mochi, self.rate, self.net_gain)

    @property
    def payout(self) -> float:
        return self.payout_raw * (1.0 if self.payout_spec else self.payout_factor)


def from_spec(spec: dict, payout_factor: float = 1.0, factor_note: str = "") -> MachineModel:
    it = spec["items"]
    ctype = spec["ceiling_type"]
    ceil = it["ceiling"]["value"]
    fh = it["first_hit"]["value"]
    if ctype == "cz_st":
        normal = int(ceil["st_games"])
        p = prob(fh.get("st"))
    else:
        normal = int(ceil["games"])
        p = prob(fh.get("at") or fh.get("st"))
    ng = it["net_gain"]["value"]
    m = MachineModel(
        id=spec["id"], name=spec["name"], ceiling_type=ctype, p_hit=p, normal_ceiling=normal,
        rate=float(it["payout_rate"]["value"]) / 100.0, coin_mochi=float(it["coin_mochi"]["value"]),
        net_gain=float(ng["at"] if isinstance(ng, dict) else ng),
        payout_spec=it.get("avg_payout", {}).get("value"),
        payout_factor=payout_factor, payout_factor_note=factor_note,
    )
    m.variants.append(Variant("normal", "通常（AT後）", [(normal, 1.0)]))
    for short in it.get("ceiling_short", {}).get("value") or []:
        when = short.get("when", "")
        if "choices" in short:
            cs = [(int(c["games"]), float(c["rate"]) / 100.0) for c in short["choices"]]
            tot = sum(r for _, r in cs)
            m.variants.append(Variant("reset", f"{when}（天井の振り分けあり）", [(g, r / tot) for g, r in cs]))
        else:
            g = short.get("st_games") if ctype == "cz_st" else short.get("games")
            if g:
                key = "reset" if "設定変更" in when else "short"
                if any(v.key == key for v in m.variants):
                    key = f"short{len(m.variants)}"
                m.variants.append(Variant(key, when, [(int(g), 1.0)]))
    if ctype == "game_cycle":
        m.notes.append("周期天井は周期の長さが公開されていないため考えない（ゲーム数天井だけで計算）")
    if ctype == "cz_st":
        m.notes.append("CZ間天井（CZに当選するだけ）とCZ成功率は考えず、ST間天井だけで計算")
        m.notes.append("天井ゲーム数の振り分け（250〜750G）・天井短縮の抽選は考えない（通常は850G）")
    if not m.payout_spec:
        m.notes.append("AT1回の平均獲得枚数は公開値が無いため、機械割から逆算して係数を掛けた")
    return m


@dataclass
class Point:
    start: int
    ev: dict[str, float]          # 交換率ごとの期待収支（円）
    hourly: dict[str, float]      # 時給（円）
    invest_yen: float             # 平均投資（円）
    ceiling_rate: float           # 天井到達率
    mean_games: float             # 当たるまでの平均ゲーム数
    hours: float                  # 平均の遊技時間
    ci95: dict[str, float]        # 期待収支の95%信頼区間の半幅（試行回数による誤差）
    range_: dict[str, tuple[float, float]]  # 推定の幅（仕様のぶれ込み）
    p90_invest_yen: float         # 投資の90%点（10回に1回はこれ以上かかる）
    max_invest_yen: float         # 天井まで回したときの投資


def simulate(m: MachineModel, variant: Variant, ev_cfg: dict, starts: list[int] | None = None,
             seed: int = 1) -> list[Point]:
    rng = np.random.default_rng(seed)
    trials = int(ev_cfg.get("trials", 200000))
    gph = float(ev_cfg.get("games_per_hour", 840))
    price = float(ev_cfg.get("coin_price_yen", 20))
    exch = ev_cfg.get("exchanges") or [{"key": "toka", "yen_per_coin": 20.0}]
    unc = ev_cfg.get("uncertainty") or {}
    h = m.hazard
    maxc = max(c for c, _ in variant.ceilings)
    step = int(ev_cfg.get("step", 50))
    starts = starts if starts is not None else list(range(0, maxc, step))
    out = []
    for s in starts:
        # s G まで当たっていない → 天井の候補を絞る（振り分けがある機種）
        cand = [(c, w) for c, w in variant.ceilings if c > s]
        if not cand:
            continue
        tot = sum(w for _, w in cand)
        cs = np.array([c for c, _ in cand])
        ws = np.array([w / tot for _, w in cand])
        ceil_draw = rng.choice(cs, size=trials, p=ws)
        remain = ceil_draw - s
        g = rng.geometric(h, size=trials)
        reached = g >= remain
        games = np.where(reached, remain, g).astype(float)
        out.append(_point(m, s, games, reached, ev_cfg, exch, price, gph, unc, cs.max() - s))
    return out


def _point(m, s, games, reached, ev_cfg, exch, price, gph, unc, max_remain) -> Point:
    pay = m.payout
    loss = 50.0 / m.coin_mochi
    invest_coins = games * loss
    hours = (games + pay / m.net_gain) / gph
    ev, hourly, ci, rng_ = {}, {}, {}, {}
    for e in exch:
        y = float(e["yen_per_coin"])
        per = pay * y - invest_coins * price
        mu = float(per.mean())
        ev[e["key"]] = mu
        hourly[e["key"]] = mu / float(hours.mean())
        ci[e["key"]] = 1.96 * float(per.std()) / math.sqrt(len(per))
        # 推定の幅：平均獲得 ±payout_pct%、コイン持ち ±coin_mochi_g（悪い組み合わせ／良い組み合わせ）
        dp = float(unc.get("payout_pct", 5)) / 100.0
        dc = float(unc.get("coin_mochi_g", 0.5))
        mg = float(games.mean())
        lo = pay * (1 - dp) * y - mg * 50.0 / (m.coin_mochi - dc) * price
        hi = pay * (1 + dp) * y - mg * 50.0 / (m.coin_mochi + dc) * price
        rng_[e["key"]] = (lo, hi)
    return Point(
        start=int(s), ev=ev, hourly=hourly, invest_yen=float(invest_coins.mean() * price),
        ceiling_rate=float(reached.mean()), mean_games=float(games.mean()), hours=float(hours.mean()),
        ci95=ci, range_=rng_, p90_invest_yen=float(np.quantile(invest_coins, 0.9) * price),
        max_invest_yen=float(max_remain * loss * price),
    )


def situational_rate(m: MachineModel, start: int, ceiling: int, trials: int = 400000, seed: int = 7) -> float:
    """start G から ceiling までを打って AT 後にやめたときの機械割（OUT/IN、IN＝3枚×総ゲーム数）。"""
    rng = np.random.default_rng(seed)
    g = rng.geometric(m.hazard, size=trials)
    remain = ceiling - start
    games = np.minimum(g, remain).astype(float)
    pay = m.payout
    net = pay - games * 50.0 / m.coin_mochi
    coin_in = 3.0 * (games + pay / m.net_gain)
    return float(1.0 + net.mean() / coin_in.mean())


def border(points: list[Point], key: str = "toka") -> int | None:
    """期待収支がプラスになり始める開始ゲーム数（以降ずっとプラス）。"""
    first = None
    for p in points:
        if p.ev[key] >= 0:
            if first is None:
                first = p.start
        else:
            first = None
    return first
