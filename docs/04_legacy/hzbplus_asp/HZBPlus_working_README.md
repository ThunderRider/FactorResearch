# HZBPlus ASP 成交额斜率策略

本文档是本项目的策略说明、生产运行手册和故障恢复手册。

项目分为两个独立阶段：

1. runner_asp.py：下载行情，计算成交额斜率，滚动选择最优参数，生成每日信号。
2. runner_nav.py：读取本地信号，对每只股票分别运行一次 RQAlpha，生成每日单位净值。

正常生产环境应依次运行这两个脚本。ASP 阶段成功后，NAV 阶段才可以开始。

---

## 1. 最重要的日期定义

trade_signal_history.csv 中的日期是信号产生日期，不是成交日期。

假设：

- 2026-08-17 收盘后，根据当日成交额计算出“买入”。
- CSV 在 2026-08-17 这一行记录“买入”。
- RQAlpha 在下一个实际交易日的日线收盘价执行买入。

例如：

| 日期 | CSV 信号 | RQAlpha 行为 |
|---|---|---|
| 2026-08-17 | 买入 | 只缓存信号，不在当天交易 |
| 2026-08-18 | 持有 | 先执行 8 月 17 日的买入，再缓存 8 月 18 日的持有 |
| 2026-08-19 | 卖出 | 先处理 8 月 18 日的持有，再缓存 8 月 19 日的卖出 |
| 2026-08-20 | 空仓 | 先执行 8 月 19 日的卖出 |

VectorBT 参数评分也使用后移一个交易日的执行矩阵，因此默认 close 价格下，VectorBT 和 RQAlpha 都按照“信号产生后，下一个交易日收盘执行”计算。

---

## 2. 项目文件与职责

~~~text
HZBPlus_working/
├── config.yaml
│   └── RQData 和 MySQL 配置
│
├── asp_logging.py
│   └── 控制台日志、文件日志、日志轮转、多进程日志队列、敏感参数脱敏
│
├── asp_data.py
│   └── RQData 登录、股票池、行情下载、数据格式标准化、数据质量检查
│
├── asp_factor.py
│   └── 成交额线性回归斜率、多参数窗口信号
│
├── asp_strategy.py
│   └── VectorBT 回测、滚动参数评分、最优参数选择、最终信号
│
├── rqalpha_backtest.py
│   └── 每只股票一个独立 RQAlpha 账户，按前一日信号计算 NAV
│
├── asp_mysql.py
│   └── MySQL 建表、每日 upsert、数据校验、备份和全量恢复
│
├── asp_output.py
│   └── 通用 CSV 和 Parquet 输出工具
│
├── runner_asp.py
│   └── 生产入口一：生成 trade_signal_history.csv
│
├── runner_nav.py
│   └── 生产入口二：生成 stock_nav_history.csv
│
├── runner.py
│   └── 兼容入口：一次运行 ASP 和 NAV，不建议作为日常生产入口
│
└── ASP_stk_rolling_bestpara_vbt.py
    └── 原始单文件版本，仅保留参考，不作为当前生产入口
~~~

依赖关系：

~~~text
runner_asp.py
    ├── asp_logging.py
    ├── asp_data.py
    ├── asp_factor.py
    ├── asp_strategy.py
    └── asp_mysql.py

runner_nav.py
    ├── asp_logging.py
    ├── rqalpha_backtest.py
    └── asp_mysql.py
~~~

---

## 3. 第一阶段：ASP 信号生成逻辑

### 3.1 读取参数并启动日志

runner_asp.py 首先读取命令行参数，然后创建日志：

~~~text
logs/asp.log
~~~

启动日志会记录：

- 开始日期和结束日期
- 参数窗口范围
- 回看天数
- worker 数量
- 是否启用 MySQL
- 输出目录
- 本次 run_id

密码、密钥、license、token 和 RQ URI 会自动脱敏。

### 3.2 获取股票池

asp_data.py 调用 RQData 获取中国普通 A 股，并筛选：

- 类型为 CS
- 当前 status 为 Active
- 上市日期早于 as-of-date 减 365 天

注意：

--as-of-date 当前只影响“上市满一年”的截止日期。

代码调用 all_instruments 时没有传历史日期，并且使用当前 Active 状态，因此历史回测会排除后来退市的股票，存在生存者偏差。

### 3.3 下载行情

每批默认下载 500 只股票，字段包括：

| 字段 | 含义 | 用途 |
|---|---|---|
| open | 开盘价 | 可选 VectorBT 评分价格 |
| close | 收盘价 | 默认 VectorBT 评分价格 |
| total_turnover | 成交额 | 计算 ASP 斜率因子 |

RQData 参数：

