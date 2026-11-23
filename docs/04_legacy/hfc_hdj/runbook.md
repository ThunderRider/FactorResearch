:::title 慧点睛每日策略任务
:::title2 hdj_strategy_v02.py 上线实施与运维操作手册
:::subtitle 生产环境 · 变更实施 / 数据验证 / 回滚预案 / 日常运维

| 项目 | 内容 |
| --- | --- |
| 文档编号 | RDC-HDJ-OPS-2026-11-01 |
| 版本 | V1.0 |
| 适用系统 | “慧”系列 · 慧点睛（HDJ）每日策略任务 |
| 变更类型 | 脚本升级 + 数据库新增表 + 定时任务调整（不停机变更） |
| 上线对象 | hdj_strategy_v02.py（替换 hdj_strategy.py；原独立快照任务 hdj_cls_snapshot.py 一并下线） |
| 生产主机 | 10.32.108.62（主） / 10.32.108.61（备） |
| 数据库 | 小福牛生产 MySQL，库名 rdc-cloud |
| 编制 | 【待填：算法策略组】 |
| 审核 | 【待填：项目经理 / 生产运维】 |
| 执行 | 生产运维（钟声远） / 算法策略（雷朋、吴丁杰） |
| 编制日期 | 2026-11-09 |
| 文档状态 | □ 初稿　☑ 待评审　□ 评审通过　□ 已发布 |

:::toc

## 1 文档说明

### 1.1 编制目的

本手册面向生产运维与项目经理，给出慧点睛每日策略任务由“旧版双脚本模式”升级为“快照内置单脚本模式（hdj_strategy_v02.py）”的完整上线操作说明。内容覆盖变更内容、上线前准备、逐步操作命令与预期结果、数据验证、验收标准、回滚预案、风险清单，以及上线后的监控与日常运维要点。

运维人员按第 4 章的顺序执行、按第 5 章逐项验收，即可完成本次上线；任何一步与“预期结果”不一致时，转第 6 章回滚或按附录 B 处置。

### 1.2 适用对象

| 角色 | 在本手册中的职责 |
| --- | --- |
| 生产运维（执行人） | 代码上传、容器操作、定时任务调整、首次跑批、按检查单执行与记录 |
| 算法策略 / 研发（技术支持） | 脚本逻辑确认、报错定位、结果口径解释、跑批结果业务核对 |
| 项目经理 | 变更审批、提供生产配置与账号、协调 DBA、业务侧确认与验收签字 |
| DBA | 执行建表与加列 DDL、数据库备份与回滚数据恢复 |

### 1.3 使用方式与占位符约定

- 第 3 章为上线前准备，必须全部确认通过后，才可进入第 4 章。
- 第 4 章每一步均给出“操作命令 → 预期结果 → 异常处置”三段式说明。
- 文中以 `< >` 包裹的内容为占位符，执行前必须替换为实际值，并在 3.1 的环境参数登记表中登记留档。
- 文中命令默认在**宿主机**执行；标注“容器内”的命令需先 `docker exec -it <容器ID> /bin/bash` 进入容器后执行。
- 附录 D 为可打印的勾选式上线检查单，建议打印后在变更现场逐项勾选、签字。

### 1.4 参考文档

| 文档 | 用途 |
| --- | --- |
| hdj_strategy_v02.py | 本次上线的策略脚本（快照 + 计算 + 落库全流程） |
| hdj_main_strategy_daily.sh | 定时任务入口脚本（容器内执行策略） |
| create_hdj_cls_article_snapshot.sql | 新增快照表 hdj_cls_article_snapshot 的 DDL |
| testsql.sql | 建表 + 推荐表增加 type 列的可重复执行脚本 |
| config.yaml / logging.yaml / logconfig.py | 配置与日志定义 |
| 慧抢筹线上变更需求.docx（V1.0，2026-03-10） | 变更四步法流程模板（更新文件 → 新增表 → 定时任务 → 初始跑批） |
| 慧抢筹线上变更需求 20261103.docx / 慧抢筹线上变更需求20261103.pdf（V1.1，2026-11-03） | 变更文档结构与执行步骤模板；本手册第 4 章与之对齐并细化 |
| 测试反馈表-慧抢筹优化-20261103.pdf | 测试反馈表的格式与结论表述（总结论：全部通过），本手册第 5 章验收结论沿用同一格式 |
| 慧点睛上线以及运维文档.pdf | 生产服务器、网络端口、监控手段、告警阈值、干系人 |
| 慧点睛策略侧部署方案.pdf | 部署路径、docker 操作、crontab 时间点、时区要求 |
| 慧点睛应急演练文档.pdf | 容器异常、数据同步异常的应急处置脚本路径与切换流程 |

> 说明：本次上线对象为慧点睛（HDJ）。慧抢筹（WPQC）的两份变更需求与测试反馈表仅作为**流程模板、文档结构模板与测试结论格式**的参照，不改变慧点睛的库表、脚本与调度；慧抢筹的 strategy02.py 变更与本手册无关，切勿混用。

### 1.5 术语与缩写

| 术语 | 说明 |
| --- | --- |
| 财联社源表 | 财联社新闻主表 lian_v1_article，stocks 字段为逗号分隔的股票代码 |
| 快照表 | hdj_cls_article_snapshot，新闻-股票关系历史冻结表，本次新增 |
| 推荐表 | hdj_strategy_recom_stocks，对客展示的每日推荐股票表 |
| strategy_code | 策略标识；慧点睛固定为 2，慧抢筹为 1 |
| 米筐 / rqdatac | 行情与交易日历数据源，需 license + key 初始化 |
| 快照内置 | 快照转写与策略计算合并到同一个脚本、同一次调度中执行 |
| 幂等 | 重复执行不产生重复数据、不改变已有历史结果 |
| RDC-CLOUD | 小福牛生产 MySQL 的库名 |
| 容器 | “慧”系列 Docker 容器，宿主机 10.32.108.62（主）/ 10.32.108.61（备） |

## 2 变更概述

### 2.1 变更背景

慧点睛每日策略任务自 2026 年 3 月上线以来，按“财联社新闻 → 米筐行情 → 涨幅与成交额斜率筛选 → 写入推荐表”的链路每日 08:31 产出推荐股票。运行中暴露出以下问题，本次变更即针对这些问题：

| 序号 | 问题 | 具体现象 | 业务影响 |
| --- | --- | --- | --- |
| 1 | 财联社源表可被回溯修改 | 旧脚本每次直连 lian_v1_article 取数，财联社侧不定时 update / delete 源表数据 | 同一交易日不同时间重跑，历史新闻-股票关系会变化，推荐结果不可复现 |
| 2 | 双脚本、双定时任务 | 需先执行 hdj_cls_snapshot.py 转写快照，再执行 hdj_strategy.py 计算 | 两个失败点，任一失败都要人工介入，排障链路长 |
| 3 | 米筐初始化依赖交互终端 | 旧脚本调用 rqdatac.init() 不传凭据，依赖容器内已存在的登录会话 | 换机、重建容器、会话过期后任务直接失败，凭据无法移交 |
| 4 | 指标口径依赖当日日线 | 旧版先对指标 shift(1)，再按“行情日期 = 新闻交易日”合并 | 早盘执行时当日日线尚不存在，易出现当日指标缺失、当日推荐为空 |
| 5 | 缺少过程日志 | 旧脚本仅在关键节点打印，长任务期间无输出 | 无法判断任务是否卡死，不满足“早盘任务 ≤14 分钟”的过程监控要求 |

### 2.2 变更目标

1. 新闻-股票关系首次落库即冻结，后续策略只读快照表，保证结果可复现、可审计。
2. 快照转写与策略计算合并为一个脚本、一个定时任务，减少失败点与人工介入。
3. 米筐凭据改由 config.yaml 的 rq_api 节点提供，不依赖交互终端会话。
4. 指标口径调整为“上一交易日收盘行情指标 → 下一交易日推荐”，早盘即可产出当日推荐，不再等待当日日线。
5. 全流程输出进度日志（含百分比进度），便于观察耗时与定位卡点。

### 2.3 变更内容清单

| 序号 | 类型 | 对象 | 变更内容 | 是否必须 |
| --- | --- | --- | --- | --- |
| 1 | 脚本 | hdj_strategy_v02.py | 新增/覆盖：内置快照转写、指标计算、推荐落库全流程 | 必须 |
| 2 | 脚本 | hdj_main_strategy_daily.sh | 入口脚本指向 hdj_strategy_v02.py | 必须 |
| 3 | DDL | hdj_cls_article_snapshot | 新建快照表，唯一键 (id, stock_code) | 必须 |
| 4 | DDL | hdj_strategy_recom_stocks | 增加 type 列（新闻类型），并按新闻 ID 回填历史记录 | 必须 |
| 5 | 配置 | config.yaml | 增加 rq_api.license / rq_api.key；需要分库时增加 source_db_* / rdc_db_* | 必须 |
| 6 | 调度 | 宿主 crontab | 保持每日 08:31 单任务；若现网存在独立快照任务则下线 | 必须 |
| 7 | 文档 | 上线及运维文档 | 更新本手册与运维文档版本，登记新表与新日志关键字 | 建议 |

### 2.4 新旧版本差异对照

| 对比项 | 旧版（hdj_strategy.py + hdj_cls_snapshot.py） | 新版（hdj_strategy_v02.py） |
| --- | --- | --- |
| 数据来源 | 直连财联社 lian_v1_article | 先写快照表，策略只读快照表 |
| 历史冻结 | 无，源表变动即影响结果 | 唯一键 (id, stock_code) + INSERT IGNORE，首次落库即冻结 |
| 任务数量 | 2 个（快照任务 + 策略任务） | 1 个（快照内置） |
| 米筐初始化 | rqdatac.init()，无参，依赖终端会话 | rqdatac.init(license, key)，凭据来自 config.yaml |
| 指标口径 | 当日指标 shift(1) 后按当日行情日期合并 | 行情日 d 的指标直接用于 d 的下一交易日，不再 shift；并限制 trade_date ≤ 当日 |
| 推荐表写入 | DELETE 全表后 INSERT | 事务内 DELETE WHERE strategy_code = 2 后 INSERT |
| 推荐表字段 | 无 type | 新增 type（20014 / 20015 / 20021 / 20025） |
| 空结果处理 | 抛错退出，表内保留旧数据 | 允许 0 条并清空 strategy_code = 2 数据（重点风险，见 RK-01） |
| 中间文件 | cls_data.csv 落盘中转 | 不再使用 CSV 中转；输出 zpqc_final_new.csv、hdj_recommendations_debug.csv |
| 日志 | 关键节点打印 | 全流程进度日志，每 10% 输出一次进度 |

### 2.5 影响范围

- **受影响**：慧点睛每日推荐（APP / 前端“慧点睛”标的展示）、推荐表 hdj_strategy_recom_stocks 中 strategy_code = 2 的数据、17:30 回测任务所读取的 zpqc_final_new.csv。
- **不受影响**：慧抢筹（wpqc）任务与 wpqc_strategy_* 表；回测净值表 hdj_strategy_daily_net、hdj_bm_daily_net 的结构；其他“慧”系列策略。
- **数据层面**：新增 1 张表（快照表）；推荐表新增 1 个可空列（type）；历史推荐记录按新闻 ID 回填 type，匹配不到的历史记录保持 NULL。

### 2.6 变更窗口与实施时间轴

建议安排在交易日收盘后（建议 18:00 之后，避开 17:30 的回测任务）至次日 07:30 之前完成，避开 08:31 定时任务与 09:30 开盘。变更需求文档登记的执行时间为 2026-11-04 收盘后，**具体日期以项目经理最终通知为准**。

| 时点 | 动作 | 责任人 | 预计耗时 |
| --- | --- | --- | --- |
| T-3 日 | 提交变更申请、DBA 变更单、获取生产库账号与米筐生产凭据 | 项目经理 | — |
| T-1 日 | 测试环境全流程演练、准备备份目录、打印检查单 | 算法 + 运维 | 1 小时 |
| T 日 18:00 | 通知变更开始、静默告警、备份脚本与 crontab、备份推荐表 | 运维 + DBA | 10 分钟 |
| T 日 18:10 | 代码上传与替换（主、备两台服务器） | 运维 | 10 分钟 |
| T 日 18:20 | 数据库变更：新建快照表、推荐表增加 type 列 | DBA | 10 分钟 |
| T 日 18:30 | 配置调整与自检（配置、连接、米筐初始化） | 运维 | 10 分钟 |
| T 日 18:40 | 首次手动跑批（全量快照 + 计算 + 落库） | 运维 + 算法 | 10～30 分钟 |
| T 日 19:10 | 数据校验与业务确认 | 算法 + 项目经理 | 20 分钟 |
| T 日 19:30 | 定时任务确认、恢复告警、收尾归档 | 运维 | 10 分钟 |
| T+1 日 08:31 | 首次定时任务自动执行；09:00 前完成巡检并回报 | 运维 | 30 分钟 |

> 时间轴为建议值，且刻意安排在 17:30 回测任务之后开始：主机的回测任务（30 17 * * *）读取 zpqc_final_new.csv，若在其执行期间替换脚本或覆盖 CSV，会造成当日净值计算口径混乱。若因特殊原因必须在 17:30 前开始，需先注释回测任务，并在 Step 8 收尾时恢复。此外，若首次全量快照耗时明显超过 30 分钟（取决于财联社源表数据量），可提前在 T-1 日的测试环境完成一次全量演练以获得实际耗时，并据此调整窗口。


## 3 上线前准备

### 3.1 环境参数登记表（执行前必须填写完整）

下表为本手册所有命令要用到的参数，执行前由项目经理 / 运维 / DBA 共同确认并填写。**本表为变更现场的唯一依据，未填写的项不得开始执行。**

