# 把 vol_20d 作为正因子放进 V8 打分

**一句话进度**：门 1 立项 → 判决完成，**假设不成立（2/6）**。见 [conclusion.md](conclusion.md)。

| 文件 | 说明 |
|---|---|
| [idea.md](idea.md) | 假设 + 精确构造 + 可证伪预测 + **失败判据（跑之前写死）** |
| [config.yaml](config.yaml) | 参数（主口径 w=1.0，先验等权；0.25/0.5 只作稳健性） |
| [run.py](run.py) | 唯一执行入口 |
| [conclusion.md](conclusion.md) | 判决（门 7） |
| `result/` | `score_results.csv`、`verdict.csv`、`diagnostic_replacement.csv`、`portfolio.csv` |

## 结论摘要

* 样本内 N=4 改善（20.98 → 24.63bp/日），**样本外从 +9.39 掉到 +1.18**。
* 权重扫描无稳定方向：IS 最优 w=0.5 在 OOS 最差，OOS 最优 w=0.25 在 IS 最差 → 噪声。
* V5：同波动缩放后 v1 = +10.25bp > v2 = +1.18bp → **只是换 beta，选股变差**。
* 副产品：z(vol_20d) 与 z(amihud) 截面相关 −0.04，两者正交，共线担忧不成立。
* **这是修"V8 顶端失效"的第三次失败**（宽度 / 高波动排除 / vol 进打分），
  建议停止在该方向加 N，并考虑把 V8 从 `active` 降级。
