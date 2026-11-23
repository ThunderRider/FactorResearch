# ASP 策略接入券商投顾社区生产化方案

## 1. Summary

目标是把当前 ASP 成交额斜率策略改造成一条可每日运行、可审计、可对客展示的生产流水线：

- 每日自动从米筐拉取行情数据，校验后保存为 parquet。
- vectorbt 负责参数搜索和候选参数生成。
- 生产信号按“每日落库冻结”原则固化：历史买卖点一旦发布，不因后续寻参或重算改变。
- 米筐量化回测读取冻结买卖点，输出策略净值，并使用沪深 300 作为 benchmark。
- 最终将买卖点、持仓、策略净值、benchmark 净值、参数版本和运行日志写入 MySQL，供投顾社区读取。

## 2. Overall Architecture

整体流程分为五层：

1. 数据层：每日自动拉取米筐行情、指数和基础数据，校验后保存 parquet。
2. 研究层：vectorbt 做参数搜索，生成候选参数和研究指标。
3. 信号层：使用当前生产参数生成每日买卖点，并写入 MySQL 冻结。
4. 回测层：米筐量化回测读取冻结买卖点，生成策略净值和沪深 300 benchmark 净值。
5. 展示层：券商 APP 投顾社区只读取 MySQL 中已经冻结和发布的数据。

核心原则：

- 研究和生产分离。
- 寻参和信号发布分离。
- 历史买卖点不可因后续寻参被覆盖。
- 对客展示以冻结信号和米筐回测净值为准。

## 3. Daily Data Update

新增每日数据任务 `daily_data_update`。

### 3.1 Data Sources

使用米筐 `rqdatac` 拉取：

- 股票日行情：
  - `open`
  - `close`
  - `total_turnover`
- 指数行情：
  - 沪深 300，建议使用 `000300.XSHG`
- 交易日历：
  - 判断目标日期是否为交易日
- 股票基础信息：
  - 股票代码
  - 股票名称
  - 上市状态
  - 行业信息，如后续做行业中性化可复用

### 3.2 Parquet Storage

数据落地为 parquet，建议保存为矩阵格式：

- `data_rq/cn_stock_open_YYYYMMDD_YYYYMMDD.parquet`
- `data_rq/cn_stock_close_YYYYMMDD_YYYYMMDD.parquet`
- `data_rq/cn_stock_total_turnover_YYYYMMDD_YYYYMMDD.parquet`
- `data_rq/index_000300_XSHG_close_YYYYMMDD_YYYYMMDD.parquet`

每次运行生成元数据文件：

- `data_rq/data_manifest_YYYYMMDD.json`

manifest 至少记录：

- 数据日期
- 拉取时间
- 数据字段
- 股票数量
- 每个字段缺失率
- 文件路径
- 文件 hash
- 米筐请求参数
- 校验状态

### 3.3 Data Validation

校验规则：

- 目标日期必须是交易日。
- 行情数据日期必须等于目标交易日。
- 股票数量不能低于配置阈值。
- `open`、`close`、`total_turnover` 缺失率不能超过配置阈值。
- `open`、`close` 不得大面积为 0 或负数。
- `total_turnover` 不得大面积为负数。
- 沪深 300 benchmark 数据必须存在。
- parquet 写入后重新读取，确认 shape、index、columns 与 manifest 一致。

校验失败处理：

- 不生成当日信号。
- 不覆盖旧 parquet。
- 写入 `job_runs` 失败日志。
- 触发告警或人工检查。

## 4. Vectorbt Parameter Search

新增 `parameter_search` 任务。

### 4.1 Search Objective

vectorbt 负责研究和寻参，不直接负责对客展示净值。

可搜索参数：

- `window`
- `quantiles`
- `target_quantile`
- `signal_lag`
- `min_names`
- 交易费率
- 滑点
- 后续可扩展为换手率版本、行业中性化版本、市值中性化版本

### 4.2 Candidate Output

寻参结果写入候选参数表 `strategy_param_candidates`，不直接覆盖生产参数。

候选结果至少包含：

- `strategy_id`
- `candidate_id`
- 参数 JSON
- 回测开始日期
- 回测结束日期
- 样本内区间
- 样本外区间
- 总收益
- 年化收益
- 超额收益
- 夏普
- 最大回撤
- Calmar
- 平均持仓数量
- 平均换手率
- 生成时间

### 4.3 Production Parameter Release

生产参数采用“定期自动发布”：

- 建议默认月度发布。
- 每月第一个交易日前，系统根据上一周期候选参数自动选择生产版本。
- 新参数生成新的 `param_version`。
- `effective_from` 设置为下一个交易日。
- `effective_to` 在下一次参数切换时补齐。

