# wpqc · 慧抢筹（V1 → V8）

> **源目录**：`~/my_quantproject/wpqc/`
> **迁移日期**：2026-11-20
> **迁移方式**：逐字复制，字节一致，未做任何修改
> **项目性质**：A 股尾盘选股 + 次日卖出，日频全换手；已生产化

---

## 这个项目是什么

```
T 日 14:45 买入 → T+1 日 11:15（或 13:30）清仓 → 每日 100% 全换手
两个股票池：大盘池 = 沪深300 + 中证500；小盘池 = 中证1000 + 中证2000（剔除 ST）
```

三个核心结论（V7 定稿）：

1. 选股层是 **1 个真因子 + 2 个暴露**（`vol_ratio` 独立；`amihud`、`ret_20d` 不独立）
2. 仓位层（指数成交量斜率档位）是**全套最结实的一层**，2026 年贡献 +33.73pp
3. 决策器（离散度择线）**已失效**，降级为"研究记录"

---

## 文件清单与读法

### 层 1 · 对外材料

| 文件 | 是什么 | 什么时候读 |
|---|---|---|
| `STRATEGY_V6_FINAL.md` | V6 定稿的对外说明书（明确标注"因子构造属保密内容"） | 想看"对外怎么说" |
| `STRATEGY07.md` | V7 策略逻辑（去掉前视、默认纯 V3、成本口径说实话） | 想看"审计之后怎么改" |
| `STRATEGY08.md` | V8 结构版（2+4=6 只、等权、统一档位） | 想看"从参数问题拆出结构问题" |

### 层 2 · 对内全解

| 文件 | 是什么 |
|---|---|
| `STRATEGY_V6_INTERNAL.md` | V6 因子全解（构造、参数、证据链） |
| `notion_02_factors.md` | V7 因子全解（三个因子的经济含义 + 统计证据 + **哪些说法已不成立**） |
| `notion_05_performance.md` | V7 业绩 |
| `notion_06_repro.md` | V7 的代码结构、5 处改动、复现方式 |
| `STRATEGY06.md` | V6 详细说明（一个脚本、两条选股线、一个决策器） |

### 层 3 · 实验记录（**最有价值的一层**）

| 文件 | 内容 |
|---|---|
| `EXPERIMENTS_V1_V6.md` | ★ **V1→V6 实验全记录**（652 行）。统一实验口径、盈亏平衡线的来历、6 个版本的对照、**7 个因子实验的完整证伪过程**、2026 年专项归因、出场时点矩阵、流动性检验 |
| `OVERFITTING_TESTS_V6.md` | ★ **防过拟合体检与测试清单**（402 行）。八篇框架 → 三层的映射、"做到/没做到"对照表、现场补做的 6 个诊断、P0/P1/P2 清单 |
| `P0_P1_RESULTS.md` | ★ **P0/P1 执行报告**（321 行）。12 项检查的判定线与实际结果、修正后的口径表、对策略含义的 5 条结论 |

### 层 4 · CLS 票池（事件类数据的旁支）

| 文件 | 内容 |
|---|---|
| `cls_pool_README.md` | 财联社电报 → 每日票池。**PIT 校验做得最干净的一份**（截断不变性 8/8） |
| `cls_pool_EVAL_FACTORS_CLS.md` | 在该票池上评估因子 |
| `cls_pool_EVAL_V8_ON_CLS.md` | ★ 把 V8 套到 CLS 票池 → **"不建议部署"**。因子有效但迁移不了（够不着尾部） |

---

## 三个必读段落

### 1. 盈亏平衡线的来历（`EXPERIMENTS_V1_V6.md` §1.3）

```
每日成本率 = 0.1% × 2 × 日均敞口
每单位敞口的日收益必须 > 0.200% 才不亏钱

V1: 0.196%  → 差一点 → 净 −0.9%
V3: 0.315%  → 过线   → 净 +9.4%
```

