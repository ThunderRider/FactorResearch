# data/ · 数据字典

> **这是数据层的唯一入口文档。**
> 规范（怎么组织、怎么命名、怎么校验）在
> [`../docs/01_architecture/data_layer.md`](../docs/01_architecture/data_layer.md)；
> PIT 属性在 [`../registry/field_pit.yaml`](../registry/field_pit.yaml)；
> 这里回答**"我这个数据集长什么样、字段什么意思、单位是什么"**。

---

## 0. 五级目录

```
data/
├── README.md          ← 你在这里
├── MANIFEST.csv       ← 数据集清单（每个文件一行）
├── raw/               外部数据原样落地，只增不改，永不删
├── curated/           规范化矩阵 date × ticker，parquet 宽表，一字段一文件
├── features/          因子长表 date,ticker,factor,value
├── labels/            标签长表 date,ticker,label,value
└── panels/            features ⨝ labels，评估输入
```

**只有 `raw/` 不可重建。** 其余三级都可以由 `raw/` + 代码重算。
因此 `.gitignore` 只允许 `README.md` / `MANIFEST.csv` / `.gitkeep` 入库。

---

## 1. 启动：第一次怎么把数据填进来

### 1.1 最省力：直接复用旧项目的缓存 ⭐ 推荐

`~/my_quantproject/wpqc_factor/data_rq/` 下的 parquet **命名规范与本仓库完全一致**，
可以直接软链或移动（约 2.3 GB，避免重复下载）：

```bash
cd ~/my_quantproject/FactorResearch
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_30m_post_*.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_index_30m_post_*.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_mac_pit_universe_*.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_open_20200101_20260513.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_close_20200101_20260513.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_total_turnover_20200101_20260513.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_turnover_rate_20200101_20260513.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_market_cap_20200101_20260513.parquet data/curated/
```

然后在 `MANIFEST.csv` 里登记（含 `start` / `end` / `n_rows` / `n_tickers`）。

⚠️ **注意**：这批缓存的区间是 **2020-01-01 ~ 2026-05-18**，不包含之后的数据。
要延长必须重新取数（见 §1.2）。

⚠️ **先读** `~/my_quantproject/wpqc_factor/data_rq/*_cache_meta.json` 里的 `known_issues`。

### 1.2 从头取数（需要 RQData 授权）

```bash
cp .env.example .env        # 填 RQDATA_USERNAME / RQDATA_PASSWORD

# 30 分钟个股（主力数据集）
python -m factorlab.data.build --dataset 30m_stock \
  --start 2020-01-01 --end 2026-11-30

# 5 分钟（只在需要精确执行价时取，体积大）
python -m factorlab.data.build --dataset 5m_stock \
  --start 2024-01-01 --end 2026-11-30

# 日线 + 市值 + 换手率
python -m factorlab.data.build --dataset daily_stock \
  --start 2020-01-01 --end 2026-11-30

# PIT 成分股快照（每日）—— 必做，否则有幸存者偏差
python -m factorlab.data.build --dataset universe_pit \
  --start 2020-01-01 --end 2026-11-30
```

每个命令都会：
1. 分块取数（`--chunk-size 500`）
2. 按字段落盘成宽表 parquet
3. 写 `data/<dataset>/meta.json`（含 `known_issues`）
4. 追加 `MANIFEST.csv`

### 1.3 外部数据（手工落地）

| 数据集 | 放哪 | 注意 |
|---|---|---|
| CLS 财联社电报 | `data/raw/cls/cls_历史数据.xlsx` | 只需 `time` / `stocks` 两列；PIT 见 `field_pit.yaml` |
| 行业分类 | `data/raw/industry/` | 必须带**生效日期**，否则有 PIT 问题 |
| 指数成分股历史 | 优先用 RQData 逐日取；离线时用 `cn_mac_pit_universe` | 严禁用最新成分 |
| 财务数据 | `data/raw/fundamental/` | **必须用公告日 ≠ 报告期** |
| 海外对照数据 | `data/raw/spy/`（小文件，可入库） | 见 `docs/04_legacy/intraday_momentum/` |

