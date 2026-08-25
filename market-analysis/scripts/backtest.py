"""
backtest.py — 贝叶斯信号系统历史回测验证

核心问题：当我们的信号显示第3/4/5档时，
          S&P 500 接下来实际上涨的频率是多少？

方法：
  1. 读取已计算好的每日信号（prob + tier）
  2. 与实际 S&P 500 前向收益对比
  3. 按档位分组，计算实际胜率和均值
  4. 校准曲线：模型预测概率 vs 实际实现率
  5. t检验：各档位与基准的差异是否显著

输出：
  data/processed/backtest_results.json
  （由 build_signals.py 嵌入 signals.json 的 backtest 字段）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from scipy import stats

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

HORIZONS = [1, 5, 10, 20, 30]   # 前向天数


def block_bootstrap_p(x, base_rate, block, n_iter=5000, seed=20260824):
    """移动块自助 p 值 —— 尊重「前向窗口重叠」造成的自相关(2026-08-24 新增)。

    为什么必须有:up_{h}d / ret_{h}d 是**逐日**算的 h 日前向结果,相邻两天的窗口重叠 (h-1)/h,
    高度自相关。`ttest_1samp` 把每天当独立观测 → 有效样本约 n/h、标准误被低估约 √h 倍 →
    **p 值被低估一到两个数量级**。实测(NASDAQ 校准桶):naive p=0.0001 → 块自助 0.052;
    0.0003 → 0.089;<51% 桶 0.033 → 0.448(显著性直接翻掉)。
    这与 dip_hold_study / fear_greed 的去重叠段级自助是同一套诚实标准,此处补齐。

    块长取 = 前向窗口长度 h(一个块内的重叠结构被整体搬走,块之间近似独立)。
    p 用 (1+命中)/(B+1) 的保守写法,永不报 0;固定种子保证已发布 p 可复现。
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    block = max(1, min(int(block), n))
    if n < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_iter, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_iter, -1)[:, :n]
    means = x[idx].mean(axis=1)
    center = float(means.mean())
    obs_dev = abs(float(x.mean()) - float(base_rate))
    hits = int(np.sum(np.abs(means - center) >= obs_dev))
    return (1 + hits) / (n_iter + 1)