> "评价这类策略，看'年化收益'没用，要看'每单位敞口的日收益'。
> 因为它把'选股质量'和'仓位大小'分开了。"

**这条已经被搬到 `docs/02_methods/portfolio_eval.md` 作为第一原则。**

### 2. 那个"诚实的瞬间"（`OVERFITTING_TESTS_V6.md` §3.2）

> "顺带一个'反优化'的好消息：全样本 SR 最高的是 `T=0.6`（0.97），文档选了中性 `T=0.5`（0.91）。
> **这是主动放弃最优点、选了最稳点**——这条要写进材料，它是'我们没在调参'的证据。"

**这种记录比任何"我们没有过拟合"的声明都有说服力。**
新仓库要求把类似的时刻写进 `conclusion.md`（见 `docs/03_knowledge/lessons_learned.md` L15）。

### 3. 自我诊断（`OVERFITTING_TESTS_V6.md` §0）

> "这套策略不是'没做过防过拟合'，而是'**防过拟合做在了错误的层，且缺三件审计工具**'。"

它列出的"做对的四件事"（结构极简 / 时间顺序 / 安慰剂 / 证伪清单）
和"缺的六件事"（N 记账 / DSR / PBO / Purging / PI / 脆弱性曲线），
**就是本仓库 `docs/02_methods/overfitting_controls.md` 的结构来源。**

---

## 值得搬的代码（源目录里，未复制到本仓库）

> 代码没有复制过来——因为新仓库的 `src/factorlab/` 会重写这些逻辑。
> 但下面这些**设计**值得照抄：

| 源文件 | 值得抄什么 |
|---|---|
| `overfit_lab/core.py` | **离线复现层**：不依赖 rqdatac，只用本地快照把生产策略逐行复现。含 `Book`（选股矩阵）、`top_n`（向量化取前 N）、`allocate`（等权+上限再分配）、`backtest`（含成本） |
| `overfit_lab/validate.py` | **先证明"尺子是对的"**：离线 vs 生产的 recall 99.72%、日收益相关 0.99985、决策器一致率 100%。**做反事实实验前必做这一步** |
| `overfit_lab/p1.py` | 置换重要性、正交化、边界稳定性、禁运、出场时点验证的完整实现 |
| `eval_wpqc_factors.py` | `build_snapshot`（30m bar → 每日快照）、`ic_analysis`（池内 RankIC）、`decile_analysis`、`picks_report`（逐段收益分解 + 换手 + 成本） |
| `build_variant_panel.py` | 向量化 IC（`rank` + 矩统计，避免上百次 `groupby.apply`）；`bar_features`（RESI/coef_std 的多窗口变体） |
| `strategy02.py` | `fetch_price`（分块并发取数）、`build_pools`（PIT 成分股）、`index_signal`（档位） |

**反面参考**：`strategy01~08.py` 之间有约 40% 的重复代码。
新仓库的做法是**复用逻辑进 `src/factorlab/`，变体用 config 表达**。

---

## 值得复用的数据（在 `wpqc_factor/data_rq/`，未复制）

```
cn_stock_30m_post_{open,high,low,close,volume}_20200101_20260518.parquet   ~1.1GB
cn_mac_5m_post_{open,high,low,close,volume}_20200101_20260518.parquet      ~830MB
cn_index_30m_post_*_20200101_20260518.parquet                              ~1.7MB
cn_stock_{open,close,total_turnover,turnover_rate,market_cap}_*.parquet    ~270MB
cn_mac_pit_universe_20200101_20260518.parquet                              PIT 成分股快照 ⭐
cn_stock_universe_*.csv                                                    股票池快照
```

**命名规范与本仓库 `docs/01_architecture/data_layer.md` §2 完全一致** ——
意味着这些缓存**可以直接放进新仓库的 `data/curated/`**，不需要转换。
这是本仓库坚持沿用旧命名的实际原因。

详见 [`../wpqc_factor_resi/README.md`](../wpqc_factor_resi/README.md)。
