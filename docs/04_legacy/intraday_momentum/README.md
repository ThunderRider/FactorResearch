# 日内动量策略复现（方法论对照）

> **源文件**：`~/my_quantproject/wpqc_factor/intraday_momentum_strategy_reproduction_spec.md`
> （`hzbplus/` 下有一份完全相同的副本）
> **迁移日期**：2026-11-20
> **迁移方式**：逐字复制，字节一致
> **项目性质**：把一篇公开的**美股 SPY 日内动量**策略精确复现（规格文档 28 KB）

---

## 为什么这份文档值得保留

它不是"一个 A 股因子"，而是一个**方法论校准工具**。理由：

### 1. 它是外生的

这个策略来自公开研究 + 公开数据（yfinance 的 SPY 1min/5min），
**它的结论不依赖本项目的任何假设**。

所以它可以用作**管线的回归测试**：
如果你的 `factorlab` 管线跑不出文档里记录的结果，说明管线有问题，
而不是"这个策略没用"。

**这是唯一能用"外部真值"检验自己代码的方式。**

### 2. 它逼你想清楚"复现"到底是什么意思

```
能不能复现 = 用的是不是同一份数据（含时间戳口径、复权、时区）
           + 交易规则是不是逐条一致（入场/出场/成本/仓位）
           + 断点处理是不是一致（缺 bar、停牌、日切）
```

**大多数"复现失败"不是策略失效，是这三件事之一没对齐。**

### 3. 它把"规格文档"写成了可执行的形式

28 KB 的规格文档，包含：数据获取、bar 聚合、信号定义、执行假设、成本、
以及对照结果。**这是 `research/_template/` 应该产出的东西的样子。**

---

## 怎么用它

### 作为 `tests/` 的回归目标

```
tests/fixtures/
└── spy_1min_20260511_20260605.parquet     ← 见 wpqc_factor/data/spy/
```

（源目录有 `yfinance_SPY_1min_20260511_20260605_intraday.parquet` 等 4 个文件，
合计约 224 KB —— **可以安全地作为 fixture 复制进新仓库**。）

```python
# tests/test_intraday_momentum.py
def test_spy_intraday_momentum_reproduces():
    """用 fixture 数据复现规格文档的基准结果。若失败，说明管线有问题。"""
```

### 作为"研究规格"的范例

写 `idea.md` 时，参照它的颗粒度：

| 规格文档有的 | 本仓库要求 |
|---|---|
| 数据源与区间 | `data/MANIFEST.csv` |
| bar 定义（时间戳是开始还是结束） | `docs/01_architecture/conventions.md` §1 |
| 信号的精确定义 | `registry/factors.yaml` 的 `definition` |
| 执行假设（何时成交、什么价） | `docs/01_architecture/conventions.md` §3 |
| 成本 | `configs/default.yaml` |
| 预期结果与容差 | `conclusion.md` 的判定线 |

---

## 迁移清单

已复制：

```
intraday_momentum_strategy_reproduction_spec.md    28 KB
```

建议后续从源目录复制（**小文件，适合做 fixture**）：

```
~/my_quantproject/wpqc_factor/data/spy/
├── yfinance_SPY_1min_20260511_20260605_intraday.parquet        214 KB
├── yfinance_SPY_20260511_20260605_daily.parquet                  6 KB
├── yfinance_SPY_20260511_20260605_dividends.parquet              1.5 KB
└── yfinance_SPY_1min_20260511_20260605_cache_meta.json           1.6 KB
→ 目标：tests/fixtures/spy/
```

以及：

```
~/my_quantproject/wpqc_factor/results/spy_intraday_momentum/
└── SPY_1min_baseline_20260511_20260605_config.json      1.1 KB
→ 目标：tests/fixtures/spy/（作为回归基准）
```

**注意**：`.gitignore` 里有 `*.parquet` 的全局忽略，但已显式白名单
`!tests/fixtures/**`。这几个文件因此可以入库。

---

## 一句话

> **一个仓库最缺的往往不是"更多因子"，而是"一个能证明自己的管线是对的基准"。**
> 这份文档就是那个基准。