| 参数 | 值 | 来源 | 已确认 |
| --- | --- | --- | --- |
| 主服务器 IP | 10.32.108.62 | 慧点睛策略侧部署方案 | □ |
| 备服务器 IP | 10.32.108.61 | 慧点睛策略侧部署方案 | □ |
| 慧点睛容器 ID（主） | 【填写，docker ps 查询】 | 生产运维 | □ |
| 慧点睛容器 ID（备） | 【填写，docker ps 查询】 | 生产运维 | □ |
| 容器内工作目录 | /workspace/hdj_strategy/hdj | 慧点睛策略侧部署方案 | □ |
| MySQL 主机 | 【填写】（部署方案登记 15.24.131.142） | 项目经理 / DBA | □ |
| MySQL 端口 | 【填写】（部署方案登记 3307，注意事项见 RK-02） | DBA | □ |
| 库名 | rdc-cloud | 慧点睛策略侧部署方案 | □ |
| DB 账号 / 密码 | 【填写】 | 项目经理 | □ |
| 米筐 license / key | 【填写】 | 项目经理 / 算法 | □ |
| 变更执行日期 | 【填写】（登记 2026-11-04 收盘后） | 项目经理 | □ |
| 变更执行人 | 【填写】 | 生产运维 | □ |

### 3.2 现网现状识别与变更场景判定

现网可能处于以下几种状态之一，直接影响需要执行哪些步骤。**上线前必须先完成本节识别，按判定结果裁剪第 4 章的步骤。**

识别命令（宿主机执行）：

```bash
# 1) 当前定时任务：确认调用了哪个入口脚本、是否存在独立快照任务
crontab -l | grep -i -E "hdj|snapshot"

# 2) 容器内文件现状：确认是否已有 hdj_strategy_v02.py、入口脚本指向哪个 py
docker exec -it <容器ID> bash -lc '
  cd /workspace/hdj_strategy/hdj
  ls -l --time-style=+%F_%T hdj_strategy*.py hdj_cls_snapshot.py 2>/dev/null
  echo "---- hdj_main_strategy_daily.sh ----"
  cat hdj_main_strategy_daily.sh
  echo "---- config.yaml 键名（不显示值）----"
  grep -E "^[a-z_]+:|^  [a-z_]+:" config.yaml
'

# 3) 数据库现状：快照表是否存在、推荐表是否已有 type 列
mysql -h <DB_HOST> -P <DB_PORT> -u <DB_USER> -p'<DB_PASSWORD>' -N -e "
SELECT 'SNAPSHOT_TABLE', COUNT(*) FROM information_schema.TABLES
 WHERE TABLE_SCHEMA='rdc-cloud' AND TABLE_NAME='hdj_cls_article_snapshot';
SELECT 'TYPE_COLUMN', COUNT(*) FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA='rdc-cloud' AND TABLE_NAME='hdj_strategy_recom_stocks' AND COLUMN_NAME='type';
"
```

场景判定表：

| 场景 | 识别特征 | 需执行的步骤 |
| --- | --- | --- |
| A：首次上线快照版 | 无快照表；推荐表无 type 列；入口脚本调用 hdj_strategy.py；无快照定时任务 | 第 4 章 Step 1～Step 8 全部执行 |
| B：快照表已建、策略仍为旧版 | 快照表已存在；推荐表可能已有 type 列；入口脚本仍调用 hdj_strategy.py | Step 1、Step 2（仅补加 type 列，已存在则跳过）、Step 3、Step 4、Step 5～8 |
| C：已运行 v02 旧版（2026-09 版） | 快照表存在；type 列存在；入口脚本已调用 hdj_strategy_v02.py | Step 1（覆盖更新）、Step 3（补齐 rq_api 配置）、Step 4（校核）、Step 5～8；Step 2 仅做结构校验 |
| D：双任务并存 | 存在 hdj_cls_snapshot 相关定时任务 | 按 A/B/C 执行，并额外执行 4.4.4 下线旧快照任务 |

> 无论哪种场景，本手册都要求把 Step 1～Step 8 的“校验”动作做完，只是“实际变更动作”按上表裁剪。

### 3.3 环境与依赖核查

```bash
# 宿主机信息
hostname; date; cat /etc/os-release | head -3
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'

# 进入容器
docker exec -it <容器ID> /bin/bash

# 容器内 Python 与依赖（容器内执行）
python3 -V
python -V                      # 入口脚本使用 python，必须确认存在且为 3.x
which python python3
python3 -c "import rqdatac, pymysql, pandas, numpy, scipy, yaml; print('DEPS_OK')"
python3 -c "import rqdatac; print('rqdatac', rqdatac.__version__)"
python3 -c "import pandas, numpy, scipy; print('pandas', pandas.__version__, 'numpy', numpy.__version__, 'scipy', scipy.__version__)"

# 目录与文件
cd /workspace/hdj_strategy/hdj && pwd && ls -l
```

| 检查项 | 期望结果 | 不通过时的处理 |
| --- | --- | --- |
| python3 版本 | ≥ 3.6 | 联系研发确认兼容性，必要时更换镜像 |
| python 命令 | 存在且 `python -V` 为 3.x | 将 hdj_main_strategy_daily.sh 中的 `python` 改为 `python3`（见 4.4.2） |
| 依赖导入 | 输出 DEPS_OK | 由研发提供离线安装包，运维在容器内 `pip3 install` 后重新自检 |
| rqdatac 版本 | 可正常导入并打印版本号 | 版本过低导致参数不兼容时联系研发 |
| 工作目录 | /workspace/hdj_strategy/hdj 存在且可写 | 按部署方案创建目录并授权 |
| 磁盘空间 | 可用空间 ≥ 10 GB（日志 + 快照表增长） | 清理旧日志或扩容后再执行 |

### 3.4 网络连通性核查

慧点睛任务依赖两类外部访问：小福牛生产 MySQL 与米筐 RQDATA。按《慧点睛上线以及运维文档》，米筐相关地址与端口如下：

| 目标 | 端口 | 说明 |
| --- | --- | --- |
| rqdata.ricequant.com（121.5.97.82） | 80 / 443 | rqsdk 数据服务 |
| rqdatad-pro.ricequant.com（212.64.120.155） | 16011 | rqdatac 行情服务 |
| 生产 MySQL（15.24.131.142） | 3307（以 DBA 确认为准） | 小福牛生产库 |

连通性测试（容器内执行，容器可能没有 nc，优先用 Python）：

```bash
python3 - <<'PY'
import socket
targets = [("15.24.131.142", 3307), ("rqdatad-pro.ricequant.com", 16011), ("rqdata.ricequant.com", 80)]
for host, port in targets:
    s = socket.socket(); s.settimeout(3)
    try:
        s.connect((host, port)); print(f"{host}:{port} OK")
    except Exception as e:
        print(f"{host}:{port} FAIL {e}")
    finally:
        s.close()
PY
```

数据库连通性与时区校验（容器内、工作目录下执行，确认脚本风格的连接参数可用）：

```bash
cd /workspace/hdj_strategy/hdj
python3 - <<'PY'
import pymysql, yaml
cfg = yaml.safe_load(open('config.yaml', encoding='utf-8'))['database']
conn = pymysql.connect(host=cfg['db_host'], user=cfg['db_username'],
                       password=cfg['db_password'], db=cfg['db_name'], charset='utf8mb4')
cur = conn.cursor()
cur.execute("SELECT VERSION(), NOW(), @@global.time_zone, @@session.time_zone")
print(cur.fetchone())
cur.execute("SHOW TABLES LIKE 'hdj_%'")
print([r[0] for r in cur.fetchall()])
conn.close()
print("DB_OK")
PY
```

| 检查项 | 期望结果 | 不通过时的处理 |
| --- | --- | --- |
| 米筐 16011 / 80 端口 | OK | 联系网络/运维开通策略，参考运维文档登记的 IP 白名单 |
| 生产 MySQL 端口 | OK | 确认端口（3307 或 3306）、白名单；见 RK-02 |
| DB_OK | 打印版本、时间与 hdj_ 开头的表 | 账号/库名/权限问题，联系项目经理与 DBA |
| 数据库时间 | 与东八区当前时间一致 | 见 4.4.5 时区核查 |

### 3.5 配置与凭据准备

本次需要在 config.yaml 中提供以下配置项（键名必须完全一致，脚本按键名读取）：

| 配置项 | 说明 | 来源 |
| --- | --- | --- |
| database.source_db_host / _username / _password / _name | 财联社源库连接；未配置时回退 db_* | 项目经理 / DBA |
| database.rdc_db_host / _username / _password / _name | RDC-CLOUD 库连接；未配置时回退 db_* | 项目经理 / DBA |
| database.db_host / db_username / db_password / db_name | 通用回退配置（源库与目标库同库时只需这一组） | 项目经理 / DBA |
| rq_api.license | 米筐 license | 项目经理 / 算法（米筐账号） |
| rq_api.key | 米筐 key | 项目经理 / 算法（米筐账号） |

> 脚本的取配置顺序为：source_db → cls_db → db；rdc_db → target_db → db。取第一个四项齐全的配置，四项缺一即跳过。**分库部署时必须显式配置 source_db_* 与 rdc_db_*，否则会回退到 db_* 并可能写错库。**

### 3.6 备份清单与备份操作

| 备份对象 | 位置 | 备份方式 | 保留期 |
| --- | --- | --- | --- |
| 现网脚本与配置 | 容器内 /workspace/hdj_strategy/hdj/backup/<日期>/ | cp -p | 30 天 |
| 宿主 crontab | /tmp/crontab_hdj_backup_<日期>.txt 及运维归档 | crontab -l 重定向 | 30 天 |
| 推荐表现网数据 | 数据库备份表 bak_hdj_recom_<日期> | CREATE TABLE ... AS SELECT | 30 天 |
| 快照表 | 本次为新建表，无需备份 | — | — |
| zpqc_final_new.csv | 同备份目录 | cp -p | 30 天 |

```bash
# 1) 宿主 crontab 备份
crontab -l > /tmp/crontab_hdj_backup_$(date +%Y%m%d).txt
cat /tmp/crontab_hdj_backup_$(date +%Y%m%d).txt

# 2) 容器内脚本、配置、CSV 备份（主备两台都要做）
docker exec -it <容器ID> bash -lc '
  cd /workspace/hdj_strategy/hdj
  BK=backup/$(date +%Y%m%d)
  mkdir -p $BK
  cp -p hdj_strategy.py hdj_cls_snapshot.py hdj_main_strategy_daily.sh config.yaml logging.yaml logconfig.py $BK/ 2>/dev/null
  cp -p zpqc_final_new.csv $BK/ 2>/dev/null
  ls -l $BK/
'
```

```sql
-- 3) 推荐表数据备份（DBA 执行，日期按实际修改）
CREATE TABLE `rdc-cloud`.bak_hdj_recom_20261104 AS
SELECT * FROM `rdc-cloud`.hdj_strategy_recom_stocks;
```

> 备份表创建于加列之前时不含 type 列，回滚恢复时按 6.3 的脚本执行，不要直接整表替换。

### 3.7 通知与告警处理

| 事项 | 动作 | 责任人 |
| --- | --- | --- |
| 变更开始通知 | 企微群“小福牛生产巡检告警群”发布变更开始、影响范围、预计结束时间 | 生产运维 |
| 告警静默 | 扶摇、xxljob、博睿相关告警在窗口内静默；不支持静默的，提前告知值守人员本次告警为预期内 | 生产运维 |
| 业务侧通知 | 告知项目经理：窗口内不更新推荐，次日 08:31 起恢复正常 | 项目经理 |
| 变更完成通知 | 发布变更结果、实际耗时、次日验证安排 | 生产运维 |
| 干系人 | 通知：雷朋、吴丁杰；汇报：谢总、王钟菱、顾卓斐 | 项目经理 |

### 3.8 上线准入条件（Go / No-Go）

以下条件全部勾选为“是”方可开始执行；任一项为“否”，由项目经理决定延期。

| 序号 | 准入条件 | 是 / 否 | 确认人 |
| --- | --- | --- | --- |
| 1 | 变更申请已审批，变更窗口已确定 | □ | 项目经理 |
| 2 | 生产 DB 账号、库表权限已确认（建表/加列由 DBA 执行或已授权） | □ | 项目经理 / DBA |
| 3 | 米筐生产 license / key 已确认并在有效期内 | □ | 算法 |
| 4 | 主、备服务器 SSH 可登录，慧点睛容器运行中 | □ | 生产运维 |
| 5 | 3.2 现状识别完成，场景已判定 | □ | 生产运维 |
| 6 | 3.6 备份全部完成并核对 | □ | 生产运维 / DBA |
| 7 | 测试环境已完成同等操作演练（含首次全量快照） | □ | 算法 |
| 8 | 回滚方案、备份、旧脚本可回退路径已确认 | □ | 生产运维 |
| 9 | 变更窗口内无其他变更冲突 | □ | 项目经理 |
| 10 | 业务方已知悉窗口内不更新推荐 | □ | 项目经理 |

## 4 上线操作步骤

本章为变更实施的主体部分，共 8 步。执行顺序不可颠倒，前一步的“预期结果”未达成时不得进入下一步。

| 步骤 | 名称 | 关键产物 | 是否需要停机 |
| --- | --- | --- | --- |
| Step 1 | 代码上传与替换 | 容器内 hdj_strategy_v02.py、hdj_main_strategy_daily.sh | 否 |
| Step 2 | 数据库变更 | 快照表、推荐表 type 列 | 否 |
| Step 3 | 配置调整 | config.yaml（rq_api、分库配置） | 否 |
| Step 4 | 定时任务调整 | 宿主 crontab（08:31 单任务） | 否 |
| Step 5 | 首次跑批 | 快照数据、推荐数据、CSV | 否 |
| Step 6 | 数据校验 | 校验 SQL 结果 | 否 |
| Step 7 | 业务验证 | 前端/APP 展示确认 | 否 |
| Step 8 | 收尾 | 文档、归档、告警恢复 | 否 |