~~~text
frequency = 1d
adjust_type = pre
expect_df = True
~~~

当 RQData 返回 MultiIndex DataFrame 时，代码明确使用 data[field] 读取当前字段，不会固定取第 0 列。

所有字段最后统一为宽表：

~~~text
date        000001.XSHE  000002.XSHE  ...
2026-08-14       ...          ...
2026-08-17       ...          ...
~~~

### 3.4 数据校验

asp_data.py 会检查：

- DataFrame 是否为空
- 是否存在有效有限数值
- 负数比例是否异常
- open、close、total_turnover 是否有共同日期
- 三个字段是否有共同股票
- 有效值比例、最小值、平均值和中位数

这些统计写入 asp_run_meta_YYYYMMDD.json。

### 3.5 计算成交额斜率

默认参数窗口为 5 到 35 个交易日。

可以使用 `--periods 5,8,13,21` 只计算指定的四个窗口。列表会去重并升序排列，每个窗口必须是大于等于 2 的整数；显式列表优先于 `--period-start` 和 `--period-end`。未传 `--periods` 时，仍按起止窗口计算连续整数。日志和 JSON 中的 `periods` 记录实际计算列表，`period_start`、`period_end` 记录该列表的最小值和最大值。

例如将离散窗口测试结果写入独立目录（不写 MySQL）：

~~~bash
$PY runner_asp.py --periods 5,8,13,21 --results-dir results/window_test/discrete --log-dir results/window_test/discrete/logs
$PY runner_nav.py --results-dir results/window_test/discrete --log-dir results/window_test/discrete/logs
~~~

第一阶段成功后再运行第二阶段，两个阶段应使用相同的起止日期。合并入口 `runner.py` 同样接受 `--periods`，第二阶段 `runner_nav.py` 从信号 CSV 读取结果，无须传窗口参数。

对每只股票、每个窗口、每个交易日，用最近 N 天成交额做线性回归：

~~~text
成交额持续增加 -> 斜率为正
成交额持续减少 -> 斜率为负
~~~

信号规则：

| 昨日斜率 | 今日斜率 | 原始信号 |
|---|---|---|
| 小于 0 | 大于或等于 0 | 买入 |
| 大于 0 | 小于 0 | 卖出 |
| 其他情况 |  | 不产生新的切换信号 |

signal_lag 必须为 0，因为 CSV 日期必须保留为信号产生日期。

### 3.6 VectorBT 参数评分

每个参数窗口都建立一套独立回测。

时间处理：

~~~text
signal_entries     = 信号产生日期
execution_entries  = signal_entries.shift(1)
~~~

因此 8 月 17 日产生的信号，在 VectorBT 中使用 8 月 18 日的价格执行。

默认 VectorBT 参数：

| 参数 | 默认值 |
|---|---|
| 价格字段 | close |
| 初始资金 | 1,000,000 |
| fees | 0.000025 |
| slippage | 0 |
| size | 全部可用资金 |
| accumulate | False |
| frequency | 1D |

### 3.7 滚动选择最优参数

默认：

~~~text
lookback_bars = 252
min_lookback_bars = 252
~~~

评分过程：

1. 取每个窗口的每日收益率。
2. 将收益率转换为 log return。
3. 回看最近 252 个交易日并求和。
4. score 再 shift(1)，当天选参数时只使用前一日及更早的历史评分。
5. 对每只股票、每个交易日，选择评分最高的窗口。

前 252 个评分行不足时，best_window 为空，最终状态按空仓处理。

### 3.8 生成最终四种信号

每个参数窗口都有自己的持仓状态。程序先选择当天最优窗口，再取该窗口当天的状态。

最后比较“昨天最终状态”和“今天最终状态”：

| 昨日状态 | 今日状态 | CSV 信号 | target_position |
|---|---|---|---|
| 空仓 0 | 持仓 1 | 买入 | 1 |
| 持仓 1 | 空仓 0 | 卖出 | 0 |
| 持仓 1 | 持仓 1 | 持有 | 1 |
| 空仓 0 | 空仓 0 | 空仓 | 0 |

参数窗口发生切换时，即使单个窗口当天没有发生斜率穿越，最终选择状态的变化仍可能生成买入或卖出。

### 3.9 第一阶段输出

默认目录：

~~~text
results/rolling_bestpara_vbt/
~~~

输出文件：

| 文件 | 内容 |
|---|---|
| trade_signal_history.csv | 全回测区间、全部股票、每日四种信号 |
| asp_run_meta_YYYYMMDD.json | 参数、数据统计、最新诊断、最优窗口统计、日志位置 |

trade_signal_history.csv 每次运行都会重新计算并覆盖为完整历史，不是每天新建一个 CSV。

