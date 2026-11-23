# 数据层规范

> **这是本仓库最重要的文档之一**。因子研究的 90% 的坑，都是数据格式与口径不一致造成的。
> 本文定义：数据分几级、每级什么格式、文件怎么命名、元数据写什么、加新数据集要过哪些检查。

---

## 1. 五级数据，各有唯一职责

```
raw ──► curated ──► features ─┐
  └───► labels ───────────────┴──► panels ──► eval / backtest
```

| 级别 | 目录 | 一句话 | 格式 | 单位粒度 |
|---|---|---|---|---|
| **raw** | `data/raw/<dataset>/` | 外部数据**原样**落地 | 原始（csv/xlsx/parquet/PDF） | 不在本仓库定义 |
| **curated** | `data/curated/` | 规范化矩阵，可直接用于计算 | parquet **宽表** | `date × ticker`，一字段一文件 |
| **features** | `data/features/` | 因子值 | parquet **长表** | `date, ticker, factor` |
| **labels** | `data/labels/` | 目标收益 | parquet **长表** | `date, ticker, label` |
| **panels** | `data/panels/` | features ⨝ labels，评估输入 | parquet **宽表** | 一行 = 一个 (date, ticker) |

### 为什么 curated 用宽表、features 用长表

- **curated 宽表**：矩阵运算（rolling、shift、截面 rank）用 `date × ticker` 的 DataFrame 最快，
  而且是"一个字段一个文件"，内存能按需加载。
- **features 长表**：因子数量会从 3 长到 300，宽表会变成 300 列的稀疏矩阵；
  长表加因子只是加行，`groupby(['date','factor'])` 天然支持批量 IC。
- **panels 宽表**：一次评估就是一列一列算相关，宽表最省事，且便于 `to_parquet` 后直接 `read_parquet(columns=...)`。

---

## 2. 命名规范（文件即文档）

```
<domain>_<instrument>_<freq>_<adjust>_<field>_<start>_<end>.<ext>
```

| 段 | 取值 | 例子 |
|---|---|---|
| domain | `cn` / `us` / `hk` | `cn` |
| instrument | `stock` / `index` / `mac`（池）/ `futures` | `stock` |
| freq | `1d` / `5m` / `30m` / `1min` | `30m` |
| adjust | `post`（后复权）/ `pre` / `none` | `post` |
| field | 字段名 | `close` |
| start / end | `YYYYMMDD` | `20200101_20261130` |

实例：

```
data/curated/cn_stock_30m_post_close_20200101_20261130.parquet
data/curated/cn_stock_30m_post_volume_20200101_20261130.parquet
data/curated/cn_index_30m_post_close_20200101_20261130.parquet
data/features/features_20200101_20261130_v3.parquet
data/labels/labels_20200101_20261130_v1.parquet
data/panels/panel_mac-min_20200101_20261130_v3.parquet
```

> 命名沿用了旧项目 `wpqc_factor/data_rq/` 的习惯（`cn_stock_30m_post_volume_20200101_20260518.parquet`），
> 目的很实际：**一行 `ls` 就能看出覆盖区间和复权方式**，不需要打开文件。
> 新旧数据可以直接并存、直接复用缓存。

**版本号 `_vN`**：只在 features / labels / panels 上加。
含义是"**构造逻辑变了**"，不是"数据变多了"——数据区间变长只改日期段，不改版本号。

---

## 3. 各级的精确 schema

### 3.1 curated（宽表，一字段一文件）

```python
# 索引：DatetimeIndex 名 `date`（交易日，tz-naive，Asia/Shanghai 按日归一）
# 列：ticker（RQData order_book_id 格式）
#
#                         000001.XSHE  000002.XSHE  600000.XSHG  ...
# date
# 2020-01-02                  16.12       27.30        10.55
# 2020-01-03                  16.20       27.55        10.61

index.name == 'date'
columns.name == 'ticker'
dtype: float64（volume / total_turnover 用 float64 避免 int 溢出与 NA 冲突）
```

硬规则：

1. **索引必须是 `date`**，且已排序、无重复。
2. **列必须是 ticker**，格式 `000001.XSHE` / `600000.XSHG`（不以 `sh`/`sz` 前缀）。
3. **价格必须后复权**（`adjust_type: post`）。混用前复权会让**历史收益失真**且无法察觉。
4. **时间戳语义**：分钟级 bar 的 index 若保留时间，约定为 **bar 的结束时刻**
   （`14:30:00` = 14:00–14:30 那根）。这是旧项目 `build_snapshot` 的口径，必须一致。
5. **不用 0 表示缺失**，用 `NaN`。停牌日保留在索引里、值为 `NaN`。
6. **不存派生量**。`curated` 只存"从数据源直接拿到的原始字段"，任何 rolling/shift 结果属于 features。

