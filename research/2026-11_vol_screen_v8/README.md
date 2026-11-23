# 高波动排除逻辑修 V8 顶端失效

**一句话进度**：门 1 立项 → 判决完成，**假设被证伪**且方向相反。见 [conclusion.md](conclusion.md)。

| 文件 | 说明 |
|---|---|
| [idea.md](idea.md) | 假设 + 精确构造 + 可证伪预测 + **失败判据（跑之前写死）** |
| [config.yaml](config.yaml) | 参数（波动阈值固定 2/3，不做搜索） |
| [run.py](run.py) | 唯一执行入口 |
| [conclusion.md](conclusion.md) | 判决（门 7） |
| `result/` | `screen_results.csv`、`screen_diagnostic.csv`、`verdict.csv`、`portfolio.csv`、`mirror.py`（方向对照） |

## 结论摘要

* 剔除高波动前 1/3：**判据只过 1/5**，OOS 从 +9.39 掉到 −0.35bp/日。
* 诊断反转：基线 top-4 里**被剔掉的高波动成员 +34.78bp，保留的低波动成员 −11.10bp**。
* 反向验证（剔低波动）OOS +16.01 vs 基线 +9.39，但全样本只高 1.2bp → 未确认。
* **方法论教训**：全交易日口径与高档日口径给出相反结论；筛选检验必须在本策略的真实持仓日上做。