### 4.1 Step 1 代码上传与替换

#### 4.1.1 获取代码

```bash
# 宿主机准备临时目录
cd /tmp && rm -rf hdj_bundle && mkdir -p hdj_bundle && cd hdj_bundle

# 方式一（推荐）：从 Git 拉取，正式环境用 master，测试环境用 test
git clone -b master --single-branch http://rdc-git.hfzq.com.cn:30180/RDC-Algorithm/morning_session.git
# git clone -b test --single-branch http://rdc-git.hfzq.com.cn:30180/RDC-Algorithm/morning_session.git

# 方式二：扶摇云盘下载后上传（雷朋/hqc 目录），从本地传到服务器
# scp hdj_strategy_v02.py hdj_main_strategy_daily.sh <用户>@10.32.108.62:/tmp/hdj_bundle/
```

本次只需替换 **2 个文件**：hdj_strategy_v02.py、hdj_main_strategy_daily.sh。config.yaml、logging.yaml、logconfig.py、hdj_backtest.py、hdj_main_backtest_daily.sh 保持现网不动（config.yaml 在第 4.3 步就地修改）。

#### 4.1.2 文件完整性校验

```bash
cd /tmp/hdj_bundle
ls -l hdj_strategy_v02.py hdj_main_strategy_daily.sh
sha256sum hdj_strategy_v02.py hdj_main_strategy_daily.sh
file hdj_strategy_v02.py
```

| 检查项 | 期望结果 |
| --- | --- |
| 文件存在 | 两个文件均列出，大小非 0 |
| sha256 | 与研发提供的校验值一致（记入附录 E） |
| 编码 | `file` 输出包含 UTF-8，或 `head -1` 显示 `# -*- coding: utf-8 -*-` |
| 换行符 | 不得为 CRLF（`file` 不显示 CRLF）；若为 CRLF 用 `sed -i 's/\r$//'` 转换 |

#### 4.1.3 备份现网文件

按 3.6 的容器内备份命令执行，确认备份目录已生成且包含 6 个文件。**未完成备份不得覆盖。**

#### 4.1.4 覆盖文件（主、备两台服务器都执行）

```bash
CID=<容器ID>
docker cp /tmp/hdj_bundle/hdj_strategy_v02.py        $CID:/workspace/hdj_strategy/hdj/hdj_strategy_v02.py
docker cp /tmp/hdj_bundle/hdj_main_strategy_daily.sh $CID:/workspace/hdj_strategy/hdj/hdj_main_strategy_daily.sh

docker exec -it $CID bash -lc '
  cd /workspace/hdj_strategy/hdj
  chmod +x hdj_main_strategy_daily.sh
  ls -l --time-style=+%F_%T hdj_strategy_v02.py hdj_main_strategy_daily.sh
'
```

> 备机（10.32.108.61）虽然没有定时任务，但应急演练中会通过 scene2_updateCron_sync.sh 启用备机定时任务，因此**备机文件必须与主机同步更新**，否则切换备机后会运行旧脚本。

#### 4.1.5 语法与依赖自检

```bash
docker exec -it $CID bash -lc 'cd /workspace/hdj_strategy/hdj && python3 -m py_compile hdj_strategy_v02.py && echo COMPILE_OK'
docker exec -it $CID bash -lc 'cd /workspace/hdj_strategy/hdj && python3 -c "import rqdatac, pymysql, pandas, numpy, scipy, yaml; print(\"DEPS_OK\")"'
docker exec -it $CID bash -lc 'cd /workspace/hdj_strategy/hdj && cat hdj_main_strategy_daily.sh'
```

`hdj_main_strategy_daily.sh` 的正确内容应为：

```bash
#!/bin/bash

# 定义工作目录变量
WORK_DIR="/workspace/hdj_strategy/hdj"

# 进入目录并运行 Python 脚本
cd "$WORK_DIR" || { echo "无法进入目录 $WORK_DIR"; exit 1; }
python ./hdj_strategy_v02.py
```

#### 4.1.6 预期结果与异常处置

| 检查项 | 预期结果 | 不通过时的处理 |
| --- | --- | --- |
| docker cp | 无报错，容器内文件时间戳为本次上传时间 | 检查容器 ID、路径、磁盘空间；确认容器内目录已存在 |
| chmod | 无报错，权限含 x | 用 root 或容器内 sudo 执行 |
| py_compile | 输出 COMPILE_OK | 文件传输损坏或编码问题，重新上传并按 4.1.2 校验 |
| 依赖导入 | 输出 DEPS_OK | 见 3.3 依赖处理 |
| 入口脚本 | 调用 hdj_strategy_v02.py | 未生效时重新 docker cp，或手工编辑（见 4.4.2） |

### 4.2 Step 2 数据库变更

本步骤由 DBA 执行或由运维在 DBA 授权下执行。两项变更互相独立，可并行。

#### 4.2.1 新增快照表

```sql
CREATE TABLE IF NOT EXISTS `rdc-cloud`.hdj_cls_article_snapshot (
    snap_id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    id                  INT NOT NULL COMMENT '财联社新闻文章ID（lian_v1_article.id）',
    formatted_time      VARCHAR(19) NOT NULL COMMENT '新闻发布时间（YYYY-MM-DD HH:MM:SS）',
    stock_code          VARCHAR(20) NOT NULL COMMENT '新闻关联股票代码',
    type                INT NOT NULL COMMENT '新闻类型（20014/20015/20021/20025）',
    first_snapshot_date DATE NOT NULL COMMENT '该关系首次转写落库日期（快照日期）',
    update_time         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (snap_id),
    UNIQUE KEY uk_id_stock_code (id, stock_code),
    KEY idx_first_snapshot_date (first_snapshot_date),
    KEY idx_formatted_time (formatted_time),
    KEY idx_type (type)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci
  COMMENT = '慧点睛财联社新闻-股票关系每日快照表（历史冻结，策略只读本表）';
```

执行方式一（脚本文件，文件内已带 `rdc-cloud` 库名前缀，无需 USE）：

```bash
mysql -h <DB_HOST> -P <DB_PORT> -u <DB_USER> -p'<DB_PASSWORD>' \
      --default-character-set=utf8mb4 < create_hdj_cls_article_snapshot.sql
```

执行方式二（在数据库客户端中直接粘贴上面的 SQL 执行）。

> 唯一键 `uk_id_stock_code (id, stock_code)` 是“历史冻结 + 重复执行不覆盖”的基础，**缺失该唯一键会导致每日重跑不断追加重复行、推荐结果失真**，建表后必须按 4.2.3 校验。

#### 4.2.2 推荐表增加 type 列

若推荐表尚无 type 列，执行以下可重复执行的脚本（来自 testsql.sql，已做存在性判断）：

```sql
SET @type_column_exists := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'rdc-cloud'
      AND TABLE_NAME = 'hdj_strategy_recom_stocks'
      AND COLUMN_NAME = 'type'
);
SET @add_type_sql := IF(
    @type_column_exists = 0,
    'ALTER TABLE `rdc-cloud`.hdj_strategy_recom_stocks ADD COLUMN type INT NULL COMMENT ''财联社新闻类型（20014/20015/20021/20025）'' AFTER stock_name',
    'SELECT 1'
);
PREPARE add_type_stmt FROM @add_type_sql;
EXECUTE add_type_stmt;
DEALLOCATE PREPARE add_type_stmt;

-- 为已有推荐记录按新闻 ID 回填 type；没有匹配记录的旧数据保持 NULL
UPDATE `rdc-cloud`.hdj_strategy_recom_stocks AS r
JOIN `rdc-cloud`.hdj_cls_article_snapshot AS s ON s.id = r.id
SET r.type = s.type
WHERE r.type IS NULL;
```

> type 列必须为 **NULL 允许**：历史推荐记录可能匹配不到快照（快照表新建、历史新闻已不可见），回填后仍为 NULL 属正常。脚本对新写入的记录要求 type 非空，见附录 A.6。

#### 4.2.3 数据库结构校验

```sql
-- 1) 快照表结构：确认唯一键存在
SHOW CREATE TABLE `rdc-cloud`.hdj_cls_article_snapshot\G

-- 2) 快照表与推荐表是否已存在
SELECT TABLE_NAME, TABLE_ROWS, CREATE_TIME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'rdc-cloud'
  AND TABLE_NAME IN ('hdj_cls_article_snapshot', 'hdj_strategy_recom_stocks');

-- 3) 推荐表 type 列
SHOW COLUMNS FROM `rdc-cloud`.hdj_strategy_recom_stocks LIKE 'type';

-- 4) 关键索引
SHOW INDEX FROM `rdc-cloud`.hdj_cls_article_snapshot;
```

| 校验项 | 期望结果 |
| --- | --- |
| 表存在 | hdj_cls_article_snapshot 出现在结果中 |
| 唯一键 | SHOW INDEX 中存在 Key_name = uk_id_stock_code，Non_unique = 0，含 id 与 stock_code 两列 |
| 字符集 | utf8mb4 / utf8mb4_general_ci |
| type 列 | 存在，类型 int，Null = YES，位置在 stock_name 之后 |
| 建表时间 | 为本次变更时间 |

#### 4.2.4 异常处置

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| ERROR 1044/1142 权限不足 | 账号无 CREATE / ALTER 权限 | 由 DBA 执行；或在变更单中补充授权 |
| ERROR 1050 Table already exists | 表已存在（IF NOT EXISTS 生效时会提示 warning，不会报错） | 按 3.2 已判定为场景 B/C，跳过建表，仅做结构校验 |
| ERROR 1060 Duplicate column name 'type' | type 列已存在 | 正常，跳过加列；执行回填 UPDATE |
| 表建在错误的库 | 未使用 `rdc-cloud` 前缀或客户端默认库不同 | DROP 后按 4.2.1 原文重建，或 `RENAME TABLE` 迁移 |
| 唯一键缺失 | 手工建表时漏写 | 立即补建：`ALTER TABLE ... ADD UNIQUE KEY uk_id_stock_code (id, stock_code);`（执行前先清理重复行） |

### 4.3 Step 3 配置调整

#### 4.3.1 备份配置文件

```bash
docker exec -it <容器ID> bash -lc '
  cd /workspace/hdj_strategy/hdj
  cp -p config.yaml config.yaml.bak.$(date +%Y%m%d_%H%M)
  ls -l config.yaml*
'
```

#### 4.3.2 编辑 config.yaml

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && vi config.yaml'
```

配置模板（值由项目经理 / DBA / 算法提供，**本手册不承载任何生产口令**）：

```yaml
# 财联社源库（与 RDC-CLOUD 同库时可省略 source_db_*，只保留 db_*）
database:
  source_db_host: "<财联社源库地址>"
  source_db_username: "<财联社源库账号>"
  source_db_password: "<财联社源库口令>"
  source_db_name: "<财联社源库库名>"

  # RDC-CLOUD 目标库（快照表、推荐表所在库）
  rdc_db_host: "<RDC-CLOUD 地址>"
  rdc_db_username: "<RDC-CLOUD 账号>"
  rdc_db_password: "<RDC-CLOUD 口令>"
  rdc_db_name: "rdc-cloud"

  # 通用回退配置：分库配置缺失时脚本会回退到这一组
  db_host: "<地址>"
  db_port: "3307"          # 注意：当前脚本未使用 db_port，见 RK-02
  db_name: "rdc-cloud"
  db_username: "<账号>"
  db_password: "<口令>"

rq_api:
  license: "<米筐生产 license>"
  key: "<米筐生产 key>"
```

| 配置要求 | 说明 |
| --- | --- |
| 键名完全一致 | 脚本按固定键名读取，多空格、大小写、中文引号都会导致取不到配置 |
| 引号 | 统一使用英文半角引号；口令含特殊字符时用单引号包裹 |
| 编码 | UTF-8，保存后确认无 BOM |
| rq_api | license 与 key 都必须为非空字符串，否则脚本直接抛错退出 |
| 分库 | 源库与目标库不同时必须显式配置 source_db_* 与 rdc_db_* |

#### 4.3.3 配置自检

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && python3 - <<PY
import yaml
cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
db = cfg.get("database", {})
print("database keys:", sorted(db.keys()))
print("rq_api keys:", sorted(cfg.get("rq_api", {}).keys()))
for prefix in ("source_db", "rdc_db", "db"):
    keys = [f"{prefix}_{k}" for k in ("host", "username", "password", "name")]
    print(prefix, "complete:", all(db.get(k) for k in keys))
print("rq_api license/key non-empty:", bool(cfg.get("rq_api", {}).get("license")) and bool(cfg.get("rq_api", {}).get("key")))
PY'
```

期望输出（按实际配置）：

```
database keys: ['db_host', 'db_name', 'db_password', 'db_port', 'db_username', 'rdc_db_host', 'rdc_db_name', 'rdc_db_password', 'rdc_db_username', 'source_db_host', 'source_db_name', 'source_db_password', 'source_db_username']
rq_api keys: ['key', 'license']
source_db complete: True
rdc_db complete: True
db complete: True
rq_api license/key non-empty: True
```

#### 4.3.4 米筐初始化自检

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && python3 - <<PY
import yaml, rqdatac
cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["rq_api"]
rqdatac.init(cfg["license"], cfg["key"])
print("RQ_INIT_OK")
print("交易日检查:", rqdatac.get_next_trading_date("2026-11-06", n=1, market="cn"))
PY'
```

| 检查项 | 期望结果 | 不通过时的处理 |
| --- | --- | --- |
| RQ_INIT_OK | 打印成功 | license 失效 / 网络不通 / 并发超限，见附录 B |
| 交易日返回 | 返回下一个交易日（示例应为 2026-11-09） | 日历服务异常，联系米筐或稍后重试 |

#### 4.3.5 配置权限

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && chmod 600 config.yaml && ls -l config.yaml'
```