如果启用 --mysql，只把 CSV 最后一行 upsert 到 trade_signals。

---

## 4. 第二阶段：RQAlpha 单股票 NAV 回测

### 4.1 输入

runner_nav.py 读取：

~~~text
results/rolling_bestpara_vbt/trade_signal_history.csv
~~~

它不需要 close_price.csv，也不会再次连接 RQData。

RQAlpha 使用本地 bundle：

~~~text
~/.rqalpha-plus/bundle
~~~

### 4.2 每只股票一个独立账户

不是把 5000 只股票放进一个组合。

实际结构：

~~~text
000001.XSHE -> 一个独立 RQAlpha 账户
000002.XSHE -> 一个独立 RQAlpha 账户
000004.XSHE -> 一个独立 RQAlpha 账户
...
~~~

每只股票：

- 初始资金 1,000,000
- 账户中只允许这一只股票
- frequency 为 1d
- 目标持仓比例为 90%
- 结果为该股票自己的单位净值

### 4.3 次日执行状态机

每天 handle_bar 按以下顺序执行：

1. 读取 pending_signal，也就是上一交易日缓存的信号。
2. 根据 pending_signal 判断目标持仓。
3. 生成订单。
4. 再读取当前日期信号，保存为新的 pending_signal。

目标状态：

| 信号 | 当前空仓 | 当前持仓 |
|---|---|---|
| 买入 | 买到约 90% 仓位 | 不重复买入 |
| 持有 | 买到约 90% 仓位 | 继续持有，不每日调仓 |
| 卖出 | 不操作 | 清仓 |
| 空仓 | 不操作 | 清仓 |

将“持有”视为目标持仓有两个作用：

- 从中途日期开始回测时，起始日前最后一行是“持有”也能恢复仓位。
- 买入日遇到停牌导致订单失败时，后续“持有”可以继续尝试建仓。

将“空仓”视为目标空仓，可以在卖出失败后继续尝试清仓。

### 4.4 中途开始回测

假设信号文件包含：

| 日期 | 信号 |
|---|---|
| 2026-08-14 | 买入 |
| 2026-08-17 | 持有 |

如果 RQAlpha 的 start-date 是 2026-08-17：

1. 初始化时找到严格早于 8 月 17 日的最后一条信号。
2. 将 8 月 14 日“买入”放入 pending_signal。
3. 8 月 17 日第一根 bar 执行买入。
4. 8 月 17 日自己的“持有”留到下一交易日处理。

如果起始日前最后一条是“持有”，新账户也会在第一天建立目标仓位。

### 4.5 RQAlpha 撮合和费用

当前配置：

| 参数 | 值 |
|---|---|
| frequency | 1d |
| matching_type | current_bar |
| 成交价格 | 当前日线收盘价 |
| 目标仓位 | 90% |
| slippage | 0 |
| volume_limit | False |
| price_limit | False |
| liquidity_limit | False |
| inactive_limit | False |
| 最低佣金 | 5 元 |
| stock_commission_multiplier | 0.5 |
| tax_multiplier | 1 |

停牌是交易所状态，即使策略信号来自有历史数据的日期，下一交易日执行时仍可能停牌。订单会失败，但后续“持有”或“空仓”状态会继续尝试。

### 4.6 第二阶段输出

| 文件 | 内容 |
|---|---|
| stock_nav_history.csv | 每行一个日期，每列一只股票，单元格是独立账户单位净值 |
| nav_meta_YYYYMMDD.json | 起止日期、成功股票数、NAV 大小、run_id、日志位置 |

如果启用 --mysql，只把 NAV 最后一行的非空数据 upsert 到 stock_daily_nav。

---

## 5. MySQL 表结构和前端使用

### 5.1 trade_signals

主要字段：

| 字段 | 含义 |
|---|---|
| stock_code | 股票代码 |
| trade_date | 信号产生日期 |
| signal | 买入、卖出、持有、空仓 |
| target_position | 1 表示目标持仓，0 表示目标空仓 |
| run_stamp | 运行批次 |
| created_at | 首次创建时间 |
| updated_at | 最后更新时间 |

唯一键：

~~~text
(stock_code, trade_date)
~~~

同一天重复运行会更新，不会插入重复记录。

前端查询最新信号：

~~~sql
SELECT stock_code, trade_date, signal, target_position
FROM trade_signals
WHERE stock_code = '000001.XSHE'
ORDER BY trade_date DESC
LIMIT 1;
~~~

查询 K 线买卖标签：

~~~sql
SELECT trade_date, signal
FROM trade_signals
WHERE stock_code = '000001.XSHE'
  AND signal IN ('买入', '卖出')
