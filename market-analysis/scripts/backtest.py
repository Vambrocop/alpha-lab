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


def block_bootstrap_p(mask, y_all, block=20, n_iter=5000, seed=20260824):
    """循环块自助 p 值 —— 块在**日历序列**上连续,mask 随之一起被重采样。

    为什么必须有:up_{h}d / ret_{h}d 是**逐日**算的 h 日前向结果,相邻两天的窗口重叠
    (h-1)/h,高度自相关。`ttest_1samp` 把每天当独立观测 → 有效样本约 n/h、标准误低估约
    √h 倍 → **p 值被低估一到两个数量级**。

    **2026-08-27 重要修正(用户质疑「是不是矫枉过正」→ 实测证实确实过头了)**:
    初版是在「某一档的观测**子集**」自身数组上取连续块。但某档的日子在日历上是**散落**的
    ——"20 个连续元素" ≠ "20 个连续日历日",可能横跨数月;那些元素本就近乎独立,却被当成
    一个整体搬走 → 破坏了比实际更多的结构 → p 偏大。实测同一批数据两种口径:
      <51%   散落 0.071 vs 日历 0.038      57-60%  散落 0.313 vs 日历 0.170
      60-63% 散落 0.131 vs 日历 0.057(**结论翻转**:正确口径下本该显著)
      Tier>=4 散落 0.332 vs 日历 0.117
    散落口径系统性保守 1.8–2.8 倍。自相关存在于**日历时间**里,故块必须在日历上连续。
    改为与 walk_forward.block_bootstrap_diff 同一语义(那边一直是对的)。

    p = 自助分布中「差值穿越 0」的双侧份额(CI 反演),(1+命中)/(B+1) 的保守写法在
    此处不再需要——用与 walk_forward 一致的份额法,便于两处结论可比。
    固定种子保证已发布 p 可复现。mask 为空/过小 → None(调用方据此不判显著)。
    """
    mask = np.asarray(mask, dtype=bool)
    y_all = np.asarray(y_all, dtype=float)
    n = len(y_all)
    if n == 0 or mask.sum() < 10:
        return None
    block = max(1, min(int(block), n))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    diffs = []
    for _ in range(n_iter):
        starts = rng.integers(0, n, n_blocks)
        idx = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        ys, ss = y_all[idx], mask[idx]
        if ss.sum() == 0:
            continue
        diffs.append(ys[ss].mean() - ys.mean())
    if not diffs:
        return None
    diffs = np.array(diffs)
    p = 2 * min(float((diffs <= 0).mean()), float((diffs >= 0).mean()))
    return min(p, 1.0)


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
        "method_note": "样本内验证；样本外表现见 walk_forward。**重叠窗口已按块自助修正**(2026-08-24 引入，2026-08-27 修正口径)：up_{h}d 逐日采样、相邻样本共享 h-1 天，t 检验把每天当独立观测会低估 p 一到两个数量级。块自助的块取在**日历序列**上(mask 随之重采样)——初版曾在散落子集上取块，系统性过度保守 1.8–2.8 倍、误判掉本该显著的格(如 SP500 Tier≥4：散落 0.209 vs 日历 0.017)，已更正。significant = 「t 检验与块自助都过」，两个 p 值均照登、可自行复核。", "degraded": bool(df.empty),   # True＝本轮 0 条可回测记录，以下字段为降级空结构
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
            # 传 mask + **完整日序列**(块在日历上连续;2026-08-27 修正,见函数注释)
            p_blk = block_bootstrap_p((df["tier"] == tier).to_numpy(),
                                      df[col_up].to_numpy(float), block=h)
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
        p_blk = block_bootstrap_p((df["bucket"] == lbl).to_numpy(),
                                  df["up_20d"].to_numpy(float), block=20)
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
    p_blk = block_bootstrap_p((df["tier"] >= 4).to_numpy(),
                              df["up_20d"].to_numpy(float), block=20)

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