> 生产口令、米筐 license/key 属于敏感信息：不得写入本手册、不得粘贴到群聊、不得提交到 Git 明文仓库。如现网 Git 仓库中保存了 config.yaml，需确认仓库权限范围。

#### 4.3.6 预期结果与异常处置

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| 配置文件缺少 database 节点 | 文件为空、缩进错误、YAML 语法错误 | 用 `python3 -c "import yaml;print(yaml.safe_load(open('config.yaml')))"` 定位行号 |
| 配置文件缺少 rq_api 节点 | 未添加 rq_api 段或缩进错误 | 按 4.3.2 模板补齐 |
| rq_api.license 必须是非空字符串 | license 为空或写成中文引号 | 修正引号与内容 |
| 配置读取正常但连接失败 | 主机/端口/账号/白名单 | 见 3.4 与 7.2 |


### 4.4 Step 4 定时任务调整

慧点睛的定时任务配置在**宿主机**（不在容器内），由 cron 通过 `docker exec` 进入容器执行入口脚本。主备两台服务器中，**只有主机 10.32.108.62 配置定时任务**，备机不配置（应急切换时由 scene2_updateCron_sync.sh 临时启用）。

#### 4.4.1 查看并备份现有定时任务

```bash
crontab -l
crontab -l > /tmp/crontab_hdj_backup_$(date +%Y%m%d).txt

# 过滤慧点睛相关任务，确认现状
crontab -l | grep -n -i -E "hdj|snapshot"
```

现网（2026-03 部署方案）中慧点睛相关任务为两条：

```bash
# 每日早盘推荐（08:31）
31 8 * * * docker exec -d <容器ID> bash -c "/workspace/hdj_strategy/hdj/hdj_main_strategy_daily.sh"

# 每日回测净值（17:30）
30 17 * * * docker exec -d <容器ID> bash -lic "cd /workspace/hdj_strategy/hdj && ./hdj_main_backtest_daily.sh > ./logs/backtest_daemon_exec.log 2>&1"
```

回测任务本次**不做任何改动**，仅需确认其存在。注意回测脚本读取的是工作目录下的 `zpqc_final_new.csv`，该文件由早盘策略任务生成，因此**早盘任务与回测任务的先后顺序不能颠倒**。

#### 4.4.2 修改入口脚本（如仍指向旧脚本或使用 python）

若 3.2 识别发现 `hdj_main_strategy_daily.sh` 仍调用 `hdj_strategy.py`，或 `python` 命令不可用，则在容器内修改：

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && vi hdj_main_strategy_daily.sh'
```

修改后的正确内容（`python` 不可用时改为 `python3`）：

```bash
#!/bin/bash

# 定义工作目录变量
WORK_DIR="/workspace/hdj_strategy/hdj"

# 进入目录并运行 Python 脚本
cd "$WORK_DIR" || { echo "无法进入目录 $WORK_DIR"; exit 1; }
python ./hdj_strategy_v02.py
```

```bash
# 确认修改结果与可执行权限
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && tail -2 hdj_main_strategy_daily.sh && ls -l hdj_main_strategy_daily.sh'
```

#### 4.4.3 修改定时任务（保持每日 08:31 单任务）

```bash
crontab -e
```

两种方案二选一：

**方案 A（最小变更，与现网一致）**：保持原行不变，因为入口脚本已改为调用 hdj_strategy_v02.py。

```bash
31 8 * * * docker exec -d <容器ID> bash -c "/workspace/hdj_strategy/hdj/hdj_main_strategy_daily.sh"
```

**方案 B（推荐）**：在方案 A 基础上增加运行日志重定向，便于事后排查（`docker exec -d` 默认丢弃 stdout，只有 logging 写入的 logs/wpqc.log 能留存）。

```bash
31 8 * * * docker exec -d <容器ID> bash -c "/workspace/hdj_strategy/hdj/hdj_main_strategy_daily.sh >> /workspace/hdj_strategy/hdj/logs/daily_strategy_exec.log 2>&1"
```

> 采用方案 B 前必须确认容器内 `logs` 目录已存在，否则重定向会失败、任务不执行：
> `docker exec -it <容器ID> bash -lc 'ls -ld /workspace/hdj_strategy/hdj/logs'`
> 若不存在：`docker exec -it <容器ID> bash -lc 'mkdir -p /workspace/hdj_strategy/hdj/logs'`

#### 4.4.4 下线旧的独立快照任务（场景 D 必做）

若现网仍存在调用 hdj_cls_snapshot.py 的定时任务（本次快照已内置到策略脚本，双任务会造成重复取数与重复写入），需在 `crontab -e` 中**注释掉**该行（保留原文注释，便于回滚）：

```bash
# 2026-11-04 慧点睛快照已内置到 hdj_strategy_v02.py，本任务停用（保留以便回滚）
# 30 8 * * * docker exec -d <容器ID> bash -c "/workspace/hdj_strategy/hdj/hdj_main_snapshot_daily.sh"
```

> 只注释、不删除脚本文件：`hdj_cls_snapshot.py` 与对应 .sh 保留在容器内，回滚时直接恢复 crontab 备份即可。

#### 4.4.5 时区核查

慧点睛要求服务器与容器时区为东八区（Asia/Shanghai），否则会出现交易日错位、推荐日期错误、cron 执行时间偏移。

```bash
# 宿主机
timedatectl 2>/dev/null || date

# 容器内
docker exec -it <容器ID> bash -lc 'date; date -u; cat /etc/timezone 2>/dev/null; echo TZ=$TZ; python3 -c "import datetime;print(\"python now:\", datetime.datetime.now())"'
```

| 检查项 | 期望结果 | 不通过时的处理 |
| --- | --- | --- |
| 宿主时区 | Asia/Shanghai，`date` 显示 CST +0800 | `timedatectl set-timezone Asia/Shanghai` |
| 容器时区 | 与宿主一致，`/etc/timezone` 为 Asia/Shanghai | 重启容器并挂载 /etc/localtime，或设置容器环境变量 TZ=Asia/Shanghai（由运维按现网规范处理） |
| 时间偏差 | 与标准时间偏差 ≤ 1 分钟 | 校准 NTP 后重新执行本步骤 |

#### 4.4.6 定时任务校验

```bash
# 1) 确认任务已写入且仅一条慧点睛早盘任务
crontab -l | grep -c "hdj_main_strategy_daily.sh"
crontab -l | grep -n -i -E "hdj|snapshot"

# 2) 确认 cron 服务运行中
systemctl status cron 2>/dev/null | head -5 || service cron status

# 3) 模拟执行一次入口脚本（在容器外，验证 docker exec + 脚本路径 + 权限）
docker exec -it <容器ID> bash -lc '/workspace/hdj_strategy/hdj/hdj_main_strategy_daily.sh' | tail -5
```

> 第 3 项会真实执行一次策略任务（等同于重跑），若刚完成 Step 5 首次跑批，可不重复执行；若执行，结束后按 Step 6 再校验一次数据（重跑幂等，不会产生重复推荐）。

| 校验项 | 期望结果 |
| --- | --- |
| 慧点睛早盘任务数 | 1（方案 A/B 均只有一条） |
| 回测任务 | 仍存在，未被修改 |
| 快照任务 | 无（或已注释） |
| cron 服务 | active (running) |
| 模拟执行 | 能进入工作目录并输出策略日志，不报“无法进入目录”“command not found” |

### 4.5 Step 5 首次跑批

#### 4.5.1 跑批前检查

| 序号 | 检查项 | 命令或方法 | 通过标准 |
| --- | --- | --- | --- |
| 1 | 快照表已建 | 4.2.3 第 1 项 | 表存在且唯一键正确 |
| 2 | type 列已加 | 4.2.3 第 3 项 | 列存在 |
| 3 | 配置可读 | 4.3.3 | 各段 complete=True |
| 4 | 米筐可初始化 | 4.3.4 | RQ_INIT_OK |
| 5 | 容器内 logs 目录 | `ls -ld logs` | 存在可写 |
| 6 | 磁盘空间 | `df -h /workspace` | 可用 ≥ 10 GB |
| 7 | 时间窗口 | `date`、`crontab -l` | 避开 08:25～08:40 与 17:30 回测任务，且留出足够时间在次日 07:30 前完成 |
| 8 | 无人同时操作 | 与运维确认 | 变更窗口内独占执行 |

#### 4.5.2 执行首次跑批

```bash
docker exec -it <容器ID> bash -lc '
  set -o pipefail
  cd /workspace/hdj_strategy/hdj
  time python3 hdj_strategy_v02.py --config ./config.yaml 2>&1 | tee logs/first_run_$(date +%Y%m%d_%H%M).log
  echo EXIT_CODE=$?
'
```

> 建议使用 `docker exec -it`（前台交互）：`report_progress` 会同时打印到控制台，可以实时观察任务是否推进；日志同时由 logconfig 写入 `logs/wpqc.log`。

#### 4.5.3 关键日志与耗时观察

日志按以下顺序出现，每一条都对应一个可观测的阶段。若某条长时间不出现（超过表中“正常耗时”的 3 倍），说明该阶段卡住，按附录 B 定位。

| 顺序 | 日志关键字 | 含义 | 正常耗时（首次） |
| --- | --- | --- | --- |
| 1 | 开始慧点睛每日策略任务，PID=...，配置文件：... | 任务启动 | 立即 |
| 2 | 财联社源库数据库连接完成 / RDC-CLOUD数据库连接完成 | 两个库连接成功 | 秒级 |
| 3 | 财联社源表查询完成，共 N 条关系记录 | 源表取数完成 | 数秒～数十秒 |
| 4 | 开始写入新闻快照：N 条，共 M 批 | 开始写快照 | 立即 |
| 5 | 快照写入进度：x/M 批，累计新增 N 条 | 每批进度 | 首次 1～10 分钟 |
| 6 | 快照写入完成：本次有效 N 条，新增 M 条，重复关系自动跳过 | 快照提交成功 | 同上 |
| 7 | 快照表读取完成，共 N 条关系记录 | 策略从快照读入 | 秒级 |
| 8 | 新闻清洗完成：保留 N 条，剔除 M 条 | 时间/代码清洗 | 秒级 |
| 9 | 新闻交易日映射完成，共 N 条 | 交易日历映射 | 秒级～1 分钟 |
| 10 | 股票代码转换完成：保留 N 条、M 只股票，过滤北交所 K 条 | 米筐代码转换 | 秒级～1 分钟 |
| 11 | 开始请求米筐日线行情：M 只股票，日期 2025-04-01 至 YYYY-MM-DD | 行情请求开始 | 立即 |
| 12 | 米筐行情获取完成：N 行 | 行情返回 | 1～3 分钟 |
| 13 | 开始计算10日成交额斜率，共 M 只股票 | 斜率计算开始 | 立即 |
| 14 | 成交额斜率计算进度：x/M（y%），已耗时 | 每 10% 进度 | 1～3 分钟 |
| 15 | 行情指标日期映射完成：行情最新日期=...，指标适用最大日期=... | 指标日期映射 | 秒级 |
| 16 | 当日筛选检查：日期=...，候选=N 条，涨幅指标缺失=M 条，涨幅通过=K 条 | 当日候选与门槛统计 | 立即 |
| 17 | 推荐池计算完成：生成 N 条推荐 | 选股完成 | 秒级 |
| 18 | 新闻ID和股票名称匹配完成 | 前端展示字段补齐 | 秒级 |
| 19 | CSV 输出完成：zpqc_final_new.csv、hdj_recommendations_debug.csv | CSV 产出 | 秒级 |
| 20 | 推荐表更新完成：写入 N 条记录 | 推荐表事务提交 | 秒级 |
| 21 | 当日策略计算任务完成 | 全流程成功 | 立即 |

**成功判定标准（三条同时满足）**：

1. 命令退出码为 0（输出 `EXIT_CODE=0`）；
2. 日志最后出现“推荐表更新完成：写入 N 条记录”与“当日策略计算任务完成”；
3. `logs/error.log` 中本次时间段没有 ERROR 级日志（WARNING 允许，见 4.6 表后说明）。

#### 4.5.4 产物检查

```bash
docker exec -it <容器ID> bash -lc '
  cd /workspace/hdj_strategy/hdj
  ls -l --time-style=+%F_%T zpqc_final_new.csv hdj_recommendations_debug.csv logs/ | tail -20
  echo "---- 推荐 CSV 头 5 行 ----"
  head -5 zpqc_final_new.csv
  echo "---- 调试 CSV 头 3 行 ----"
  head -3 hdj_recommendations_debug.csv
  echo "---- 错误日志尾部 ----"
  tail -5 logs/error.log 2>/dev/null
'
```

| 检查项 | 期望结果 |
| --- | --- |
| zpqc_final_new.csv | 时间戳为本次执行时间，含表头 TRADE_DT,TICKER,type,TARGET_WEIGHT |
| hdj_recommendations_debug.csv | 时间戳为本次执行时间，含 id、symbol 等调试字段 |
| logs/wpqc.log | 已追加本次执行日志，按天切分 |
| logs/error.log | 本次无 ERROR（历史 ERROR 可忽略，按时间定位） |

#### 4.5.5 异常处置

| 现象 | 可能原因 | 处置 |
| --- | --- | --- |
| 退出码非 0，日志停在“财联社源表查询完成”之后 | 目标库连接或快照表不存在 | 按 4.2.3 校验表；核对 rdc_db_* 配置 |
| 报 `Table 'rdc-cloud.hdj_cls_article_snapshot' doesn't exist` | 未执行 Step 2 | 执行 4.2.1，重跑 |
| 报 `配置文件缺少 rq_api 节点` | 配置未更新 | 执行 4.3.2，重跑 |
| 报 `财联社源库数据库连接失败，已重试 3 次` | 源库地址/端口/账号/白名单 | 见 3.4、7.2 |
| 日志停在“开始请求米筐日线行情”超过 10 分钟 | 米筐限流、网络抖动、股票数量过多 | 观察网络与米筐状态，必要时重跑（重跑幂等） |
| 报 `部分推荐股票找不到关联新闻 ID，拒绝写入不完整结果` | 快照与代码匹配异常 | 保留现场，联系研发；此时推荐表未变更，仍是旧数据 |
| 日志显示“生成 0 条推荐” | 当日无候选或涨幅门槛全部未通过 | **立即停止后续操作**，按 RK-01 处理，必要时回滚数据 |
| 任务超时（> 14 分钟） | 首次全量快照数据量大 | 记录耗时，正常现象；若持续超时按 RK-03 评估 |

