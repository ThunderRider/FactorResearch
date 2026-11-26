#!/usr/bin/env python3
"""计算 12 个 GTJA191 候选因子（日频 OHLCV），落成 (date, ticker, factor) 长表。

PIT：所有日频因子统一 .shift(1)（用 T−1 已收盘的日线，T 日 14:30 决策安全），
与 build_panel.py 里现有 gtja 因子的处理一致。

因子族覆盖（刻意避开"只对 price/volume 排个序"这类与 vol_ratio/ret_20d 重叠的构造）：
  117 时序排名复合（volume / 价幅 / 收益三重 tsrank）
  152 9 日收益率的短长均线差（趋势）
  168 -volume/MA(volume,20)（缩量，vol_ratio 的日频版）
  094 30 日带符号成交量（资金流）
  102 量增/量减的不对称度
  110 20 日上涨/下跌力度比
  145 量能趋势 (MA9-MA26)/MA12
  105 开盘价与成交量秩相关
  093 跳空低开后 20 日累计恢复力
  118 20 日上下影线比
  096 KDJ 类（收盘在 9 日区间的位置，双重平滑）
  111 量加权收盘位置差分
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

DATA = Path("/home/pl_ubuntu/my_quantproject/wpqc_factor/data_rq")
OUT = HERE / "result" / "extra_factors.parquet"
W = 20
BAR = ["open", "close", "high", "low", "volume"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def read30(field):
    df = pd.read_parquet(DATA / f"cn_stock_30m_post_{field}_20200101_20260518.parquet")
    df.index = pd.to_datetime(df.index)
    return df


def at_time(wide, hhmm):
    out = wide[wide.index.strftime("%H:%M") == hhmm].copy()
    out.index = out.index.normalize()
    return out


def sma(s, n, m=1):
    """中国公式的 SMA(X,N,M) = EMA(alpha=M/N)。"""
    return s.ewm(alpha=m / float(n), adjust=False).mean()


def ts_rank(s, window):
    return s.rolling(window, min_periods=max(3, window // 2)).rank(pct=True)


def main() -> int:
    t0 = time.time()
    log("读 30m ...")
    o, c, h, l, v = (read30(f) for f in BAR)
    log("聚合成日线 ...")
    d_open = at_time(o, "10:00")
    d_close = at_time(c, "15:00")
    d_high = h.groupby(h.index.normalize()).max()
    d_low = l.groupby(l.index.normalize()).min()
    d_vol = v.groupby(v.index.normalize()).sum()
    del o, c, h, l, v
    common = d_open.index
    for x in (d_close, d_high, d_low, d_vol):
        common = common.intersection(x.index)
    cols = d_open.columns
    for x in (d_close, d_high, d_low, d_vol):
        cols = cols.intersection(x.columns)
    op, cl, hi, lo, vol = (x.reindex(index=common, columns=cols).astype("float64")
                           for x in (d_open, d_close, d_high, d_low, d_vol))
    del d_open, d_close, d_high, d_low, d_vol
    log(f"日线 {op.shape}")

    prev_close = cl.shift(1)
    ret1 = cl / prev_close - 1.0
    rng = (hi - lo).replace(0.0, np.nan)

    log("计算 12 个因子 ...")
    F = {}

    # 117
    F["g117"] = ((ts_rank(vol, 32) * (1 - ts_rank(cl + hi - lo, 16))
                  * (1 - ts_rank(ret1, 32))))

    # 152
    base = (cl / cl.shift(9)).shift()                    # 9 日收益率的平滑输入
    sm = sma(base, 9, 1).shift()
    d1 = sm.rolling(12, min_periods=12).mean()
    d2 = sm.rolling(26, min_periods=26).mean()
    F["g152"] = sma(d1 - d2, 9, 1)

    # 168
    F["g168"] = -vol / vol.rolling(W, min_periods=W).mean()

    # 094
    signed = vol.where(cl > prev_close, -vol.where(cl < prev_close, 0.0))
    F["g094"] = signed.rolling(30, min_periods=30).sum()

    # 102
    dv = (vol - vol.shift(1))
    F["g102"] = (sma(dv.clip(lower=0), 6, 1)
                 / sma(dv.abs(), 6, 1).replace(0.0, np.nan) * 100.0)

    # 110
    up = (hi - prev_close).clip(lower=0)
    dn = (prev_close - lo).clip(lower=0)
    F["g110"] = (up.rolling(20, min_periods=20).sum()
                 / dn.rolling(20, min_periods=20).sum().replace(0.0, np.nan) * 100.0)

    # 145
    F["g145"] = ((vol.rolling(9, min_periods=9).mean() - vol.rolling(26, min_periods=26).mean())
                 / vol.rolling(12, min_periods=12).mean().replace(0.0, np.nan) * 100.0)

    # 105：-corr(rank(open), rank(volume), 10)
    ro = op.rank(axis=1, pct=True)
    rv = vol.rank(axis=1, pct=True)
    F["g105"] = -ro.rolling(10, min_periods=10).corr(rv)

    # 093
    rec = (op - lo).where(op < op.shift(1), 0.0)
    rec = np.maximum(rec, (op - op.shift(1)).where(op < op.shift(1), 0.0))
    F["g093"] = rec.rolling(20, min_periods=20).sum()

    # 118
    F["g118"] = ((hi - op).rolling(20, min_periods=20).sum()
                 / (op - lo).rolling(20, min_periods=20).sum().replace(0.0, np.nan) * 100.0)

    # 096
    pos9 = (cl - lo.rolling(9, min_periods=9).min()) / (
        hi.rolling(9, min_periods=9).max() - lo.rolling(9, min_periods=9).min()).replace(0.0, np.nan)
    F["g096"] = sma(sma(pos9 * 100.0, 3, 1), 3, 1)

    # 111
    inner = vol * ((cl - lo) - (hi - cl)) / rng
    F["g111"] = sma(inner, 11, 2) - sma(inner, 4, 2)

    log("shift(1) 并落盘 ...")
    parts = []
    for name, df in F.items():
        s = df.shift(1).stack(future_stack=True)
        s.name = name
        s.index = s.index.set_names(["date", "ticker"])
        parts.append(s)
    out = pd.concat(parts, axis=1).reset_index()
    out["date"] = pd.to_datetime(out["date"])
    out.to_parquet(OUT, index=False, compression="zstd")
    log(f"写出 {OUT}  {out.shape}  用 {time.time()-t0:.0f}s")
    print(out.head(3).to_string())
    print("\n覆盖率：")
    print((out.drop(columns=["date", "ticker"]).notna().mean().round(3)).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
