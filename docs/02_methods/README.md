# 02 · 方法

> 这一层回答**"怎么做才对"**，与具体因子无关。
> 主文档是 [`research_workflow.md`](research_workflow.md) 的 **7 道门**，其余四篇是它的展开。

| 文件 | 对应门 | 内容 |
|---|---|---|
| [`research_workflow.md`](research_workflow.md) | **全部** | ★ 7 道门的完整流程、判定线、检查表 |
| [`factor_eval.md`](factor_eval.md) | 门 3、门 4 | RankIC / NW-t / 块自举 / 分层 / 辛普森悖论 / 覆盖率 / 相关矩阵 |
| [`portfolio_eval.md`](portfolio_eval.md) | 门 5 | 单位敞口日收益 / 脆弱性曲线 / 块自举 / 分年 / 超额 / 容量 / 执行假设 |
| [`overfitting_controls.md`](overfitting_controls.md) | 门 6 | N 记账 / DSR / PBO / 禁运 / 置换重要性 / 安慰剂 / FDR |
| [`lookahead_audit.md`](lookahead_audit.md) | 门 6 | 前视体检的四道检查 + 五类手工检查 + 常见前视模式 |
| [`reproduction_fidelity.md`](reproduction_fidelity.md) | 门 3–6 的**前置** | ★ 复现口径差异 11 条 + 复用前检查清单（池成分/复权/进场价/滑点） |

---

## 一张图记住七个门

```
门1 假设 ──► 门2 登记 ──► 门3 IC ──► 门4 独立 ──► 门5 组合 ──► 门6 审计 ──► 门7 判决
   │            │           │           │             │            │           │
 idea.md    trials_log   ic_summary    orth+PI     backtest      DSR/PBO   factors.yaml
 四处必答    先记账      NW-t/CI      正交+置换    单位敞口    禁运/前视    退役条件
 ↓驳回       ↓驳回       ↓驳回        ↓驳回        ↓驳回        ↓驳回      active/watch/rejected
```

**驳回是常态。** 旧项目 12 个因子方向，最终只有 1 个（`vol_ratio`）同时通过独立性与组合层。

---

## 三个最容易跳过、也最该做的

1. **门 1 的"失败判据"** —— 不写它，等于允许自己看到结果后再定义"什么算成功"。
2. **门 2 的"先记账"** —— 不记，DSR 永远只能估算。
3. **门 5 的"脆弱性曲线"** —— 不画，"年化 13%"会被当成点估计，而它可能是"最好的 10 天"。

---

## 与其他目录的关系

| 想知道 | 去哪 |
|---|---|
| 字段什么时候可知 | [`../01_architecture/pit_policy.md`](../01_architecture/pit_policy.md) |
| 已测过哪些因子、结论如何 | [`../03_knowledge/factor_zoo.md`](../03_knowledge/factor_zoo.md) |
| 哪些方向别再试 | [`../03_knowledge/falsified.md`](../03_knowledge/falsified.md) |
| 旧项目当时怎么做的（带原始数字） | [`../04_legacy/README.md`](../04_legacy/README.md) |
| 代码在哪 | `src/factorlab/` |