---

## 2. 字段字典（curated 层）

### 2.1 价格与量（`cn_stock_30m_*` / `cn_stock_5m_*` / `cn_stock_*` 日线）

| 字段 | 单位 | 含义 | 注意 |
|---|---|---|---|
| `open` | 元 | bar 开盘价 | 后复权；绝对值无经济意义 |
| `high` | 元 | bar 最高价 | |
| `low` | 元 | bar 最低价 | |
| `close` | 元 | bar 收盘价 | |
| `volume` | **股** | bar 成交量 | 不是手（1 手 = 100 股） |
| `total_turnover` | **元** | bar 成交额 | |
| `turnover_rate` | 小数 | 日换手率 | 日线才有 |
| `market_cap` | 元 | 总市值 | 日线才有；⚠️ 含当日收盘价 → 需 shift |

**时间戳语义**：分钟级数据的时间戳是 **bar 的结束时刻**。
`14:30:00` 代表 **14:00–14:30** 这一根。

**A 股 30 分钟 bar 的时间点**（每天 8 根）：

```
10:00  10:30  11:00  11:30  13:30  14:00  14:30  15:00
```

（注意 11:30 与 13:30 之间是午休，13:00 开盘但那半小时并入 13:30 的 bar）

### 2.2 快照字段（features 里由 bar 压缩得到）

命名：`<字段首字母><HHMM>`。

| 快照字段 | 由什么得到 | 已知时点 |
|---|---|---|
| `o1000` | `open` @ 10:00 | T 10:00 |
| `c1100` | `close` @ 11:00 | T 11:00 |
| `c1130` | `close` @ 11:30 | T 11:30 |
| `c1330` | `close` @ 13:30 | T 13:30 |
| `c1400` | `close` @ 14:00 | T 14:00 |
| `c1430` | `close` @ 14:30 | **T 14:30 = as_of** |
| `c1500` | `close` @ 15:00 | T 15:00 ⚠️ |
| `v1400` | `volume` @ 14:00 | T 14:00 |
| `v1430` | `volume` @ 14:30 | T 14:30 |
| `a1430` | `total_turnover` @ 14:30 | T 14:30 |
| `day_amt` | `total_turnover` 当日求和 | T 15:00 ⚠️ |
| `day_vol` | `volume` 当日求和 | T 15:00 ⚠️ |
| `day_high` / `day_low` | 当日 max / min | T 15:00 ⚠️ |

⚠️ 标记的字段 **必须 `shift(1)`** 才能进因子。完整表见
[`../registry/field_pit.yaml`](../registry/field_pit.yaml)。

### 2.3 指数

| 数据 | 用途 |
|---|---|
| `cn_index_30m`（000300 / 399303 / 000852 / 399905 / 932000） | 档位（tier）的成交量斜率；超额收益的基准 |
| `cn_index_1d` | 长期基准、市场状态划分 |

**档位的窗口单位是 bar 数**（102 根 ≈ 13 天，72 根 ≈ 9 天），不是天数。
用自然日做横轴会让小盘池 23% 的信号翻转（旧项目实测：V3 净 9.55% → −1.37%）。

### 2.4 股票池（PIT）

| 文件 | 结构 | 用途 |
|---|---|---|
| `cn_mac_pit_universe_*.parquet` | 长表 `date, order_book_id, pool, ...` | 每日成分股快照 |
| `cn_stock_universe_*.csv` | 宽表/单列 | 某截面的全市场股票列表 |

**规则**：池的定义用**当日**成分。`configs/universe.yaml` 定义了 mac / min / all 三个池。

---

## 3. `MANIFEST.csv` 格式

每写入任何级别的数据，追加一行：

```csv
dataset,level,path,start,end,n_rows,n_tickers,built_at,builder,git_sha,snapshot,hash,note
```