自动发布需要满足风控条件：

- 最大回撤不能超过阈值。
- 平均持仓数量不能低于阈值。
- 平均换手率不能超过阈值。
- 样本外表现不能显著劣化。
- 参数不能过度集中在极端分位或极短窗口。

关键约束：

- 新参数只影响 `effective_from` 及之后的信号。
- 已发布历史买卖点不能被新参数覆盖。
- 如需修正历史错误，只能通过修订版本追加记录，不能原地改写。

## 5. Daily Frozen Signal Generation

新增 `daily_signal_generate` 任务。

### 5.1 Signal Calculation

读取截至目标交易日可用的 parquet 数据，并按目标交易日查找当前生效的生产参数。

沿用当前 ASP 核心逻辑：

1. 对每只股票计算 `total_turnover` 的 rolling 线性回归斜率。
2. 每个交易日横截面分成 `quantiles` 组。
3. 选择 `target_quantile` 且 `slope > 0` 的股票。
4. 如果入选数量低于 `min_names`，当日不生成持仓或保持空仓。
5. 入选股票等权分配目标权重。
6. 默认 `signal_lag=1`，避免前视。

默认生产初始参数建议：

- `window=20`
- `quantiles=5`
- `target_quantile=3`
- `signal_lag=1`
- `min_names=30`
- `price_field=open`

### 5.2 Signal Outputs

每日生成三类结果：

- 目标持仓：
  - 股票代码
  - 股票名称
  - 目标权重
  - 参数版本
  - 数据版本
- 买卖点：
  - 买入
  - 卖出
  - 调仓
  - 上一日权重
  - 当日目标权重
  - 权重变化
- 诊断信息：
  - 入选股票数量
  - 当日换手率
  - 缺失率
  - 使用参数版本
  - 使用数据版本

### 5.3 Freeze Policy

信号冻结采用“每日落库冻结”。

MySQL 中需要约束：

- 生产展示表对 `(strategy_id, signal_date, symbol)` 做唯一约束。
- 参数版本表记录每个信号对应的 `param_version`。
- 数据 manifest 表记录每个信号对应的 `data_version`。

任务行为：

- 如果目标交易日信号不存在，则生成并写入。
- 如果目标交易日信号已经发布，则直接跳过。
- 默认不允许重算、覆盖或删除历史信号。
- 如遇数据错误，需要走修订流程，生成 `correction_version`。

## 6. RQ Backtest From Frozen Signals

新增 `rq_backtest_from_signals` 任务。

### 6.1 Backtest Input

米筐量化回测只读取冻结买卖点或冻结目标权重。

输入来源：

- MySQL `strategy_daily_positions`
- MySQL `strategy_trade_signals`
- 或由 MySQL 导出的 CSV 临时文件

禁止在米筐回测中重新计算因子，避免回测结果和对客买卖点不一致。

### 6.2 Backtest Output

回测输出：

- 策略每日净值
- 策略每日收益
- 沪深 300 benchmark 净值
- 沪深 300 benchmark 收益
- 超额净值
- 回撤
- 年化收益
- 夏普
- 最大回撤
- Calmar

benchmark 口径：

- 使用沪深 300 `000300.XSHG`。
- 策略净值和 benchmark 净值在同一开始日期归一为 1。
- 对客展示策略净值、benchmark 净值和超额净值。

### 6.3 Failure Handling

- 米筐回测失败时，当日净值不发布。
- 买卖点保留为“已生成未回测”。
- 写入 `job_runs` 失败日志。
- 下一次任务允许从失败日期继续补算净值。

## 7. MySQL Schema Plan

建议新增或整理以下表。

### 7.1 strategy_master

记录策略主信息：

- `strategy_id`
- `strategy_name`
- `display_name`
- `description`
- `status`
- `created_at`
- `updated_at`

### 7.2 strategy_param_versions

记录生产参数版本：

- `strategy_id`
- `param_version`
- `params_json`
- `effective_from`
- `effective_to`
- `release_status`
- `created_at`

### 7.3 strategy_param_candidates

记录 vectorbt 寻参候选结果：

- `strategy_id`
- `candidate_id`
- `params_json`
- `train_start`
- `train_end`
- `test_start`
- `test_end`
- `metrics_json`
- `created_at`

### 7.4 daily_data_manifest

记录每日数据文件和校验状态：

- `data_version`
- `trade_date`
- `field`
- `file_path`
- `file_hash`
- `row_count`
- `column_count`
- `missing_rate`
- `validation_status`
- `created_at`

