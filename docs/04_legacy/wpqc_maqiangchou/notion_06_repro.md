# 慧抢筹 V7 · 复现与代码

> 本文说明 V7 的代码结构、5 处改动、如何运行、以及如何在不连行情库的情况下复现全部结论。

---

## 1. 文件结构

```
wpqc/
├── strategy07.py            ★ V7 生产版（本文档的主角）
├── strategy06.py              V6 研究版（含决策器，保留对照）
├── strategy02.py              工具库：取数 / 成分股 / 指数档位 / RESI
├── strategy04.py              V3 选股原型（V7 继承其逻辑）
├── test_strategy07.py         V7 冒烟测试（13 项）
│
├── STRATEGY07.md              V7 策略逻辑说明
├── EXPERIMENTS_V1_V6.md       V1→V6 实验全记录
├── P0_P1_RESULTS.md           P0/P1 防过拟合审计结果
├── OVERFITTING_TESTS_V6.md    测试设计依据（为什么这么测）
│
├── overfit_lab/               ★ 离线复现与审计引擎（不需要 rqdatac）
│   ├── core.py                选股 + 回测 + 指标
│   ├── validate.py            复现校验
│   ├── p0.py                  P0-1 ~ P0-4
│   ├── p1.py                  P1-5 ~ P1-9
│   ├── summary.py             修正叠加口径表
│   └── extract.py             大文件 → 快速缓存
│
└── eval_out/
    ├── v7_report.txt          V7 业绩报告（含脆弱性表）
    ├── overfit/               P0/P1 的全部结果 CSV
    └── panel_*.pkl            因子面板（2.9M 行）
```

---

## 2. V7 的 5 处代码改动

### 改动 1：`amt20` 滞后（去掉 15 分钟前视）

```python
# strategy07.py · add_factors()
AMT_LAG = 1

amt20 = g('day_amt').transform(
    lambda s: s.rolling(AMT_WINDOW, min_periods=MIN_HISTORY).mean())
out['amt20'] = amt20.groupby(level=0).shift(AMT_LAG) if AMT_LAG else amt20
```

**为什么**：V6 的 `amt20` 含当日 15:00 的成交额，而决策在 14:45。
修正后 V3 净年化 −1.66pp、V6 −1.97pp，6.02% 的选股发生变化。

### 改动 2：缺失收益显式记账

```python
def _eval(target, rets, cost=0.001, ret_col='ret_total', exit_cost=0.0):
    ...
    m['w_ret'] = m['TARGET_WEIGHT'] * m[ret_col]
    m['is_missing'] = m[ret_col].isna()          # ← 新增
    d = m.groupby('date').agg(exposure=('TARGET_WEIGHT', 'sum'),
                              gross=('w_ret', 'sum'),
                              n_miss=('is_missing', 'sum')).sort_index()
```

**为什么**：原来 NaN 在 `sum()` 里被静默跳过，等于"按 0% 成交"。
实测只有 8 笔（全在样本最后一天），影响 0.00pp，但必须记账。

### 改动 3：默认模式改为纯 V3

```python
p.add_argument('--mode', default='v3', choices=['v3', 'decision', 'both'])
```

**为什么**：决策器 PBO = 56.3%、禁运后样本外 Sharpe 腰斩、2026 年超额全靠单日。

### 改动 4：卖出腿滑点参数

```python
p.add_argument('--exit-cost-bp', type=float, default=0.0)

# _eval 内：
d['cost'] += exit_cost * d['exposure']
```

**为什么**：13:30 出场的 +4.3pp 增量，在卖出腿多付 5bp 后归零。
报告必须能同时给出这两个口径。

### 改动 5：脆弱性表

```python
def fragility(ret, ks=(0, 1, 2, 3, 5, 8, 10, 15, 20)):
    for k in ks:
        y = ret.drop(index=ret.nlargest(k).index) if k else ret
        rows.append(dict(k=k, ann=_perf(y)['ann'], sharpe=_perf(y)['sharpe']))
```

**为什么**：去掉最好 5 天归零，这是必须披露的集中度特征。

---

## 3. 怎么运行

### 3.1 生产（需要 rqdatac 授权）

