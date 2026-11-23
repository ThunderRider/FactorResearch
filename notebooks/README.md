# notebooks · 探索

> **这里只放探索。正式结论必须走 `research/<dir>/run.py` + `conclusion.md`。**

---

## 为什么 notebook 不能当结论

旧项目的教训（`lessons_learned.md` L16 与 ADR 0004）：

- `test01.ipynb` **22 MB**，是当时唯一的结论来源
- 执行顺序是隐式的 → **换台机器重跑会不一样**
- diff 不可读 → review 时看不出改了什么
- 输出嵌在文件里 → 无法判断"这个数字是哪个版本的代码跑的"

---

## Notebook 的正确用法

| 可以做 | 不可以做 |
|---|---|
| 看数据长什么样 | 作为结论的唯一来源 |
| 试公式对不对 | 直接产出写进 `docs/03_knowledge/` 的数字 |
| 画一张探索图 | 藏着关键参数 |
| 快速验证一个想法 | 提交 20 MB 的输出 |

**规则**：notebook 里任何"值得保留的结论"，**必须在 24 小时内回写**成
`research/*/conclusion.md` 或 `docs/03_knowledge/` 的一段。

---

## 命名与体积

```
notebooks/
├── 2026-11-20_vol_ratio_first_look.ipynb
└── 2026-11-21_amihud_orth_explore.ipynb
```

- 日期前缀（与 journal 一致）
- **提交前清空输出**：`jupyter nbconvert --clear-output --inplace <file>`
  （⚠️ `.gitignore` 不排除 ipynb，但排除 `*.parquet` / `*.pkl`；
  不要把 22 MB 的输出提交进来）

---

## 一条硬规则

> **如果一个 notebook 超过 2 周还在被引用作为结论来源，说明有人懒得写文档。**
>
> 这时候的正确动作不是"继续用 notebook"，而是把它里面的逻辑搬进 `run.py`。
