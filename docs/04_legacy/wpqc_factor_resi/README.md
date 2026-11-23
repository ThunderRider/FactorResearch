# wpqc_factor · RESI 单因子研究 + 数据构建

> **源目录**：`~/my_quantproject/wpqc_factor/`
> **迁移日期**：2026-11-20
> **迁移方式**：逐字复制，字节一致
> **项目性质**：单因子（RESI / rolling_coef_std）研究 + 多频率行情数据构建 + 日内动量复现

---

## 这个项目是什么

三件事混在一起：

1. **单因子研究**：`RESI`（ln 典型价的线性回归残差标准差）与 `rolling_coef_std`（量价滚动相关的标准差）
2. **数据构建**：`prepare_*_rq.py` 三个脚本，从 RQData 拉 30m/5m/日线，落成 parquet 宽表缓存
3. **策略复现**：MAC 高 RESI + 低 coef 的选股策略 + vectorbt 回测 + SPY 日内动量复现

---

## 文件清单

| 文件 | 是什么 | 价值 |
|---|---|---|
| `README_resi_workspace.md` | 工作区说明（notebook 与数据构建脚本的索引） | 导览 |
| `DATA_UPLOAD_NOTES.md` | ★ **哪些大文件被排除、为什么**（GitHub 100MB 限制 + 无 git-lfs）。含完整的大小表与 `.gitignore` 模式 | **数据资产管理的第一手记录** |
| `overfit_risk_summary.md` | MAC 高 RESI 低 coef 策略的过拟合风险总结 | 单因子策略的风险清单 |
| `five_minute_rqalpha_summary.md` | 5 分钟精度下的 RQAlpha 费用实验（14:45 → 11:15） | **执行精度的对照** |

未复制的（在源目录，属代码/大文件）：

```
prepare_wpqc_resi_data_rq.py     30m parquet 缓存构建（宽表，一字段一文件）
prepare_wpqc_5m_data_rq.py       5m MAC 池缓存构建
prepare_cn_stock_data_rq.py      日线 + 市值 + 换手率 + 股票池 + PIT 成分
analyze_wpqc_resi_rolling_coef.ipynb          单因子 + 组合因子分析
analyze_mac_high_resi_low_coef.ipynb          MAC 高 RESI 低 coef 专项
backtest_mac_high_resi_low_coef_w80_top5_top3_vectorbt.ipynb
spy_intraday_momentum_vectorbt.ipynb
config.yaml                       ← 含 RQData 凭证，**永不迁移**
```

---

## 可直接复用的数据（重要）

**源目录** `wpqc_factor/data_rq/` 下的缓存，命名规范与本仓库完全一致，
可以**直接放进新仓库的 `data/curated/`**：

| 文件 | 大小 | 内容 |
|---|---|---|
| `cn_stock_30m_post_open_20200101_20260518.parquet` | 212 MB | 个股 30 分钟开盘价（宽表） |
| `cn_stock_30m_post_close_20200101_20260518.parquet` | 212 MB | 收盘价 |
| `cn_stock_30m_post_high_20200101_20260518.parquet` | 211 MB | 最高价 |
| `cn_stock_30m_post_low_20200101_20260518.parquet` | 208 MB | 最低价 |
| `cn_stock_30m_post_volume_20200101_20260518.parquet` | 394 MB | 成交量 |
| `cn_mac_5m_post_{open,close,high,low}_*.parquet` | 各 ~165 MB | MAC 池 5 分钟 OHLC |
| `cn_mac_5m_post_volume_*.parquet` | 310 MB | MAC 池 5 分钟量 |
| `cn_index_30m_post_*_*.parquet` | 各 ~340 KB | 指数 30 分钟 |
| `cn_index_5m_post_*_*.parquet` | 各 ~2 MB | 指数 5 分钟 |
| `cn_stock_{open,close,market_cap,total_turnover,turnover_rate}_20200101_20260513.parquet` | 各 44~60 MB | 日线五字段（已后复权） |
| `cn_mac_pit_universe_20200101_20260518.parquet` | 179 KB | ⭐ **PIT 成分股快照**（每日） |
| `cn_mac_pit_universe_20200101_20260518.csv` | 28 MB | 同上，CSV 版 |
| `cn_stock_universe_20260518.csv` | 1.3 MB | 股票池快照 |
| `wpqc_30m_cache_meta.json` | 7 KB | 30m 缓存的元数据（含 `known_issues`） |
| `wpqc_mac_5m_cache_meta.json` | 8 KB | 5m 缓存的元数据 |

**总计约 2.3 GB。** 迁移方式：

```bash
# 不要复制（同一块盘，直接软链或移动）
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_30m_post_* \
      ~/my_quantproject/FactorResearch/data/curated/

# 然后在 MANIFEST 里登记（区间是 2020-01-01 ~ 2026-05-18）
```

⚠️ **注意两点**：
1. 这些缓存的区间到 **2026-05-18**，不含之后的新数据
2. `meta.json` 里的 `known_issues` 必须读一遍再决定能不能直接用

---

## 值得搬的代码

| 源文件 | 值得抄什么 |
|---|---|
| `prepare_wpqc_resi_data_rq.py` | ★ **宽表 parquet 缓存的完整实现**：分块取数（`--chunk-size 500`）、字段分别落盘、`meta.json` 记录参数与 `known_issues`、失败时写 `write_failure_meta`、`--force` 重取 |
| `prepare_cn_stock_data_rq.py` | 日线 + 市值 + 换手率的批量构建，含股票池过滤（上市满一年 + Active） |
| `prepare_wpqc_5m_data_rq.py` | 5 分钟数据的构建（同上，但品种是 MAC 池） |

这三份的**命名规范、目录结构、meta 格式**直接被本仓库
`docs/01_architecture/data_layer.md` 与 `configs/data.yaml` 继承。

---

## 与主项目的关系

`wpqc_factor` 是 `wpqc` 的**单因子侧翼**：

- `wpqc` 关心"哪条选股线更好"（组合层）
- `wpqc_factor` 关心"RESI / coef_std 这两个因子本身怎么样"（因子层）

两边共享同一份 30 分钟 bar 缓存与同一套收益口径（14:45 买 → 次日 11:15 卖），
因此结论可以直接对照。

**最重要的负面结论**（现已进 `docs/03_knowledge/factor_zoo.md`）：

```
RESI:     IC −0.058（看似最强），但与 20 日波动率相关 0.72 → 是"买高波动"的马甲
coef_std: IC −0.009（≈0）
→ V1（用这两个因子）组合层：毛年化 21.5%、净 +0.9%、MDD −38.7%、
                              前 10 天贡献 97% 的毛收益
```

---

## 关于 `DATA_UPLOAD_NOTES.md`（值得单独说）

这份 2.5KB 的文件解决了一个非常实际的问题：**"哪些数据该进版本库，哪些不该"**。

它做了三件事：

1. **明确列出被排除的大文件与大小**（852MB / 839MB / 394MB / …）
2. **解释原因**（WSL 无 git-lfs，GitHub 拒收 100MB+）
3. **给出替代方案**（装 Git LFS / release asset / 对象存储）
4. **额外列出"第一次 push 超过 2GB 后又被排除的模式"**（`results/**/*.parquet`、`data_rq/cn_stock_total_turnover_*.parquet`）

**本仓库的 `.gitignore` 与 `docs/01_architecture/data_layer.md §5` 直接沿用了这套思路。**
