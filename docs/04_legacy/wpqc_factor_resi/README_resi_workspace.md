# Factortest RESI / rolling_coef_std

Research workspace for testing the MAC high `RESI` + low `rolling_coef_std`
stock-selection strategy.

## Main Notebooks

- `analyze_wpqc_resi_rolling_coef.ipynb`: single-factor and combined-factor analysis.
- `analyze_mac_high_resi_low_coef.ipynb`: dedicated MAC high RESI then low coefficient-std analysis.
- `backtest_mac_high_resi_low_coef_w80_top5_top3_vectorbt.ipynb`: fixed-parameter vectorbt backtest, including 30-minute approximation and 5-minute `14:45 -> 11:15` RQAlpha-fee experiment.

## Data Builders

- `prepare_wpqc_resi_data_rq.py`: 30-minute OHLCV parquet cache builder.
- `prepare_wpqc_5m_data_rq.py`: 5-minute MAC universe OHLCV parquet cache builder.
- `prepare_cn_stock_data_rq.py`: daily stock data builder used by earlier analysis.

## Notes

`config.yaml` is ignored to avoid leaking RQData credentials. Some local data
files exceed GitHub's 100 MB file limit and are excluded; see
`DATA_UPLOAD_NOTES.md`.
