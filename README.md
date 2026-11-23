# FactorResearch · 因子研究工作台

> **这是什么**：一个长期演进的 A 股因子研究仓库。**每个新因子、新想法都从这里出生、被检验、被判决、被归档**。
> **不是什么**：不是实盘交易系统，也不是策略回测脚本堆。生产策略代码留在各自项目里，这里只产出**结论 + 可复现的证据**。
>
> 建立时间：2026-11-20 · 设计依据：`my_quantproject` 下 wpqc / wpqc_factor / hzbplus / hfc 四个项目的经验与教训

---

## 1. 三十秒上手

```bash
cd ~/my_quantproject/FactorResearch

# 1) 环境（复用旧项目的 rq conda 环境即可）
conda activate rq
pip install -r requirements.txt          # 增量：pyarrow / PyYAML / python-dotenv / statsmodels

# 2) 凭证
cp .env.example .env                     # 填 RQDATA_USERNAME / RQDATA_PASSWORD
                                         # .env 已被 gitignore，永不入库

# 3) 自检（不连行情库，用合成数据验证管线）
python -m pytest tests/ -q

# 4) 开一个新的研究方向
cp -r research/_template research/2026-11_我的新因子
#    然后按 research/_template/README.md 的五步走
```

**日常只有三条命令**（详见 `docs/02_methods/research_workflow.md`）：

```bash
python -m factorlab.data.build --dataset 30m --start 2020-01-01 --end 2026-11-30
python -m factorlab.eval.run    --panel <panel> --factors <f1,f2> --out artifacts/results/<run_id>
python -m factorlab.audit.lookahead --config configs/data.yaml     # 每次回测前必跑
```

---

## 2. 三条铁律（违反任何一条，结论作废）

### 铁律 1 · PIT（Point-In-Time）：任何进入 T 日决策的字段，必须 `<= as_of(T)`

本仓库所有研究统一以 **`as_of(D) = D 14:30`（Asia/Shanghai）** 为决策时点（与尾盘选股口径一致；日频研究可整体平移到收盘后）。

> **为什么写成铁律**：旧项目 wpqc 唯一的"可证伪偏差"就是这条 —— 流动性门槛 `amt20` 用了当日 15:00 的成交额，
> 而决策在 14:45。**15 分钟的前视，让 V3 净年化虚高 1.66pp、改变了 6.02% 的选股**。
> 前视不是"运气差"，是**偏差**，它不会随样本变长而消失。

每加一个字段，必须在 [`registry/field_pit.yaml`](registry/field_pit.yaml) 里登记"最后可知时点"。
审计脚本 `factorlab.audit.lookahead` 会对照该表逐列检查 `as_of` 覆盖。

### 铁律 2 · 记账：每跑一次试验，`registry/trials_log.csv` 加一行（**包括失败的**）

> **为什么**：所有"这个夏普是真的吗"的判断，都依赖 `N`（你试了多少次）。
> 旧项目最终能清点出 **N≈110**（后续含随机抽样超过 900），一次都没记在事前，
> 于是 DSR 只能给敏感性网格（0.51~0.77），**永远无法确定策略是不是一个谎言**。
> 记账是**制度成本，不是技术成本**——但它是唯一能回答"我是不是靠运气"的东西。

不记账的试验 = 不存在；但它在你的搜索空间里真实存在，并悄悄污染 DSR。

### 铁律 3 · 先判死，再优化

每个因子必须先过 **"该不该留"**，才谈"怎么调"：

```
IC 显著  ≠  组合层有用  ≠  有独立信息  ≠  样本外还在
```

旧项目三条真实的死法，各对应一道必过的门：

| 死法 | 实例 | 对应检验 |
|---|---|---|
| **马甲因子**（跟已有暴露共线） | `MAX20` IC −0.051 很漂亮，但与 20 日波动率相关 **0.874** | 正交化 + 相关矩阵 |
| **IC 好但组合不赚钱** | MAX 因子的 9 种用法全部变差（25.5% → 14.8%~23.1%） | 组合层回测（不是只有 IC） |
| **辛普森悖论**（混杂变量） | 按"分数档"分层看着单调，控制"仓位档"后完全不单调（相关 −0.039） | 分层时必须控制市场状态 |