### 3.2 features（长表）

```python
# 列（固定 4 列，顺序固定）：
#   date    datetime64[ns]
#   ticker  category / str
#   factor  category / str   ← 因子名，与 registry/factors.yaml 的 id 完全一致
#   value   float64
#
# date        ticker        factor       value
# 2026-11-19  000001.XSHE   vol_ratio    0.8312
# 2026-11-19  000001.XSHE   ret_20d     -0.0412
# 2026-11-19  000002.XSHE   vol_ratio    1.1043
```

硬规则：

1. **`factor` 必须能在 `registry/factors.yaml` 里查到**。查不到 = 没有登记 = 不存在。
2. **不允许存"中间量"**（如 `v_ma20`），除非它在 registry 里是一条正式因子。
   中间量属于计算过程，在代码里。
3. **一个 features 文件 = 一个构造逻辑版本**。加因子 = 出新 `_vN` 文件，不覆盖旧文件。
4. **缺失就是缺失**，不要前向填充。前向填充属于特征工程决策，要在代码里显式做并记录。

### 3.3 labels（长表）

```python
# 列：
#   date    datetime64[ns]
#   ticker  category / str
#   label   category / str   ← 与 registry/labels.yaml 的 id 一致
#   value   float64          ← 收益的**小数**形式（0.0123 = +1.23%）
#
# 硬规则：标签必须是"未来信息"，因此
#   ① 每行 date 的 value 用到的行情必须 > date 的 as_of 时刻；
#   ② 最后一个交易日的长周期标签必然是 NaN，这是正常的，**不要用别的值填**。
```

### 3.4 panels（宽表，评估输入）

```python
# 索引：MultiIndex (date, ticker)，或普通列 + 显式 set_index
# 列：
#   pool            str        所属股票池
#   <factor_1..N>   float64    因子值
#   <label_1..M>    float64    标签值
#   entry           float64    入场价（可审计，不是必须）
#   tradable        bool       当日是否可交易（涨跌停/停牌/流动性）
```

**关键：`tradable` 是数据，不是过滤。** 因子层绝不删行，只打标记；
是否剔除由评估代码决定。这样"含过滤"与"不含过滤"的结论可以并排比较——
旧项目 V3 的 `gap` 因子"不加过滤是有 14,807% 的幻觉，加过滤是 −81.5%"，就是没分开的后果。

---

## 4. 元数据：MANIFEST + meta.json

### 4.1 `data/MANIFEST.csv`（数据集清单，必填）

每次写入任何级别的数据，都追加一行：

```csv
dataset,level,path,start,end,n_rows,n_tickers,built_at,builder,git_sha,snapshot,hash,note
cn_stock_30m_post_close,curated,data/curated/cn_stock_30m_post_close_20200101_20261130.parquet,2020-01-01,2026-11-30,1683000,5300,2026-11-20T16:40:00+08:00,factorlab.data.build,abc1234,2026-11-20,sha256:9f2c...,ok
```

| 列 | 含义 | 为什么必须有 |
|---|---|---|
| `dataset` | 数据集名 | 定位 |
| `level` | raw/curated/features/labels/panels | 判断可重建性 |
| `path` | 相对路径 | |
| `start`,`end` | 覆盖区间 | **防止"我以为覆盖到 2026-11"** |
| `n_rows`,`n_tickers` | 规模 | 快速发现缺数 |
| `built_at` | ISO8601 带时区 | 排序与回滚 |
| `builder` | 命令/脚本 | 复现 |
| `git_sha` | 代码版本 | 复现 |
| `snapshot` | 数据快照 tag | 与研究配置对齐 |
| `hash` | `sha256:...` 前 16 位即可 | 检测"文件被悄悄改过" |
| `note` | `ok` / 异常说明 | 质量问题的唯一载体 |

> 为什么 hash 只留前 16 位：完整 sha256 太长，人眼无用；
> 前 16 位已经足够检测"同一条命令两次产出不同文件"。真要校验时重算。

### 4.2 单数据集 `meta.json`（可选，复杂数据集用）

旧项目 `cn_stock_cache_meta.json` / `wpqc_30m_cache_meta.json` 是这个模式，沿用：

```json
{
  "dataset": "cn_stock_30m",
  "adjust_type": "post",
  "frequency": "30m",
  "start_date": "2020-01-01",
  "end_date": "2026-11-30",
  "as_of_date": "2026-11-30",
  "fields": ["open", "high", "low", "close", "volume", "total_turnover"],
  "universe_size": 5300,
  "files": {"open": "cn_stock_30m_post_open_...parquet", "...": "..."},
  "source": "rqdatac.get_price",
  "rqdatac_version": "2.9.x",
  "known_issues": ["2026-11-17 之后仅有部分股票"],
  "built_at": "2026-11-30T18:00:00+08:00"
}
```

