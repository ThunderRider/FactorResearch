# 旧项目档案（Legacy）

> **这里存放 `my_quantproject` 下已有项目的原始文档，逐字复制，未做任何删改。**
> 目的：① 结论可追溯（每个数字都能回查原文）；② 新仓库不重复造轮子；
> ③ 未来如果有人问"当初到底怎么做的"，能拿到一手材料。
>
> **这不是"归档区"（意思是"以后不看"），恰恰相反——它是证据库。**

---

## 迁移约定

1. **原文逐字复制**，不删、不改、不重新排版。文件与源文件 **字节一致**，可直接 `diff` 核对。
2. **来源记录在各子目录的 `README.md` 里**（源路径 + 迁移日期 + 该文件当时的作用）。
3. 需要"浓缩版"时**另写一篇**，开头写 `> 浓缩自 <原文件>`，两份都保留。
4. **不要在旧文件里修 bug 或改数字。** 发现错误 → 在 `docs/03_knowledge/` 里加一条"更正"。
   原始文档的错误本身是教训。

---

## 五个项目，各是什么

| 项目 | 一句话 | 代码 | 数据 | 本仓库位置 |
|---|---|---|---|---|
| **wpqc**（慧抢筹） | A 股尾盘选股 + 次日卖出。V1→V8 八个版本，**研究纪律最完整**（试验记录、防过拟合审计、证伪清单齐全） | `strategy01~08.py`、`overfit_lab/` | 30 分钟 bar、461MB 面板、1.2GB 缓存 | [`wpqc_maqiangchou/`](wpqc_maqiangchou/) |
| **wpqc_factor** | RESI / rolling_coef_std 单因子研究 + 30m/5m 数据构建脚本 + 日内动量复现 | `prepare_*_rq.py`、notebooks | `data_rq/`（30m/5m parquet 缓存，可直接复用） | [`wpqc_factor_resi/`](wpqc_factor_resi/) |
| **hzbplus** | ASP：成交额线性回归斜率择时 + vectorbt 全市场参数寻优 | `ASP_*.py`、`runner_*.py` | 日线宽表 CSV | [`hzbplus_asp/`](hzbplus_asp/) |
| **hfc** | 慧点睛 HDJ：CLS（财联社）事件驱动，SQL Server + MySQL，已生产化 | `hdj_strategy*.py`、`cls_sqltest.py` | CLS 电报、票池 | [`hfc_hdj/`](hfc_hdj/) |
| **（散落）** | 日内动量策略复现（美股 SPY 5m/1min，作为方法论对照） | — | yfinance | [`intraday_momentum/`](intraday_momentum/) |

---

## 迁移后怎么用这些档案

| 你的目的 | 读哪个 |
|---|---|
| 想知道"某个数字从哪来" | 直接 grep 对应文件（结论文件里都写了出处） |
| 想复用某个做法（PIT 校验、脆落性曲线、安慰剂） | `../02_methods/`，那里已经提炼成方法 |
| 想知道"这个坑以前踩过吗" | `../03_knowledge/lessons_learned.md` + `falsified.md` |
| 想复用数据缓存 | 见 [`wpqc_factor_resi/README.md`](wpqc_factor_resi/README.md) 的"可直接复用的数据" |
| 想复用代码 | 见各目录 README 的"值得搬的代码" |

---

## wpqc 的文档体系（为什么它值得学）

这个项目的文档分了四层，每层有明确职责，**这是本仓库 `docs/` 结构的直接来源**：

```
STRATEGY_V6_FINAL.md      对外材料：能讲的都讲了（且明确标注"因子部分保密"）
STRATEGY_V6_INTERNAL.md   对内全解：因子构造、参数、证据
EXPERIMENTS_V1_V6.md      实验全记录：V1→V6 每一次改动的对照数字
OVERFITTING_TESTS_V6.md   测试设计：为什么这么测（含"该做但没做"的清单）
P0_P1_RESULTS.md          测试结果：12 项检查的判定与结论
```

**最值得学的一点**：`OVERFITTING_TESTS_V6.md` 是**先写"该测什么"再测**，
`P0_P1_RESULTS.md` 是**结果逐项对照判定线**。
两者分开，避免了"看着结果编测试"。

**最值得学的第二点**：它公开承认自己的缺陷。

> "真正缺的，是'审计层'——全部缺失：N 记账 / DSR / PBO / Purging / 置换重要性 / 脆弱性曲线。"

这句话在这个项目里的价值，超过任何一个正收益的数字。

---

## 目录清单

```
04_legacy/
├── README.md                          ← 你在这里
├── wpqc_maqiangchou/                  ← 慧抢筹 V1→V8（14 篇）
├── wpqc_factor_resi/                  ← RESI 单因子 + 数据构建（5 篇）
├── hzbplus_asp/                       ← ASP 成交额斜率（4 篇）
├── hfc_hdj/                           ← 慧点睛 HDJ 运维手册（1 篇）
└── intraday_momentum/                 ← 日内动量复现规格（1 篇）
```

参考材料在 `../03_knowledge/reference/`：

```
量化防过拟合系列重塑_merged.pdf        ← 8 篇框架（WFV / 正则化 / DSR / PBO-CSCV /
                                        Purging-Embargo / 置换重要性 / 非平稳 / Fool's Gold）
```

**这份 PDF 是 `../02_methods/overfitting_controls.md` 的理论来源。** 建议先读方法文档，
遇到需要原始推导时再翻 PDF。