### 7.5 strategy_daily_positions

记录每日冻结目标持仓：

- `strategy_id`
- `trade_date`
- `symbol`
- `symbol_name`
- `target_weight`
- `param_version`
- `data_version`
- `publish_status`
- `created_at`

### 7.6 strategy_trade_signals

记录每日买卖点：

- `strategy_id`
- `trade_date`
- `symbol`
- `symbol_name`
- `signal_type`
- `previous_weight`
- `target_weight`
- `weight_delta`
- `param_version`
- `data_version`
- `publish_status`
- `created_at`

### 7.7 strategy_nav

记录策略和 benchmark 净值：

- `strategy_id`
- `trade_date`
- `strategy_nav`
- `strategy_return`
- `benchmark_nav`
- `benchmark_return`
- `excess_nav`
- `drawdown`
- `backtest_version`
- `created_at`

### 7.8 strategy_daily_diagnostics

记录每日策略诊断：

- `strategy_id`
- `trade_date`
- `selected_count`
- `target_weight_turnover`
- `missing_rate`
- `param_version`
- `data_version`
- `diagnostics_json`
- `created_at`

### 7.9 job_runs

记录任务运行日志：

- `job_id`
- `job_name`
- `trade_date`
- `started_at`
- `finished_at`
- `status`
- `input_version`
- `output_version`
- `error_message`

## 8. Scheduling Plan

### 8.1 Daily Flow

建议每日收盘后运行：

1. 判断当日是否为交易日。
2. 拉取米筐行情和沪深 300 数据。
3. 执行数据校验。
4. 校验通过后保存 parquet 和 manifest。
5. 读取当前生产参数。
6. 生成当日冻结目标持仓和买卖点。
7. 米筐回测读取冻结信号，更新策略净值和 benchmark 净值。
8. 写入 MySQL。
9. 生成运行报告。

### 8.2 Monthly Flow

建议每月第一个交易日前运行：

1. vectorbt 对最近历史区间做寻参。
2. 生成候选参数。
3. 根据风控规则筛选候选参数。
4. 自动发布下一周期生产参数。
5. 新参数从 `effective_from` 开始生效。

### 8.3 Rerun Policy

支持按 `trade_date` 重跑任务，但默认规则如下：

- 数据任务可以补拉缺失日期。
- 信号任务不覆盖已发布日期。
- 回测任务可以补算缺失净值。
- 参数发布任务不能修改已经生效过的历史参数区间，只能新增版本或追加修订。

## 9. Test Plan

### 9.1 Data Validation Tests

- 缺少行情字段时任务失败。
- 沪深 300 数据缺失时任务失败。
- 股票数量低于阈值时任务失败。
- parquet 写入后可重新读取。
- manifest 中 hash、shape、字段与 parquet 一致。

### 9.2 Signal Freeze Tests

- 同一交易日重复运行不改变历史买卖点。
- 参数版本变更后，只影响 `effective_from` 之后的信号。
- 新增未来日期信号时，过去日期记录完全不变。
- 已发布信号不允许被普通任务覆盖。

### 9.3 Strategy Logic Tests

- Q3 且 `slope > 0` 的筛选结果与当前脚本一致。
- `signal_lag=1` 生效。
- `min_names` 不足时不生成持仓。
- 等权权重合计为 1，空仓日期权重合计为 0。

### 9.4 Backtest Tests

- 米筐回测只读取冻结信号。
- benchmark 使用沪深 300。
- 策略净值、benchmark 净值、超额净值均能写入 MySQL。
- 重跑回测不会改变冻结买卖点。

### 9.5 End-to-End Acceptance

指定一个历史交易日，从拉数、校验、信号、回测、MySQL 落库完整跑通。

验收标准：

- 数据 manifest 状态为通过。
- 当日信号成功冻结。
- 米筐回测成功输出净值。
- MySQL 中买卖点、持仓、净值、benchmark 均可查询。
- 重跑后历史买卖点 hash 完全一致。

## 10. Assumptions

- 信号冻结采用“每日落库冻结”：历史买卖点发布后不可被寻参覆盖。
- vectorbt 寻参结果采用“定期自动发布”：建议默认月度发布新参数版本。
- 米筐回测定位为“展示级独立回测”：对客净值以米筐读取冻结信号后的结果为准。
- 生产策略初始版本沿用当前 ASP 逻辑：`total_turnover` 斜率、5 分位、Q3、`slope > 0`、等权。
- 后续如果要升级到换手率、行业中性化、市值中性化，应作为新 `strategy_id` 或新主版本发布，避免污染当前历史展示。