ORDER BY trade_date;
~~~

### 5.2 stock_daily_nav

主要字段：

| 字段 | 含义 |
|---|---|
| stock_code | 股票代码 |
| trade_date | 净值日期 |
| nav | 单位净值 |
| run_stamp | 运行批次 |
| created_at | 创建时间 |

NAV 表不保存 position。目标仓位只保存在 trade_signals.target_position。

前端查询净值曲线：

~~~sql
SELECT trade_date, nav
FROM stock_daily_nav
WHERE stock_code = '000001.XSHE'
ORDER BY trade_date;
~~~

### 5.3 备份表

全量恢复前会自动创建并覆盖：

~~~text
trade_signals_backup
stock_daily_nav_backup
~~~

备份保存的是“本次全量恢复开始前”的正式表数据，不是持续实时备份。

---

## 6. 环境准备

### 6.1 进入项目

~~~bash
cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working
~~~

生产命令建议使用绝对 Python 路径，避免 cron、nohup 和普通终端使用了不同环境：

~~~bash
PY=/home/pl_ubuntu/miniforge3/envs/rq/bin/python
$PY --version
~~~

### 6.2 检查主要依赖

~~~bash
$PY -c "import pandas, numpy, numba, vectorbt, rqalpha, rqdatac, pymysql, yaml; print('dependencies OK')"
~~~

### 6.3 检查 RQAlpha bundle

~~~bash
ls -lh /home/pl_ubuntu/.rqalpha-plus/bundle
test -f /home/pl_ubuntu/.rqalpha-plus/bundle/instruments.pk && echo "bundle OK"
~~~

代码默认 bundle 路径：

~~~text
~/.rqalpha-plus/bundle
~~~

不是旧路径：

~~~text
~/.rqalpha/bundle
~~~

### 6.4 配置 config.yaml

RQData：

~~~yaml
rq_api:
  license: '替换为真实license'
  key: '替换为真实key'
~~~

需要 MySQL 时：

~~~yaml
database:
  db_host: '127.0.0.1'
  db_port: 3306
  db_name: 'quant'
  db_username: 'quant_writer'
  db_password: '替换为真实密码'
~~~

也兼容：

~~~yaml
mysql:
  host: '127.0.0.1'
  port: 3306
  database: 'quant'
  user: 'quant_writer'
  password: '替换为真实密码'
~~~

保护配置文件：

~~~bash
chmod 600 config.yaml
~~~

不要把带有真实密码和密钥的 config.yaml 提交到 Git。

---

## 7. 正常调用方式

以下命令均假设已经执行：

~~~bash
cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working
PY=/home/pl_ubuntu/miniforge3/envs/rq/bin/python
START_DATE=2024-01-01
END_DATE=$(date +%F)
~~~

策略应在交易日收盘、RQData 当日数据可用后运行。如果当天数据还没有更新，应把 END_DATE 改为最后一个已经确认有完整行情的交易日。

### 7.1 不写 MySQL

第一阶段：

~~~bash
$PY runner_asp.py \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --as-of-date $END_DATE \
  --workers 1
~~~


第一阶段成功后运行第二阶段：

~~~bash
$PY runner_nav.py \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --workers 1 \
  --batch-size 100
~~~

### 7.2 写入 MySQL

config.yaml 配置完成后：

~~~bash
$PY runner_asp.py \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --as-of-date $END_DATE \
  --workers 1 \
  --mysql
~~~

然后：

~~~bash
$PY runner_nav.py \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --workers 1 \
  --batch-size 100 \
  --mysql
~~~

没有 --mysql 时，程序不会连接 MySQL。

### 7.3 多进程

ASP 和 NAV 的 worker 参数彼此独立：

~~~bash
$PY runner_asp.py --workers 4 --mysql
$PY runner_nav.py --workers 4 --batch-size 100 --mysql
~~~

含义：

- runner_asp.py 的 --workers 控制 VectorBT 股票批次并行。
- runner_nav.py 的 --workers 控制 RQAlpha 股票批次并行。
- --batch-size 100 表示每个 RQAlpha worker 顺序处理一批股票，不表示创建 100 个进程。

建议先用 workers=1 验证完整流程，再根据服务器 CPU 和内存逐步增加到 2 或 4。

### 7.4 指定日志

~~~bash
$PY runner_asp.py \
  --log-dir logs \
  --log-level INFO \
  --log-retention-days 30
~~~

默认日志：

~~~text
logs/asp.log
logs/nav.log
logs/all.log
~~~

午夜自动轮转，默认保留 30 份。

### 7.5 兼容入口

一次运行 ASP 和 NAV：