### 4.6 Step 6 数据校验

以下 SQL 全部在 rdc-cloud 库执行，结果记入附录 D 检查单。日期条件中的 `CURDATE()` 在非交易时段执行时可能没有当日数据，此时把条件改为“最近一个交易日”（见第 1 条）。

```sql
-- 1) 推荐表：最近 10 个交易日的推荐条数分布（确认有当日/最近交易日数据）
SELECT cal_date, COUNT(*) AS cnt
FROM `rdc-cloud`.hdj_strategy_recom_stocks
WHERE strategy_code = '2'
GROUP BY cal_date
ORDER BY cal_date DESC
LIMIT 10;

-- 2) 推荐表：当日明细（正常应为 5 条，权重 0.19）
SELECT id, cal_date, stock_code, stock_name, type, target_percent, trade_way, strategy_code
FROM `rdc-cloud`.hdj_strategy_recom_stocks
WHERE strategy_code = '2' AND cal_date = CURDATE()
ORDER BY target_percent DESC, stock_code;

-- 3) 推荐表：字段完整性（三项均应为 0）
SELECT
  SUM(id IS NULL)                                            AS null_id,
  SUM(stock_name IS NULL OR stock_name = '')                 AS null_name,
  SUM(type IS NULL)                                          AS null_type,
  SUM(target_percent <> 0.19)                                AS bad_weight,
  SUM(trade_way <> 1)                                        AS bad_trade_way,
  SUM(strategy_code <> '2')                                  AS bad_strategy
FROM `rdc-cloud`.hdj_strategy_recom_stocks
WHERE cal_date = CURDATE();

-- 4) 推荐表：同一交易日同一股票重复（应为 0 行）
SELECT cal_date, stock_code, COUNT(*) AS c
FROM `rdc-cloud`.hdj_strategy_recom_stocks
WHERE strategy_code = '2'
GROUP BY cal_date, stock_code
HAVING c > 1;

-- 5) 推荐表：不得出现未来交易日（应为 0）
SELECT COUNT(*) AS future_rows
FROM `rdc-cloud`.hdj_strategy_recom_stocks
WHERE strategy_code = '2' AND cal_date > CURDATE();

-- 6) 推荐与快照的新闻关联（应为 0 行，即每条推荐都能找到对应新闻）
SELECT r.cal_date, r.stock_code, r.id
FROM `rdc-cloud`.hdj_strategy_recom_stocks r
LEFT JOIN `rdc-cloud`.hdj_cls_article_snapshot s ON s.id = r.id
WHERE r.strategy_code = '2' AND r.cal_date = CURDATE() AND s.id IS NULL;

-- 7) 快照表：总量与首日落库日期
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT id)          AS news_cnt,
       COUNT(DISTINCT stock_code)  AS stock_cnt,
       MIN(first_snapshot_date)    AS min_snapshot_date,
       MAX(first_snapshot_date)    AS max_snapshot_date
FROM `rdc-cloud`.hdj_cls_article_snapshot;

-- 8) 快照表：当日新增条数
SELECT COUNT(*) AS today_new
FROM `rdc-cloud`.hdj_cls_article_snapshot
WHERE first_snapshot_date = CURDATE();

-- 9) 快照表：唯一键重复（应为 0）
SELECT COUNT(*) AS dup_cnt FROM (
  SELECT id, stock_code
  FROM `rdc-cloud`.hdj_cls_article_snapshot
  GROUP BY id, stock_code
  HAVING COUNT(*) > 1
) t;

-- 10) 快照表：新闻类型分布（应只含 20014/20015/20021/20025）
SELECT type, COUNT(*) AS cnt
FROM `rdc-cloud`.hdj_cls_article_snapshot
GROUP BY type;
```

| 序号 | 检查项 | 期望结果 | 不通过处理 |
| --- | --- | --- | --- |
| 1 | 最近交易日条数 | 最近交易日为 5 条（候选不足时为实际条数，且不为 0） | 0 条按 RK-01 处理 |
| 2 | 当日明细 | 5 条，target_percent 均 0.19，type 非空 | 见 4.5.5 |
| 3 | 字段完整性 | 全部为 0 | 非 0 说明数据不完整，保留现场联系研发 |
| 4 | 重复推荐 | 0 行 | 检查是否同日多次写入异常，联系研发 |
| 5 | 未来交易日 | 0 | 说明版本或时区异常，检查时区与脚本版本 |
| 6 | 新闻关联 | 0 行 | 说明快照与推荐不匹配，联系研发 |
| 7 | 快照总量 | 总行数 > 0，min_snapshot_date 为首次转写日期 | 0 行说明快照未写入，见 4.5.5 |
| 8 | 当日新增 | 首次跑批应接近总行数；次日起为当日增量 | 与预期差异过大时核对源表当日新闻量 |
| 9 | 唯一键重复 | 0 | 立即停止跑批并联系 DBA/研发 |
| 10 | 类型分布 | 仅 4 种类型 | 出现其他类型说明源查询被改动，联系研发 |

> 关于 WARNING：日志中“忽略 N 条时间无效或股票代码为空的新闻关系”“忽略 N 种米筐无法转换的股票代码”属正常清洗行为（财联社源数据中存在少量脏数据），只要数量与历史量级相当即可，不需处置。

### 4.7 Step 7 业务验证

| 序号 | 验证项 | 方法 | 期望结果 | 责任人 |
| --- | --- | --- | --- | --- |
| 1 | 推荐条数与股票 | 与 SQL 第 2 项结果比对前端/APP 展示 | 条数、代码、名称完全一致 | 算法 + 项目经理 |
| 2 | 推荐日期 | 前端展示的推荐日期 | 为最近交易日（早盘任务为当日） | 算法 |
| 3 | 新闻跳转 | 点击标的查看关联新闻 | 能跳转到对应新闻，type 与新闻类型一致 | 项目经理 |
| 4 | 股票名称 | 前端展示名称 | 与实际证券简称一致，无空值 | 算法 |
| 5 | 权重展示 | 前端/接口中的目标权重 | 0.19（或业务约定的展示口径） | 项目经理 |
| 6 | 历史数据 | 前几个交易日的推荐是否仍可查 | 历史推荐未被清空或错乱 | 项目经理 |
| 7 | 数据同步任务 | 小福牛侧数据同步是否正常 | 无同步失败告警 | 生产运维 |

> 业务验证由项目经理在变更现场确认并签字（附录 D）。若前端有缓存，需按现有机制等待刷新或通知前端刷新后再确认。

### 4.8 Step 8 收尾

| 序号 | 收尾项 | 操作 | 责任人 |
| --- | --- | --- | --- |
| 1 | 记录实际耗时 | 把首次跑批总耗时、各阶段耗时记入运维文档 | 生产运维 |
| 2 | 恢复告警 | 取消扶摇/xxljob/博睿静默，确认告警通道正常 | 生产运维 |
| 3 | 发布完成通知 | 企微群通知变更完成、次日验证安排 | 生产运维 |
| 4 | 备份归档 | 备份目录、crontab 备份、备份表保留 30 天 | 生产运维 / DBA |
| 5 | 文档更新 | 本手册版本记录、日志关键字、新表信息同步到运维文档 | 算法 |
| 6 | 次日值守 | T+1 日 08:31 观察自动任务，09:00 前完成巡检并回报 | 生产运维 |
| 7 | 现场清理 | 清理 /tmp/hdj_bundle 中的临时文件（备份目录保留） | 生产运维 |

## 5 验收标准

上线完成后按下表逐项验收，全部“通过”方可判定上线成功。验收结论按《测试反馈表-慧抢筹优化-20261103.pdf》的格式出具：总结论勾选“全部通过”，并附各验收项结果。

| 编号 | 验收项 | 验收方法 | 期望结果 | 责任人 | 结果 |
| --- | --- | --- | --- | --- | --- |
| AC-01 | 脚本部署正确 | 4.1.5 py_compile、文件时间戳、sha256 | COMPILE_OK，文件为本次上传版本 | 生产运维 | □ |
| AC-02 | 快照表结构 | 4.2.3 SHOW CREATE TABLE / SHOW INDEX | 表存在，唯一键 uk_id_stock_code 正确 | DBA | □ |
| AC-03 | 推荐表 type 列 | 4.2.3 SHOW COLUMNS | type 列存在且允许 NULL | DBA | □ |
| AC-04 | 配置正确 | 4.3.3、4.3.4 | 各段 complete=True，RQ_INIT_OK | 生产运维 | □ |
| AC-05 | 首次跑批成功 | 4.5.2、4.5.3 | 退出码 0，出现成功关键字 | 生产运维 | □ |
| AC-06 | 跑批耗时 | 4.5.3 的 time 输出 | 首次 ≤ 30 分钟；日常目标 ≤ 14 分钟（监控阈值） | 生产运维 | □ |
| AC-07 | 快照数据正确 | 4.6 第 7～10 项 | 行数 > 0，无重复，类型仅 4 种 | 算法 | □ |
| AC-08 | 推荐数据正确 | 4.6 第 1～6 项 | 最近交易日 5 条，字段完整，无未来日期 | 算法 | □ |
| AC-09 | 幂等性 | 同日重跑一次，比对 4.6 第 7、8、1 项 | 快照表行数不增加，推荐条数不变 | 生产运维 | □ |
| AC-10 | CSV 产出 | 4.5.4 | 两个 CSV 时间戳更新，内容可读 | 生产运维 | □ |
| AC-11 | 定时任务 | 4.4.6 | 08:31 单任务，回测任务保留，快照任务已下线 | 生产运维 | □ |
| AC-12 | 次日自动执行 | T+1 日 08:31 后查看日志与数据 | 自动执行成功，数据与手工跑批一致 | 生产运维 | □ |
| AC-13 | 回测任务 | T+1 日 17:30 回测任务执行后查看 hdj_strategy_daily_net | 净值表正常更新，无报错 | 生产运维 | □ |
| AC-14 | 业务确认 | 4.7 | 前端展示与数据库一致，项目经理签字 | 项目经理 | □ |
| AC-15 | 监控告警 | 扶摇、xxljob、博睿 | 无异常告警，告警通道已恢复 | 生产运维 | □ |


## 6 回滚方案

### 6.1 回滚触发条件

出现以下任一情况，立即启动回滚（由项目经理决策，生产运维执行）：

| 编号 | 触发条件 | 判定依据 |
| --- | --- | --- |
| R-01 | 首次跑批失败且 30 分钟内无法定位解决 | 退出码非 0，日志停在某阶段 |
| R-02 | 跑批“成功”但推荐结果为 0 条，推荐表 strategy_code = 2 数据被清空 | 日志“生成 0 条推荐”；SQL 第 1 项无当日数据 |
| R-03 | 推荐结果与业务预期明显不符（股票、条数、日期错乱） | 4.7 业务验证不通过 |
| R-04 | 数据校验项失败且无法快速修复（如唯一键重复、新闻关联缺失） | 4.6 第 4、6、9 项非 0 |
| R-05 | 次日 08:31 自动任务失败，影响早盘推送 | T+1 日日志异常 |
| R-06 | 出现无法解释的数据库异常或锁等待，影响其他任务 | DBA 判定 |

### 6.2 决策与授权

- 回滚由**项目经理**决策，生产运维执行，算法策略提供技术支持。
- 判定回滚后，先在企微群发布“开始回滚”，并记录回滚开始时间。
- 回滚目标时限：**15 分钟内**恢复旧版运行能力并保证当日推荐可用。

### 6.3 回滚步骤

按以下顺序执行，前一步完成后再执行下一步。

#### 6.3.1 第一步：停用新任务，避免自动执行

```bash
# 方式一：把 08:31 那行注释掉（推荐，保留原文便于恢复）
crontab -e
# 在该行前加 #，保存退出

# 确认
crontab -l | grep -n "hdj_main_strategy_daily.sh"
```

#### 6.3.2 第二步：恢复旧版脚本与入口

```bash
docker exec -it <容器ID> bash -lc '
  cd /workspace/hdj_strategy/hdj
  BK=backup/<备份日期>          # 替换为 3.6 生成的备份目录，如 backup/20261104
  cp -p $BK/hdj_strategy.py            ./hdj_strategy.py
  cp -p $BK/hdj_cls_snapshot.py        ./hdj_cls_snapshot.py
  cp -p $BK/config.yaml                ./config.yaml
  cp -p $BK/hdj_main_strategy_daily.sh ./hdj_main_strategy_daily.sh
  chmod +x hdj_main_strategy_daily.sh
  ls -l --time-style=+%F_%T hdj_strategy.py hdj_cls_snapshot.py hdj_main_strategy_daily.sh config.yaml
'
```

恢复后确认入口脚本指回旧脚本：

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && tail -1 hdj_main_strategy_daily.sh'
# 期望输出：python ./hdj_strategy.py
```

#### 6.3.3 第三步：恢复定时任务

```bash
# 直接用备份覆盖（会同时恢复被注释的快照任务与 08:31 任务）
crontab /tmp/crontab_hdj_backup_<备份日期>.txt
crontab -l | grep -n -i -E "hdj|snapshot"
```

> 若备份 crontab 中本来就包含快照任务，恢复后需手工补跑一次快照与策略（顺序：先 hdj_cls_snapshot.py，再 hdj_strategy.py），以保证旧链路的数据完整。

#### 6.3.4 第四步：恢复推荐表数据（仅在数据被破坏时执行）

```sql
-- 1) 清掉新版写入的数据
DELETE FROM `rdc-cloud`.hdj_strategy_recom_stocks WHERE strategy_code = '2';