def run_backtest(daily, long_csv, label):
    """用「信号对应指数自身」的长历史验证（纳指信号→纳指收益，标普→标普）"""
    print(f"=== 贝叶斯信号回测验证（{label}）===\n")
    print(f"  信号数量：{len(daily)} 天")

    # ── 加载该指数长历史 ──────────────────────────────────────────
    sp = pd.read_csv(RAW_DIR / long_csv, index_col=0, parse_dates=True).squeeze()
    sp = sp.sort_index().dropna()
    # 只保留日频价格（去掉非交易日的 NaN）
    sp = sp[sp > 0]
    print(f"  {label}：{sp.index[0].date()} – {sp.index[-1].date()}，{len(sp)} 行\n")

    # ── 构建每日记录 ───────────────────────────────────────────────
    records = []
    sp_dates = sp.index

    for date_str, sig in daily.items():
        ts = pd.Timestamp(date_str)
        if ts not in sp_dates:
            continue

        pos = sp_dates.get_loc(ts)
        row = {
            "date":  date_str,
            "prob":  sig["prob"],
            "tier":  int(sig["tier"]),
            "month": int(sig.get("month", 0)),
        }

        for h in HORIZONS:
            if pos + h < len(sp):
                p0  = sp.iloc[pos]
                ph  = sp.iloc[pos + h]
                ret = float((ph - p0) / p0)
                row[f"ret_{h}d"] = round(ret * 100, 4)
                row[f"up_{h}d"]  = int(ret > 0)

        records.append(row)

    if records:
        df = pd.DataFrame(records)
    else:
        # 降级续跑（2026-07-03 用户拍板，替代此前的 fail-closed raise）：
        # 显式构造与正常路径同 dtype 的空表，让下面完全相同的聚合代码
        # （baseline/by_tier/calibration/tier4_strategy）自然产出 NaN/空结构，
        # 而不是让下游在隐式 object-dtype 空表上崩（scipy ttest_ind 对
        # object dtype 的双空数组会抛 AttributeError，numeric dtype 则安全返回 NaN）。
        empty_dtypes = {"date": "object", "prob": "float64", "tier": "int64", "month": "int64"}
        for h in HORIZONS:
            empty_dtypes[f"ret_{h}d"] = "float64"
            empty_dtypes[f"up_{h}d"] = "int64"
        df = pd.DataFrame({c: pd.Series(dtype=t) for c, t in empty_dtypes.items()})

    df = df.dropna(subset=[f"ret_{h}d" for h in HORIZONS])
    if df.empty:
        print(f"⚠️ [WARN] {label}: 0 条可回测记录(信号与 {long_csv} 无重叠日期，"
              f"或前向窗口数据在 dropna 后归零)——上游数据损坏或错位；"
              f"降级返回空结构续跑（不再 fail-closed 中止，2026-07-03 用户拍板）")
    print(f"  可回测记录：{len(df)} 天（含完整前向数据）\n")

    results = {
        # 方法论提示：前向窗口逐日采样，相邻样本高度重叠（20日窗口共享19天），
        # 有效样本量约为名义值的1/20，p值偏乐观；显著性仅作参考。
        # 另注意：先验/LR由全历史估计，本回测属样本内验证；
        # 真实样本外表现以 walk_forward 结果为准。
        "index": label,
        "method_note": "样本内验证；样本外表现见 walk_forward。**重叠窗口已按块自助修正**(2026-08-24):up_{h}d 逐日采样、相邻样本共享 h-1 天,t 检验把每天当独立观测会低估 p 一到两个数量级(实测校准桶 0.0001→0.052、0.0003→0.089、0.033→0.448)。故 significant 收紧为「t 检验与块自助(块长=前向窗口)都过」,两个 p 值均照登、可自行复核。",
        "degraded": bool(df.empty),   # True＝本轮 0 条可回测记录，以下字段为降级空结构
    }

    # ── 1. 全样本基准 ──────────────────────────────────────────────
    print("=== 基准（全样本）===")
    baseline = {}
    for h in HORIZONS:
        wr  = float(df[f"up_{h}d"].mean() * 100)
        avg = float(df[f"ret_{h}d"].mean())
        baseline[f"{h}d"] = {
            "win_rate":   round(wr,  1),
            "avg_return": round(avg, 2),
            "n":          len(df),
        }
        print(f"  {h:>2}日：胜率={wr:.1f}%  均值={avg:+.2f}%")
    results["baseline"] = baseline

    # ── 2. 按档位（Tier）分组 ───────────────────────────────────────
    print("\n=== 各档位表现 ===")
    tier_rows = []
    for tier in [1, 2, 3, 4, 5]:
        sub = df[df["tier"] == tier]
        if len(sub) < 15:
            print(f"  Tier {tier}: 样本不足 ({len(sub)})，跳过")
            continue

        row = {"tier": tier, "n": len(sub), "horizons": {}}
        print(f"\n  Tier {tier}（n={len(sub)}）")

        for h in HORIZONS:
            col_up  = f"up_{h}d"
            col_ret = f"ret_{h}d"
            s   = sub[col_up].values
            r   = sub[col_ret].values
            base_wr = df[col_up].mean()

            wr       = float(s.mean() * 100)
            avg_ret  = float(r.mean())
            med_ret  = float(np.median(r))
            t_stat, p_val = stats.ttest_1samp(s, base_wr)
            p_blk = block_bootstrap_p(s, base_wr, block=h)      # 块长=该窗口长度(尊重重叠)
            diff_wr  = round(wr - float(base_wr * 100), 1)

            row["horizons"][f"{h}d"] = {
                "win_rate":   round(wr, 1),
                "avg_return": round(avg_ret, 2),
                "med_return": round(med_ret, 2),
                "diff_vs_baseline": diff_wr,
                "t_stat":     round(float(t_stat), 3),
                "p_value":    round(float(p_val), 4),
                "p_block_bootstrap": (None if p_blk is None else round(float(p_blk), 4)),
                # 收紧:t 检验 + 块自助都过才算显著(前者忽略重叠自相关会低估 p 一到两个数量级)
                "significant":bool(p_val < 0.10 and p_blk is not None and p_blk < 0.10),
                "significant_ttest_only": bool(p_val < 0.10),
            }
            sig_str = "[*]" if p_val < 0.10 else "   "
            print(f"    {h:>2}日: 胜率={wr:.1f}%({diff_wr:+.1f}pp)  "
                  f"均值={avg_ret:+.2f}%  p={p_val:.3f} {sig_str}")

        tier_rows.append(row)
    results["by_tier"] = tier_rows

    # ── 3. 校准曲线（概率区间 → 实际胜率）─────────────────────────
    print("\n=== 校准曲线（20日窗口）===")
    bins   = [0.48, 0.51, 0.54, 0.57, 0.60, 0.63, 0.70, 1.0]
    labels = ["<51%","51-54%","54-57%","57-60%","60-63%","63-70%",">70%"]
    df["bucket"] = pd.cut(df["prob"], bins=bins, labels=labels, right=True)

    cal_rows = []
    for lbl in labels:
        sub = df[df["bucket"] == lbl]
        if len(sub) < 20:
            continue
        s = sub["up_20d"]
        r = sub["ret_20d"]
        mid = float(lbl.replace("<","").replace(">","")
                       .split("-")[0].replace("%","")) / 100
        wr   = float(s.mean() * 100)
        avg  = float(r.mean())
        _base20 = df["up_20d"].mean()
        t_stat, p_val = stats.ttest_1samp(s.values, _base20)
        p_blk = block_bootstrap_p(s.values, _base20, block=20)
        cal_rows.append({
            "bucket":        lbl,
            "prob_mid":      round(mid, 3),
            "n":             len(sub),
            "actual_wr_20d": round(wr,  1),
            "avg_ret_20d":   round(avg, 2),
            "t_stat":        round(float(t_stat), 3),
            "p_value":       round(float(p_val), 4),
            "p_block_bootstrap": (None if p_blk is None else round(float(p_blk), 4)),
            "significant":   bool(p_val < 0.10 and p_blk is not None and p_blk < 0.10),
            "significant_ttest_only": bool(p_val < 0.10),
        })
        sig_str = "[*]" if p_val < 0.10 else "   "
        print(f"  {lbl:>9}: 实际胜率={wr:.1f}%  均值={avg:+.2f}%  n={len(sub)} {sig_str}")
    results["calibration_20d"] = cal_rows

    # ── 4. 高档位集中持有策略 vs 买入持有对比 ──────────────────────
    print("\n=== 策略对比（仅在信号≥第4档时买入）===")
    h = 20
    tier4_up = df[df["tier"] >= 4][f"up_{h}d"]
    all_up   = df[f"up_{h}d"]

    wr4  = float(tier4_up.mean() * 100)
    wra  = float(all_up.mean() * 100)
    n4   = len(tier4_up)
    # 注:ttest_ind 在此本就不当(tier4 是 all 的**子集**,两样本不独立);块自助对基率检验更合适。
    t_stat, p_val = stats.ttest_ind(tier4_up.values, all_up.values)
    p_blk = block_bootstrap_p(tier4_up.values, float(all_up.mean()), block=20)

    print(f"  仅Tier≥4买入：胜率={wr4:.1f}%  n={n4}天  "
          f"vs 全时间买入={wra:.1f}%  p={p_val:.4f}")

    results["tier4_strategy"] = {
        "win_rate_20d":       round(wr4, 1),
        "baseline_win_rate":  round(wra, 1),
        "diff":               round(wr4 - wra, 1),
        "n_days":             n4,
        "p_value":            round(float(p_val), 4),
        "p_block_bootstrap":  (None if p_blk is None else round(float(p_blk), 4)),
        "significant":        bool(p_val < 0.10 and p_blk is not None and p_blk < 0.10),
        "significant_ttest_only": bool(p_val < 0.10),
        "avg_return_20d":     round(float(df[df["tier"]>=4]["ret_20d"].mean()), 2),
        "baseline_avg_ret":   round(float(df["ret_20d"].mean()), 2),
    }

    return results


if __name__ == "__main__":
    # 全量信号流在 processed/（signals.json 发布版只含近两年，P1-3 瘦身）
    full = PROC_DIR / "daily_signals_full.json"
    if full.exists():
        with open(full, encoding="utf-8") as f:
            sig_data = json.load(f)
    else:
        with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
            sig_data = json.load(f)

    results = {
        "NASDAQ": run_backtest(sig_data["daily_signals"],
                               "NASDAQ_COMP_long.csv", "NASDAQ"),
    }
    sp_daily = sig_data.get("daily_signals_sp500")
    if sp_daily:
        results["SP500"] = run_backtest(sp_daily, "SP500_long.csv", "SP500")

    # 写入 processed/，由 build_signals.py 统一嵌入 signals.json
    out = PROC_DIR / "backtest_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 回测结果已写入 {out}（重跑 build_signals.py 后生效）")