~~~bash
$PY runner.py \
  --workers 2 \
  --nav-workers 2 \
  --mysql
~~~

runner.py 仍可使用，但生产上推荐拆分运行。拆分后可以单独重跑失败阶段，不必重复计算已经成功的部分。

---

## 8. 生产后台运行

### 8.1 顺序后台运行两阶段

~~~bash
mkdir -p logs run

nohup setsid bash -c '
set -e
cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working
PY=/home/pl_ubuntu/miniforge3/envs/rq/bin/python
START_DATE=2024-01-01
END_DATE=$(date +%F)

$PY runner_asp.py \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --as-of-date $END_DATE \
  --workers 4 \
  --mysql

$PY runner_nav.py \
  --start-date $START_DATE \
  --end-date $END_DATE \
  --workers 4 \
  --batch-size 100 \
  --mysql
' > logs/daily_launcher.log 2>&1 &

echo $! > run/daily.pid
~~~

因为 shell 使用 set -e：

- ASP 成功后才会运行 NAV。
- ASP 返回非零时，NAV 不会开始。
- NAV 返回非零时，后台任务整体失败。

### 8.2 查看后台进程

~~~bash
PID=$(cat run/daily.pid)
ps -o pid,ppid,pgid,stat,etime,cmd -p $PID
~~~

查看相关 Python 进程：

~~~bash
ps -ef | grep -E "runner_asp.py|runner_nav.py" | grep -v grep
~~~

### 8.3 查看实时日志

~~~bash
tail -f logs/asp.log
tail -f logs/nav.log
tail -f logs/daily_launcher.log
~~~

只看异常：

~~~bash
grep -E "ERROR|CRITICAL|异常停止|回测失败" logs/asp.log | tail -100
grep -E "ERROR|CRITICAL|异常停止|回测失败" logs/nav.log | tail -100
~~~

### 8.4 正常停止后台任务

后台命令使用 setsid 创建独立进程组。停止时发送 TERM：

~~~bash
PID=$(cat run/daily.pid)
kill -- -$PID
~~~

确认退出：

~~~bash
ps -ef | grep -E "runner_asp.py|runner_nav.py" | grep -v grep
~~~

只有在 TERM 长时间无效、确认进程无法正常退出时，才最后使用：

~~~bash
kill -9 -- -$PID
~~~

强制停止可能发生在 CSV 或数据库写入中间，因此下一次运行前必须执行第 10 节的数据检查。

### 8.5 使用 crontab 每个交易日自动运行

可以把下面内容保存为项目目录下的 run_daily.sh。脚本使用当天日期作为行情结束日，ASP 成功后才会继续执行 NAV：

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working

PY=/home/pl_ubuntu/miniforge3/envs/rq/bin/python
RUN_DATE="${1:-$(date +%F)}"

$PY runner_asp.py \
  --start-date 2024-01-01 \
  --end-date "$RUN_DATE" \
  --as-of-date "$RUN_DATE" \
  --workers 4 \
  --mysql

$PY runner_nav.py \
  --start-date 2024-01-01 \
  --end-date "$RUN_DATE" \
  --workers 4 \
  --batch-size 100 \
  --mysql
~~~

首次部署时执行：

~~~bash
cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working
chmod +x run_daily.sh
mkdir -p logs run
~~~

编辑定时任务：

~~~bash
crontab -e
~~~

例如每周一到周五 18:30 启动：

~~~cron
30 18 * * 1-5 /usr/bin/flock -n /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working/run/daily.lock /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working/run_daily.sh >> /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working/logs/daily_cron.log 2>&1
~~~

这里的 flock 使用非阻塞锁。同一轮任务仍在运行时，下一次定时启动会直接退出，避免两个进程同时覆盖 CSV 或写入 MySQL。crontab 只按星期判断，不知道 A 股节假日；节假日运行通常只会重算到最近一个交易日，因此仍要根据公司的交易日调度系统决定是否进一步限制。

---

## 9. 每日运行成功标准

以下检查命令默认在项目目录执行。每次打开新终端后先设置：

~~~bash
cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working
PY=/home/pl_ubuntu/miniforge3/envs/rq/bin/python
~~~

### 9.1 日志成功标记

ASP：

~~~bash
grep "程序正常结束" logs/asp.log | tail -1
grep "ASP信号任务完成" logs/asp.log | tail -1
~~~

NAV：

~~~bash
grep "程序正常结束" logs/nav.log | tail -1
grep "RQAlpha NAV任务完成" logs/nav.log | tail -1
~~~

### 9.2 检查文件更新时间