-- 2) 从备份表恢复（备份表在加列前创建、不含 type 列，故不复制 type）
INSERT INTO `rdc-cloud`.hdj_strategy_recom_stocks
    (id, cal_date, stock_code, stock_name, target_percent, trade_way, strategy_code)
SELECT id, cal_date, stock_code, stock_name, target_percent, trade_way, strategy_code
FROM `rdc-cloud`.bak_hdj_recom_20261104;

-- 3) 核对条数与最近日期
SELECT cal_date, COUNT(*) AS cnt
FROM `rdc-cloud`.hdj_strategy_recom_stocks
WHERE strategy_code = '2'
GROUP BY cal_date ORDER BY cal_date DESC LIMIT 5;
```

#### 6.3.5 第五步：补跑旧链路（按需）

数据恢复后，若需要补出当日推荐，按旧链路顺序执行：

```bash
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && python3 hdj_cls_snapshot.py && python3 hdj_strategy.py'
```

### 6.4 回滚验证

| 序号 | 验证项 | 方法 | 期望结果 |
| --- | --- | --- | --- |
| 1 | 脚本版本 | `ls -l` 与 `tail -1 hdj_main_strategy_daily.sh` | 时间戳为备份时间，入口指向 hdj_strategy.py |
| 2 | 定时任务 | `crontab -l` | 与备份一致，08:31 任务恢复 |
| 3 | 推荐数据 | 4.6 第 1、2 项 | 条数与备份前一致，当日推荐可用 |
| 4 | 前端展示 | 4.7 | 与数据库一致 |
| 5 | 告警 | 扶摇/xxljob | 无新增异常 |

### 6.5 回滚注意事项

1. **不要 DROP 新表、不要删除 type 列**：快照表保留可作为审计与后续重新上线的基础；type 列为可空列，旧脚本不写该列，保留不影响旧链路；前端可能已按 type 适配，删列会造成二次故障。
2. 回滚只回退“运行版本”，不回退“数据库结构”，因此回滚速度快、风险低。
3. 回滚后如需再次上线，必须重新执行第 3 章准备与第 4 章步骤（快照表已存在时按场景 B/C 裁剪）。
4. 回滚全过程需记录：触发原因、回滚开始/结束时间、执行人、数据恢复条数、前端确认结果。
5. 回滚完成后 24 小时内保持值守，确认次日 08:31 旧任务正常。

## 7 风险清单与应对

| 编号 | 风险 | 影响 | 可能性 | 应对措施 | 责任人 |
| --- | --- | --- | --- | --- | --- |
| RK-01 | 当日无候选股票时，脚本以 0 条结果执行“先删后插”，推荐表 strategy_code = 2 被清空 | 前端无推荐，业务影响 | 中 | 跑批后立即看“当日筛选检查”与“生成 N 条推荐”；为 0 时按 6.3.4 恢复数据并联系研发 | 生产运维 + 算法 |
| RK-02 | 脚本不读取 db_port，连接固定走 3306；而生产库登记为 3307 | 首次跑批连接失败，任务无法执行 | 高 | 上线前用 3.4 的连接测试脚本验证实际端口；若仅 3307 可用，需研发改造后上线，或使用可直连 3306 的地址 | 算法 + DBA |
| RK-03 | 首次全量快照数据量大，写入耗时长；单事务在最后统一 commit，期间回滚段增长 | 跑批超时、影响同时段其他任务 | 中 | 变更窗口安排在收盘后；提前在测试环境演练取得实际耗时；监控磁盘与 InnoDB 回滚段 | 生产运维 + DBA |
| RK-04 | 米筐 license 失效、并发限流或网络抖动 | 行情取不到，任务失败 | 中 | 上线前 4.3.4 验证；失败后重跑（幂等）；保留运维文档中的米筐告警通道 | 算法 + 生产运维 |
| RK-05 | 容器或宿主机时区不是东八区 | 交易日错位、推荐日期错误、cron 时间偏移 | 中 | 4.4.5 时区核查；变更后 T+1 日核对推荐日期 | 生产运维 |
| RK-06 | 入口脚本用 `python`，容器内无该命令或指向 Python 2 | 定时任务直接失败 | 低 | 3.3 核查 `python -V`；不可用时改为 python3（4.4.2） | 生产运维 |
| RK-07 | 指标口径变更（不再 shift、按下一交易日映射）导致结果与旧版不同 | 业务方误判为“算错了”；回测曲线与历史不一致 | 高 | 上线前由算法向项目经理/投研说明口径；上线后对比新旧结果并留档；必要时按业务要求调整 | 算法 + 项目经理 |
| RK-08 | zpqc_final_new.csv 被 17:30 回测任务读取，若 CSV 未生成或路径变化 | 回测净值不更新或使用旧数据 | 中 | 保持工作目录与文件名不变；Step 5 校验 CSV；T 日 17:30 后核对净值表 | 生产运维 |
| RK-09 | 同日重复执行覆盖推荐表与 CSV | 若第二次执行时数据源异常，会用异常结果覆盖正常结果 | 低 | 重跑前确认数据源正常；重跑后用 4.6 校验；保留首次日志 | 生产运维 |
| RK-10 | 快照冻结后，财联社修改/删除源新闻，前端按快照 id 跳转可能失效 | 新闻跳转 404 或内容不符 | 中 | 属设计预期（历史可复现优先）；向业务说明；如确需跳转可用性，另行评估按源表跳转 | 算法 + 项目经理 |
| RK-11 | 旧快照定时任务未下线，与新脚本重复取数/写入 | 重复执行、源库压力、日志混乱 | 中 | 4.4.4 严格检查并注释旧任务；用 crontab -l 过滤 snapshot 复核 | 生产运维 |
| RK-12 | 备机文件未同步更新，应急切换后运行旧脚本 | 切换后备机产出与主机不一致 | 高 | Step 1 在主机、备机都执行；附录 D 检查单中单列备机项 | 生产运维 |
| RK-13 | 推荐表历史数据被回填 type 时锁表时间较长 | 变更窗口内短时锁等待 | 低 | 回填 UPDATE 在变更窗口执行；大表可分批复核；必要时 DBA 低峰执行 | DBA |
| RK-14 | 日志文件 logs/wpqc.log 命名沿用旧项目（wpqc），运维容易找错 | 排障时找不到日志 | 低 | 本手册 8.1 明确日志路径；运维文档同步更新 | 算法 + 生产运维 |

## 8 上线后监控与日常运维

### 8.1 日志位置与查看方式

| 文件（容器内绝对路径） | 内容 | 说明 |
| --- | --- | --- |
| /workspace/hdj_strategy/hdj/logs/wpqc.log | 全部 INFO 及以上日志，按天切分 | 沿用旧项目文件名，**慧点睛日志也写入此文件**，不是新建 hdj.log |
| /workspace/hdj_strategy/hdj/logs/error.log | ERROR 级日志，按天切分 | 排障第一入口 |
| /workspace/hdj_strategy/hdj/logs/daily_strategy_exec.log | cron 执行的控制台输出（采用 4.4.3 方案 B 时生成） | 含 report_progress 的实时输出 |
| /workspace/hdj_strategy/hdj/logs/first_run_*.log | 首次跑批的完整输出 | 变更留档 |
| /workspace/hdj_strategy/hdj/logs/backtest_daemon_exec.log | 回测任务输出 | 既有 |

日志保留：TimedRotatingFileHandler 每天 0 点切分，backupCount = 30，即保留 30 天。

```bash
# 实时观察（容器内）
docker exec -it <容器ID> bash -lc 'tail -f /workspace/hdj_strategy/hdj/logs/wpqc.log'

# 查看最近一次执行的阶段进度
docker exec -it <容器ID> bash -lc 'grep -E "开始|完成|进度|筛选检查|推荐表更新" /workspace/hdj_strategy/hdj/logs/wpqc.log | tail -30'

# 只看错误
docker exec -it <容器ID> bash -lc 'tail -50 /workspace/hdj_strategy/hdj/logs/error.log'

# 统计今日是否成功
docker exec -it <容器ID> bash -lc 'grep -c "当日策略计算任务完成" /workspace/hdj_strategy/hdj/logs/wpqc.log'
```

### 8.2 每日巡检（交易日）

| 时间 | 巡检项 | 命令或方法 | 期望结果 |
| --- | --- | --- | --- |
| 08:31 后 5 分钟 | 任务是否启动 | `tail -5 logs/daily_strategy_exec.log` 或 `tail -5 logs/wpqc.log` | 出现“开始慧点睛每日策略任务” |
| 08:45 前 | 任务是否完成 | 查看日志尾部 | 出现“当日策略计算任务完成”，耗时 ≤14 分钟 |
| 08:50 前 | 推荐条数 | SQL 4.6 第 1 项 | 当日 5 条（或业务约定条数） |
| 08:50 前 | 字段完整性 | SQL 4.6 第 3 项 | 全部为 0 |
| 09:00 前 | 前端展示 | 4.7 | 与数据库一致 |
| 每日收盘后 | 回测任务 | 17:30 后查看日志与净值表 | 净值表更新，无报错 |
| 每日 | 磁盘与日志 | `df -h`、统计 logs 目录文件数 | 可用空间 ≥ 20%，日志按天切分正常 |

### 8.3 监控指标与告警阈值

在既有监控体系（扶摇日志、xxljob、博睿/扶摇 zabbix）基础上，建议补充以下与本次变更直接相关的监控项：

| 指标 | 采集方式 | 告警阈值 | 告警方式 | 说明 |
| --- | --- | --- | --- | --- |
| 早盘任务执行耗时 | 日志时间戳差值 | > 14 分钟 | 企微/短信 | 沿用运维文档既有阈值 |
| 任务是否执行 | 日志出现“当日策略计算任务完成” | 交易日 09:00 前未出现 | 企微/短信 | 新增，替代“交易日9点取不到数据”兜底 |
| 数据源连接错误 | error.log 关键字“数据库连接失败” | 连续 1 次 | 企微/短信 | 沿用既有阈值 |
| 当日推荐条数 | SQL 4.6 第 1 项 | = 0（或 ≠5） | 企微/短信 | 新增，对应 RK-01 |
| 快照当日新增 | SQL 4.6 第 8 项 | = 0 且源表有当日新闻 | 企微 | 新增，判断源表或快照写入异常 |
| CPU 峰值 | zabbix | ≥95% 持续 15 分钟 | 企微/短信 | 沿用既有阈值 |
| 磁盘使用率 | zabbix | ≥85% | 企微 | 沿用既有阈值 |

### 8.4 常见故障处置

| 现象 | 定位 | 处置 |
| --- | --- | --- |
| 08:31 后日志无输出 | ①cron 是否运行 ②容器是否运行 ③docker exec 是否报错 | 依次检查 `systemctl status cron`、`docker ps`、手工执行 4.4.6 第 3 项 |
| 日志停在“财联社源表查询完成” | 目标库连接、快照表 | 按 3.4 测试连接；按 4.2.3 校验表 |
| 日志停在“开始请求米筐日线行情” | 米筐接口、网络、许可 | 4.3.4 复测；联系米筐；重跑 |
| 报错 `Access denied for user` | 账号/口令/授权 | 核对 config.yaml 与 DBA 授权 |
| 报错 `Unknown database 'rdc-cloud'` | 库名错误 | 核对 rdc_db_name |
| 报错 `Table ... doesn't exist` | 表未建或被删 | 执行 4.2.1 |
| 报错 `部分推荐股票找不到关联新闻 ID` | 快照与代码匹配 | 保留现场，联系研发；推荐表未变更 |
| 推荐条数为 0 | 当日无候选 / 门槛未通过 / 源数据异常 | 按 RK-01 处理：先恢复数据，再定位 |
| 任务耗时明显变长 | 源表增大、米筐变慢、磁盘 IO | 查看分阶段耗时日志，评估是否调整 cron 时间或优化 |
| 回测任务失败并提示 CSV 不存在 | 早盘任务未产出 CSV | 补跑早盘任务；检查工作目录 |

### 8.5 重跑标准操作（SOP）

适用场景：早盘任务失败、数据校验不通过、需要补数据。

```bash
# 1) 记录重跑原因与开始时间
# 2) 确认数据源可用（DB、米筐）
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && python3 - <<PY
import yaml, rqdatac
cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["rq_api"]
rqdatac.init(cfg["license"], cfg["key"]); print("RQ_OK")
PY'

# 3) 重跑（交互观察）
docker exec -it <容器ID> bash -lc 'set -o pipefail; cd /workspace/hdj_strategy/hdj && time python3 hdj_strategy_v02.py --config ./config.yaml 2>&1 | tee logs/rerun_$(date +%Y%m%d_%H%M).log; echo EXIT_CODE=$?'

# 4) 按 4.6 重新校验，5) 记录重跑结果
```

重跑注意：

1. 重跑是幂等的：快照表因 INSERT IGNORE 不会重复写入；推荐表按 strategy_code = 2 先删后插，结果与上次一致（前提是数据源一致）。
2. 同一天多次重跑不会累积推荐数据，但会覆盖 CSV 文件；若回测已执行过，需评估是否重新回测。
3. 重跑前务必确认不是“数据源异常”导致上次失败，否则会用异常结果覆盖正常数据。

### 8.6 数据与容量维护

