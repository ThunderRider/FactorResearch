#!/usr/bin/env python3
"""小盘池宽度研究 —— 门 1 判决用。

判决对象：min 腿（中证1000+2000）单位敞口日收益，N ∈ {4, 20, 50}。
切分 2024-12-31 + 禁运 120 交易日；全样本数字不作证据（见 idea.md §5）。

运行：python research/2026-11_min_pool_breadth/run.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from factorlab.eval.ic import newey_west_t  # noqa: E402

DATA = Path("/home/pl_ubuntu/my_quantproject/wpqc_factor/data_rq")
OUT = Path(__file__).resolve().parent / "result"
OUT.mkdir(parents=True, exist_ok=True)
CFG = yaml.safe_load((Path(__file__).resolve().parent / "config.yaml").read_text())
pd.set_option("display.width", 230)
pd.set_option("display.max_columns", 80)

LABELS = ["0930", "1115", "1330"]
PRIMARY = "1115"
NS = CFG["select"]["n_min"]
BUDGET = CFG["weights"]["budget"]
COST = CFG["cost"]["side"]
LOW = CFG["tier"]["low"]


# ---------------------------------------------------------------- 数据
def bars(field, tods):
    df = pd.read_parquet(DATA / f"cn_stock_30m_post_{field}_20200101_20260518.parquet")
    df.index = pd.to_datetime(df.index)
    tod = pd.Series(df.index.strftime("%H:%M"), index=df.index)
    out = {}
    for t in tods:
        sub = df.loc[(tod == t).to_numpy()].copy()
        sub.index = sub.index.normalize()
        out[t] = sub
    return out


def daily(name):
    df = pd.read_parquet(DATA / f"cn_stock_{name}_20200101_20260513.parquet")
    df.index = pd.to_datetime(df.index).normalize()
    return df


def perf(s):
    s = pd.Series(s).dropna()
    if len(s) < 20:
        return {"ann_pct": np.nan, "sharpe": np.nan, "mdd_pct": np.nan, "n": len(s)}
    nav = (1 + s).cumprod()
    ann = float(nav.iloc[-1] ** (252 / len(s)) - 1)
    vol = float(s.std(ddof=1)) * np.sqrt(252)
    return {"ann_pct": round(ann * 100, 2),
            "sharpe": round(ann / vol, 2) if vol else np.nan,
            "mdd_pct": round(float((nav / nav.cummax() - 1).min()) * 100, 2),
            "n": int(len(s))}


def mean_bp(s):
    s = pd.Series(s).dropna()
    return round(float(s.mean()) * 1e4, 2) if len(s) else np.nan


def main() -> int:
    print("读取数据 ...", flush=True)
    cs = bars("close", ["11:00", "11:30", "13:30", "14:30", "15:00"])
    op = bars("open", ["10:00"])
    vo = bars("volume", ["14:30"])
    c1100, c1130, c1330, c1430, c1500 = (cs[t] for t in
                                         ("11:00", "11:30", "13:30", "14:30", "15:00"))
    o1000, v1430 = op["10:00"], vo["14:30"]
    d_amt, d_close = daily("total_turnover"), daily("close")
    d_ret = d_close.pct_change(fill_method=None)

    entry = (c1430.fillna(c1500) + c1500.fillna(c1430)) / 2.0
    exit1115 = (c1100.shift(-1).fillna(c1130.shift(-1))
                + c1130.shift(-1).fillna(c1100.shift(-1))) / 2.0
    lab = {"0930": o1000.shift(-1) / entry - 1.0,
           "1115": exit1115 / entry - 1.0,
           "1330": c1330.shift(-1) / entry - 1.0}

    amt20 = d_amt.rolling(20, min_periods=10).mean().shift(1)
    vol_ratio = v1430 / v1430.rolling(20, min_periods=10).mean().replace(0, np.nan)
    ret_20d = c1430 / c1430.shift(20) - 1.0
    amihud = (d_ret.abs() / d_amt.replace(0, np.nan)).rolling(20, min_periods=10).mean().shift(1)

    tol = CFG["filter"]["limit_tolerance"]
    min_amt = float(CFG["filter"]["min_amt20"])
    tradable = (((c1430 / c1500.shift(1) - 1).abs() < tol) & (v1430 > 0)
                & (amt20 > min_amt)).fillna(False).astype(bool)

    u = pd.read_parquet(REPO / CFG["pools"]["universe_path"])
    u["date"] = pd.to_datetime(u["date"])
    T = c1430.columns

    def pp(name):
        return (u[u["pool"] == name].assign(v=True)
                .pivot_table(index="date", columns="order_book_id", values="v", aggfunc="first")
                .reindex(index=c1430.index, columns=T).fillna(False).astype(bool))

    mac, minp = pp("mac"), pp("min")

    # 档位
    tv = pd.read_parquet(DATA / "cn_index_30m_post_volume_20200101_20260518.parquet")[CFG["tier"]["index"]]
    tv.index = pd.to_datetime(tv.index)
    xb = np.arange(float(CFG["tier"]["window_bars"]))
    xb = xb - xb.mean()
    den = float((xb ** 2).sum())
    sl = tv.rolling(int(CFG["tier"]["window_bars"]), min_periods=72).apply(
        lambda y: float((xb * (y - y.mean())).sum()) / den, raw=True)
    at = sl[sl.index.strftime("%H:%M") == CFG["tier"]["bar"]].copy()
    at.index = at.index.normalize()
    tier = (at > 0).astype(float).where(at.notna()).reindex(c1430.index).shift(CFG["tier"]["lag"])

    # 打分（一次算好，各 N 共用）
    def score_of(pmask):
        mm = (pmask & tradable).fillna(False).astype(bool)
        z = {}
        for nm, f in (("vr", vol_ratio), ("am", amihud), ("r20", ret_20d)):
            f = f.where(mm)
            z[nm] = f.sub(f.mean(axis=1), axis=0).div(
                f.std(axis=1).replace(0, np.nan), axis=0).clip(-CFG["z_clip"], CFG["z_clip"])
        return (-z["vr"] + z["am"] - z["r20"]).where(mm)

    rk_mac = score_of(mac).rank(axis=1, ascending=False)
    rk_min = score_of(minp).rank(axis=1, ascending=False)

    # 切分 + 禁运
    cal = c1430.index
    split = pd.Timestamp(CFG["sample"]["split"])
    i_split = int(cal.searchsorted(split))          # 第一个 > split 的位置
    i_oos = min(i_split + int(CFG["sample"]["embargo_days"]), len(cal) - 1)
    oos_start = cal[i_oos]
    judge_from = pd.Timestamp(CFG["sample"]["judge_from"])
    print(f"切分 {split.date()}  禁运 {CFG['sample']['embargo_days']} 交易日  "
          f"OOS 起 {oos_start.date()}  （判决起点 {judge_from.date()}）")

    hi = (tier > 0.5).fillna(False)
    hi_judge = hi & (hi.index >= judge_from)
    HI_IDX = hi_judge[hi_judge].index          # ⚠️ 只有高档日

    def seg(s_idx, tag):
        """把索引切成 IS / OOS。"""
        if tag == "IS":
            return s_idx[(s_idx >= judge_from) & (s_idx <= split)]
        if tag == "OOS":
            return s_idx[s_idx >= oos_start]
        return s_idx[s_idx >= judge_from]

    # ---------------------------------------------------------------- 逐 N
    rows = []
    unit_series = {}
    for n in NS:
        top_min = rk_min.le(float(n), axis=0).fillna(False)
        top_mac = rk_mac.le(float(CFG["select"]["n_mac"]), axis=0).fillna(False)
        for mode in ("equal_all", "fixed_33_67"):
            for lbl in LABELS:
                L = lab[lbl]
                unit = L.where(top_min).mean(axis=1)                       # min 腿单位敞口
                ew_min = L.where((minp & tradable).fillna(False).astype(bool)).mean(axis=1)
                sel_all = pd.concat([L.where(top_mac).mean(axis=1).rename("mac"),
                                     unit.rename("min")], axis=1)
                if mode == "equal_all":
                    wmac, wmin = 1.0 / (CFG["select"]["n_mac"] + n) * CFG["select"]["n_mac"], \
                                 1.0 / (CFG["select"]["n_mac"] + n) * n
                else:
                    wmac, wmin = 1.0 / 3.0, 2.0 / 3.0
                mix = (sel_all["mac"] * wmac + sel_all["min"] * wmin)
                exposure = BUDGET * tier
                gross = mix * exposure
                cost = COST * (exposure.fillna(0.0) + exposure.shift(1).fillna(0.0))
                net = (gross - cost).dropna()

                for win in ("ALL", "IS", "OOS"):
                    idx_u = seg(unit.dropna().index, win)
                    idx_h = idx_u.intersection(HI_IDX)
                    uu = unit.reindex(idx_h).dropna()
                    _lo = oos_start if win == "OOS" else judge_from
                    _hi = split if win == "IS" else net.index.max()
                    nn = net.loc[(net.index >= _lo) & (net.index <= _hi)]
                    rows.append({
                        "n_min": n, "mode": mode, "label": lbl, "window": win,
                        "unit_bp": mean_bp(uu),
                        "unit_t_nw": round(newey_west_t(uu, lag=20), 2) if len(uu) > 20 else np.nan,
                        "excess_vs_ew_bp": round(mean_bp(uu - ew_min.reindex(uu.index)), 2)
                        if len(uu) else np.nan,
                        "unit_vol_bp": round(float(uu.std(ddof=1)) * 1e4, 1) if len(uu) > 2 else np.nan,
                        "n_days": int(len(uu)),
                        "port_net_ann_pct": perf(nn).get("ann_pct"),
                        "port_sharpe": perf(nn).get("sharpe"),
                        "port_mdd_pct": perf(nn).get("mdd_pct"),
                    })
                if mode == "equal_all" and lbl == PRIMARY:
                    unit_series[n] = unit
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "breadth_results.csv", index=False)

    # ---------------------------------------------------------------- 判定
    print("\n" + "=" * 120)
    print("【1】min 腿单位敞口日收益（高档日，bp/日）—— 主口径 equal_all，label=1115")
    main = res[(res["mode"] == "equal_all") & (res.label == PRIMARY)]
    print(main.pivot_table(index="n_min", columns="window",
                           values=["unit_bp", "unit_t_nw", "excess_vs_ew_bp",
                                   "unit_vol_bp", "port_net_ann_pct"]).to_string())

    print("\n【2】三个出场口径对照（min 腿，equal_all）")
    print(res[(res["mode"] == "equal_all")].pivot_table(
        index=["n_min", "label"], columns="window", values="unit_bp").to_string())

    print("\n【3】稳健性：固定资金结构 33/67")
    print(res[(res["mode"] == "fixed_33_67") & (res.label == PRIMARY)].pivot_table(
        index="n_min", columns="window", values="unit_bp").to_string())

    # F1..F5
    def val(n, win="OOS", col="unit_bp"):
        d = main[(main.n_min == n) & (main.window == win)]
        return float(d.iloc[0][col]) if len(d) and pd.notna(d.iloc[0][col]) else np.nan

    f = {}
    f["F1_OOS_n50_minus_n4_ge_2bp"] = val(50) - val(4)
    f["F2_IS_monotone"] = val(4, "IS") < val(20, "IS") < val(50, "IS")
    f["F2_OOS_monotone"] = val(4) < val(20) < val(50)
    f["F3_OOS_excess_over_ew_gt0"] = val(50, "OOS", "excess_vs_ew_bp")

    # F4 同波动缩放（OOS）
    r4 = unit_series[4].reindex(unit_series[4].index.intersection(HI_IDX)).dropna()
    r50 = unit_series[50].reindex(unit_series[50].index.intersection(HI_IDX)).dropna()
    r4o, r50o = r4[r4.index >= oos_start], r50[r50.index >= oos_start]
    if len(r4o) > 5 and len(r50o) > 5 and r4o.std() > 0:
        scale = float(r50o.std() / r4o.std())
        f["F4_scaled_n4_bp"] = round(float(r4o.mean() * scale) * 1e4, 2)
        f["F4_n50_bp"] = round(float(r50o.mean()) * 1e4, 2)
        f["F4_n50_better"] = f["F4_n50_bp"] > f["F4_scaled_n4_bp"]
    else:
        f["F4_scaled_n4_bp"] = f["F4_n50_bp"] = f["F4_n50_better"] = np.nan

    # F5 脆弱性（OOS，剔除最好 5 天）
    k = int(CFG["judge"]["F5_fragility_k"])
    r50_all = unit_series[50].reindex(
        unit_series[50].index.intersection(HI_IDX)).dropna()
    keep = r50_all.sort_values(ascending=False).iloc[k:]
    f["F5_n50_after_drop5_bp"] = round(float(keep.mean()) * 1e4, 2)

    print("\n" + "=" * 120)
    print("【4】门 1 判决（对应 idea.md §4 的 F1–F5）")
    verdict = []
    verdict.append(("F1  OOS: N50 − N4 ≥ 2bp/日",
                    f"{f['F1_OOS_n50_minus_n4_ge_2bp']:+.2f}bp",
                    "PASS" if f["F1_OOS_n50_minus_n4_ge_2bp"] >= 2.0 else "FAIL"))
    verdict.append(("F2a IS 单调 4<20<50", f"{f['F2_IS_monotone']}",
                    "PASS" if f["F2_IS_monotone"] else "FAIL"))
    verdict.append(("F2b OOS 单调 4<20<50", f"{f['F2_OOS_monotone']}",
                    "PASS" if f["F2_OOS_monotone"] else "FAIL"))
    verdict.append(("F3  OOS: N50 超额(对池均) > 0", f"{f['F3_OOS_excess_over_ew_gt0']:+.2f}bp",
                    "PASS" if f["F3_OOS_excess_over_ew_gt0"] > 0 else "FAIL"))
    verdict.append(("F4  同波动下 N50 仍优于 N4",
                    f"N50 {f['F4_n50_bp']:+.2f} vs N4缩放 {f['F4_scaled_n4_bp']:+.2f}",
                    "PASS" if f["F4_n50_better"] is True else "FAIL"))
    verdict.append(("F5  剔除最好5天后 N50 > 0", f"{f['F5_n50_after_drop5_bp']:+.2f}bp",
                    "PASS" if f["F5_n50_after_drop5_bp"] > 0 else "FAIL"))
    vdf = pd.DataFrame(verdict, columns=["判据", "实测", "结果"])
    vdf.to_csv(OUT / "gate1_verdict.csv", index=False)
    print(vdf.to_string(index=False))
    n_pass = int((vdf["结果"] == "PASS").sum())
    print(f"\n通过 {n_pass}/6")
    print("→ 门 7 判决：" + ("candidate（可继续观察）" if n_pass == 6 else "watch（不得 active）"))

    # 分年（min 腿，N=50）
    print("\n" + "=" * 120)
    print("【5】min 腿单位敞口分年（高档日，N=4 / N=50，bp/日）")
    rows = []
    for n in NS:
        s = unit_series[n].reindex(unit_series[n].index.intersection(HI_IDX)).dropna()
        by = s.groupby(s.index.year).apply(lambda x: round(float(x.mean()) * 1e4, 2))
        rows.append({"n_min": n, **{str(k): v for k, v in by.items()}})
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\n产物目录：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
