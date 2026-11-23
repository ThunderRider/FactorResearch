# tests · 冒烟测试

> **这些测试的目的不是覆盖率，而是"防止有人悄悄把口径改错"。**
> 每一条对应一处真实踩过的坑（见 `../docs/03_knowledge/lessons_learned.md`）。

```bash
python -m pytest tests -q
```

**不需要 RQData、不需要任何真实数据** —— 全部用合成数据，所以任何人克隆下来就能跑。

---

## 测试地图

| 测试 | 防的是什么坑 |
|---|---|
| `test_decomposition_identity` | 三段分解的乘积不等于主标签 → "拆开看"失去意义 |
| `test_label_is_forward_looking` | 最后一天的标签被填了值 → 用了不存在的数据 |
| `test_amihud_shift_applied_after_rolling` | `shift` 加在 `rolling` 之前 → 语义错位（L9） |
| `test_check_shift_version_detects_wrong_version` | 用"含今日"的字段做因子（L8，值 1.66pp） |
| `test_impact_threshold` | 前视修正的判定线被放宽 |
| `test_rank_ic_detects_signal` | IC 算错（方向 / 分组） |
| `test_newey_west_penalises_autocorrelation` | 重叠窗口下 naive t 高估（L-gate3） |
| `test_ic_summary_splits_by_pool` | 混池算 IC → 把池间差异当信号 |
| `test_decile_is_monotone_on_strong_signal` | 分层排序反了 |
| `test_allocate_respects_cap` / `_keeps_cash_when_all_capped` | 单票上限被突破 / 现金被强行用掉 |
| `test_backtest_cost_formula` | 日成本公式错（应为 `单边 × (今日+昨日敞口)`） |
| `test_per_unit_breakeven_flag` | 盈亏平衡线（0.200%/日）判定失效 |
| `test_fragility_curve_decreases` | 脆弱性曲线方向错 |
| `test_block_bootstrap_interval_contains_point` | 自举实现错 |
| `test_concentration_detects_extreme_day` | 收益集中度算错 |
| `test_excess_discounts_by_exposure` | 超额不按敞口折算 → 虚高 |
| `test_dsr_decreases_with_more_trials` | DSR 没有惩罚 N（L13） |
| `test_psr_matches_unpenalised_case` | N=1 时 DSR ≠ PSR（公式错） |
| `test_pbo_high_on_pure_noise` / `_low_when_one_config_dominates` | PBO/CSCV 实现错（应能从 50% 分出信号） |
| `test_wide_roundtrip_and_manifest` | 宽表往返丢失精度 / MANIFEST 没写 |
| `test_write_wide_rejects_bad_index` | 索引约定（DatetimeIndex + name='date'）被破坏 |
| `test_quality_flags_bad_ticker` | ticker 格式校验失效 |
| `test_registry_loads_and_is_consistent` | active 因子缺退役条件 |
| `test_field_pit_covers_active_factors` | 因子引用了未登记的字段（来路不明） |
| `test_trials_log_parses` | 记账文件损坏 |
| `test_orthogonalize_removes_control_exposure` | 正交化实现错（残差仍与 control 相关）|
| `test_proxy_factor_loses_its_ic` | 把"暴露型因子"当成独立因子（旧项目 amihud 形态）|
| `test_genuine_factor_keeps_its_ic` | 保留率判定线被放宽 |
| `test_sign_flip_is_flagged` | 符号翻转没有被识别出来（最危险的一种）|
| `test_orthogonalize_rejects_unknown_column` | 控制变量写错却静默通过 |
| `test_split_with_embargo_counts` | 禁运把 IS 样本切错 |
| `test_embargo_reduces_oos_sample` | 禁运没生效 |
| `test_oos_metrics_reports_three_required_fields` | 报告缺"切分日/禁运长度/OOS 天数"三要素 |
| `test_embargo_sensitivity_monotone_decay_shape` | 敏感性网格的基准列算错 |
| `test_snapshot_uses_bar_end_timestamps` | bar 时间戳改成开始时刻（差一格，全盘口径错）|
| `test_up_to_asof_aggregates_exclude_late_bars` | 「截至 as_of」的聚合混进了 15:00 的 bar |
| `test_build_panel_shape_and_columns` | 面板缺列（后续门全部跑不动）|
| `test_panel_labels_satisfy_decomposition` | 面板里的三段分解不满足恒等式 |
| `test_panel_has_no_lookahead_in_amt20` | 面板里塞了「含今日」的 amt20 |
| `test_tradable_is_a_flag_not_a_filter` | 可交易标记被当成删除行的过滤器 |
| `test_unknown_factor_is_rejected` | 拼错因子名却静默产出空列 |
| `test_wide_fields_to_bars_roundtrip` | 宽表与 bar 长表互转丢数据 |
| `test_load_field_wide_picks_latest` | 多区间文件时取错版本 |
| `test_write_panel_registers_manifest` | 面板落盘没登记 MANIFEST |
| `test_frontmatter_is_valid` | 技能的 name/description 不合 DSH 契约（会直接不被发现）|
| `test_frontmatter_has_no_legacy_keys` | 用了已废弃的驼峰 frontmatter 键 |
| `test_referenced_repo_paths_exist` | 技能引用了不存在的仓库路径 |
| `test_referenced_modules_exist` | 技能引用了不存在的模块 |
| `test_thresholds_are_all_present` | 技能漏掉某条判定线 |
| `test_test_baseline_matches_reality` | 技能里写的测试基线已过期 |
| `test_thresholds_match_config` | 技能与 configs/ 各写一套判定线 |
| `test_referenced_resources_exist` | 技能的 references/ 链接失效 |
| `test_checklists_covers_every_gate` | 检查单漏掉某道门（等于允许跳门）|
| `test_three_iron_laws_are_all_enforced` | 三条铁律缺了可判定内容 |

---

## 建议的扩展

正式研究时，把关键数字做成**回归测试**：

```python
# tests/test_regression.py
def test_v3_reproduces_legacy():
    """用 wpqc 的离线快照复现 V3，净年化应落在 9.59% ± 0.3pp。"""
```

**前提是有离线复现层**（旧项目 `overfit_lab/` 的作用，见 `lessons_learned.md` L16）。
没有它，回归测试只能依赖真实数据，跑不快也跑不稳。

---

## fixture 放哪

```
tests/fixtures/           ← .gitignore 里已白名单（允许 *.parquet 入库）
├── spy/                  日内动量复现用的小文件（约 224 KB）
└── panel_mini.parquet    一个小面板（几万行），供 CLI 冒烟测试
```

**只放小文件**。大文件用脚本生成，不入库。
