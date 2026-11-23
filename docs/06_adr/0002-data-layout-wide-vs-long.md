# 0002 · curated 用宽表、features 用长表、panels 用宽表

- **状态**：已接受
- **日期**：2026-11-20
- **关联**：[`../01_architecture/data_layer.md`](../01_architecture/data_layer.md)

## 背景

数据在仓库里要以什么形状存？这个问题看似技术细节，实际决定了所有下游代码的写法。

旧项目全是宽表（`date × ticker` 的 CSV/parquet），结果：
- 因子从 3 个长到 20 个之后，宽表变成 20 列；
- 每次加因子都要改文件结构；
- 想看"某个因子在某天的截面分布"，要先从大文件里截。

但旧项目的宽表也有明显优点：矩阵运算（rolling / shift / 截面 rank）用 pandas 直接写，
不需要 `groupby` 再 `unstack`。

## 选项

**A. 全宽表**

```
curated/  date × ticker
features/ date × ticker × factor   （三维，只能用 MultiIndex 列）
```

- 优点：所有运算都是矩阵运算，最快
- 缺点：features 的列会爆炸（20 因子 × 5 池 = 100 列，命名混乱）；加因子 = 改 schema

**B. 全长表**

```
data:  date, ticker, field, value
```

- 优点：schema 永不变化（加字段 = 加行）
- 缺点：每次运算都要 `pivot`/`unstack`，慢 3~10 倍；内存峰值高

**C. 分级选择**（本决定）

```
curated：宽表（一字段一文件）  ← 矩阵运算的原料
features：长表（4 列固定）      ← 因子会无限制增长
labels：长表（4 列固定）
panels：宽表（在磁盘上，读进来就是矩阵）
```

- 优点：每级用最适合的形状
- 缺点：形状转换的代码要写一次（约 40 行），且要保证转换无损

## 决定

**采用 C。**

理由按"数据的增长维度"来分：

| 级 | 增长的维度 | 形状 | 因为 |
|---|---|---|---|
| curated | **字段数**（~10，稳定） | 宽表 | 字段少且固定，宽表能直接矩阵运算 |
| features | **因子数**（3 → 300） | 长表 | 因子会无限制增长，宽表的列会爆炸 |
| labels | **标签数**（~8，稳定） | 长表 | 与 features 保持一致，便于 join |
| panels | 无（一次性快照） | 宽表 | 评估时一列一列算相关，宽表最省事；且 parquet 支持按列读 |

**关键：curated 的"一字段一文件"**。
`cn_stock_30m_post_close_20200101_...parquet` 只有一个字段的宽表。
好处：① 按需加载（只要 close 就不读 volume）；② 加字段 = 加文件，不改 schema；
③ 文件大小可控（30 分钟全市场一个字段 ≈ 200~400 MB，能放进内存）。

## 代价

1. **多一层转换代码**：`curated（宽）→ features（长）` 要写 `melt`；`→ panels（宽）` 要写 `pivot`。
   这部分代码在 `src/factorlab/io/store.py`，只写一次。
2. **文件数变多**：curated 下每个"数据集 × 字段"一个文件。
   30m 数据集 6 个字段 = 6 个文件；加 5m 就是 12 个。可接受。
3. **长表的行数会很大**：900 万 stock-day × 20 因子 = 1.8 亿行。
   需要按年分区（`data/features/2026/...`）或按因子分组。
   **这是当前设计的已知压力点。**

## 什么时候应该重新考虑

- 如果 features 长表超过 5 亿行 → 按年 + 按因子族分区，或改用 duckdb/parquet 数据集
- 如果 curated 的单字段文件超过 1 GB → 按年分区
- 如果需要频繁做"因子 × 因子"的截面运算（如多因子合成），可以在 `artifacts/cache/` 里
  落一份宽表快照，但不改变 `data/` 的形状

## 影响

- `docs/01_architecture/data_layer.md` §3 给出了三级的精确 schema
- `src/factorlab/io/store.py` 负责形状转换
- 所有因子代码只接受"宽表 return matrix"，不关心存的是哪种形状