~~~bash
ls -lh \
  results/rolling_bestpara_vbt/trade_signal_history.csv \
  results/rolling_bestpara_vbt/stock_nav_history.csv \
  results/rolling_bestpara_vbt/*meta_*.json
~~~

### 9.3 检查 CSV 最后日期和大小

~~~bash
$PY -c "
import pandas as pd
p='results/rolling_bestpara_vbt/trade_signal_history.csv'
d=pd.read_csv(p, index_col=0, encoding='utf-8-sig')
print('signal shape=', d.shape)
print('signal last_date=', d.index[-1])
print('signal last counts=', d.iloc[-1].value_counts().to_dict())
"
~~~

~~~bash
$PY -c "
import pandas as pd
p='results/rolling_bestpara_vbt/stock_nav_history.csv'
d=pd.read_csv(p, index_col=0, encoding='utf-8-sig')
print('nav shape=', d.shape)
print('nav last_date=', d.index[-1])
print('nav non_null=', int(d.iloc[-1].notna().sum()))
"
~~~

### 9.4 检查 MySQL 最新日期

~~~sql
SELECT MAX(trade_date) AS latest_signal_date, COUNT(*) AS total_rows
FROM trade_signals;

SELECT MAX(trade_date) AS latest_nav_date, COUNT(*) AS total_rows
FROM stock_daily_nav;
~~~

检查某一天股票数：

~~~sql
SELECT trade_date, COUNT(*) AS stock_count
FROM trade_signals
WHERE trade_date = '2026-08-17'
GROUP BY trade_date;

SELECT trade_date, COUNT(*) AS stock_count
FROM stock_daily_nav
WHERE trade_date = '2026-08-17'
GROUP BY trade_date;
~~~

---

## 10. 中断、重启和恢复场景

项目目前没有批次级 checkpoint。进程停止后不能从某个 ASP batch 或某只 RQAlpha 股票继续，只能重跑对应阶段。

以下恢复命令也需要先进入项目目录并指定 rq 环境的 Python：

~~~bash
cd /home/pl_ubuntu/my_quantproject/hzbplus/HZBPlus_working
PY=/home/pl_ubuntu/miniforge3/envs/rq/bin/python
~~~

### 10.1 ASP 阶段中断

判断：

~~~bash
tail -100 logs/asp.log
grep "ASP信号任务完成" logs/asp.log | tail -1
~~~

如果本次 run_id 没有“ASP信号任务完成”，重新运行第一阶段：

~~~bash
$PY runner_asp.py \
  --start-date 2024-01-01 \
  --end-date $(date +%F) \
  --as-of-date $(date +%F) \
  --workers 4 \
  --mysql
~~~

说明：

- ASP 会重新计算完整历史。
- trade_signal_history.csv 会重新覆盖。
- MySQL 使用唯一键 upsert，同一天重复运行不会生成重复记录。

第一阶段成功后再运行 runner_nav.py。

### 10.2 ASP 已成功，NAV 阶段中断

如果 trade_signal_history.csv 已完成，不需要重新跑 ASP。

直接重跑：

~~~bash
$PY runner_nav.py \
  --start-date 2024-01-01 \
  --end-date $(date +%F) \
  --workers 4 \
  --batch-size 100 \
  --mysql
~~~

NAV 会从完整信号 CSV 重新回测全部股票并覆盖 stock_nav_history.csv。

### 10.3 服务器重启

服务器启动后先确认旧进程不存在：

~~~bash
ps -ef | grep -E "runner_asp.py|runner_nav.py" | grep -v grep
~~~

然后检查日志和文件：

~~~bash
tail -100 logs/asp.log
tail -100 logs/nav.log
ls -lh results/rolling_bestpara_vbt/
~~~

决策：

| 状态 | 操作 |
|---|---|
| ASP 未完成 | 重新运行 ASP，然后运行 NAV |
| ASP 完成，NAV 未完成 | 只重新运行 NAV |
| 两阶段均完成，MySQL 最新日期正确 | 不需要重跑 |
| CSV 完整，但 MySQL 缺数据 | 执行 MySQL 全量恢复 |

### 10.4 RQData 暂时不可用

日志通常会出现登录失败、连接失败或行情批次为空。

处理：

1. 不删除旧 CSV。
2. 不运行 NAV，因为没有新的完整信号。
3. RQData 恢复后重新运行 runner_asp.py。
4. ASP 成功后再运行 runner_nav.py。

### 10.5 MySQL 暂时不可用，但本地 CSV 已成功

ASP 和 NAV 都是先写本地 CSV，再写 MySQL。

如果日志显示 CSV 已写完，但 MySQL 连接或写入失败，本地文件可以作为恢复来源。

MySQL 恢复后执行：

~~~bash
$PY runner_asp.py \
  --results-dir results/rolling_bestpara_vbt \
  --mysql \
  --mysql-full-reload
~~~

这个命令不会重新下载 RQData，也不会重新计算策略。它会：

1. 从本地完整 CSV 读取数据。
2. 将正式表复制到固定备份表。
3. 使用 DELETE 清空正式表。
4. 从 CSV 分批重建 trade_signals。
5. 如果 stock_nav_history.csv 存在，再重建 stock_daily_nav。

### 10.6 MySQL 全量恢复中断

当前全量恢复不是单一原子事务：

- 删除正式表后会提交。
- 每 5000 行提交一次。
- 中途宕机会留下部分正式数据。
- 再次执行全量恢复会覆盖固定 backup 表，因此不要在未判断备份内容前盲目重跑。

先检查：

~~~sql
SELECT COUNT(*) FROM trade_signals;
SELECT COUNT(*) FROM trade_signals_backup;
SELECT COUNT(*) FROM stock_daily_nav;
SELECT COUNT(*) FROM stock_daily_nav_backup;
~~~

如果需要从备份恢复信号表：

~~~sql
START TRANSACTION;

DELETE FROM trade_signals;

INSERT INTO trade_signals (
    id, stock_code, trade_date, signal, target_position,
    run_stamp, created_at, updated_at
)
SELECT
    id, stock_code, trade_date, signal, target_position,
    run_stamp, created_at, updated_at
FROM trade_signals_backup;

COMMIT;
~~~

恢复 NAV 表：

~~~sql
START TRANSACTION;

DELETE FROM stock_daily_nav;

INSERT INTO stock_daily_nav (
    id, stock_code, trade_date, nav, run_stamp, created_at
)
SELECT
    id, stock_code, trade_date, nav, run_stamp, created_at
FROM stock_daily_nav_backup;

COMMIT;
~~~

恢复完成并核对数量后，才能重新执行 --mysql-full-reload。

正式生产库执行上述 SQL 前，应再做数据库级快照或 mysqldump。

### 10.7 CSV 可能在写入时被强制停止

先尝试读取：

~~~bash
$PY -c "
import pandas as pd
for p in [
    'results/rolling_bestpara_vbt/trade_signal_history.csv',
    'results/rolling_bestpara_vbt/stock_nav_history.csv',
]:
    try:
        d=pd.read_csv(p, index_col=0, encoding='utf-8-sig')
        print(p, 'OK', d.shape, d.index[-1])
    except Exception as e:
        print(p, 'FAILED', type(e).__name__, e)
"
~~~

如果 trade_signal_history.csv 损坏，重跑 runner_asp.py。

如果只有 stock_nav_history.csv 损坏，而信号 CSV 完整，只重跑 runner_nav.py。

---

## 11. 日志说明

### 11.1 日志格式

~~~text
时间 | 级别 | 进程名 | 模块名 | run_id | 内容
~~~

例如：

~~~text
2026-08-17 18:30:21 | INFO | MainProcess | runner_asp | run_id=... | ASP信号任务开始
2026-08-17 18:42:09 | INFO | SpawnProcess-2 | asp_strategy | run_id=... | VectorBT批次完成
2026-08-17 19:03:14 | ERROR | SpawnProcess-1 | rqalpha_backtest | run_id=... | 单股RQAlpha回测失败
~~~

### 11.2 日志级别

| 级别 | 含义 |
|---|---|
| DEBUG | 矩阵大小、因子窗口等详细调试信息 |
| INFO | 正常步骤、批次进度、文件和数据库写入 |
| WARNING | 单股失败、部分失败、需要注意但任务可继续 |
| ERROR | 当前操作失败、无 NAV、异常堆栈 |
| CRITICAL | 预留给无法继续的系统级故障 |

### 11.3 多进程日志

worker 不直接写文件。

~~~text
worker -> QueueHandler -> 主进程 QueueListener -> 控制台和日志文件
~~~

这样 workers=1 和 workers=4 使用相同日志格式，不会因为多个进程同时轮转日志而互相覆盖。

### 11.4 RQAlpha 自己的日志

RQAlpha 框架可能仍向终端输出 user_system_log。项目自己的单股异常会另外写入 nav.log，并带股票代码、batch 和 Python 堆栈。

---

## 12. 常用参数

### 12.1 runner_asp.py

| 参数 | 默认值 | 含义 |
|---|---|---|
| --results-dir | results/rolling_bestpara_vbt | 输出目录 |
| --start-date | 2024-01-01 | 行情和策略开始日期 |
| --end-date | 今天 | 行情和策略结束日期 |
| --as-of-date | 今天 | 上市满一年筛选参考日期 |
| --period-start | 5 | 最短斜率窗口 |
| --period-end | 35 | 最长斜率窗口 |
| --periods | 未设置 | 逗号分隔的候选窗口，例如 5,8,13,21；去重排序，优先于起止窗口 |
| --lookback-bars | 252 | 参数评分回看交易日 |
| --min-lookback-bars | 252 | 最少评分交易日 |
| --batch-size | 300 | ASP 每批股票数 |
| --workers | 1 | ASP worker 数 |
| --price-field | close | VectorBT 评分价格 |
| --init-cash | 1000000 | VectorBT 初始资金 |
| --fees | 0.000025 | VectorBT 固定费率 |
| --slippage | 0 | VectorBT 滑点 |
| --signal-lag | 0 | 必须为 0 |
| --chunk-size | 500 | RQData 每批股票数 |
| --config | config.yaml | 配置文件 |
| --mysql | 关闭 | 启用 MySQL |
| --mysql-full-reload | 关闭 | 从本地 CSV 重建 MySQL |
| --log-dir | logs | 日志目录 |
| --log-level | INFO | 日志级别 |
| --log-retention-days | 30 | 轮转日志保留份数 |

### 12.2 runner_nav.py

| 参数 | 默认值 | 含义 |
|---|---|---|
| --results-dir | results/rolling_bestpara_vbt | 输出目录 |
| --signal-csv | trade_signal_history.csv | 信号文件名 |
| --start-date | 2024-01-01 | RQAlpha 开始日期 |
| --end-date | 今天 | RQAlpha 结束日期 |
| --workers | 1 | RQAlpha worker 数 |
| --batch-size | 100 | 每个批次股票数 |
| --config | config.yaml | MySQL 配置文件 |
| --mysql | 关闭 | 启用 MySQL |
| --log-dir | logs | 日志目录 |
| --log-level | INFO | 日志级别 |
| --log-retention-days | 30 | 轮转日志保留份数 |

完整帮助：

~~~bash
$PY runner_asp.py --help
$PY runner_nav.py --help
$PY runner.py --help
~~~

---

## 13. 当前已知限制

这些问题不会被日志系统自动修复，生产使用时需要明确知道。

### 13.1 当前 Active 股票池产生生存者偏差

历史回测使用当前 Active 股票，退市股票可能被排除。严格历史研究需要按历史日期动态构建股票池。

### 13.2 VectorBT 和 RQAlpha 成本模型不同

VectorBT 使用固定 fees；RQAlpha 使用最低佣金、佣金倍率和印花税。两者虽然默认在次日收盘时间上对齐，但收益和参数排名不保证完全一致。

### 13.3 open 价格模式与 RQAlpha 不完全对齐

runner_asp.py 允许 --price-field open，但 RQAlpha 1d current_bar 使用收盘价。生产默认应保持 close。

### 13.4 单股失败不会自动终止全部 NAV

RQAlpha 单只股票失败时会记录 ERROR，并继续其他股票。最终日志会汇总成功和失败数量。

当前 runner_nav.py 仍可能用成功股票覆盖 NAV CSV，因此生产完成后必须检查 nav_success_count 和失败日志。

### 13.5 NAV 日期索引使用完整信号索引

runner_nav.py 当前将结果重新对齐到整份信号 CSV 日期。中途起跑可能在起始日前产生空值行，结束日期早于 CSV 最后日期时尾部也可能出现空值。

### 13.6 MySQL 全量恢复不是原子操作

DELETE 和分批导入会多次提交。中断时要按第 10.6 节处理。

### 13.7 没有断点续跑

ASP batch 和 RQAlpha 股票批次没有持久化 checkpoint。进程重启后只能重跑整个失败阶段。

### 13.8 CSV 不是原子替换

程序直接写目标 CSV，没有先写临时文件再 rename。强制停止发生在写文件时可能损坏 CSV，必须按第 10.7 节检查。

---

## 14. 推荐的每日运维顺序

每天收盘且 RQData 数据更新后：

1. 检查磁盘、RQData 和 MySQL 是否可用。
2. 运行 runner_asp.py。
3. 确认 asp.log 出现“程序正常结束”。
4. 检查 trade_signal_history.csv 最后日期。
5. 运行 runner_nav.py。
6. 确认 nav.log 中的成功股票数和失败股票数。
7. 检查 stock_nav_history.csv 最后日期和非空股票数。
8. 检查 MySQL 两张表的 MAX(trade_date)。
9. 保留日志和当日 meta JSON。
10. 任何一步失败，按第 10 节只重跑需要的阶段。

生产上不要只看进程是否退出。必须同时检查日志成功标记、CSV 最后日期、NAV 成功股票数和 MySQL 最新日期。

