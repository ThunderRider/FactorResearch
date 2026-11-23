# Data Upload Notes

This repository includes the research code, notebooks, generated summaries, and
as much cached data as can be pushed to a normal GitHub repository without Git
LFS.

## Included

- Strategy source scripts and notebooks.
- Metadata JSON files under `data_rq/`.
- Small and medium parquet/CSV result files under the 100 MB GitHub file limit.
- 5-minute index OHLCV parquet files.
- Point-in-time MAC universe files.
- Backtest result tables and figures.

## Excluded Large Files

The local WSL environment does not have a working `git-lfs` binary, and GitHub
normal repositories reject individual files larger than 100 MB. The following
large local files are therefore excluded by `.gitignore`:

| Size | Path |
|---:|---|
| 852.39 MB | `results/wpqc_resi_rolling_coef_analysis/alphalens_factor_data_RESI.csv` |
| 839.57 MB | `results/wpqc_resi_rolling_coef_analysis/alphalens_factor_data_rolling_coef_std.csv` |
| 394.08 MB | `data_rq/cn_stock_30m_post_volume_20200101_20260518.parquet` |
| 310.31 MB | `data_rq/cn_mac_5m_post_volume_20200101_20260518.parquet` |
| 212.10 MB | `data_rq/cn_stock_30m_post_open_20200101_20260518.parquet` |
| 211.74 MB | `data_rq/cn_stock_30m_post_close_20200101_20260518.parquet` |
| 210.89 MB | `data_rq/cn_stock_30m_post_high_20200101_20260518.parquet` |
| 208.25 MB | `data_rq/cn_stock_30m_post_low_20200101_20260518.parquet` |
| 165.84 MB | `data_rq/cn_mac_5m_post_open_20200101_20260518.parquet` |
| 165.81 MB | `data_rq/cn_mac_5m_post_close_20200101_20260518.parquet` |
| 160.76 MB | `data_rq/cn_mac_5m_post_high_20200101_20260518.parquet` |
| 159.86 MB | `data_rq/cn_mac_5m_post_low_20200101_20260518.parquet` |

To upload these files later, install Git LFS and track `*.parquet` plus the two
large Alphalens CSV files, or publish the large datasets via a release asset or
external object storage.

## Additional Large Generated Files

The first push attempt with all sub-100MB files was still over 2GB and timed
out. To make the repository practical without Git LFS, the commit also excludes
large generated factor-cache parquet files and large turnover parquet files via
these patterns:

- `results/mac_high_resi_low_coef_analysis/*.parquet`
- `results/wpqc_resi_rolling_coef_analysis/*.parquet`
- `data_rq/cn_stock_total_turnover_*.parquet`
- `data_rq/cn_stock_turnover_rate_*.parquet`

These files can be regenerated from the notebooks/scripts or uploaded later via
Git LFS or release assets.

## Credentials

`config.yaml` is intentionally ignored because it may contain RQData credentials.
