"""段階2〜5をまとめて実行する。

    python pipeline/ev/run.py            # 全機種：シミュレーション → 答え合わせ → 合格機種だけ表
    python pipeline/ev/run.py godeater_r # 1機種だけ

出力（data/ev/ と data/compare/ は公開リポジトリのあいだ git に入れない）
- data/ev/<ID>.json           シミュレーション結果（開始ゲーム数ごと）
- data/ev/tables/<ID>_*.md/png 合格した機種の note 用の表
- data/compare/report.md      答え合わせの詳細（他サイトの数値を含む。成果物に載せない）
- docs/ev_status.md           機種ごとの状態（合格／準備中と原因）。他サイトの数値は書かない
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ev import calibrate, compare  # noqa: E402
from ev.model import border, from_spec, simulate  # noqa: E402
from ev.specs import SPEC_DIR, load_spec  # noqa: E402
from ev.tables import markdown_table, png_table  # noqa: E402
from notelib.config import DATA_DIR, ROOT, load_config, today, write_json  # noqa: E402

EV_DIR = DATA_DIR / "ev"

# 答え合わせで差が大きかったときの原因（data/compare/report.md の差の出方を見て書いたもの。他サイトの数値は書かない）
CAUSES = {
    "godeater_r": ("設定変更時（天井600G）だけ、浅いゲーム数で自作が高く出る。差は打ち始めが浅いほど大きく、"
                   "深くなると縮むので、天井の違いではなく「設定変更後のATの獲得枚数」の見方の違い。"
                   "比べた相手もこの状況は暫定版。設定変更後の平均獲得枚数（またはメーカー公表の状況別機械割）が足りない"),
    "otome5": ("設定変更時（天井650G）だけ、どの打ち始めでもほぼ同じ額だけ自作が高い。"
               "通常時はほぼ一致しているので、天井の扱いではなく「設定変更後のATの獲得枚数」の違い。"
               "相手の表もリセット時は暫定。設定変更後の平均獲得枚数が足りない"),
    "milliongod_kiseki": ("通常・設定変更時とも、どの打ち始めでもほぼ同じ額だけ自作が低い。"
                          "天井恩恵（ループストック・Z-ZONE）の上乗せと、通常時のモード（天国・超天国）を入れていないため。"
                          "ループストック1つあたりの平均獲得枚数・モード移行率が足りない"),
}
BORDERS = DATA_DIR / "sheet" / "_borders.yaml"


def sheet_borders(mid: str) -> dict[str, int]:
    """標準ボーダー。シートに line の行が本当にあるときだけ使う。"""
    if not BORDERS.exists():
        return {}
    allb = yaml.safe_load(BORDERS.read_text(encoding="utf-8")) or {}
    out = {}
    for variant, b in (allb.get(mid) or {}).items():
        p = DATA_DIR / "sheet" / f"{b['sheet']}.txt"
        if p.exists() and any(ln.rstrip() == b["line"].rstrip() for ln in p.read_text(encoding="utf-8").splitlines()):
            out[variant] = int(b["games"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args()
    cfg = load_config()
    ev_cfg = cfg["ev"]
    cmp_cfg = ev_cfg.get("compare", {})
    specs = [load_spec(p) for p in sorted(SPEC_DIR.glob("*.yaml"))]
    cal = calibrate.fit(specs)
    if ev_cfg.get("payout_factor_default") is not None:
        cal.factor = float(ev_cfg["payout_factor_default"])
    print("係数:", cal.note)
    status_rows, report = [], ["# 答え合わせの詳細（内部用。他サイトの数値を含むので成果物に載せない）", "",
                               f"作成：{today().isoformat()}", "", f"係数：{cal.note}", ""]
    for r in cal.rows:
        report.append(f"- 係数の推定：{r['machine']} {r['from']}G〜 公表{r['published']:.1f}% ／ 計算{r['model']:.2f}%")
    for spec in specs:
        mid = spec["id"]
        if a.ids and mid not in a.ids:
            continue
        m = from_spec(spec, cal.factor, cal.note)
        res = {"id": mid, "name": m.name, "date": today().isoformat(), "params": {
            "hazard": m.hazard, "p_hit": m.p_hit, "ceiling": m.normal_ceiling, "rate": m.rate,
            "coin_mochi": m.coin_mochi, "net_gain": m.net_gain, "payout_raw": m.payout_raw,
            "payout_factor": cal.factor, "payout": m.payout}, "notes": m.notes, "variants": {}}
        ref = compare.load_reference(mid)
        verdicts = []
        report += ["", f"## {m.name}（{mid}）", "",
                   f"- 当たりやすさ 1/{1 / m.hazard:.1f}（天井込みで初当たり1/{1 / m.p_hit:.1f}）、"
                   f"AT1回の獲得 {m.payout:.0f}枚（逆算 {m.payout_raw:.0f}枚 × {cal.factor:.3f}）"]
        sb = sheet_borders(mid)
        step = int(ev_cfg.get("step", 50))
        for v in m.variants:
            # 標準ボーダー（シートのゲーム数）が刻みに乗らないときは、その行も計算する
            sbv = sb.get("reset" if v.key == "reset" else "normal")
            maxc = max(c for c, _ in v.ceilings)
            starts = sorted(set(range(0, maxc, step)) | {sbv}) if sbv is not None and sbv % step and sbv < maxc else None
            pts = simulate(m, v, ev_cfg, starts)
            res["variants"][v.key] = {"label": v.label, "ceilings": v.ceilings, "border_toka": border(pts, "toka"),
                                      "border_56": border(pts, "5.6"), "points": [asdict(p) for p in pts]}
            if v.key in ref:
                vr = compare.compare_variant(v.key, pts, ref[v.key], cmp_cfg)
                ok = vr.passed(cmp_cfg)
                verdicts.append((v, pts, vr, ok))
                report += ["", f"### {v.label}：{'合格' if ok else '不合格'}", "",
                           f"- 許容内 {vr.n_ok}/{vr.n}、差の最大 {vr.max_abs:.0f}円、平均の差 {vr.mean_diff:+.0f}円、"
                           f"プラスになり始めるG（等価） 自作{vr.border_mine}G／相手{vr.border_ref}G", "",
                           "| 開始G | 交換 | 自作 | 相手 | 差 | 許容内 |", "|---:|---|---:|---:|---:|:-:|"]
                report += [f"| {r['start']} | {r['exchange']} | {r['mine']} | {r['ref']} | {r['diff']:+} | "
                           f"{'○' if r['ok'] else '×'} |" for r in vr.rows]
        res["verdicts"] = {v.key: ok for v, _p, _vr, ok in verdicts}
        write_json(EV_DIR / f"{mid}.json", res)
        passed = [(v, pts) for v, pts, _vr, ok in verdicts if ok]
        if not ref:
            state, why = "準備中", ("比べる相手が無い（公開されている期待値表が見つからない。"
                                   "状況別機械割は係数の推定に使ったので答え合わせには使えない）")
        elif len(passed) == len(verdicts):
            state, why = "合格", ""
        else:
            bad = [vr for _, _, vr, ok in verdicts if not ok]
            state = "一部合格" if passed else "準備中"
            why = "；".join(f"{next(v.label for v in m.variants if v.key == vr.variant)}："
                           f"許容内{vr.n_ok}/{vr.n}・差の最大{vr.max_abs:,.0f}円・平均の差{vr.mean_diff:+,.0f}円・"
                           f"プラスになり始めるGの差{abs((vr.border_mine or 0) - (vr.border_ref or 0))}G" for vr in bad)
            cause = CAUSES.get(mid)
            why += "。原因：" + (cause or "／".join(m.notes))
        status_rows.append((m, state, why, verdicts))
        for v, pts in passed:   # 合格した状況だけ表にする
            sbv = sb.get("reset" if v.key == "reset" else "normal")
            md = markdown_table(m, v, pts, ev_cfg, cal.note, sbv)
            out = EV_DIR / "tables" / f"{mid}_{v.key}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(md, encoding="utf-8")
            png_table(m, v, pts, EV_DIR / "tables" / f"{mid}_{v.key}.png", sbv, ev_cfg)
        print(f"{m.name}: {state} {why}")
    (DATA_DIR / "compare").mkdir(parents=True, exist_ok=True)
    if a.ids:   # 一部の機種だけのときは、全体の状態（docs/ev_status.md）と report.md は書き換えない
        return
    (DATA_DIR / "compare" / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    write_status(status_rows, cal, ev_cfg)


def write_status(rows, cal, ev_cfg) -> None:
    c = ev_cfg.get("compare", {})
    lines = ["# 自作期待値表の状態（段階4・5）", "",
             f"更新：{today().isoformat()}。`python pipeline/ev/run.py` が書き換える。**他サイトの数値はここに書かない**（詳細は data/compare/report.md。git に入れない）。", "",
             "## 合格の基準（結果を見る前に決めたもの。config の ev.compare）", "",
             f"- 比べた点の {int(float(c.get('min_pass_share', 0.8)) * 100)}% 以上で、差が {c.get('max_diff_yen')}円 か 相手の値の {int(float(c.get('max_diff_ratio')) * 100)}% のどちらか大きい方の以内",
             f"- 等価で期待値がプラスになり始めるゲーム数の差が {c.get('max_border_diff_g')}G 以内",
             "- 比べる相手：なな徹の天井期待値表（算出条件が文字で公開されている信頼サイト）。ちょんぼりすたの表はたられば氏の実戦値の画像の引用で、条件が比べられる形で書かれていないため使わなかった", "",
             f"## 平均獲得枚数の係数", "", f"- {cal.note}", "",
             "## 機種ごとの状態", "",
             "状況（通常／設定変更時など）ごとに合否を決め、合格した状況だけ表を作る。不合格の状況は「準備中」。", "",
             "| 機種 | 状態 | 比べた状況 | 許容内 | 差の最大 | プラスになり始めるGの差 | 準備中の原因 |",
             "|---|---|---|---|---|---|---|"]
    for m, state, why, verdicts in rows:
        if not verdicts:
            lines.append(f"| {m.name} | {state} | — | — | — | — | {why} |")
            continue
        for i, (v, _pts, vr, ok) in enumerate(verdicts):
            bd = abs((vr.border_mine or 0) - (vr.border_ref or 0)) if vr.border_mine is not None and vr.border_ref is not None else "—"
            lines.append(f"| {m.name if i == 0 else ''} | {state if i == 0 else ''} | {v.label}（{'○' if ok else '×'}） | "
                         f"{vr.n_ok}/{vr.n} | {vr.max_abs:,.0f}円 | {bd}G | {why if (i == 0 and state != '合格') else ''} |")
    lines += ["", "合格した機種の表は `data/ev/tables/`（有料の中身なので公開リポジトリのあいだは push しない）。", ""]
    (ROOT / "docs" / "ev_status.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