---

## 3. 目录地图

```
FactorResearch/
├── README.md                  ← 你在这里：铁律 + 地图
│
├── docs/                      ★ 全部文档（唯一的知识入口）
│   ├── 00_quickstart.md           第一天怎么跑
│   ├── 01_architecture/           仓库布局 / 数据分层 / PIT 铁律 / 命名约定
│   ├── 02_methods/                ★ 研究流程 7 道门 + 各类检验怎么做
│   ├── 03_knowledge/              ★ 从旧项目提炼的教训、因子动物园、已证伪清单
│   ├── 04_legacy/                 ★ 旧项目策略档案（含原文，可追溯）
│   ├── 05_journal/                研究日志（按日期，只追加不改）
│   └── 06_adr/                    架构决策记录（为什么这样设计）
│
├── registry/                  ★ 状态中枢（YAML/CSV，人可读、代码可加载）
│   ├── factors.yaml               因子注册表：定义/方向/状态/证据/退役规则
│   ├── labels.yaml                标签（目标收益）口径表
│   ├── field_pit.yaml             ★ 字段最后可知时点
│   └── trials_log.csv             ★ N 记账
│
├── configs/                   配置（无凭证）
├── data/                      ★ 数据层（内容不入库，只有 README + MANIFEST）
│   ├── README.md                  数据字典：每个数据集是什么、怎么来、怎么校验
│   ├── MANIFEST.csv               数据集清单（路径/区间/行数/哈希）
│   ├── raw/                       原始落地（外部文件原样，禁止改写）
│   ├── curated/                   规范化矩阵（date × ticker，parquet）
│   ├── features/                  因子面板（long）
│   ├── labels/                    标签面板（多口径目标收益）
│   └── panels/                    模型就绪面板（features ⨝ labels）
│
├── research/                  ★ 研究方向，一个想法一个目录（可无限新增）
│   └── _template/                 复制即用的五步模板
│
├── src/factorlab/             可复用代码（薄，只放"会被复用的"）
│   ├── io/                        取数、缓存、manifest/meta
│   ├── features/                  因子构造（快照 + 因子库）
│   ├── eval/                      IC/分层/正交/置换/稳健性
│   ├── portfolio/                 选股、权重、回测
│   └── audit/                     前视体检、DSR、PBO、试验记账
│
├── artifacts/                 产出（缓存 / 结果 / 报告，不进版本库）
├── notebooks/                 探索用 Jupyter（结论必须回写成 md）
└── tests/                     冒烟测试 + 合成数据 fixture
```

**为什么 docs 和 registry 是一等公民**：旧项目最强的资产不是代码，是
`EXPERIMENTS_V1_V6.md` / `P0_P1_RESULTS.md` 里那些**带对照数字的结论**。
新仓库把"知识"和"状态"从代码里拆出来，让它们能跨项目、跨年份复用。

---

## 4. 一个因子的一生（唯一合法路径）

```
  idea.md            →  ① 假设：经济逻辑 + 可证伪的预测
      ↓
  registry           →  ② 登记：factors.yaml 加一条 status: candidate，trials_log 开账
      ↓
  panel + eval       →  ③ 因子层：IC / NW-t / 分层 / 覆盖率 / 衰减
      ↓
  orth + PI          →  ④ 独立性与重要性：是不是马甲？去掉它还剩多少？
      ↓
  portfolio          →  ⑤ 组合层：能否跨过盈亏平衡线（不是看年化收益）
      ↓
  audit              →  ⑥ 审计：前视 / DSR / PBO / 禁运 / 脆弱性曲线
      ↓
  conclusion.md      →  ⑦ 判决：active / watch / rejected，写清适用边界与退役条件
```

每一步的门槛与判据见 [`docs/02_methods/research_workflow.md`](docs/02_methods/research_workflow.md)。
**跳过任何一步，结论只能标 `draft`，不得进入 `docs/03_knowledge/`。**

