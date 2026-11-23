# 快速上手

> 目标：**30 分钟内**从零跑到第一次因子评估。
> 如果你只有 5 分钟，看 [§0](#0-五分钟版) 就够了。

---

## 0. 五分钟版

```bash
cd ~/my_quantproject/FactorResearch

# 1) 自检（不连行情库，用合成数据）
python -m pytest tests -q                 # 应看到 60 passed

# 2) 注册表一致性（不连行情库）
python -m factorlab.audit.registry_check

# 3) 读三个文件就够了
#    README.md                      ← 三条铁律
#    docs/02_methods/research_workflow.md   ← 7 道门
#    docs/03_knowledge/lessons_learned.md   ← 24 条教训
```

上面 3 步都不需要 RQData。要真正开始研究，继续往下。

---

## 1. 环境

```bash
conda activate rq                 # 复用旧项目的环境（pandas / numpy 已有）
pip install -r requirements.txt   # 增量：pyarrow / PyYAML / python-dotenv / statsmodels
pip install pytest                # 跑测试用
```

**最小依赖**：`pandas` `numpy` `pyarrow` `PyYAML`。
`rqdatac` 只有取数时需要 —— **其余全部可离线运行**（这是刻意设计，见 `lessons_learned.md` L16）。

---

## 2. 凭证

```bash
cp .env.example .env
# 编辑 .env，填 RQDATA_USERNAME / RQDATA_PASSWORD
```

`.env` 已被 `.gitignore` 忽略，**永不入库**。

> ⚠️ 旧项目的 `config.yaml` 里有明文凭证，那份文件**没有**被迁移过来。
> 如果要在旧目录里跑旧代码，请自己确认那份凭证是否还需要轮换。

---

## 3. 数据

### 3.1 最省力：复用旧项目的缓存（约 2.3 GB，直接软链）

```bash
cd ~/my_quantproject/FactorResearch
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_30m_post_*.parquet  data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_index_30m_post_*.parquet  data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_mac_pit_universe_*.parquet data/curated/
ln -s ~/my_quantproject/wpqc_factor/data_rq/cn_stock_market_cap_*.parquet data/curated/
```

**命名规范完全一致**，所以不需要转换。详见 [`../data/README.md`](../data/README.md) §1.1。

⚠️ 这批缓存只到 **2026-05-18**。要延长必须重新取数。

### 3.2 从头取数

```bash
python -m factorlab.data.build --dataset 30m_stock --start 2020-01-01 --end 2026-11-30
python -m factorlab.data.build --dataset universe_pit --start 2020-01-01 --end 2026-11-30
```

第一条给行情，第二条给 **PIT 成分股**（不做这一步就有幸存者偏差）。

### 3.3 校验

```bash
python -m factorlab.io.quality --path "data/curated/cn_stock_30m_post_close_*.parquet"
```

---

## 4. 跑第一次因子评估

假设你已经有一个面板（`data/panels/*.parquet`，含 `date / ticker / pool / <因子> / <标签>`）：

```bash
python -m factorlab.eval.run \
  --panel  data/panels/panel_mac-min_20200101_20261130_v1.parquet \
  --factors vol_ratio ret_20d \
  --label  ret_1445_next_1115 \
  --out    artifacts/results/20261120-baseline
```

看到 `ic_summary.csv` / `long_short.csv` / `coverage.csv` / `report.txt` 就成功了。

**读法**（三句话）：

1. **看 `t_newey_west`，不看 `t_naive`** —— 后者在重叠窗口下高估 20–30%
2. **看 `n_eff`，不看 `n_days`** —— 有效样本可能只有一半
3. **q10−q1 的 `spread_bp` 要和 20bp（盈亏平衡线）比** —— 不是和 0 比

---

## 5. 开一个新研究

```bash
cp -r research/_template research/2026-11_my_first_factor
cd research/2026-11_my_first_factor
```

然后按顺序：

```bash
# 1) 先写 idea.md（尤其是第 4 节"失败判据"，开题时就要写死）
$EDITOR idea.md

# 2) 改 config.yaml（run_id、panel 路径、因子）
$EDITOR config.yaml

# 3) 跑（每跑一个 stage 会自动往 trials_log 记一行）
python run.py --stage factor        # 门 3：IC / 分层 / 覆盖率
python run.py --stage independence  # 门 4：正交化 + 置换重要性
python run.py --stage portfolio     # 门 5：组合层 + 脆弱性
python run.py --stage audit         # 门 6：前视 / DSR / PBO / 禁运

# 或者按门的顺序一次跑完（不会跳过前面的门）
python run.py --stage all

# 4) 写结论
$EDITOR conclusion.md
```

**注意**：`run.py` 会在跑之前先记一行 `trials_log`（`value=None, passed=tbd`）。
这是刻意的 —— 防止"结果不好就不记了"。

---

## 6. 目录速查

| 我想… | 去 |
|---|---|
| 知道这个字段现在能不能用 | [`../registry/field_pit.yaml`](../registry/field_pit.yaml) |
| 知道这个因子测过没有 | [`factor_zoo.md`](03_knowledge/factor_zoo.md) |
| 知道这条死路走过没有 | [`falsified.md`](03_knowledge/falsified.md) |
| 知道数据怎么命名、怎么放 | [`../data/README.md`](../data/README.md) |
| 知道旧项目当时怎么做的 | [`04_legacy/`](04_legacy/README.md) |
| 知道为什么仓库长这样 | [`06_adr/`](06_adr/README.md) |

---

## 7. 三个最容易犯的错

### ❌ 1. 用 `day_amt` / `amt20` 直接做因子

它们**含当日 15:00** 的信息，而决策在 14:30。必须 `shift(1)`。

> 旧项目为此付出 1.66pp 的代价（`lessons_learned.md` L8）。

### ❌ 2. 不记账就开始跑

`trials_log.csv` 是 DSR 的分母。**先记后跑**，包括失败的。

> 旧项目事后清点出 N≈110，σ(SR) 只能给区间，DSR 永远只能报"0.51~0.77"（L13）。

### ❌ 3. 看到 IC 好就写进知识库

`IC 好 ≠ 组合层有用 ≠ 有独立信息 ≠ 样本外还在`。

> MAX 因子 IC −0.051 稳定四年，与波动率相关 0.874，9 种用法全部变差（L1）。

---

## 8. 下一步读什么

按这个顺序，从"要做"到"为什么"：

```
1. docs/01_architecture/data_layer.md        数据怎么放（做任何事之前）
2. docs/01_architecture/pit_policy.md        PIT 铁律（写任何因子之前）
3. docs/02_methods/research_workflow.md      7 道门（做任何研究之前）
4. docs/03_knowledge/lessons_learned.md      24 条教训（提任何想法之前）
5. docs/03_knowledge/falsified.md            别再试的 15 条
6. docs/04_legacy/README.md                  旧项目档案（想知道原始数字时）
```

---

## 9. 遇到问题

| 症状 | 先查 |
|---|---|
| `ModuleNotFoundError: factorlab` | `export PYTHONPATH=$PWD/src`，或 `pip install -e .` |
| `registry_check` 报错 | 按提示补 `direction` / `retire_if` / `reject_reason` |
| 宽表写入报 `index.name == 'date'` | 你的 DataFrame 索引不是 `DatetimeIndex` 或没命名 |
| `quality` 报 ticker 格式错 | 列名应是 `000001.XSHE` / `600000.XSHG`，不是 `sz000001` |
| 面板里因子找不到 | 先确认 `data/features/` 有这个因子，且已在 `registry/factors.yaml` 登记 |
