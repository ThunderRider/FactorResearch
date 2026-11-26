# 假设：GTJA191 中五个短周期价量因子是 WPQC 现有暴露之外的独立候选

> 来源与依据：
> `docs/03_knowledge/factor_zoo.md`、`docs/04_legacy/wpqc_maqiangchou/`、
> 公开 GTJA191 原报告与复现仓库。

---

## 1. 经济逻辑

WPQC V8 现有暴露集中在三层：
缩量（`vol_ratio`）、冷门/低流动性（`amihud_lag`）、20 日超跌（`ret_20d`）。
这三个暴露叠加后，恰好把组合推向“最缩量、最低流动、最超跌”的极端尾部，
而真 PIT 重测已经证明这个顶部区间不可买。

GTJA191 是短周期价量 Alpha 因子。第一批选择的目标不是继续加大这三类暴露，
而是找“价格区间位置、量价背离、上行/下行压力、时序排名”等更偏横截面形状的因子。

## 2. 精确构造

所有滚动因子使用**上一交易日完整日频数据**，再 `shift(1)` 对齐到决策日 `T`。
`gtja_015` 使用 `T` 日开盘价，10:00 即已知，14:30 决策时安全。

```
gtja_057  = EWMA( (close - rolling_min(low,9)) / (rolling_max(high,9) - rolling_min(low,9)) )
gtja_001  = - corr(rank(delta(volume,1)), rank((close-open)/open), 6)
gtja_016  = - max(corr(rank(volume), rank(vwap), 5), 5)
gtja_049  = down_magnitude_12d / (down_magnitude_12d + up_magnitude_12d)
gtja_117  = ts_rank(volume,32) * (1 - ts_rank(close+high-low,16)) * (1 - ts_rank(ret,32))
gtja_015  = open / close.shift(1) - 1        # 只做诊断，不进入本次组合打分
```

方向：

- `gtja_057`：-1，接近 9 日高点视为短期过热
- `gtja_001`：+1，量价负相关视为“缩量上涨/量价背离”
- `gtja_016`：+1，同上但用 VWAP 排名
- `gtja_049`：+1，下行压力占比高视为超跌后的修复候选
- `gtja_117`：+1，高量能、近期弱势视为反弹候选

## 3. 可证伪的预测

1. 这些因子至少一部分在 mac/min 池中 `|NW t| >= 3`。
2. 与 `vol_ratio / amihud_lag / ret_20d` 的秩相关不高，至少一半低于 `0.70`。
3. 对 `log_amt20 / log_mktcap / vol_20d / ret_20d` 正交后，IC 保留率超过 `60%`。
4. 在不是只取 top-4 的宽口径下，至少一个候选能对 WPQC 组合层产生正贡献。

## 4. 失败判据（**开题时就写死**）

如果出现以下任一情况，**直接丢弃，不再调参**：

- [x] 任一候选与 `vol_ratio / amihud_lag / ret_20d` 秩相关 > 0.70，则直接搁置
- [x] 任一候选正交后 IC 保留率 < 60% 或符号翻转，则判为旧暴露
- [x] 净置换重要性 < 0.10，则不进入后续组合层
- [x] 五个候选在宽口径组合层均未越过盈亏平衡线，则整个方向降为 `watch`

## 5. 已知的反面证据

`docs/03_knowledge/falsified.md #16` 已证伪“继续修 WPQC 顶部”的三种做法。
本次不是修 top-4，而是筛选独立候选。已知 `gap` 类因子曾被证伪为涨停污染源，
因此 `gtja_015` 只做诊断，不直接进打分。

## 6. 适用池与容量预期

池：真 PIT `mac = 沪深300+中证500`、`min = 中证1000+中证2000`。
第一批只看因子层和独立性，组合层先采用 `N=20` 宽口径，
避免已知的 `top-4` 极端尾部失效。

---

*开题日期：2026-11-26*
*预计工作量：1 天*