---

## 5. 我该先读什么

| 你想… | 读这个 |
|---|---|
| 立刻开跑 | [`docs/00_quickstart.md`](docs/00_quickstart.md) |
| 知道数据怎么放、字段什么意思 | [`data/README.md`](data/README.md) + [`registry/field_pit.yaml`](registry/field_pit.yaml) |
| 做一次合规的研究 | [`docs/02_methods/research_workflow.md`](docs/02_methods/research_workflow.md) |
| 避免重复踩坑 | [`docs/03_knowledge/lessons_learned.md`](docs/03_knowledge/lessons_learned.md) |
| 查某个因子是否已测过 | [`docs/03_knowledge/factor_zoo.md`](docs/03_knowledge/factor_zoo.md) / [`registry/factors.yaml`](registry/factors.yaml) |
| 别再浪费时间的死路 | [`docs/03_knowledge/falsified.md`](docs/03_knowledge/falsified.md) |
| 看旧项目（慧抢筹 / RESI / ASP / 慧点睛）怎么做的 | [`docs/04_legacy/README.md`](docs/04_legacy/README.md) |
| 为什么仓库长这样 | [`docs/06_adr/`](docs/06_adr/README.md) |

---

## 6. 与旧项目的关系

本仓库**不接管**旧项目的代码与数据，只接管它们沉淀的**知识**。

| 旧目录 | 它是什么 | 在本仓库的位置 |
|---|---|---|
| `wpqc/` | 慧抢筹 V1→V8：尾盘选股 + 次日卖出，含最完整的研究纪律 | [`docs/04_legacy/wpqc_maqiangchou/`](docs/04_legacy/wpqc_maqiangchou/) |
| `wpqc_factor/` | RESI / rolling_coef_std 单因子研究 + 30m/5m 数据构建脚本 | [`docs/04_legacy/wpqc_factor_resi/`](docs/04_legacy/wpqc_factor_resi/) |
| `hzbplus/` | ASP 成交额斜率择时 + vectorbt 参数寻优 | [`docs/04_legacy/hzbplus_asp/`](docs/04_legacy/hzbplus_asp/) |
| `hfc/` | 慧点睛 HDJ：CLS 财联社事件驱动（SQL/生产化） | [`docs/04_legacy/hfc_hdj/`](docs/04_legacy/hfc_hdj/) |
| （散落在 wpqc* 内） | 日内动量 / SPY 5m 复现 | [`docs/04_legacy/intraday_momentum/`](docs/04_legacy/intraday_momentum/) |

迁移约定（详见 [`docs/04_legacy/README.md`](docs/04_legacy/README.md)）：

1. **原文逐字复制，字节一致**，不删、不改、不重排版 —— 可以直接 `diff` 核对源文件。
2. **来源记录在各子目录的 `README.md`**（源路径 / 迁移日期 / 每个文件当时的作用）。
3. 需要"浓缩版"时**另写一篇**（本仓库的浓缩版是 `docs/03_knowledge/` 下的
   `lessons_learned.md` / `factor_zoo.md` / `falsified.md`），并在开头写明 `> 来源：<原文件>`。
   两份都保留 —— 旧文档里的对照数字本身就是证据。
4. **不在旧文件里修 bug 或改数字。** 发现错误 → 在 `docs/03_knowledge/` 加一条"更正"。

---

## 7. 版本与协作约定

- **时间**：所有日期 `YYYY-MM-DD`；时间戳带时区；CSV 里**不用** Excel 序列号。
- **标识**：一次运行一个 `run_id = <YYYYMMDD>-<slug>`，贯穿 results / report / trials_log。
- **不可变**：`docs/05_journal/` 与 `registry/trials_log.csv` **只追加，不改历史行**（改错就加一行更正）。
- **可复现**：任何写进 `docs/03_knowledge/` 的数字，必须能由仓库内代码 + `MANIFEST.csv` 里记录的数据重算得到。

---

*本仓库的设计目标不是"跑得更多"，而是"**每个能上线的结论，都说得出它是怎么活下来的**"。*