`known_issues` 是重点：**数据的缺陷必须写在数据旁边**，而不是在研究者的记忆里。

---

## 5. 存储与性能约定

| 项 | 约定 | 理由 |
|---|---|---|
| 格式 | parquet + `snappy` 或 `zstd` | 比 csv 小 5–10 倍，且保留 dtype |
| 索引 | 写盘时 `index=True`，`date` 作为索引 | 便于 `read_parquet` 直接得到矩阵 |
| 压缩 | 宽表用 `zstd`（数值多），长表用 `snappy`（读写快） | |
| 单文件 | **> 500MB 必须分区** | GitHub 拒收 100MB+；内存也放不下 |
| 分区 | 按年：`data/curated/2024/...` | 大多数研究只回测 2–3 年 |
| 缓存 | `artifacts/cache/`，30 天清理 | 缓存可以随时删，删了要能重建 |
| pickle | **仅用于无法表化的对象**（如 sklearn 模型、dict）。面板一律 parquet | 旧项目 `v6_cache.pkl` 1.2GB 是个警示 |

**内存估算（A 股全市场）**：

```
5300 只 × 1700 交易日 ≈ 900 万行
一个 float64 字段（宽表）≈ 72 MB
30 分钟 bar：8 根/天 → 7200 万行 ≈ 576 MB/字段
→ 所以 bar 级数据必须按字段拆文件，且按年分区
```

---

## 6. 加一个新数据集：检查清单

按顺序过，任何一项不过就不要写入 `curated`：

- [ ] **1. 落 raw**：原始文件进 `data/raw/<dataset>/`，不改内容；写一行 MANIFEST。
- [ ] **2. 明确时间语义**：这个字段是**时点值**还是**区间累计值**？
      区间累计值（如当日成交额）在盘中是不完整的，见 [`pit_policy.md`](pit_policy.md)。
- [ ] **3. 登记 PIT**：在 `registry/field_pit.yaml` 写下"最后可知时点"与"是否需要 shift"。
- [ ] **4. 对齐索引**：`date` 升序、无重复；ticker 用 `XXXXXX.XSHE/XSHG`。
- [ ] **5. 复权口径**：后复权；若原数据是前复权或不复权，**不要混入同一文件**。
- [ ] **6. 缺失语义**：停牌 → `NaN`；不存在的标的 → 不出现（不是 0）。
- [ ] **7. 质量校验**：跑 `factorlab.io.quality.check()`，看
      每日股票数、缺失率、非正价格、异常跳变（单日 > 30% 且复权正确时不允许出现）。
- [ ] **8. 写 MANIFEST**：含 `hash` 与 `note`。
- [ ] **9. 抽查**：随机 3 个 (date, ticker)，到原始数据源核对价格。
      **这一步最容易被跳过，也最容易发现"复权复错了"。**

---

## 7. 数据集字典（已定义的数据集）

| dataset | 频率 | 字段 | 落盘名示例 | 来源 |
|---|---|---|---|---|
| `cn_stock_30m` | 30m | open/high/low/close/volume/total_turnover | `cn_stock_30m_post_close_20200101_20261130.parquet` | RQData |
| `cn_stock_5m` | 5m | 同上 | `cn_stock_5m_post_close_...parquet` | RQData |
| `cn_stock_daily` | 1d | 上述 + turnover_rate / market_cap | `cn_stock_close_...parquet` | RQData |
| `cn_index` | 30m / 1d | open/high/low/close/volume | `cn_index_30m_post_close_...parquet` | RQData |
| `cn_mac_pit_universe` | 1d | 每日的成分股快照（长表） | `cn_mac_pit_universe_...parquet` | RQData `index_components(as_of)` |
| `cn_st_stock_days` | 1d | 每日 ST 标记 | `cn_st_stock_days_...parquet` | RQData / bundle |

详细的字段含义、单位、口径见 **[`data/README.md`](../../data/README.md)**；PIT 属性见
**[`registry/field_pit.yaml`](../../registry/field_pit.yaml)**。

---

## 8. 什么时候可以删数据

| 级别 | 可删？ | 条件 |
|---|---|---|
| raw | ❌ **永不删** | 重新获取有成本（授权/时效），且是唯一的真相源 |
| curated | ✅ | 能由 raw + 代码重建，且 MANIFEST 里有 builder 与 git_sha |
| features | ✅ | 同上；但删之前确认没有 `docs/03_knowledge/` 里的结论依赖它 |
| labels | ✅ | 同上 |
| panels | ✅ | 纯派生物，随时重建 |
| artifacts | ✅ | 缓存级别，30 天自动清 |

**判定规则**：如果删了它，"半年后有人想复现某个结论"会失败，那就不能删。
`raw` 与 `docs/03_knowledge/` 引用的中间件属于这一类。