| 列 | 例 | 说明 |
|---|---|---|
| `dataset` | `cn_stock_30m` | 数据集名 |
| `level` | `curated` | raw / curated / features / labels / panels |
| `path` | `data/curated/cn_stock_30m_post_close_20200101_20261130.parquet` | 相对路径 |
| `start` / `end` | `2020-01-01` / `2026-11-30` | 覆盖区间 |
| `n_rows` / `n_tickers` | `1683000` / `5300` | 规模 |
| `built_at` | `2026-11-20T16:40:00+08:00` | ISO8601 带时区 |
| `builder` | `factorlab.data.build` | 命令 |
| `git_sha` | `abc1234` | 代码版本 |
| `snapshot` | `2026-11-20` | 数据快照 tag |
| `hash` | `sha256:9f2c...` | 前 16 位足够 |
| `note` | `ok` / `异常说明` | 质量问题的唯一载体 |

查询示例：

```python
import pandas as pd
m = pd.read_csv('data/MANIFEST.csv', parse_dates=['start','end'])
m[m.level == 'curated'].sort_values('built_at').tail(10)
```

---

## 4. 质量校验

落盘前必须跑：

```bash
python -m factorlab.io.quality --path data/curated/cn_stock_30m_post_close_*.parquet
```

检查项（对应 `configs/data.yaml` 的 `quality` 段）：

| 检查 | 阈值 | 不通过怎么办 |
|---|---|---|
| 每日股票数 | >= 100 | 查是否漏了板块 / 区间错 |
| 缺失率 | <= 30% | 查停牌是否合理 |
| 价格非正 | 0 行 | **一定有问题**，后复权序列不该有 ≤0 |
| 单日跳变 > 30% | 0 行（后复权下） | 查是否混入了前复权或不复权 |
| 索引唯一、升序 | 必须 | 必须修 |
| ticker 格式 | `XXXXXX.XSHE/XSHG` | 必须修 |

**最后一步：抽查 3 个 (date, ticker)，到原始数据源核对价格。**
最容易跳过，也最容易发现"复权复错了"。

---

## 5. 已知局限（持续更新）

> **这一节是数据层最重要的部分之一。** 数据的缺陷必须写在数据旁边，
> 而不是研究者的记忆里 —— 否则每个人都会重新踩一遍。

### 5.1 旧项目缓存（2026-05-18 截止）

- 区间只到 **2026-05-18**，之后的数据需要重新取
- `cn_mac_pit_universe` 的 CSV 版有 28 MB，parquet 版只有 179 KB（优先用后者）
- 30 分钟数据的 `total_turnover` 字段在部分早期日期缺失

### 5.2 旧项目审计暴露的口径问题

| 问题 | 影响 | 处理 |
|---|---|---|
| 缺市值表 → 用 `log_amt20` 做规模代理 | `amihud` 的"非流动性溢价"叙事不成立 | **待补**：从 `cn_stock_market_cap_*.parquet` 接入真市值 |
| 部分标的不在 `instruments.pk` 快照内 | 池过滤可能误杀新股 | 用 RQData 逐日取，不用静态快照 |
| 交易日历曾靠工作日外延补齐 10 天 | 若延长到有长假的时段会错 | 一律 `rqdatac.get_trading_dates` |

### 5.3 数据本身的固有局限

| 局限 | 后果 |
|---|---|
| 无 L2 逐笔 / 盘口 | 冲击成本只能用平方根模型近似 |
| 无分钟级以下数据 | 14:45 的成交价只能用 (c1430+c1500)/2 近似 |
| 后复权序列的绝对价格无意义 | 不能用"股价 < 5 元"这类因子 |
| 财务数据只有季度频率 | 日频因子需处理公告日滞后 |

---

## 6. 目录占位说明

每个空目录放一个 `.gitkeep`，说明它存在但内容不入库：

```
data/raw/.gitkeep           外部数据原样落地
data/curated/.gitkeep       date × ticker 宽表
data/features/.gitkeep      因子长表
data/labels/.gitkeep        标签长表
data/panels/.gitkeep        评估输入
```

**不要因为目录是空的就删掉它** —— 目录结构本身就是约定。
