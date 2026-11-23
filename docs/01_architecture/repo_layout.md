# 仓库布局：为什么这样分

> 一句话：**把"会变化的东西"和"不该变化的东西"分开**。
> 旧项目的教训是——数据、代码、结论、凭证全堆在一个目录里，18 个月后没人说得清哪个 CSV 是哪次跑的。

---

## 1. 五层的职责边界

```
┌──────────────────────────────────────────────────────────────────┐
│ L5  knowledge    docs/03_knowledge   +  docs/04_legacy           │
│     只读的结论：我们知道了什么、什么已证伪              (长期稳定) │
├──────────────────────────────────────────────────────────────────┤
│ L4  decision     registry/factors.yaml + trials_log.csv          │
│     当前状态：哪些因子处于什么状态、跑了多少次试验      (每轮更新) │
├──────────────────────────────────────────────────────────────────┤
│ L3  research     research/<direction>/                           │
│     一次研究的全部痕迹：idea → code → result → conclusion        │
├──────────────────────────────────────────────────────────────────┤
│ L2  library      src/factorlab/                                  │
│     被 ≥2 个研究复用的逻辑（取数、标签、IC、回测、审计）         │
├──────────────────────────────────────────────────────────────────┤
│ L1  data         data/{raw,curated,features,labels,panels}       │
│     可重建的资产：从 raw 一路推到 panels                (不入版本库) │
└──────────────────────────────────────────────────────────────────┘
```

**判据：一段代码该放哪里？**

| 情况 | 放哪 |
|---|---|
| 只有这一个研究方向会用 | `research/<direction>/` 里，就地放着 |
| 第二个研究要用它了 | **搬进 `src/factorlab/`**，并在原处留一行 import |
| 是配置而不是逻辑 | `configs/` |
| 是结论而不是代码 | `docs/` |

不要提前抽象。`src/factorlab/` 里只放**已经被复用过的**逻辑——这是旧项目 8 个 `strategy0X.py` 互相 copy 40%
的教训的反面。

---

## 2. 数据层为什么分五级，而不是一个 `data/`

旧项目的数据目录长这样（真实情况）：

```
wpqc/
├── LDmac_01.csv  34730 行     ← 这是什么？哪个日期？哪个池？
├── LDmac_cpv_016.csv 32523   ← 和上面差在哪？
├── wpqc_v6.csv   185610
├── variants_decile.csv  28MB
├── panel_*.pkl  461MB
└── ...  70+ 个 csv/pkl，命名靠记忆
```

问题不是"没整理"，是**没有层级，所以无法判断一个文件的角色**。新设计用五级，每级有唯一职责：

| 级别 | 目录 | 内容 | 可重建？ | 谁写 | 谁读 |
|---|---|---|---|---|---|
| 0 原始 | `data/raw/` | 外部文件原样落地（RQData 导出、xlsx、PDF 解析结果） | ❌ **不可**（要重新申请/下载） | 取数脚本 | curated 构建 |
| 1 规范 | `data/curated/` | 宽表矩阵：`date × ticker`，后复权，parquet | ✅ 从 raw | `factorlab.data.build` | features 构建 |
| 2 特征 | `data/features/` | 因子长表：`date, ticker, factor, value` | ✅ 从 curated | 因子代码 | 评估 |
| 3 标签 | `data/labels/` | 目标收益长表：`date, ticker, label, value` | ✅ 从 curated | `factorlab.labels` | 评估 |
| 4 面板 | `data/panels/` | features ⨝ labels（模型就绪，一次评估一个文件） | ✅ | 合并脚本 | eval / backtest |

**关键规则**：

1. **只能向下依赖**。`features` 不准读 `raw`，`panels` 不准重新取数。
2. **`raw` 只增不改**。要修正？新增一个 `raw/<dataset>/v2/`，并在 MANIFEST 里说明为什么 v1 作废。
3. **每级都写 MANIFEST**。任何数据集必须有 `data/MANIFEST.csv` 一行，否则视为不存在。
4. **`curated` 以"字段"为单位落盘，不以"品种"为单位**。旧项目 `cn_stock_30m_post_open_20200101_20260518.parquet`
   这种命名直接沿用——它不是好看，是**一行 `ls` 就能看出覆盖区间和复权方式**。

---

## 3. 为什么 `registry/` 单独一层

`registry/` 是**唯一的状态真相源**。它回答四个问题：

| 问题 | 文件 |
|---|---|
| 这个因子叫什么、怎么算、什么方向、现在什么状态？ | `factors.yaml` |
| 这个标签（目标收益）的精确口径是什么？ | `labels.yaml` |
| 这个字段在决策时点知道了吗？ | `field_pit.yaml` |
| 我一共试了多少次？ | `trials_log.csv` |

**为什么不是数据库**：这三类东西的特点是"人要看、要 diff、要写进报告"。
YAML/CSV 能被 git 逐行 diff，能被人直接读懂，能在 code review 里讨论。
数据库适合存百万行数据，不适合存"决策的理由"。

**为什么 `trials_log.csv` 是 CSV 不是 YAML**：它会很长（几百上千行），
需要按列筛选统计（`N`、`σ(SR)`），CSV 用 pandas 一行就能算。

---

## 4. 为什么 `research/` 一个方向一个目录

旧项目的知识散在 `EXPERIMENTS_V1_V6.md`（30KB）、`P0_P1_RESULTS.md`（17KB）、
`notion_docs/*.md`、`STRATEGY0X.md`（5 份）、`eval_out/overfit/*.csv`（20+ 个）里。
它们**都很有价值，但找不回来**——因为没有一个"一次研究 = 一个目录"的边界。

新结构：

```
research/2026-11_vol_ratio_bar_choice/
├── README.md          一句话：做什么、现在到哪一步
├── idea.md            假设：经济逻辑 + 可证伪的预测 + 失败判据
├── config.yaml        本次研究的参数
├── run.py             可复现的执行入口（不是 notebook）
├── result/            产物（gitignore）
└── conclusion.md      判决：留 / 观察 / 丢，以及为什么
```

`research/` 的目录名带月份前缀（`2026-11_`），因为 `ls research/` 本身就是一条时间线。

**模板**在 `research/_template/`。**不要自己造结构**——复制它，改内容。

---

## 5. 反模式对照表

| ❌ 旧项目里出现过 | ✅ 本仓库的做法 |
|---|---|
| 8 个 `strategy0X.py` 互相 copy 40% | 复用逻辑进 `src/factorlab/`，变体用 config 表达 |
| 22MB 的 `test01.ipynb` 是唯一结论来源 | notebook 只做探索，结论回写 `conclusion.md` |
| `panel_*.pkl` 461MB 放在仓库根 | 进 `artifacts/cache/` 或外部盘，gitignore |
| 凭证写在 `config.yaml` 里并提交 | `.env` + `.env.example` 模板 |
| 结论在 5 个 md 里各写一版，数字互不一致 | 一个结论一处，其他链接过去 |
| "样本外 99.1 分位"但没有边界日期 → 不可复现 | 任何 IS/OOS 必须写明切分日与禁运长度 |
| 试验次数靠事后清点（N≈110） | 跑之前开账，跑完立刻记一行 |

---

## 6. 变更这个结构时

改结构要走 ADR：在 `docs/06_adr/` 新建一篇，写明
**背景 / 选项 / 决定 / 代价**，然后把本文件的对应段落改掉。
理由很简单：结构是团队共识的载体，静默改动会让历史文档全部失效。