| 维护项 | 频率 | 操作 | 责任 |
| --- | --- | --- | --- |
| 日志清理 | 自动（保留 30 天） | 确认 logs 目录按天切分，超期文件自动删除；磁盘紧张时手工清理 30 天前文件 | 生产运维 |
| 快照表容量 | 每周 | `SELECT COUNT(*), MIN(first_snapshot_date) FROM hdj_cls_article_snapshot;` 观察增长趋势 | DBA |
| 快照表清理 | 按需（不早于 1 年） | 冻结表是历史可复现的基础，**原则上不清理**；确需清理需算法评估并报备 | 算法 + DBA |
| 推荐表备份表清理 | 变更后 30 天 | `DROP TABLE bak_hdj_recom_<日期>;` | DBA |
| 容器内备份目录清理 | 30 天后 | `rm -rf /workspace/hdj_strategy/hdj/backup/<日期>` | 生产运维 |
| 数据库备份 | 每日收盘后（既有机制） | 沿用现有小福牛 MySQL 备份策略 | DBA |
| 配置变更留档 | 每次变更 | config.yaml 改动需记录键名与变更人，口令不入档 | 生产运维 |

## 9 附录

### 附录 A 脚本逻辑说明（hdj_strategy_v02.py）

本节面向需要理解或排查结果的运维与研发人员，说明脚本做了什么、按什么顺序做、失败会怎样。

#### A.1 总体流程

一次执行分为两大阶段、共 9 个步骤：

| 阶段 | 步骤 | 主要动作 | 失败表现 |
| --- | --- | --- | --- |
| 阶段一 快照 | 1 | 读取 config.yaml，校验 database / rq_api | 抛 ValueError，任务不执行 |
| 阶段一 快照 | 2 | 连接财联社源库、RDC-CLOUD 库（各重试 3 次，间隔 2 秒） | 抛 RuntimeError，任务不执行 |
| 阶段一 快照 | 3 | 查询 lian_v1_article（4 种 type），JSON_TABLE 展开 stocks | 空数据仅告警，继续下一步 |
| 阶段一 快照 | 4 | 批量 INSERT IGNORE 写入快照表（2000 条/批），最后统一 commit | 回滚并抛错 |
| 阶段二 计算 | 5 | 从快照表读取全量关系（只读快照，不再访问财联社） | 空则抛错 |
| 阶段二 计算 | 6 | 清洗、交易日映射、股票代码转换、去重、过滤北交所 | 抛错或跳过脏数据 |
| 阶段二 计算 | 7 | 米筐日线行情 → 10 日累计涨幅 → 10 日成交额斜率 → 下一交易日映射 | 无行情则抛错 |
| 阶段二 计算 | 8 | 合并新闻与指标，涨幅 <12% 过滤，按交易日取斜率 Top5，权重 0.19 | 0 条时返回空结果 |
| 阶段二 计算 | 9 | 匹配新闻 ID 与股票名称 → 写 CSV → 事务写推荐表 | 缺 id 则拒绝写入 |

> 关键设计：阶段一先“冻结”财联社当天可见的关系，阶段二只读快照。因此**即使当天财联社修改或删除了新闻，历史推荐结果也不会变**；同一天重跑也不会重复写快照。

#### A.2 阶段一：快照转写

- 源查询：`lian_v1_article` 与 `JSON_TABLE` 联表，把 `stocks`（逗号分隔）拆成多行；仅取 type ∈ {20014, 20015, 20021, 20025}；不带日期条件（首次运行会把源表当前全量历史一次性落库，之后每日只增量新增）。
- 清洗：剔除 stock_code 为 NULL 的行；按 (id, stock_code) 去重（保留第一条）；stock_code 去首尾空格。
- 写入：`INSERT IGNORE`，每 2000 条一批，全部批次完成后统一 `commit`。
- 幂等：唯一键 (id, stock_code) + INSERT IGNORE，重复关系直接跳过，不覆盖首次版本；`first_snapshot_date` 记录首次落库日期。
- 空数据保护：源表返回 0 条时只记 WARNING，**不会清空快照表历史数据**，随后阶段二会因“快照表没有可用新闻关系”而报错退出（推荐表不受影响）。

#### A.3 阶段二：数据清洗与计算

| 处理 | 规则 | 目的 |
| --- | --- | --- |
| 时间清洗 | formatted_time 转 datetime，失败置空并剔除；code 去空白后剔除空值 | 剔除脏数据 |
| 交易日映射 | `dt_1 = 新闻时间 - 8 小时 30 分`；取 `dt_1` 的日期；用米筐 `get_next_trading_date(n=1, market=cn)` 取下一交易日作为 trade_date | 把新闻归入其影响的交易日（早于 08:30 的新闻算前一日，节假日顺延） |
| 代码转换 | `rqdatac.id_convert` 批量转换（如 sz300065 → 300065.XSHE）；批量失败时逐个转换，无法转换的剔除并告警 | 得到米筐标准代码 |
| 过滤北交所 | 剔除代码含 BJSE 的记录 | 与旧策略保持一致 |
| 去重 | 按 (trade_date, order_book_id) 去重，保留最后一条 | 一只股票每个交易日只保留一条新闻关系 |

#### A.4 指标口径（本次变更重点）

| 指标 | 计算方式 | 说明 |
| --- | --- | --- |
| cum_return_10d | `close / close.shift(10) - 1) × 100`，按股票分组 | 10 个交易日累计涨幅（%） |
| total_turnover_slope_10d | 对过去 10 个交易日的成交额（x，单位 1e7）与 Excel 日期序号（y）做线性回归，取斜率 | 成交额随时间的变化趋势；窗口内成交额完全相同则斜率记 0 |
| next_trade_date | 每个行情日期的下一交易日 | 指标适用日期 |
| 指标映射 | 行情日 d 的指标 → 交易日 d+1；**不再执行 shift(1)** | 早盘即可用上一交易日收盘数据生成当日推荐 |
| 日期上限 | 只保留 trade_date ≤ 当日 的指标 | 避免生成未来交易日的推荐 |

> 口径变化说明：旧版先对指标 shift(1)，再按“行情日期 = 新闻交易日”合并，早盘执行时当日日线尚未生成，容易出现当日指标缺失；新版改为“行情日 d 的指标用于 d 的下一交易日”，同一组数值的对应关系保持一致，但不再依赖当日日线。**该变化会使新旧版本的推荐结果存在差异**，上线前需业务确认（见 RK-07）。

#### A.5 选股规则

1. 新闻与指标按 (trade_date, order_book_id) 左连接；
2. 过滤 `cum_return_10d < 12`（10 日累计涨幅小于 12%）；
3. 按 trade_date 分组，取 `total_turnover_slope_10d` 最大的 5 只；
4. 每只权重固定 0.19；
5. 输出字段 TRADE_DT / TICKER / type / TARGET_WEIGHT。

> 每个交易日最多 5 只；候选不足 5 只时为实际条数；当日无候选时为 0 条（对应 RK-01）。

#### A.6 新闻 ID 与股票名称、落库

- 新闻 ID 匹配：按股票数字代码匹配快照记录，优先取与推荐 type 相同的新闻，再取时间 ≤ 推荐交易日中最近的一条；找不到则 id 为空。
- 股票名称：`rqdatac.instruments` 获取证券简称（symbol）。
- 写入前校验：只要有任意一条推荐缺 id，直接抛错“部分推荐股票找不到关联新闻 ID，拒绝写入不完整结果”，**不修改推荐表**。
- 写入方式：同一事务内 `DELETE FROM hdj_strategy_recom_stocks WHERE strategy_code = 2`，再批量 INSERT；失败则整体回滚。
- 空结果：允许 0 条，此时执行 DELETE 后不插入任何行（**这是唯一会清空当日推荐的路径**，见 RK-01）。

#### A.7 关键常量与可调参数

| 常量 | 值 | 说明 |
| --- | --- | --- |
| SNAPSHOT_TABLE | hdj_cls_article_snapshot | 快照表名 |
| RECOMMEND_TABLE | hdj_strategy_recom_stocks | 推荐表名 |
| STRATEGY_CODE | 2 | 慧点睛策略标识 |
| NEWS_TYPES | 20014, 20015, 20021, 20025 | 参与计算的新闻类型 |
| INSERT_BATCH_SIZE | 2000 | 快照批量写入条数 |
| MAX_RETRIES / RETRY_DELAY_SECONDS | 3 / 2 秒 | 数据库连接重试 |
| PRICE_START_DATE | 2025-04-01 | 行情起始日期（硬编码） |
| 斜率窗口 | 10 个交易日 | 成交额斜率 |
| 涨幅阈值 | 12% | 10 日累计涨幅上限 |
| 每日选股数 | 5 | 每个交易日最多 5 只 |
| TARGET_WEIGHT | 0.19 | 单票目标权重 |

> 以上参数如需调整（如涨幅阈值、选股数量、行情起始日期），必须走变更流程并重新评估历史回测，禁止上线现场直接修改。

#### A.8 数据库表结构与字段映射

推荐表 hdj_strategy_recom_stocks（本次仅新增 type 列）：

| 列 | 类型 | 本次脚本写入内容 |
| --- | --- | --- |
| recom_id | INT AUTO_INCREMENT | 自增，脚本不写 |
| id | INT | 匹配到的财联社新闻 ID |
| strategy_code | VARCHAR(20) | 固定 2 |
| stock_code | VARCHAR(20) | 米筐代码，如 300065.XSHE |
| stock_name | VARCHAR(50) | 米筐证券简称 |
| type | INT（本次新增） | 匹配到的新闻类型 |
| trade_way | VARCHAR(20) | 固定 1（买入） |
| target_percent | DECIMAL(5,2) | 固定 0.19 |
| cal_date | DATE | 推荐适用的交易日 |
| update_time | TIMESTAMP | 自动维护 |

快照表 hdj_cls_article_snapshot（本次新增）：结构见 4.2.1，字段为 snap_id、id、formatted_time、stock_code、type、first_snapshot_date、update_time。

#### A.9 耗时构成（首次与日常）

| 阶段 | 首次 | 日常 | 主要影响因素 |
| --- | --- | --- | --- |
| 配置与连接 | 秒级 | 秒级 | 网络 |
| 源表查询 | 数秒～数十秒 | 同左 | 财联社表数据量、索引 |
| 快照写入 | 1～10 分钟 | 秒级～1 分钟 | 首次全量、后续仅新增（但每日仍会全量读取并尝试写入） |
| 快照读取与清洗 | 秒级 | 秒级～1 分钟 | 快照表数据量 |
| 交易日映射 | 秒级～1 分钟 | 同左 | 不同日期数量、米筐接口 |
| 代码转换 | 秒级～1 分钟 | 同左 | 原始代码种类数 |
| 米筐日线行情 | 1～3 分钟 | 同左 | 股票数量、区间长度、米筐限流 |
| 斜率计算 | 1～3 分钟 | 同左 | 股票数 × 交易日数（逐股票 Python 循环） |
| 落库 | 秒级 | 秒级 | 推荐条数 |

#### A.10 主要函数清单

| 函数 | 职责 |
| --- | --- |
| load_config | 读取并校验 YAML 配置 |
| initialize_rqdatac | 用 rq_api 凭据初始化米筐 |
| get_db_conf / connect_mysql | 取数据库配置、建立连接（重试 3 次） |
| fetch_source_rows / write_snapshot | 源表取数、批量写快照 |
| snapshot_cls_data | 阶段一入口，管理两个库连接 |
| read_snapshot_data | 只读快照表 |
| normalize_news_data / convert_stock_codes | 清洗、交易日映射、代码转换 |
| calculate_volume_slope_excel_reversed | 10 日成交额斜率 |
| build_recommendations | 指标计算、筛选、选股 |
| attach_news_and_names | 补新闻 ID 与股票名称 |
| write_recommendations | 事务更新推荐表 |
| run | 串起全流程，输出 CSV 与数据库 |
| report_progress | 同时写日志与标准输出（供运维观察） |


### 附录 B 报错速查表

| 报错或现象（日志原文关键字） | 原因 | 处置 | 是否影响已有数据 |
| --- | --- | --- | --- |
| 配置文件缺少 database 节点 | config.yaml 为空、YAML 语法错误、缩进错误 | 用 `python3 -c "import yaml;print(yaml.safe_load(open('config.yaml')))"` 定位；按 4.3.2 修正 | 否（任务未开始） |
| 配置文件缺少 rq_api 节点，或该节点不是键值配置 | 未配置 rq_api 段 | 按 4.3.2 补齐 license/key | 否 |
| 配置文件 rq_api.license 必须是非空字符串 | license 为空或用了中文引号 | 修正引号与内容，重新自检 4.3.3 | 否 |
| 配置文件缺少 source_db 数据库连接参数 | 分库配置四项不齐或键名拼写错误 | 核对 3.5 键名；同库部署时检查 db_* 是否齐全 | 否 |
| 财联社源库数据库连接失败，已重试 3 次 | 地址/端口/账号/白名单/网络 | 3.4 连通性测试；确认端口（见 RK-02） | 否 |
| RDC-CLOUD数据库连接失败，已重试 3 次 | 同上（目标库） | 同上 | 否 |
| ERROR 1045 Access denied for user | 账号或口令错误 | 与项目经理/DBA 核对 | 否 |
| ERROR 1049 Unknown database | 库名错误 | 核对 rdc_db_name / source_db_name | 否 |
| ERROR 1146 Table ... doesn't exist | 快照表未建 | 执行 4.2.1 | 否 |
| ERROR 1142 DELETE command denied | 账号缺 DELETE/INSERT 权限 | DBA 授权 | 否（事务回滚） |
| 快照表没有可用新闻关系，无法计算策略 | 快照表为空（未跑过、被清空、源查询无数据） | 确认源表有数据、快照表已建；重跑 | 否（推荐表未改动） |
| 快照数据缺少字段 | 快照表结构被改动 | 核对表结构；恢复标准 DDL | 否 |
| 快照新闻中没有时间和股票代码均有效的记录 | 源数据全部脏或时间格式异常 | 抽查源表 formatted_time、stock_code | 否 |
| 快照新闻中没有可转换的米筐股票代码 | 米筐 id_convert 失败（网络/许可/代码格式） | 4.3.4 验证米筐；抽查 stock_code 格式 | 否 |
| 米筐未返回行情数据 | 股票列表为空、日期区间无数据、许可异常 | 核对 PRICE_START_DATE；重试；联系米筐 | 否 |
| 部分推荐股票找不到关联新闻 ID，拒绝写入不完整结果 | 快照与代码匹配异常 | 保留现场联系研发；推荐表保持旧数据 | 否（主动拒绝写入） |
| 生成 0 条推荐 / 当日筛选检查 候选=0 | 当日无新闻候选，或涨幅门槛全部未通过 | 按 RK-01：立即停止，恢复数据（6.3.4），联系研发 | **是（会清空 strategy_code=2）** |
| 任务无任何输出且 cron 无记录 | cron 未生效、容器未运行、docker exec 失败 | 检查 cron 服务、容器状态、手工执行 4.4.6 | 否 |
| command not found: python | 容器无 python 命令 | 改为 python3（4.4.2） | 否 |
| 日志停在斜率计算进度中间 | 股票数多、CPU/IO 瓶颈 | 观察是否仍有进度输出；必要时延长窗口重跑 | 否 |
| rqdatac.init 报错 / 连接超时 | 米筐许可失效、并发超限、网络 | 4.3.4 复测；错峰重跑；联系米筐 | 否 |

