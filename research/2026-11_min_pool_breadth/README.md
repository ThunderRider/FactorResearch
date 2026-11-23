# 小盘池持仓宽度（4 → 20 / 50）

**一句话进度**：门 1 立项 → 门 5 判决完成，结果 `watch`（F3 未过）。见 [conclusion.md](conclusion.md)。

| 文件 | 说明 |
|---|---|
| [idea.md](idea.md) | 假设 + 精确构造 + 可证伪预测 + **失败判据（跑之前写死）** |
| [config.yaml](config.yaml) | 参数（改任何一项 = 新试验） |
| [run.py](run.py) | 唯一执行入口：`python research/2026-11_min_pool_breadth/run.py` |
| [conclusion.md](conclusion.md) | 判决（门 7） |
| `result/` | `breadth_results.csv`、`gate1_verdict.csv`、`rank_band_profile.csv`、`top_failure_mechanism.csv`，以及三个诊断脚本（`ic_is_oos.py` / `rank_profile.py` / `mechanism.py`） |

## 结论摘要

* min 腿单位敞口日收益随宽度单调上升（4 → 20 → 50：+20.98 / +27.62 / +29.63 bp/日，全样本），
  OOS 同向（+9.39 / +15.29 / +15.50），波动按 1/√N 下降，同波动对照下仍然更好。
* **但 OOS 里没有任何宽度跑赢 min 池等权均值**（N=50 为 −4.32bp，44 天，标准误约 15bp）
  → 放宽宽度是"减少过度集中的伤害"，不是创造 alpha。
* 打分 IC 在 OOS 未衰减（+0.056，t=6.1），但 top-N 拿不到 → **顶端失效**是比宽度更根本的问题。
* 2023 年方向翻转（N=4 +34.29 vs N=50 −20.84）→ regime 依赖。

**判决 `watch`**：不得 `active`，下一步应先定位"顶端为什么失效"，而不是继续加宽。
