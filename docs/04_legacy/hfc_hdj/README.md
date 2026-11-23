# hfc · 慧点睛（HDJ）

> **源目录**：`~/my_quantproject/hfc/`
> **迁移日期**：2026-11-20
> **迁移方式**：逐字复制，字节一致
> **项目性质**：CLS（财联社）电报事件驱动选股，SQL Server + MySQL，**已生产化并交付**

---

## 这个项目是什么

从财联社历史电报里抽取「时间 + 涉及股票」，构造事件驱动的选股池，
再用一套打分规则选出推荐股票，落库并通过定时任务每日运行。

**这是四个项目里唯一"交付出去"的一个** —— 它有一份 95KB 的运维手册、
一份 Word/PDF 版的上线手册、以及每日运行的 shell 脚本。

---

## 文件清单

| 文件 | 是什么 | 价值 |
|---|---|---|
| `runbook.md` | ★★★ **上线实施与运维操作手册**（95 KB）。部署、配置、数据校验、每日任务、故障恢复、回滚 | **"研究 → 生产"的完整范本**，也是本仓库唯一的生产级参考 |

未复制的（在源目录）：

```
hdj_strategy.py / hdj_strategy_v02.py   策略实现
hdj_backtest.py                         回测
hdj_cls_snapshot.py                     CLS 快照
cls_sqltest.py                          SQL Server 交互（38KB）
慧点睛-筛选.py / 慧点睛-回测.py          中文命名的业务脚本
create_hdj_cls_article_snapshot.sql     建表
testsql.sql / code_mapping.json         映射与测试
logging.yaml                            日志配置
cls*.xlsx / rqyh*.csv / zpqc_final.csv  数据快照
deliverables/
  ├── runbook.md                        ← 已复制
  ├── 慧点睛hdj_strategy_v02上线实施与运维操作手册_V1.0.docx
  ├── 慧点睛hdj_strategy_v02上线实施与运维操作手册_V1.0.pdf
  └── md2docx.py                        文档转换脚本
```

---

## 为什么这个项目的运维手册值得单独保留

因子研究做到最后一定要落地，而**落地失败的原因很少是"因子不行"**，通常是：

| 失败原因 | runbook 里对应哪一节 |
|---|---|
| 数据没更新 / 更新不全 | 数据校验 |
| 定时任务没跑 / 跑失败没人知道 | 每日任务 + 监控 |
| 配置漂移（本地改了没同步） | 配置管理 |
| 出问题不知道怎么回滚 | 故障恢复 + 回滚 |
| 交接后没人看得懂 | 全文 |

**本仓库不重复这些内容，但要求：任何从 `research/` 毕业的因子，
在进生产前必须有一份同等颗粒度的 runbook。**
`docs/02_methods/research_workflow.md` 门 7 的"上线前必须做"就是这个意思。

---

## 与 cls_pool 的关系（重要）

`hfc` 用 CLS 数据做**生产**，`wpqc/cls_pool` 用 CLS 数据做**研究**。
后者把 PIT 做得很干净（截断不变性 8/8），并且得出了一个明确的**负面结论**：

> 把 V8 的选股套到 CLS 票池上 → **不建议部署**。
> V8 的边际集中在因子横截面最极端的 **0.1% 尾部**（99.9~100% 分位 +13.3bp/次，其余 −2.2bp）；
> 而 CLS 票池的平均分位是 **0.76~0.82**（全市场 0.999），**结构上够不着尾部**。
> 323 天口径：V8 原生 +50.98%/yr（t=3.46），套到 CLS 上只有 +2.35%（t=0.24）。

来源：[`../wpqc_maqiangchou/cls_pool_EVAL_V8_ON_CLS.md`](../wpqc_maqiangchou/cls_pool_EVAL_V8_ON_CLS.md)

**这条结论已提炼成 L24**（见 [`../../03_knowledge/lessons_learned.md`](../../03_knowledge/lessons_learned.md)）：
**"换个池试试"之前，先算那个池在因子排序轴上的平均分位。**

---

## 数据与凭证

源目录的 `config.yaml`、`logging.yaml` 含数据库连接信息，**未迁移**。
本仓库对应位置：`.env.example`（MySQL 段）+ `configs/default.yaml`。

---

## 值得搬的做法

| 做法 | 说明 |
|---|---|
| `create_hdj_cls_article_snapshot.sql` | **建快照表**而不是直接查业务表 —— 保证历史可复现 |
| `code_mapping.json` | 股票代码的多源映射（`sz002317` ↔ `002317.XSHE` ↔ 交易所） |
| `hdj_main_*_daily.sh` | 每日任务的最小入口（一行 shell，参数全在配置里） |
| `logging.yaml` + `logconfig.py` | 结构化日志（控制台 + 文件 + 轮转 + 脱敏） |
| `deliverables/md2docx.py` | 把 markdown 交付成 docx/pdf（**文档即交付物**） |

最后一条值得单独说：**这个项目把 runbook 同时维护成 md / docx / pdf 三种形态**。
md 给工程，docx/pdf 给业务方。这是"文档即交付物"的正确姿势 ——
新仓库的 `docs/` 只维护 md，需要交付时再渲染。
