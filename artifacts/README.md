# artifacts · 产出

> **这一层可以随时删。** 里面的东西都能由 `data/` + 代码重算。
> 但**删之前确认没有 `docs/03_knowledge/` 的结论依赖它**。

---

## 三个子目录

| 目录 | 内容 | 寿命 | 入库？ |
|---|---|---|---|
| `cache/` | 中间大对象（panel 快照、pickle、临时中间件） | **30 天**，可随时清 | ❌ |
| `results/` | 一次运行的产物：`<run_id>/ic_summary.csv`、`backtest.csv`、`fragility.csv`… | 与研究同寿 | ❌ |
| `reports/` | 人读的报告：`<run_id>.md` / `.txt` | 长期（结论的载体） | ❌ |

**注意**：`reports/` 里的**结论**要回写到 `docs/03_knowledge/` 或 `research/*/conclusion.md`。
`reports/` 只是"当时生成的那一份"，不是知识库。

---

## run_id 约定

```
<YYYYMMDD>-<slug>

20261120-baseline
20261121-vol_ratio_bar_choice
20261122-amihud_orth_true_mktcap
```

一个 `run_id` 贯穿：
`artifacts/results/<run_id>/` · `artifacts/reports/<run_id>.md` · `registry/trials_log.csv` 的 `run_id` 列。

**为什么统一**：想知道"这个数字是哪次跑的"，一个 grep 就能串起来。

---

## 清理策略

```bash
# 清 30 天前的缓存
find artifacts/cache -type f -mtime +30 -delete

# 清掉没有对应 trials_log 记录的结果（孤儿产物）
python -m factorlab.audit.registry_check   # 会报出对不上的 run_id
```

---

## 一个容易犯的错

> 把 `artifacts/results/` 当成知识库用。

`results/` 里是**一次运行的输出**，没有上下文（不知道当时的假设、判定线、失败判据）。
知识必须写成带口径的文档，放进 `docs/03_knowledge/`。

**判据**：如果三个月后有人只看 `artifacts/` 的一份 CSV，能说出"这个结论成立吗" ——
不能。所以它只是产物，不是知识。
