"""研究执行入口 —— 一个文件跑完 7 道门。

用法::

    python run.py --stage factor          # 门 3：IC / 分层 / 覆盖率
    python run.py --stage independence    # 门 4：正交化 + 置换重要性
    python run.py --stage portfolio       # 门 5：组合层 + 脆弱性 + 块自举
    python run.py --stage audit           # 门 6：前视 / DSR / PBO / 禁运
    python run.py --stage all             # 门 3 → 6 顺序全跑

产物写到 ``result/``。**所有正式结论都从这里出，不从 notebook 出。**

三条铁律在本文件里的落地：

1. **PIT**：每个 stage 都会跑一次前视体检（门 6 之前的 stage 只跑注册表检查）。
2. **记账**：每个 stage 开跑**之前**先往 ``registry/trials_log.csv`` 追加一行。
3. **先判死**：stage 顺序固定为 factor → independence → portfolio → audit；
   ``--stage all`` 不会跳过前面的门。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
RESULT = HERE / "result"

STAGES = ["factor", "independence", "portfolio", "audit"]


# ---------------------------------------------------------------- 配置
def load_cfg() -> dict:
    path = HERE / "config.yaml"
    if not path.exists():
        raise SystemExit("缺少 config.yaml（从 research/_template 复制时应已带上）")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def run_id(cfg: dict) -> str:
    rid = cfg.get("meta", {}).get("run_id", "")
    if not rid or rid.startswith("YYYY"):
        raise SystemExit("请先在 config.yaml 里填 meta.run_id（格式 YYYYMMDD-<slug>）")
    return rid


def factor_directions(cfg: dict, available: list[str]) -> dict[str, float]:
    """``{因子列: 权重}``，权重符号即方向，权重绝对值归一。"""
    raw = {f["id"]: float(f.get("direction", 1)) for f in cfg.get("factors", [])
           if f["id"] in available}
    total = sum(abs(v) for v in raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


# ---------------------------------------------------------------- 门 2：记账
def open_trial(cfg: dict, stage: str, n_trials: int = 1) -> None:
    """**先开账再跑** —— 防止"结果不好就不记了"。"""
    from factorlab.audit.trials import log_trial

    idea = HERE / "idea.md"
    headline = ""
    if idea.exists():
        lines = [ln.strip("# ").strip() for ln in idea.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("---")]
        headline = next((ln for ln in lines if ln.startswith("假设")), lines[0] if lines else "")[:200]

    log_trial(
        run_id=run_id(cfg),
        hypothesis=headline,
        object=",".join(f["id"] for f in cfg.get("factors", [])),
        params=str({f["id"]: f.get("params", {}) for f in cfg.get("factors", [])})[:200],
        sample=f"{cfg['data']['start']}~{cfg['data']['end']}",
        metric=f"stage:{stage}",
        value=None,
        passed="tbd",
        n_trials=n_trials,
        notes=f"stage={stage}",
        script=f"{HERE.name}/run.py",
        phase="M2",
    )


# ---------------------------------------------------------------- 组合（复用）
def _build_picks(cfg: dict, panel: pd.DataFrame, directions: dict[str, float],
                 score_override: dict[str, float] | None = None) -> pd.DataFrame:
    """标准化 → 合成 → 选股 → 等权。``score_override`` 供置换重要性复用。"""
    from factorlab.portfolio import backtest, select

    pf = cfg["portfolio"]
    factors = list(directions)
    by = ("pool", "date") if "pool" in panel.columns else ("date",)
    z = select.zscore(panel, factors, by=by, clip=pf["z_clip"])
    scored = select.composite(z, score_override or directions)
    picks = select.top_n(
        scored,
        n=pf["n_picks_per_pool"],
        by=by,
        eligible="tradable" if "tradable" in scored.columns else None,
    )
    picks = backtest.equal_weight(picks, by=by, budget=pf["budget"], cap=pf["max_weight"])
    return picks


def _daily_net(cfg: dict, panel: pd.DataFrame, directions: dict[str, float]) -> pd.Series:
    """一次完整回测的日度净收益（置换重要性 / PBO 的公共回调）。"""
    from factorlab.portfolio import backtest

    picks = _build_picks(cfg, panel, directions)
    daily = backtest.backtest(picks, label=cfg["labels"]["primary"],
                              cost_one_way=cfg["portfolio"]["cost_one_way"])
    return daily["net"]


# ---------------------------------------------------------------- 门 3
def stage_factor(cfg: dict, panel: pd.DataFrame, directions: dict[str, float]) -> None:
    from factorlab.eval import decile, ic

    label = cfg["labels"]["primary"]
    factors = list(directions)
    if not factors:
        raise SystemExit(f"panel 里没有任何待检验因子；可用列：{list(panel.columns)[:20]}")

    use_pool = "pool" in panel.columns
    by = ("pool", "date") if use_pool else ("date",)
    ic_df = ic.ic_summary(panel, factors, [label], by=by,
                          min_names=cfg["eval"]["min_names_per_day"],
                          nw_lag=cfg["eval"]["nw_lag"],
                          group_keys=("pool",) if use_pool else None)
    ic_df.to_csv(RESULT / "ic_summary.csv", index=False)

    rows = []
    groups = [(None, panel)] if not use_pool else list(panel.groupby("pool"))
    for key, sub in groups:
        for f in factors:
            ls = decile.long_short_spread(sub, f, label,
                                          nq=cfg["eval"]["n_quantiles"],
                                          by=("date",),
                                          min_names=cfg["eval"]["min_names_per_day"])
            rows.append({"pool": key, "factor": f, **ls})
    ls_df = pd.DataFrame(rows)
    ls_df.to_csv(RESULT / "long_short.csv", index=False)

    # 覆盖率：< 60% 的因子只能在少数票上用
    cov_rows = []
    for key, sub in groups:
        for f in factors:
            cov = sub.groupby("date", observed=True)[f].apply(lambda s: s.notna().mean())
            cov_rows.append({"pool": key, "factor": f,
                             "coverage": float(sub[f].notna().mean()),
                             "min_daily_coverage": float(cov.min()) if len(cov) else np.nan})
    cov_df = pd.DataFrame(cov_rows)
    cov_df.to_csv(RESULT / "coverage.csv", index=False)

    print("\n[门3] IC（结论看 t_newey_west，naive t 会高估 20–30%）")
    cols = [c for c in ("pool", "factor", "mean_ic", "t_naive", "t_newey_west", "n_eff")
            if c in ic_df.columns]
    print(ic_df[cols].to_string(index=False, float_format=lambda x: f"{x: .4f}"))

    print("\n[门3] 多空价差（盈亏平衡线 = 20bp/日）")
    show = [c for c in ("pool", "factor", "spread_bp", "t_newey_west", "n_days")
            if c in ls_df.columns]
    print(ls_df[show].to_string(index=False, float_format=lambda x: f"{x: .2f}"))

    t_min = cfg.get("expectation", {}).get("nw_t_min", 3.0)
    best = float(ic_df["t_newey_west"].abs().max()) if not ic_df.empty else 0.0
    low_cov = cov_df[cov_df["coverage"] < 0.60]
    print(f"\n判定：max|NW t| = {best:.2f}（线 {t_min}）"
          f"{' 通过' if best >= t_min else ' 不通过'}"
          f"{f'；覆盖率 <60% 的因子 {len(low_cov)} 条' if len(low_cov) else ''}")


# ---------------------------------------------------------------- 门 4
def stage_independence(cfg: dict, panel: pd.DataFrame, directions: dict[str, float]) -> None:
    from factorlab.audit import permutation
    from factorlab.eval import orth

    label = cfg["labels"]["primary"]
    factors = list(directions)
    controls = cfg["eval"].get("orth_controls", [])
    use_pool = "pool" in panel.columns
    by = ("pool", "date") if use_pool else ("date",)

    # ---- 4.1 正交化 ----
    missing = [c for c in controls if c not in panel.columns]
    if missing:
        print(f"[warn] 缺少控制变量 {missing} → 正交化不完整，结论只能标 watch")
        controls = [c for c in controls if c in panel.columns]

    if len(controls) >= 3:
        orth_df = orth.retention_report(panel, factors, label, controls, by=by,
                                        min_names=cfg["eval"]["min_names_per_day"],
                                        nw_lag=cfg["eval"]["nw_lag"],
                                        group_keys=("pool",) if use_pool else None)
        orth_df.to_csv(RESULT / "orth.csv", index=False)
        print("\n[门4] 正交化")
        print(orth.format_report(orth_df))
    else:
        print("\n[门4] 控制变量少于 3 个，跳过正交化（这会显著降低结论强度）")

    # ---- 4.2 置换重要性（必须含噪声对照）----
    z_cols = {}
    for f in factors:
        zc = f + "_z"
        if zc not in panel.columns:
            z_cols = {}
            break
        z_cols[zc] = directions[f]
    if not z_cols:
        print("\n[门4] panel 里没有标准化列（<因子>_z），跳过置换重要性")
        return

    # 置换重要性作用在 z 列上，因此这里传入适配后的 directions 键
    from factorlab.portfolio.select import composite  # noqa: F401  (文档：合成口径)

    def _run(scored: pd.DataFrame) -> pd.Series:
        from factorlab.portfolio import backtest, select
        pf = cfg["portfolio"]
        picks = select.top_n(scored, n=pf["n_picks_per_pool"], by=by,
                             eligible="tradable" if "tradable" in scored.columns else None)
        picks = backtest.equal_weight(picks, by=by, budget=pf["budget"], cap=pf["max_weight"])
        return backtest.backtest(picks, label=label,
                                 cost_one_way=pf["cost_one_way"])["net"]

    pi = permutation.permutation_importance(
        panel, factor_z_cols=z_cols, run_backtest=_run, by=by,
        n_perm=cfg["eval"].get("n_perm", 100),
        include_noise_control=cfg["eval"].get("include_noise_control", True),
    )
    pi = permutation.net_information(pi)
    pi.to_csv(RESULT / "permutation.csv", index=False)

    print("\n[门4] 置换重要性（ΔSharpe 需扣除 noise_control）")
    print(pi.to_string(index=False, float_format=lambda x: f"{x: .3f}"))
    thr = cfg.get("expectation", {}).get("delta_sharpe_min", 0.10)
    if "net_delta_sharpe" in pi.columns:
        kept = pi[pi["variant"].str.startswith("shuffle:")]
        passed = kept[kept["net_delta_sharpe"] >= thr]
        print(f"\n判定：净信息量 >= {thr} 的因子 {len(passed)}/{len(kept)}")
        for _, r in kept.iterrows():
            flag = "保留" if r["net_delta_sharpe"] >= thr else "可删"
            print(f"   {r['variant']:<28} 净 ΔSharpe {r['net_delta_sharpe']:+.3f} → {flag}")


# ---------------------------------------------------------------- 门 5
def stage_portfolio(cfg: dict, panel: pd.DataFrame, directions: dict[str, float]) -> None:
    from factorlab.eval import stability
    from factorlab.portfolio import backtest

    label = cfg["labels"]["primary"]
    pf = cfg["portfolio"]

    picks = _build_picks(cfg, panel, directions)
    picks.to_csv(RESULT / "picks.csv", index=False)
    daily = backtest.backtest(picks, label=label, cost_one_way=pf["cost_one_way"])
    daily.to_csv(RESULT / "backtest.csv")

    s = backtest.summary(daily, cost_levels=tuple(pf["cost_sensitivity"]))
    print("\n[门5] 组合层")
    print(backtest.format_summary(s))

    frag = stability.fragility_curve(daily["net"], ks=tuple(cfg["audit"]["fragility_k"]))
    frag.to_csv(RESULT / "fragility.csv", index=False)
    k_pass = 5
    hit = frag.loc[frag["k"] == k_pass, "ann"]
    at_k = float(hit.iloc[0]) if len(hit) else float("nan")
    print(f"\n脆弱性：剔除最好 {k_pass} 天后净年化 = {at_k:.2%} "
          f"→ {'通过' if at_k > 0 else '不通过（必须披露）'}")

    ci = stability.block_bootstrap_metrics(daily["net"], block=20, n=3000)
    pd.DataFrame([ci]).to_csv(RESULT / "bootstrap.csv", index=False)
    print(f"块自举：年化 95% CI = [{ci['ann_lo']:.2%}, {ci['ann_hi']:.2%}]  "
          f"P(年化<0) = {ci['p_ann_negative']:.1%}")

    conc = stability.concentration(daily["net"], top=10)
    by_year = stability.by_period(daily["net"])
    by_year.to_csv(RESULT / "by_year.csv", index=False)
    print(f"集中度：最好 10 天贡献 {conc['contribution']:.0%} 的毛收益"
          f"{'（>50%，须披露）' if (conc['contribution'] or 0) > 0.5 else ''}")
    if not by_year.empty:
        print("分年：" + "  ".join(f"{r['period']} {r['ann']:.1%}" for _, r in by_year.iterrows()))


# ---------------------------------------------------------------- 门 6
def stage_audit(cfg: dict, panel: pd.DataFrame, directions: dict[str, float]) -> None:
    from factorlab.audit import dsr as D
    from factorlab.audit import pbo as P
    from factorlab.audit import purge
    from factorlab.audit import trials as T
    from factorlab.audit.lookahead import audit_panel

    out = RESULT / "audit"
    out.mkdir(parents=True, exist_ok=True)

    # ---- 6.1 前视体检 ----
    rep = audit_panel(panel)
    (out / "lookahead.txt").write_text(rep.text() + "\n", encoding="utf-8")
    print("\n[门6] 前视体检")
    print(rep.text())

    bt = RESULT / "backtest.csv"
    if not bt.exists():
        print("\n[skip] 没有 backtest.csv，跳过 DSR/PBO/禁运（先跑 --stage portfolio）")
        return
    daily = pd.read_csv(bt, index_col=0, parse_dates=True)["net"]

    # ---- 6.2 DSR（惩罚试验次数）----
    n_trials = cfg["audit"].get("n_trials_for_dsr") or T.total_n()
    d = D.deflated_sharpe(daily, n_trials=max(int(n_trials), 1))
    pd.DataFrame([d]).to_csv(out / "dsr.csv", index=False)
    print(f"\nDSR：SR(年化) = {d['sr_annual']:.2f}  PSR = {d['psr']:.3f}  "
          f"DSR(N={d['n_trials']}) = {d['dsr']:.3f}  "
          f"→ {'通过' if d['pass'] else '不通过（门槛 0.95）'}")
    grid = D.dsr_grid(daily)
    grid.to_csv(out / "dsr_grid.csv", index=False)
    print("DSR 敏感性网格（记账不全时唯一的回答）")
    print(grid.to_string(index=False, float_format=lambda x: f"{x: .3f}"))

    # ---- 6.3 PBO（选参流程是否可信）----
    if cfg["audit"].get("do_pbo"):
        variants: dict[str, pd.Series] = {}
        for f in directions:
            try:
                variants[f"single:{f}"] = _daily_net(cfg, panel, {f: 1.0})
            except Exception as exc:  # noqa: BLE001
                print(f"   [warn] 单因子变体 {f} 失败：{exc}")
        try:
            variants["composite"] = _daily_net(cfg, panel, directions)
        except Exception as exc:  # noqa: BLE001
            print(f"   [warn] 合成变体失败：{exc}")
        if len(variants) >= 3:
            rets = pd.DataFrame(variants).dropna(how="all")
            try:
                res = P.cscv_pbo(rets, n_blocks=10)
                (out / "pbo.txt").write_text(P.format_pbo(res) + "\n", encoding="utf-8")
                print("\n[门6] PBO")
                print(P.format_pbo(res))
            except Exception as exc:  # noqa: BLE001
                print(f"\n[门6] PBO 跳过：{exc}")
        else:
            print("\n[门6] PBO 跳过：候选变体不足 3 个")
    else:
        print("\n[门6] PBO 按配置跳过（参数冻结的策略可以跳过，但 conclusion.md 必须写明理由）")

    # ---- 6.4 禁运敏感性 ----
    split = cfg["audit"].get("split_date")
    embargo = int(cfg["audit"].get("embargo_days", 120))
    if split:
        sens = purge.embargo_sensitivity(daily, split=split,
                                         embargo_grid=(0, 20, min(60, embargo), embargo))
        sens.to_csv(out / "purge.csv", index=False)
        print("\n[门6] 禁运敏感性")
        print(purge.format_report(sens, feature_window=embargo))
    else:
        print("\n[门6] 未配置 audit.split_date → 跳过禁运检验")
        print("   ⚠️ 没有切分日与禁运长度的「样本外」不是证据，是措辞。")


# ---------------------------------------------------------------- 主流程
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="研究执行入口（7 道门）")
    ap.add_argument("--stage", default="all", choices=[*STAGES, "all"])
    args = ap.parse_args(argv)

    cfg = load_cfg()
    RESULT.mkdir(parents=True, exist_ok=True)
    rid = run_id(cfg)

    panel_path = Path(cfg["data"]["panel"])
    if not panel_path.is_absolute():
        panel_path = Path.cwd() / panel_path
    if not panel_path.exists():
        raise SystemExit(
            f"缺少面板 {panel_path}\n"
            "先按 data/README.md 建好数据，或把 config.yaml 的 data.panel 指向已有文件。")
    panel = pd.read_parquet(panel_path)
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"])

    directions = factor_directions(cfg, list(panel.columns))
    if not directions:
        raise SystemExit(
            "config.yaml 里的因子在面板中都不存在。\n"
            f"面板可用列（前 20）：{list(panel.columns)[:20]}")

    print(f"面板 {panel_path.name}: {len(panel):,} 行 · run_id={rid}")
    print(f"待检验因子：{directions}")

    stages = STAGES if args.stage == "all" else [args.stage]
    for st in stages:
        open_trial(cfg, st)          # 门 2：先记账再跑
        {"factor": stage_factor,
         "independence": stage_independence,
         "portfolio": stage_portfolio,
         "audit": stage_audit}[st](cfg, panel, directions)

    print(f"\n产物在 {RESULT}")
    print("下一步：写 conclusion.md（判决 + 退役条件），并同步 registry/factors.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