```bash
# 默认：11:15 卖出
python strategy07.py --config ./config.yaml --mode v3

# 13:30 卖出 + 卖出腿 5bp（V7 建议的报告口径）
python strategy07.py --mode v3 --exit-time 13:30 --exit-cost-bp 5

# 复用行情缓存（调试）
python strategy07.py --mode v3 --reuse-cache

# 研究：决策器（不推荐实盘）
python strategy07.py --mode decision
```

输出：`wpqc_v7.csv`、`wpqc_v7_signal.csv`、`eval_out/v7_report.txt`、`eval_out/v7_fragility.csv`。

### 3.2 冒烟测试（不需要行情库）

```bash
python test_strategy07.py
```

覆盖 13 项：导入、`amt20` 确实滞后、`AMT_LAG=0` 能回到原口径、`_eval` 的缺失记账、
`exit_cost` 计提方向、`allocate` 的 19% 上限、`fragility` 单调性。

### 3.3 离线复现与审计（不需要 rqdatac）

```bash
python -m overfit_lab.extract     # 一次性：1.2GB bar → 快照，461MB 面板 → parquet
python -m overfit_lab.validate    # 复现校验（必须先通过）
python -m overfit_lab.p0          # P0-1 ~ P0-4
python -m overfit_lab.p1          # P1-5 ~ P1-9（p15 建议 --n-perm 100）
python -m overfit_lab.summary     # 修正叠加口径表
```

---

## 4. 复现校验（为什么这些反事实实验可信）

`python -m overfit_lab.validate` 的输出：

| 项目 | 离线 vs 生产 | 一致性 |
|---|---|---|
| V3 选股 | 6048 / 6064 行 | recall **99.72%** |
| V3 日度净收益 | 756 天 | 相关 **0.99985**，平均绝对差 0.06bp |
| V1 选股 | 4602 / 4596 行 | recall **100.00%** |
| 决策器 | 204 / 204 天触发 | 一致率 **100%** |
| 档位 | 权重反推 vs 斜率信号 | 一致率 **100%** |

离线基线 V3 11:15 = 9.59%，生产 = 9.42%，差 0.17pp 来自 `rank(method='first')` 的并列处理。

---

## 5. 数据依赖

| 文件 | 大小 | 用途 |
|---|---|---|
| `eval_out/panel_*.pkl` | 461 MB | 因子 + 目标收益面板（2,918,536 行 × 3761 只） |
| `eval_out/v6_cache.pkl` | 1.2 GB | 30 分钟 bar 原始行情（用于 13:30 口径） |
| `eval_out/ic_daily.csv` | 4 MB | 逐日 IC |
| `eval_out/index_slope_cmp.pkl` | 65 KB | 指数成交量斜率（档位信号） |
| `eval_out/industry_map.pkl` | 90 KB | 行业分类（正交化用） |

`overfit_lab/extract.py` 会把前两个压成 `D:\ovt_cache\*.parquet`（可用 `OVT_CACHE` 改路径）。

---

## 6. 已知限制

1. **没有市值数据**：`bundle/` 里没有估值表，amihud 的市值正交化用 20 日均成交额代理，
   真正的"对市值正交"尚未做。
2. **V7 未在本机实跑**：本机没有 rqdatac 授权，V7 的性能数字来自离线复现引擎（同一套逻辑）；
   实盘前必须在生产环境跑一次 `strategy07.py` 对账。
3. **13:30 的 `ret_total_1330`** 用 `c1330.shift(-1)` 计算，与生产口径一致，但依赖行情缓存的完整性。
4. **样本只有 3.2 年、单一 regime**：不包含 2015/2018 式的系统性熊市，PBO/WFV 只能部分补偿。

---

## 7. 后续可做（已在计划里但未执行）

| 优先级 | 事项 | 预期产出 |
|---|---|---|
| P2-10 | 执行价假设（VWAP / 下一根 bar 开盘） | 入场价敏感性 |
| P2-11 | 冲击成本内生化 | AUM 上限曲线 |
| P2-12 | 档位窗口敏感性（102/72 → 60/90/120/150） | 唯一没做对照的参数 |
| P2-13 | 多假设控制（BH-FDR，12 因子 × 4 段） | 因子筛选的统计底线 |
| P2-14 | 因子退役规则（CUSUM 断点） | `ret_20d` 的处置 |
