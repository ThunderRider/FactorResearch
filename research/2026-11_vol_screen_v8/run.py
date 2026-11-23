#!/usr/bin/env python3
"""高波动排除逻辑修 V8 顶端失效 —— 门 1 判决。

运行：python research/2026-11_vol_screen_v8/run.py
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
Q = float(CFG["screen"]["drop_quantile"])
BUDGET = float(CFG["weights"]["budget"])
COST = float(CFG["cost"]["side"])


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
    vol20 = d_ret.rolling(int(CFG["screen"]["window"]), min_periods=10).std().shift(
        int(CFG["screen"]["lag"]))
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

    # 档位
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
    print(f"高档日 {len(HI)}；OOS 起 {oos.date()}；波动阈值 = 池内分位 {Q:.2%}")

    def select(pmask, n, screen):
        m = (pmask & tradable).fillna(False).astype(bool)
        z = {}
        for nm, f in (("vr", vol_ratio), ("am", amihud), ("r20", ret_20d)):
            f = f.where(m)
            z[nm] = f.sub(f.mean(axis=1), axis=0).div(
                f.std(axis=1).replace(0, np.nan), axis=0).clip(-3, 3)
        sc = (-z["vr"] + z["am"] - z["r20"]).where(m)
        if screen:
            rk_v = vol20.where(m).rank(axis=1, pct=True)
            sc = sc.where(rk_v <= Q)
        return sc.rank(axis=1, ascending=False).le(float(n), axis=0).fillna(False)

    # ---------------- 诊断：被剔除的票是不是真的更差 ----------------
    print("\n" + "=" * 120)
    print("【1】诊断：基线 min top-4 里，被高波动过滤剔掉的票 vs 保留下来的票")
    diag = []
    for n in (4, 20):
        base = select(pools["min"], n, screen=False)
        rk_v = vol20.where((pools["min"] & tradable).fillna(False).astype(bool)).rank(axis=1, pct=True)
        drop = (base & (rk_v > Q)).fillna(False)
        keep = (base & (rk_v <= Q)).fillna(False)
        for lbl in ("1115",):
            for tag, mask in (("剔除(高波动)", drop), ("保留", keep)):
                s = lab[lbl].where(mask).mean(axis=1).reindex(HI).dropna()
                diag.append({"N": n, "组": tag, "n_days": len(s),
                             "bp": round(float(s.mean()) * 1e4, 2),
                             "被剔占比": round(float(drop.sum(axis=1).sum()
                                                / max(base.sum(axis=1).sum(), 1)), 3)})
    dg = pd.DataFrame(diag)
    dg.to_csv(OUT / "screen_diagnostic.csv", index=False)
    print(dg.to_string(index=False))

    # ---------------- 主结果 ----------------
    rows = []
    for pool_name, n_mac in (("min", None),):
        for screen in (False, True):
            tag = "筛选" if screen else "基线"
            for n in NS:
                top = select(pools["min"], n, screen)
                filled = top.sum(axis=1).reindex(HI)
                for lbl in LABELS:
                    s = lab[lbl].where(top).mean(axis=1).reindex(HI).dropna()
                    for wname, sl_ in WINS.items():
                        ss = s.loc[sl_]
                        if len(ss) < 15:
                            continue
                        rows.append({"口径": tag, "N": n, "label": lbl, "window": wname,
                                     "n_days": len(ss),
                                     "bp": round(float(ss.mean()) * 1e4, 2),
                                     "取满率": round(float((filled.reindex(ss.index) == n).mean()), 3),
                                     "t_nw": round(newey_west_t(ss, 20), 2) if wname != "OOS" else np.nan})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "screen_results.csv", index=False)
    print("\n" + "=" * 120)
    print("【2】min 腿单位敞口日收益（高档日，bp/日）")
    print(res[res.label == PRIMARY].pivot_table(
        index=["口径", "N"], columns="window", values="bp").to_string())
    print("\n【3】取满率（当日能凑够 N 只的比例）")
    print(res[res.label == PRIMARY].pivot_table(
        index=["口径", "N"], columns="window", values="取满率").to_string())
    print("\n【4】三个出场口径（全样本 bp/日）")
    print(res[res.window == "ALL"].pivot_table(
        index=["口径", "N"], columns="label", values="bp").to_string())

    # ---------------- 判决 ----------------
    def val(tag, n, wname):
        d = res[(res["口径"] == tag) & (res.N == n) & (res.label == PRIMARY) & (res.window == wname)]
        return float(d.iloc[0]["bp"]) if len(d) else np.nan

    s1 = val("筛选", 4, "OOS") - val("基线", 4, "OOS")
    s2 = val("筛选", 4, "IS") - val("基线", 4, "IS")
    s3 = val("筛选", 50, "OOS") - val("基线", 50, "OOS")

    base4 = lab[PRIMARY].where(select(pools["min"], 4, False)).mean(axis=1).reindex(HI).dropna()
    scr4 = lab[PRIMARY].where(select(pools["min"], 4, True)).mean(axis=1).reindex(HI).dropna()
    k = int(CFG["judge"]["S4_fragility_k"])
    s4 = round(float(scr4.sort_values(ascending=False).iloc[k:].mean()) * 1e4, 2)

    b4o = base4.loc[oos:]
    s4o = scr4.loc[oos:]
    scale = float(s4o.std() / b4o.std()) if b4o.std() else np.nan
    s5_scr = round(float(s4o.mean()) * 1e4, 2)
    s5_base = round(float(b4o.mean() * scale) * 1e4, 2)

    verdict = pd.DataFrame([
        ("S1  OOS: 筛选N4 − 基线N4 ≥ 2bp", f"{s1:+.2f}bp", "PASS" if s1 >= 2.0 else "FAIL"),
        ("S2  IS: 筛选N4 > 基线N4", f"{s2:+.2f}bp", "PASS" if s2 > 0 else "FAIL"),
        ("S3  OOS: 筛选N50 ≥ 基线N50", f"{s3:+.2f}bp", "PASS" if s3 >= 0 else "FAIL"),
        ("S4  筛选N4 剔最好5天后 > 0", f"{s4:+.2f}bp", "PASS" if s4 > 0 else "FAIL"),
        ("S5  同波动下 筛选N4 更优", f"{s5_scr:+.2f} vs 基线缩放 {s5_base:+.2f}",
         "PASS" if s5_scr > s5_base else "FAIL"),
    ], columns=["判据", "实测", "结果"])
    verdict.to_csv(OUT / "verdict.csv", index=False)
    print("\n" + "=" * 120)
    print("【5】门 1 判决")
    print(verdict.to_string(index=False))
    n_pass = int((verdict["结果"] == "PASS").sum())
    print(f"\n通过 {n_pass}/5 → " + ("candidate" if n_pass == 5 else "watch（不得 candidate）"))

    # ---------------- 组合层 ----------------
    print("\n" + "=" * 120)
    print("【6】V8 组合净年化（0.96×档位/6，成本 0.1%/边）")
    rk_mac_b, rk_mac_s = select(pools["mac"], 2, False), select(pools["mac"], 2, True)
    rows = []
    for tag, tm, tmin, n in (("基线", rk_mac_b, select(pools["min"], 4, False), 4),
                             ("筛选", rk_mac_s, select(pools["min"], 4, True), 4),
                             ("基线", rk_mac_b, select(pools["min"], 50, False), 50),
                             ("筛选", rk_mac_s, select(pools["min"], 50, True), 50)):
        picks = (tm | tmin).fillna(False)
        np_ = picks.sum(axis=1)
        for lbl in LABELS:
            eq = lab[lbl].where(picks).sum(axis=1, min_count=1) / np_.replace(0, np.nan)
            exp = BUDGET * tier
            net = (eq * exp - COST * (exp.fillna(0) + exp.shift(1).fillna(0))).dropna()
            for wname, sl_ in WINS.items():
                p = perf(net.loc[sl_])
                rows.append({"口径": tag, "N_min": n, "label": lbl, "window": wname,
                             "net_ann_pct": p["ann_pct"], "sharpe": p["sharpe"],
                             "mdd_pct": p["mdd_pct"], "n_days": p["n"]})
    pf = pd.DataFrame(rows)
    pf.to_csv(OUT / "portfolio.csv", index=False)
    print(pf[pf.label == PRIMARY].pivot_table(
        index=["口径", "N_min"], columns="window", values="net_ann_pct").to_string())
    print(f"\n产物目录：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
