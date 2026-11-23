# research · 研究方向

> **一个想法一个目录。** 目录名带月份前缀，`ls research/` 本身就是一条时间线。

```
research/
├── README.md              ← 你在这里
├── _template/             复制即用的模板
├── 2026-11_<slug>/        第一次研究
└── 2026-12_<slug>/
```

---

## 怎么开一个新研究

```bash
cd ~/my_quantproject/FactorResearch
cp -r research/_template research/2026-11_vol_ratio_bar_choice
cd research/2026-11_vol_ratio_bar_choice
# 然后按下面的五步走
```

**不要自己造结构。** 复制模板，改内容。

---

## 一个研究的五步（与 7 道门对应）

| 步 | 文件 | 对应门 | 做完的标志 |
|---|---|---|---|
| 1 | `idea.md` | 门 1 | 四问都答了，**尤其是失败判据** |
| 2 | `registry/` + `trials_log` | 门 2 | `factors.yaml` 有记录、记账有一行 |
| 3 | `run.py` → `result/` | 门 3–5 | IC 表 / 分层 / 组合层 / 脆弱性齐了 |
| 4 | `run.py --audit` | 门 6 | 前视 / DSR / PBO / PI 都跑了 |
| 5 | `conclusion.md` | 门 7 | 状态明确 + 证据出处 + **退役条件** |

---

## 目录约定

```
2026-11_vol_ratio_bar_choice/
├── README.md          一句话：做什么、现在到哪一步（随时更新）
├── idea.md            假设（填完就不要再改，改了另开一篇）
├── config.yaml        本次研究的参数（不含凭证）
├── run.py             唯一执行入口（不用 notebook 做正式结论）
├── result/            产物（gitignored）
│   ├── ic_summary.csv
│   ├── decile.csv
│   ├── backtest.csv
│   ├── fragility.csv
│   └── audit/
└── conclusion.md      判决（写完后 add 到 docs/03_knowledge/ 的引用）
```

---

## 命名

```
<YYYY-MM>_<slug>
```

`slug` 用 **snake_case 英文**（不要中文——避免跨平台路径问题）：

```
✅ 2026-11_vol_ratio_bar_choice
✅ 2026-11_amihud_orthogonal_true_mktcap
❌ 2026-11_成交量斜率
❌ 2026-11-1测试
```

---

## 什么时候该合到 `src/`

同一个函数出现在**第二个**研究目录时，搬进 `src/factorlab/`，
并在原处留一行 import（不要留两份实现）。

> 旧项目的教训：`strategy01~08.py` 之间有约 40% 的重复代码，
> 改一处要改八处，最后没人敢动。

---

## 什么时候该归档

研究结论已经写进 `docs/03_knowledge/`、且 3 个月没有再改动 → 移到 `research/_archive/`。
**不要删** —— 它是"当时怎么想的"的唯一记录。

---

## 反模式

| ❌ | 为什么 |
|---|---|
| 直接把 notebook 当结论 | 22 MB 的 `test01.ipynb` 不是文档，三个月后自己都看不懂 |
| 结果只在聊天里说过 | 没有记录 = 不存在 |
| 一个目录放三个不相关的研究 | 找不回来 |
| 结论写进 `docs/03_knowledge/` 但没走完 7 道门 | 会污染"知识"，比没写更糟 |
| 参数放在代码里 | 改参数 = 一次新试验，必须能在 config 里看到 |
