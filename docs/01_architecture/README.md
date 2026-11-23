# 01 · 架构

仓库怎么组织、数据怎么流动、字段什么时候可知、命名怎么写。

| 文件 | 内容 | 什么时候读 |
|---|---|---|
| [`repo_layout.md`](repo_layout.md) | 五层结构（data / library / research / decision / knowledge）的职责边界与反模式 | 想加目录、想知道代码该放哪 |
| [`data_layer.md`](data_layer.md) | ★ 数据五级（raw→curated→features→labels→panels）、命名规范、精确 schema、MANIFEST、存储约定、加新数据集的 9 步清单 | 加任何数据之前 |
| [`pit_policy.md`](pit_policy.md) | ★ PIT 铁律、三个时间概念、字段可知时点表、三个高频事故、截断不变性检验 | 写任何因子之前 |
| [`conventions.md`](conventions.md) | ★ 时间/收益/成本/单位/代码/数字写法，全部约定与禁止事项 | 每天都在用 |

---

## 这一层的三条设计原则

1. **文件即文档**
   `cn_stock_30m_post_close_20200101_20261130.parquet` 这一行 `ls` 就说明了：
   市场、品种、频率、复权、字段、区间。不需要打开，不需要问人。

2. **不可重建的东西单独放**
   `raw` 永不删、永不改；`curated` 以下全部可重建。这条分界线决定了"能不能删"。

3. **口径写进机器可读的文件**
   PIT 属性在 `registry/field_pit.yaml`，标签口径在 `registry/labels.yaml`。
   写进代码注释只有写的人看；写进 YAML，审计脚本能读到、能报警。

---

## 快速索引

- 想知道"这个字段现在知道了吗" → [`pit_policy.md §2`](pit_policy.md#2-三个时间概念)
- 想知道"新数据怎么放" → [`data_layer.md §6`](data_layer.md#6-加一个新数据集检查清单)
- 想知道"命名怎么写" → [`conventions.md §2`](conventions.md#2-收益与标签)
- 想知道"为什么这样设计" → [`docs/06_adr/`](../06_adr/README.md)
