"""Build the GTJA191 first-batch research panel.

Design choices for PIT:

* GTJA rolling factors are computed on the previous completed trading day and then
  shifted one calendar row to the current decision date T.
* ``gtja_015`` is the only candidate that uses T's own opening auction price, which is
  known at 10:00 and therefore safe at the 14:30 decision time.
* The evaluation sample starts at 2023-09-11, while factor history is computed from
  2020-01-02 onward so rolling windows are fully populated.
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

from factorlab import labels as L  # noqa: E402
from factorlab.features import price_volume as pv  # noqa: E402

DATA = Path(r"\\wsl.localhost\Ubuntu\home\pl_ubuntu\my_quantproject\wpqc_factor\data_rq")
UNIVERSE = REPO / "data" / "curated" / "cn_index_pit_universe_20200102_20260518.parquet"
OUT_DIR = HERE / "result"
OUT = OUT_DIR / "panel.parquet"

START = "2020-01-02"
END = "2026-05-13"
EVAL_START = "2023-09-11"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def read_30m(field: str) -> pd.DataFrame:
    path = DATA / f"cn_stock_30m_post_{field}_20200101_20260518.parquet"
    df = pd.read_parquet(path)
    df.index.name = "datetime"
    return df


def read_daily(field: str) -> pd.DataFrame:
    path = DATA / f"cn_stock_{field}_20200101_20260513.parquet"
    df = pd.read_parquet(path)
    df.index.name = "date"
    return df


def aggregate_30m_to_daily(df: pd.DataFrame, how: str) -> pd.DataFrame:
    day = df.index.normalize()
    out = df.groupby(day).agg(how)
    out.index.name = "date"
    return out


def at_time(wide: pd.DataFrame, tod: str) -> pd.DataFrame:
    t = pd.Timestamp(tod).time()
    out = wide[wide.index.time == t].copy()
    out.index = out.index.normalize()
    out.index.name = "date"
    return out


def rank_pct_cross(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(axis=1, pct=True)


def rolling_corr(a: pd.DataFrame, b: pd.DataFrame, window: int) -> pd.DataFrame:
    cov = a.rolling(window, min_periods=window).cov(b)
    sa = a.rolling(window, min_periods=window).std(ddof=0)
    sb = b.rolling(window, min_periods=window).std(ddof=0)
    return cov / (sa * sb).replace(0.0, np.nan)


def gtja_001(open_: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    data1 = rank_pct_cross(volume.diff(1))
    data2 = rank_pct_cross((close - open_) / open_)
    return -rolling_corr(data1, data2, 6)


def gtja_016(volume: pd.DataFrame, vwap: pd.DataFrame) -> pd.DataFrame:
    temp1 = rank_pct_cross(volume)
    temp2 = rank_pct_cross(vwap)
    corr = rolling_corr(temp1, temp2, 5)
    return -corr.rolling(5, min_periods=5).max()


def gtja_049(high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    cond_up = (high + low) > (prev_high + prev_low)
    cond_dn = (high + low) < (prev_high + prev_low)
    mag = np.maximum((high - prev_high).abs(), (low - prev_low).abs())

    down = mag.where(cond_dn, np.nan).rolling(12, min_periods=1).sum()
    up = mag.where(cond_up, np.nan).rolling(12, min_periods=1).sum()
    return down / (down + up).replace(0.0, np.nan)


def gtja_057(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    hi = high.rolling(9, min_periods=9).max()
    lo = low.rolling(9, min_periods=9).min()
    pos = (close - lo) / (hi - lo).replace(0.0, np.nan)
    return pos.ewm(alpha=1.0 / 3.0, adjust=False).mean()


def ts_rank(series: pd.DataFrame, window: int) -> pd.DataFrame:
    return series.rolling(window, min_periods=max(3, window // 2)).rank(pct=True)


def gtja_117(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
             volume: pd.DataFrame) -> pd.DataFrame:
    x1 = 1.0 - ts_rank(close + high - low, 16)
    x2 = ts_rank(volume, 32)
    ret = close / close.shift(1) - 1.0
    x3 = 1.0 - ts_rank(ret, 32)
    return x1 * x2 * x3


def gtja_015(open_: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    return open_ / close.shift(1) - 1.0


def align(common_dates: pd.DatetimeIndex, common_cols: pd.Index,
          frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for name, df in frames.items():
        df = df.reindex(index=common_dates, columns=common_cols)
        df.index.name = "date"
        df.columns.name = "ticker"
        out[name] = df
    return out


def stack_named(df: pd.DataFrame, name: str) -> pd.Series:
    s = df.stack(future_stack=True).rename(name)
    s.index = s.index.set_names(["date", "ticker"])
    return s


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log("read 30m close/open/volume")
    close30 = read_30m("close")
    open30 = read_30m("open")
    volume30 = read_30m("volume")

    log("read daily amount and market cap")
    daily_amount = read_daily("total_turnover")
    daily_mktcap = read_daily("market_cap")

    log("build daily price/volume from 30m files")
    daily_open = at_time(open30, "10:00:00")
    daily_close = at_time(close30, "15:00:00")
    daily_high = aggregate_30m_to_daily(read_30m("high"), "max")
    daily_low = aggregate_30m_to_daily(read_30m("low"), "min")
    daily_volume = aggregate_30m_to_daily(volume30, "sum")

    snap_fields = {
        "c1100": at_time(close30, "11:00:00"),
        "c1130": at_time(close30, "11:30:00"),
        "c1330": at_time(close30, "13:30:00"),
        "c1430": at_time(close30, "14:30:00"),
        "c1500": at_time(close30, "15:00:00"),
        "o1000": at_time(open30, "10:00:00"),
        "v1430": at_time(volume30, "14:30:00"),
    }

    common_dates = daily_open.index.intersection(daily_close.index).intersection(daily_high.index)
    common_dates = common_dates.intersection(daily_low.index).intersection(daily_volume.index)
    common_dates = common_dates.intersection(daily_amount.index).intersection(daily_mktcap.index)
    common_dates = common_dates.intersection(snap_fields["c1430"].index)
    common_dates = common_dates[(common_dates >= pd.Timestamp(START)) &
                                (common_dates <= pd.Timestamp(END))]

    common_cols = daily_open.columns.intersection(daily_close.columns)
    for df in (daily_high, daily_low, daily_volume, daily_amount, daily_mktcap):
        common_cols = common_cols.intersection(df.columns)

    log(f"aligned daily universe: {len(common_dates)} dates x {len(common_cols)} tickers")

    d = align(common_dates, common_cols, {
        "open": daily_open,
        "close": daily_close,
        "high": daily_high,
        "low": daily_low,
        "volume": daily_volume,
        "amount": daily_amount,
        "mktcap": daily_mktcap,
    })

    vwap = d["amount"] / d["volume"].replace(0.0, np.nan)
    daily_ret = d["close"].pct_change(fill_method=None)

    log("compute GTJA191 factors")
    gtja = {
        "gtja_001": gtja_001(d["open"], d["close"], d["volume"]).shift(1),
        "gtja_016": gtja_016(d["volume"], vwap).shift(1),
        "gtja_049": gtja_049(d["high"], d["low"]).shift(1),
        "gtja_057": gtja_057(d["close"], d["high"], d["low"]).shift(1),
        "gtja_117": gtja_117(d["close"], d["high"], d["low"], d["volume"]).shift(1),
        "gtja_015": gtja_015(d["open"], d["close"]),
    }

    log("compute labels and baseline controls")
    labels = L.build_all(snap_fields)
    vol_ratio = pv.vol_ratio(snap_fields["v1430"])
    ret_20d = pv.ret_nd(snap_fields["c1430"], 20)
    amihud_lag = pv.amihud(daily_ret, d["amount"], lag=1)
    amt20_lag = pv.amt20_lag(d["amount"], lag=1)
    vol_20d = pv.vol_20d(daily_ret, lag=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_amt20 = np.log(amt20_lag.replace(0.0, np.nan))
        log_mktcap = np.log(d["mktcap"].shift(1).replace(0.0, np.nan))

    gap = snap_fields["o1000"] / snap_fields["c1500"].shift(1) - 1.0
    intraday = snap_fields["c1430"] / snap_fields["o1000"] - 1.0
    day_ret = (1.0 + gap) * (1.0 + intraday) - 1.0
    tradable = ((day_ret.abs() < 0.095)
                & (snap_fields["v1430"] > 0)
                & (amt20_lag > 5.0e7)).fillna(False)

    series = {
        **{k: v for k, v in gtja.items()},
        "vol_ratio": vol_ratio,
        "ret_20d": ret_20d,
        "amihud_lag": amihud_lag,
        "amt20_lag": amt20_lag,
        "vol_20d": vol_20d,
        "log_amt20": log_amt20,
        "log_mktcap": log_mktcap,
        **labels,
        "tradable": tradable,
    }

    log("stack and join")
    eval_mask = common_dates >= pd.Timestamp(EVAL_START)
    eval_dates = common_dates[eval_mask]
    parts = []
    for name, df in series.items():
        df = df.reindex(index=eval_dates, columns=common_cols)
        parts.append(stack_named(df, name))
    panel = pd.concat(parts, axis=1).reset_index()
    panel["date"] = pd.to_datetime(panel["date"])

    uni = pd.read_parquet(UNIVERSE).rename(columns={"order_book_id": "ticker"})
    uni["date"] = pd.to_datetime(uni["date"])
    uni = uni[["date", "ticker", "pool"]]
    panel = panel.merge(uni, on=["date", "ticker"], how="inner")
    panel = panel[["date", "ticker", "pool"] +
                  [c for c in panel.columns if c not in ("date", "ticker", "pool")]]

    keep_cols = [c for c in panel.columns if c != "tradable"]
    panel = panel[panel[keep_cols].notna().any(axis=1)].reset_index(drop=True)
    panel = panel.sort_values(["date", "ticker"]).reset_index(drop=True)

    log(f"panel {panel.shape}: {panel['date'].min().date()} ~ {panel['date'].max().date()}")
    panel.to_parquet(OUT, index=False, compression="zstd")
    log(f"wrote {OUT}")


if __name__ == "__main__":
    main()
