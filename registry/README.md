# registry · 状态中枢

> **这里是唯一的状态真相源。** 回答四个问题：
>
> 1. 这个因子叫什么、怎么算、什么方向、现在什么状态？ → [`factors.yaml`](factors.yaml)
> 2. 这个标签（目标收益）的精确口径是什么？ → [`labels.yaml`](labels.yaml)
> 3. 这个字段在决策时点知道了吗？ → [`field_pit.yaml`](field_pit.yaml)
> 4. 我一共试了多少次？ → [`trials_log.csv`](trials_log.csv)

---

## 为什么是 YAML / CSV 而不是数据库

| 需求 | YAML/CSV | 数据库 |
|---|---|---|
| 人直接读懂 | ✅ | ❌ 要查 |
| git 逐行 diff、code review | ✅ | ❌ |
| 写进报告、贴进文档 | ✅ | ⚠️ 要导出 |
| 存百万行数据 | ❌ | ✅ |
| 多用户并发写 | ❌ | ✅ |

这四类内容的共同特点是**"人要看、要 diff、要讨论"**，不是"量大"。
所以用文本文件。

`trials_log.csv` 用 CSV 而不是 YAML：它会很长（几百上千行），
需要按列筛选统计（`N`、`σ(SR)`），pandas 一行就能算。

---

## 加载方式

```python
from factorlab.config import load_registry

reg      = load_registry('factors')
labels   = load_registry('labels')
pit      = load_registry('field_pit')
trials   = load_registry('trials')     # → DataFrame
```

代码侧只读不写（除 `trials_log` 的追加与 `factors.yaml` 的状态更新）。

---

## 四个文件的职责边界（别混）

| 文件 | 回答 | 谁写 | 什么时候改 |
|---|---|---|---|
| `factors.yaml` | 因子的**定义与状态** | 研究者 | 新增因子 / 判决变更 |
| `labels.yaml` | 标签的**精确口径** | 架构 | 极少改（改了要全量重算） |
| `field_pit.yaml` | 字段的**可知时点** | 架构 | 每加一个字段 |
| `trials_log.csv` | **试验记录** | 所有人 | 每次跑实验（**只追加**） |

---

## 状态机

`factors.yaml` 里每个因子有 `status`，只能沿这个方向走：

```
draft ──► candidate ──► active ──► retired
             │            │
             └──► rejected ◄──┘
```

| 状态 | 含义 | 允许的说法 |
|---|---|---|
| `draft` | 有定义，未做正式评估 | "未验证" |
| `candidate` | 通过门 1-2，正在跑 | "研究中" |
| `active` | 通过全部 7 道门 | "有独立信息，组合层贡献 X pp" |
| `watch` | 部分通过，证据不足 | "样本内有效但样本外未验证，**不得计入业绩预期**" |
| `retired` | 曾 active，已触发退役规则 | "已退役（原因 / 日期）" |
| `rejected` | 任一门实质不通过 | "已证伪，不要再试" + 死因 |
| `input` / `control` | 不作为因子，只作构造材料 / 控制变量 | — |

**状态变更必须同时更新：**
1. `factors.yaml` 的 `status` + `status_changed` + `status_reason`
2. `docs/03_knowledge/factor_zoo.md` 的总表
3. 若从 `active` → `retired`，在 `docs/05_journal/` 记一条

---

## 一致性检查

```bash
python -m factorlab.audit.registry_check
```

检查项：

- [ ] `factors.yaml` 里每个因子的 `id` 在 `features/` 里真的存在
- [ ] `status: active` 的因子，`evidence` 字段非空
- [ ] `status: rejected` 的因子，`reject_reason` 非空
- [ ] `status: active` 的因子必须有 `retire_if`（退役条件）
- [ ] `field_pit.yaml` 覆盖 `factors.yaml` 里所有 `pit_fields`
- [ ] `trials_log.csv` 里每个 `run_id` 在 `artifacts/results/` 有对应目录（或注明已清理）
- [ ] `trials_log.csv` 的 `git_sha` 非空

**建议设为 pre-commit 钩子** —— 一致性靠检查，不靠自觉。