### 附录 C 命令速查卡

```bash
# ---------- 现状识别 ----------
crontab -l | grep -n -i -E "hdj|snapshot"
docker ps --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && ls -l --time-style=+%F_%T && cat hdj_main_strategy_daily.sh'

# ---------- 备份 ----------
crontab -l > /tmp/crontab_hdj_backup_$(date +%Y%m%d).txt
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && BK=backup/$(date +%Y%m%d) && mkdir -p $BK && cp -p hdj_strategy.py hdj_cls_snapshot.py hdj_main_strategy_daily.sh config.yaml logging.yaml logconfig.py zpqc_final_new.csv $BK/ && ls -l $BK/'

# ---------- 上传与替换 ----------
docker cp /tmp/hdj_bundle/hdj_strategy_v02.py        <容器ID>:/workspace/hdj_strategy/hdj/
docker cp /tmp/hdj_bundle/hdj_main_strategy_daily.sh <容器ID>:/workspace/hdj_strategy/hdj/
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && chmod +x hdj_main_strategy_daily.sh && python3 -m py_compile hdj_strategy_v02.py && echo COMPILE_OK'

# ---------- 配置与连接自检 ----------
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && python3 -c "import yaml;c=yaml.safe_load(open(\"config.yaml\"));print(sorted(c[\"database\"].keys()));print(sorted(c[\"rq_api\"].keys()))"'
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && python3 -c "import yaml,rqdatac;c=yaml.safe_load(open(\"config.yaml\"))[\"rq_api\"];rqdatac.init(c[\"license\"],c[\"key\"]);print(\"RQ_INIT_OK\")"'

# ---------- 定时任务 ----------
crontab -l | grep -c "hdj_main_strategy_daily.sh"
systemctl status cron | head -5
docker exec -it <容器ID> bash -lc 'date; date -u; cat /etc/timezone'

# ---------- 首次跑批 ----------
docker exec -it <容器ID> bash -lc 'set -o pipefail; cd /workspace/hdj_strategy/hdj && time python3 hdj_strategy_v02.py --config ./config.yaml 2>&1 | tee logs/first_run_$(date +%Y%m%d_%H%M).log; echo EXIT_CODE=$?'

# ---------- 日志 ----------
docker exec -it <容器ID> bash -lc 'tail -f /workspace/hdj_strategy/hdj/logs/wpqc.log'
docker exec -it <容器ID> bash -lc 'grep -E "开始|完成|进度|筛选检查|推荐表更新" /workspace/hdj_strategy/hdj/logs/wpqc.log | tail -30'
docker exec -it <容器ID> bash -lc 'tail -50 /workspace/hdj_strategy/hdj/logs/error.log'

# ---------- 回滚 ----------
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && BK=backup/<备份日期> && cp -p $BK/hdj_strategy.py $BK/hdj_cls_snapshot.py $BK/config.yaml $BK/hdj_main_strategy_daily.sh ./ && chmod +x hdj_main_strategy_daily.sh'
crontab /tmp/crontab_hdj_backup_<备份日期>.txt
```

### 附录 D 上线检查单（可打印）

变更名称：慧点睛 hdj_strategy_v02.py 上线　　变更日期：____________　　执行人：____________

| 序号 | 阶段 | 检查项 | 通过标准 | 结果 | 时间 |
| --- | --- | --- | --- | --- | --- |
| 1 | 准备 | 环境参数登记表填写完整 | 3.1 全部填写 | □ | |
| 2 | 准备 | 现状识别与场景判定 | 判定为 A / B / C / D | □ | |
| 3 | 准备 | python3 与依赖 | DEPS_OK | □ | |
| 4 | 准备 | 米筐网络与 DB 连通 | 全部 OK | □ | |
| 5 | 准备 | 时区核查 | Asia/Shanghai | □ | |
| 6 | 准备 | 脚本与配置备份 | 备份目录含 6 个文件 | □ | |
| 7 | 准备 | crontab 备份 | 备份文件已生成 | □ | |
| 8 | 准备 | 推荐表数据备份 | bak 表已建 | □ | |
| 9 | Step 1 | 文件上传（主机） | 时间戳为本次 | □ | |
| 10 | Step 1 | 文件上传（备机） | 时间戳为本次 | □ | |
| 11 | Step 1 | sha256 校验 | 与研发提供一致 | □ | |
| 12 | Step 1 | py_compile | COMPILE_OK | □ | |
| 13 | Step 1 | 入口脚本内容 | 调用 hdj_strategy_v02.py | □ | |
| 14 | Step 2 | 快照表创建 | 表存在 | □ | |
| 15 | Step 2 | 唯一键 uk_id_stock_code | 存在且含两列 | □ | |
| 16 | Step 2 | type 列 | 存在，允许 NULL | □ | |
| 17 | Step 2 | 历史 type 回填 | 执行完成无报错 | □ | |
| 18 | Step 3 | config.yaml 键名 | 各段 complete=True | □ | |
| 19 | Step 3 | 米筐初始化 | RQ_INIT_OK | □ | |
| 20 | Step 3 | 配置权限 | 600 | □ | |
| 21 | Step 4 | crontab 08:31 单任务 | 仅 1 条 | □ | |
| 22 | Step 4 | 旧快照任务已注释 | 无有效快照任务 | □ | |
| 23 | Step 4 | 回测任务保留 | 未被修改 | □ | |
| 24 | Step 4 | cron 服务运行 | active (running) | □ | |
| 25 | Step 5 | 首次跑批退出码 | EXIT_CODE=0 | □ | |
| 26 | Step 5 | 成功关键字 | 出现“当日策略计算任务完成” | □ | |
| 27 | Step 5 | 跑批耗时 | 首次 ≤30 分钟 | □ | |
| 28 | Step 5 | CSV 产出 | 两个文件已更新 | □ | |
| 29 | Step 6 | 推荐条数 | 最近交易日 5 条 | □ | |
| 30 | Step 6 | 字段完整性 | 全部为 0 | □ | |
| 31 | Step 6 | 快照唯一键重复 | 0 | □ | |
| 32 | Step 6 | 无未来交易日 | 0 | □ | |
| 33 | Step 7 | 前端与数据库一致 | 一致 | □ | |
| 34 | Step 7 | 新闻跳转 | 可跳转且 type 一致 | □ | |
| 35 | Step 8 | 告警恢复 | 通道正常 | □ | |
| 36 | Step 8 | 完成通知 | 已发布 | □ | |
| 37 | T+1 | 08:31 自动执行 | 成功，≤14 分钟 | □ | |
| 38 | T+1 | 当日数据校验 | 同 Step 6 | □ | |
| 39 | T+1 | 17:30 回测 | 净值表更新 | □ | |
| 40 | 验收 | 项目经理签字确认 | 已签字 | □ | |

项目经理签字：____________　　生产运维签字：____________　　算法签字：____________

### 附录 E 本次文件清单与校验

| 文件 | 用途 | 本次是否变更 | 部署位置（容器内） |
| --- | --- | --- | --- |
| hdj_strategy_v02.py | 策略主脚本（快照 + 计算 + 落库） | 新增/覆盖 | /workspace/hdj_strategy/hdj/ |
| hdj_main_strategy_daily.sh | 定时任务入口 | 覆盖（内容指向 v02） | /workspace/hdj_strategy/hdj/ |
| create_hdj_cls_article_snapshot.sql | 快照表 DDL | 新增（仅 DBA 执行，不部署到容器） | — |
| testsql.sql | 建表 + 加列可重复执行脚本 | 新增（仅 DBA 执行） | — |
| config.yaml | 配置（rq_api、分库） | 就地修改 | /workspace/hdj_strategy/hdj/ |
| logging.yaml / logconfig.py | 日志配置 | 不变 | /workspace/hdj_strategy/hdj/ |
| hdj_backtest.py / hdj_main_backtest_daily.sh | 回测任务 | 不变 | /workspace/hdj_strategy/hdj/ |
| hdj_strategy.py / hdj_cls_snapshot.py | 旧版脚本 | 保留（回滚用） | /workspace/hdj_strategy/hdj/ |

文件校验（上传后在宿主机与容器内各执行一次，结果记入检查单）：

```bash
sha256sum hdj_strategy_v02.py hdj_main_strategy_daily.sh
docker exec -it <容器ID> bash -lc 'cd /workspace/hdj_strategy/hdj && sha256sum hdj_strategy_v02.py hdj_main_strategy_daily.sh'
```

| 文件 | 大小（字节） | sha256（研发提供，执行前填写） |
| --- | --- | --- |
| hdj_strategy_v02.py | 【填写】 | 【填写】 |
| hdj_main_strategy_daily.sh | 【填写】 | 【填写】 |

### 附录 F 与《慧抢筹线上变更需求》四步法的对照

两份《慧抢筹线上变更需求》（V1.0 2026-03-10、V1.1 2026-11-03）规定变更按“更新文件 → 新增 RDC MySQL 表 → 修改定时任务 → 初次跑批”四步执行。本手册与该模板一一对应，并按慧点睛的实际脚本补充了配置、校验与回滚：

| 变更需求四步法 | 本手册对应章节 | 本手册的补充 |
| --- | --- | --- |
| 一、更新文件（下载代码、进入 docker、拷贝文件） | 4.1 Step 1 | 备份、sha256 校验、py_compile、依赖自检、主备双机同步 |
| 二、新增 RDC MySQL 表（wpqcdaily.sql） | 4.2 Step 2 | 慧点睛为“新增快照表 + 推荐表加 type 列”，含可重复执行脚本与结构校验 |
| 三、修改定时任务（strategy.py → strategy02.py） | 4.4 Step 4 | 单任务化、下线旧快照任务、日志重定向、时区核查、cron 复核 |
| 四、初次启动（python3 strategy02.py，观察日志） | 4.5 Step 5 | 逐条关键日志与耗时预期、产物检查、失败处置 |
| —（模板未覆盖） | 4.3 Step 3 | 配置文件与米筐凭据调整、配置自检（慧点睛 v02 新增） |
| —（模板未覆盖） | 4.6～4.7、第 5 章 | 数据校验 SQL 与验收标准 |
| —（模板未覆盖） | 第 6 章 | 回滚方案与数据恢复 |
| —（模板未覆盖） | 第 7、8 章 | 风险清单、监控阈值、巡检与重跑 SOP |

### 附录 G 上线前待确认事项清单

以下事项在本手册中以占位符或建议值表示，需在上线前由对应责任人确认并回填，确认后本手册方可定稿发布。

| 序号 | 待确认事项 | 影响章节 | 责任人 | 确认结果 |
| --- | --- | --- | --- | --- |
| 1 | 生产 MySQL 主机、端口、库名、账号（含端口是否为 3307） | 3.1、3.4、RK-02 | 项目经理 / DBA | |
| 2 | 米筐生产 license / key 及有效期 | 3.5、4.3.4 | 算法 / 项目经理 | |
| 3 | 变更执行日期与窗口（登记 2026-11-04 收盘后） | 2.6 | 项目经理 | |
| 4 | 现网是否仍存在独立快照定时任务 | 3.2、4.4.4 | 生产运维 | |
| 5 | 现网容器 ID 与容器内工作目录 | 3.1、全篇 | 生产运维 | |
| 6 | 备机 10.32.108.61 是否纳入本次文件同步 | RK-12 | 生产运维 | |
| 7 | 指标口径变更（不再 shift、按下一交易日映射）业务侧是否确认 | 2.4、A.4、RK-07 | 项目经理 / 投研 | |
| 8 | 前端/APP 展示与缓存刷新机制，验证时间点 | 4.7 | 项目经理 | |
| 9 | 告警静默方式（扶摇、xxljob、博睿是否支持） | 3.7 | 生产运维 | |
| 10 | 验收签字人与测试反馈表出具人 | 第 5 章、附录 D | 项目经理 | |
| 11 | 是否需要在本次一并调整 08:31 的时间点（视首次耗时） | 4.4.3、8.3 | 项目经理 / 运维 | |
| 12 | 本手册的文档编号、编制/审核人 | 封面 | 项目经理 | |

:::pagebreak

### 文档修订记录

| 版本 | 日期 | 修订人 | 修订内容 |
| --- | --- | --- | --- |
| V1.0 | 2026-11-09 | 【待填】 | 初版：按 hdj_strategy_v02.py 逻辑与《慧抢筹线上变更需求》四步法编制完整上线实施与运维操作手册 |
