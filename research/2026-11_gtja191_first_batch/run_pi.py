"""Permutation importance for the GTJA191 first batch.

The generic template skipped PI because the panel did not contain ``*_z`` columns.
This script builds them, then uses ``factorlab.audit.permutation`` with a two-pool
portfolio whose combined budget is 0.96 (0.48 per pool).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from factorlab.audit import permutation as PI  # noqa: E402
from factorlab.portfolio import backtest, select  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((HERE / "config.yaml").read_text(encoding="utf-8"))
    panel = pd.read_parquet(REPO / cfg["data"]["panel"])
    panel["date"] = pd.to_datetime(panel["date"])

    # Only the candidates that survived factor-layer and orthogonalization gates.
    keep = {"gtja_057": -1.0, "gtja_001": 1.0, "gtja_117": 1.0}
    factors = {f["id"]: float(f["direction"]) for f in cfg["factors"]
               if f["id"] in keep}
    pf = cfg["portfolio"]
    label = cfg["labels"]["primary"]
    by = ("pool", "date")

    z = select.zscore(panel, list(factors), by=by, clip=pf["z_clip"])
    if "tradable" in z.columns:
        z = z[z["tradable"].fillna(False)].copy()
    z_cols = {f + "_z": w for f, w in factors.items()}

    def run_backtest(scored: pd.DataFrame) -> pd.Series:
        picks = select.top_n(
            scored,
            n=pf["n_picks_per_pool"],
            by=by,
            eligible="tradable" if "tradable" in scored.columns else None,
        )
        picks = backtest.equal_weight(
            picks,
            by=by,
            budget=pf["budget"],
            cap=pf["max_weight"],
        )
        return backtest.backtest(
            picks,
            label=label,
            cost_one_way=pf["cost_one_way"],
        )["net"]

    n_perm = 10
    result = PI.permutation_importance(
        z,
        factor_z_cols=z_cols,
        run_backtest=run_backtest,
        by=by,
        n_perm=n_perm,
        include_noise_control=True,
    )
    result = PI.net_information(result)
    out = HERE / "result" / "permutation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    print(result.to_string(index=False, float_format=lambda x: f"{x: .4f}"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
