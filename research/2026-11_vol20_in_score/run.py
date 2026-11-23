#!/usr/bin/env python3
"""把 vol_20d 作为正因子放进 V8 打分 —— 门 1 判决。

运行：python research/2026-11_vol20_in_score/run.py
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
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "result"
OUT.mkdir(parents=True, exist_ok=True)
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
pd.set_option("display.width", 240)
pd.set_option("display.max_columns", 60)

LABELS = ["0930", "1115", "1330"]
PRIMARY = "1115"
NS = [int(x) for x in CFG["select"]["n_min"]]
BUDGET = float(CFG["weights"]["budget"])
COST = float(CFG["cost"]["side"])
W_MAIN = float(CFG["score"]["weight_vol20_primary"])
W_ROB = [float(x) for x in CFG["score"]["weight_vol20_robustness"]]


def bars(field, tods):
    df = pd.read_parquet(DATA / f"cn_stock_30m_post_{field}_20200101_20260518.parquet")
    df.index = pd.to_datetime(df.index)
    tod = pd.Series(df.index.strftime("%H:%M"), index=df.index)
    out = {}
    for t in tods:
        s = df.loc[(tod == t).to_numpy()].copy()
        s.index = s.index.normalize()
        out[t] = s
    return out


def daily(name):
    df = pd.read_parquet(DATA / f"cn_stock_{name}_20200101_20260513.parquet")
    df.index = pd.to_datetime(df.index).normalize()
    return df


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
    vol20 = d_ret.rolling(20, min_periods=10).std().shift(1)
    day_ret = c1430 / c1500.shift(1) - 1.0
    tradable = ((day_ret.abs() < float(CFG["filter"]["limit_tolerance"]))
                & (v1430 > 0) & (amt20 > float(CFG["filter"]["min_amt20"]))
                ).fillna(False).astype(bool)

    u = pd.read_parquet(REPO / CFG["pools"]["universe_path"])
    u["date"] = pd.to_datetime(u["date"])

    def pp(name):
        return (u[u["pool"] == name].assign(v=True)
                .pivot_table(index="date", columns="order_book_id", values="v", aggfunc="first")
                .reindex(index=c1430.index, columns=c1430.columns).fillna(False).astype(bool))

    pools = {"mac": pp("mac"), "min": pp("min")}

    tv = pd.read_parquet(DATA / "cn_index_30m_post_volume_20200101_20260518.parquet"
                         )[CFG["tier"]["index"]]
    tv.index = pd.to_datetime(tv.index)
    xb = np.arange(float(CFG["tier"]["window_bars"]))
    xb = xb - xb.mean()
    den = float((xb ** 2).sum())
    sl = tv.rolling(int(CFG["tier"]["window_bars"]), min_periods=72).apply(
        lambda y: float((xb * (y - y.mean())).sum()) / den, raw=True)
    at = sl[sl.index.strftime("%H:%M") == CFG["tier"]["bar"]].copy()
    at.index = at.index.normalize()
    tier = (at > 0).astype(float).where(at.notna()).reindex(c1430.index).shift(CFG["tier"]["lag"])

    judge = pd.Timestamp(CFG["sample"]["judge_from"])
    split = pd.Timestamp(CFG["sample"]["split"])
    cal = c1430.index
    oos = cal[int(cal.searchsorted(split)) + int(CFG["sample"]["embargo_days"])]
    hi = (tier > 0.5).fillna(False)
    HI = (hi & (hi.index >= judge))
    HI = HI[HI].index
    WINS = {"ALL": slice(judge, None), "IS": slice(judge, split), "OOS": slice(oos, None)}
    print(f"高档日 {len(HI)}；OOS 起 {oos.date()}")

    def zs(f, m):
        f = f.where(m)
        return f.sub(f.mean(axis=1), axis=0).div(f.std(axis=1).replace(0, np.nan),
                                                 axis=0).clip(-3, 3)

    def score(pmask, w):
        m = (pmask & tradable).fillna(False).astype(bool)
        z = {nm: zs(f, m) for nm, f in
             (("vr", vol_ratio), ("am", amihud), ("r20", ret_20d), ("v20", vol20))}
        return (-z["vr"] + z["am"] - z["r20"] + w * z["v20"]).where(m)

    def top(pmask, n, w):
        return score(pmask, w).rank(axis=1, ascending=False).le(float(n), axis=0).fillna(False)

    # ---- 相关性与成分替换诊断 ----
    print("\n" + "=" * 120)
    print("【0】z(vol_20d) 与 z(amihud) 的截面相关（共线检查）")
    m_min = (pools["min"] & tradable).fillna(False).astype(bool)
    za, zv = zs(amihud, m_min), zs(vol20, m_min)
    corr = za.corrwith(zv, axis=1)
    print(f"  逐日截面 Pearson 相关：均值 {float(corr.mean()):.3f}，"
          f"中位 {float(corr.median()):.3f}")

    print("\n【1】成分替换诊断（min，top-4，高档日）")
    b4 = top(pools["min"], 4, 0.0)
    v4 = top(pools["min"], 4, W_MAIN)
    drop = (b4 & (~v4)).fillna(False)      # v1 有、v2 无
    keep = (b4 & v4).fillna(False)
    rows = []
    for tag, mask in (("v1 有 / v2 无（被换掉）", drop), ("v1 与 v2 都有", keep)):
        s = lab[PRIMARY].where(mask).mean(axis=1).reindex(HI).dropna()
        vv = vol20.where(mask).mean(axis=1).reindex(HI).dropna()
        rows.append({"组": tag, "n_days": len(s), "1115_bp": round(float(s.mean()) * 1e4, 2),
                     "平均vol_20d": round(float(vv.mean()) * 1e4, 1)})
    diag = pd.DataFrame(rows)
    diag.to_csv(OUT / "diagnostic_replacement.csv", index=False)
    print(diag.to_string(index=False))
    print(f"  被换掉的占比（单元格层面）："
          f"{float(drop.sum(axis=1).sum() / max(b4.sum(axis=1).sum(), 1)):.3f}")

    # ---- 主结果 ----
    rows = []
    for w, tag in [(0.0, "v1(基线)"), (W_MAIN, "v2(w=1)")] + [(x, f"v2(w={x})") for x in W_ROB]:
        for pool_name, n_mac in (("min", None),):
            for n in NS:
                tp = top(pools[pool_name], n, w)
                for lbl in LABELS:
                    s = lab[lbl].where(tp).mean(axis=1).reindex(HI).dropna()
                    for wname, sl_ in WINS.items():
                        ss = s.loc[sl_]
                        if len(ss) < 15:
                            continue
                        rows.append({"口径": tag, "N": n, "label": lbl, "window": wname,
                                     "n_days": len(ss), "bp": round(float(ss.mean()) * 1e4, 2),
                                     "t_nw": round(newey_west_t(ss, 20), 2) if wname != "OOS" else np.nan})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "score_results.csv", index=False)
    print("\n" + "=" * 120)
    print("【2】min 腿单位敞口日收益（高档日，bp/日）")
    print(res[res.label == PRIMARY].pivot_table(
        index=["口径", "N"], columns="window", values="bp").to_string())
    print("\n【3】三个出场口径（全样本 bp/日）")
    print(res[res.window == "ALL"].pivot_table(
        index=["口径", "N"], columns="label", values="bp").to_string())

    # ---- 判决 ----
    def val(tag, n, wname):
        d = res[(res["口径"] == tag) & (res.N == n) & (res.label == PRIMARY) & (res.window == wname)]
        return float(d.iloc[0]["bp"]) if len(d) else np.nan

    v1_b4 = lab[PRIMARY].where(top(pools["min"], 4, 0.0)).mean(axis=1).reindex(HI).dropna()
    v2_b4 = lab[PRIMARY].where(top(pools["min"], 4, W_MAIN)).mean(axis=1).reindex(HI).dropna()

    V1 = val("v2(w=1)", 4, "OOS") - val("v1(基线)", 4, "OOS")
    V2 = val("v2(w=1)", 4, "IS") - val("v1(基线)", 4, "IS")
    V3 = val("v2(w=1)", 50, "OOS") - val("v1(基线)", 50, "OOS")
    k = int(CFG["judge"]["V4_fragility_k"])
    V4 = round(float(v2_b4.sort_values(ascending=False).iloc[k:].mean()) * 1e4, 2)
    b_o, s_o = v1_b4.loc[oos:], v2_b4.loc[oos:]
    scale = float(s_o.std() / b_o.std()) if b_o.std() else np.nan
    V5_v2 = round(float(s_o.mean()) * 1e4, 2)
    V5_v1 = round(float(b_o.mean() * scale) * 1e4, 2)
    w_pass = 0
    for x in [W_MAIN] + W_ROB:
        tag = "v2(w=1)" if x == W_MAIN else f"v2(w={x})"
        if val(tag, 4, "OOS") > val("v1(基线)", 4, "OOS"):
            w_pass += 1

    verdict = pd.DataFrame([
        ("V1 OOS: v2−v1 (N=4) ≥ 2bp", f"{V1:+.2f}bp", "PASS" if V1 >= 2.0 else "FAIL"),
        ("V2 IS: v2 > v1 (N=4)", f"{V2:+.2f}bp", "PASS" if V2 > 0 else "FAIL"),
        ("V3 OOS: v2 ≥ v1 (N=50)", f"{V3:+.2f}bp", "PASS" if V3 >= 0 else "FAIL"),
        ("V4 v2 N=4 剔最好5天后 > 0", f"{V4:+.2f}bp", "PASS" if V4 > 0 else "FAIL"),
        ("V5 同波动下 v2 优于 v1", f"{V5_v2:+.2f} vs {V5_v1:+.2f}",
         "PASS" if V5_v2 > V5_v1 else "FAIL"),
        ("V6 权重稳健（≥2 个 w 在 OOS 优于 v1）", f"{w_pass}/3",
         "PASS" if w_pass >= int(CFG["judge"]["V6_min_pass"]) else "FAIL"),
    ], columns=["判据", "实测", "结果"])
    verdict.to_csv(OUT / "verdict.csv", index=False)
    print("\n" + "=" * 120)
    print("【4】门 1 判决")
    print(verdict.to_string(index=False))
    n_pass = int((verdict["结果"] == "PASS").sum())
    print(f"\n通过 {n_pass}/6 → " + ("candidate" if n_pass == 6 else "watch（不得 candidate）"))

    # ---- 组合层 ----
    rows = []
    for w, tag in [(0.0, "v1(基线)"), (W_MAIN, "v2(w=1)")]:
        tm = top(pools["mac"], 2, w)
        for n in NS:
            picks = (tm | top(pools["min"], n, w)).fillna(False)
            npick = picks.sum(axis=1)
            for lbl in LABELS:
                eq = lab[lbl].where(picks).sum(axis=1, min_count=1) / npick.replace(0, np.nan)
                exp = BUDGET * tier
                net = (eq * exp - COST * (exp.fillna(0) + exp.shift(1).fillna(0))).dropna()
                for wname, sl_ in WINS.items():
                    s = net.loc[sl_]
                    if len(s) < 20:
                        continue
                    nav = (1 + s).cumprod()
                    rows.append({"口径": tag, "N_min": n, "label": lbl, "window": wname,
                                 "net_ann_pct": round(float(nav.iloc[-1] ** (252 / len(s)) - 1) * 100, 2),
                                 "sharpe": round(float((nav.iloc[-1] ** (252 / len(s)) - 1))
                                                 / (float(s.std()) * np.sqrt(252)), 2)
                                 if s.std() else np.nan,
                                 "n_days": len(s)})
    pf = pd.DataFrame(rows)
    pf.to_csv(OUT / "portfolio.csv", index=False)
    print("\n【5】V8 组合净年化（%）")
    print(pf[pf.label == PRIMARY].pivot_table(
        index=["口径", "N_min"], columns="window", values="net_ann_pct").to_string())
    print(f"\n产物目录：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
