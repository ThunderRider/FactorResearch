# 0003 · 状态中枢用 YAML/CSV 而不是数据库

- **状态**：已接受
- **日期**：2026-11-20
- **关联**：[`../../registry/README.md`](../../registry/README.md)

## 背景

仓库需要维护四类"状态"：

1. 因子的定义与生命周期状态（`factors.yaml`）
2. 标签的精确口径（`labels.yaml`）
3. 字段的 PIT 属性（`field_pit.yaml`）
4. 试验记录（`trials_log.csv`）

这四类东西的共同特点：**人要看、要对比、要讨论、要写进报告**。

## 选项

**A. SQLite / MySQL**

- 优点：并发写、索引、事务；查询快
- 缺点：**不能 git diff**。改动只能看到"值变了"，看不到"为什么变"；
  要写进报告得导出；review 时打不开

**B. JSON**

- 优点：机器友好、schema 可校验
- 缺点：没有注释；多行字符串难写（因子定义都是长文本）；diff 可读性差

**C. YAML + CSV**（本决定）

- 优点：可读、可注释、git diff 精确到行、能被报告直接引用
- 缺点：无并发写保护；无索引；大文件（>1 万行）读取慢

**D. Markdown 表格**

- 优点：人最愿意读
- 缺点：机器难解析（要写解析器，且格式一破就崩）；没有类型

## 决定

**采用 C。具体分工：**

| 文件 | 格式 | 为什么用这个格式 |
|---|---|---|
| `factors.yaml` | YAML | 每条包含长文本定义、多行 notes、嵌套 evidence → 需要注释与多行字符串 |
| `labels.yaml` | YAML | 同上（定义是公式） |
| `field_pit.yaml` | YAML | 同上（需要 `note` 字段解释陷阱） |
| `trials_log.csv` | CSV | **会长到几百上千行**；需要按列筛选统计（`N`、`σ(SR)`）；pandas 一行读 |

## 代价

1. **没有并发写保护**。多人同时改 `factors.yaml` 会冲突。
   → 缓解：单人为主；多人时用 git 分支 + 冲突时人工合并（YAML 冲突其实可读）。
2. **没有索引**。`trials_log.csv` 超过 1 万行后读取变慢（约 100ms，仍可接受）。
3. **没有类型校验**。写错字段名不会报错。
   → 缓解：`python -m factorlab.audit.registry_check` 做一致性检查（建议设为 pre-commit）。
4. **`trials_log.csv` 的追加不是原子的**。两个人同时追加会丢行。
   → 缓解：同一时刻只一个人跑实验；或每次跑完手动 `git add` 检查。

## 什么时候应该重新考虑

- `trials_log.csv` 超过 5 万行 → 迁到 SQLite，但**保留一份自动导出的 CSV 快照**用于 diff
- 出现 3 个以上并行研究者 → 改数据库 + 每日快照
- 需要跨仓库共享因子定义 → 抽成独立的包

**注意**：即使迁到数据库，**也建议保留 CSV 快照**。
"能 diff"这件事的价值，不随数据量增长而消失。

## 影响

- `registry/README.md` 说明了四个文件的职责边界
- `src/factorlab/config.py` 的 `load_registry()` 是唯一入口
- `src/factorlab/audit/registry_check.py` 做一致性检查
