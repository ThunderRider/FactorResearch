# _template · 研究模板

> **复制这个目录来开一个新研究：**
>
> ```bash
> cp -r research/_template research/2026-11_<你的slug>
> ```
>
> 然后按顺序填：`idea.md` → `config.yaml` → `run.py` → `result/` → `conclusion.md`。
> 每一步完成时把 `README.md` 的进度勾上。

---

## 进度

- [ ] 1. `idea.md` 四问都答了（**尤其是失败判据**）
- [ ] 2. `registry/factors.yaml` 加了一条 `status: draft`
- [ ] 3. `registry/trials_log.csv` 开了账（先记后跑）
- [ ] 4. 因子层：IC / NW-t / 块自举 / 逐年 / 分层 / 覆盖率
- [ ] 5. 独立性：正交化 + 置换重要性（含噪声对照）
- [ ] 6. 组合层：单位敞口日收益 vs 0.200% / 脆弱性 / 成本三档
- [ ] 7. 审计：前视体检 / DSR / PBO（或说明为何跳过）/ 禁运
- [ ] 8. `conclusion.md` 判决 + 退役条件
- [ ] 9. 更新 `docs/03_knowledge/factor_zoo.md` 与 `registry/factors.yaml` 的状态

---

## 本模板的四个文件，各管一件事

| 文件 | 作用 | 什么时候改 |
|---|---|---|
| `idea.md` | **假设**：经济逻辑 / 精确构造 / 可证伪预测 / **失败判据** | 只在开题时写一次；之后要改 → 另开一篇 |
| `config.yaml` | 本次研究的**参数** | 改一次 = 一次新试验，必须记账 |
| `run.py` | **唯一执行入口**，五步一条命令跑完 | 随研究推进 |
| `conclusion.md` | **判决**：留 / 观察 / 丢 + 证据 + 退役条件 | 只写一次，写在最后 |

---

## 为什么不用 notebook 做正式结论

- notebook 的执行顺序是隐式的，**换台机器重跑会不一样**
- diff 不可读，review 时看不出改了什么
- 22 MB 的 notebook 是"结论的黑洞"

**notebook 可以做探索**（放 `notebooks/`），但正式结论必须回写成
`run.py` + `result/*.csv` + `conclusion.md`。

---

## 检查：你的研究可以结束了吗

```markdown
- [ ] 别人拿到这个目录，能一条命令复现所有数字
- [ ] 每个数字都有口径（区间 / 池 / 成本 / 标签）
- [ ] 失败判据是开题时写的，不是事后补的
- [ ] trials_log 里的行数与实际跑的次数一致（含失败的）
- [ ] conclusion.md 里的状态与 registry/factors.yaml 一致
- [ ] 退役条件已经写了
```

六条全过，才算走完 7 道门。
