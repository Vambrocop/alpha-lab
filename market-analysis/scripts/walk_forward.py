"""
walk_forward.py — 滚动验证 + 模型优化

两个任务：
1. Walk-Forward Test：用训练期数据学习LR，在测试期验证，获得真实样本外准确率
2. 优化LR：找到每个技术因子的经验LR（不再手动设定），输出供 build_signals.py 使用

滚动窗口：
  2000-2012训练 → 2012-2014测试
  2000-2014训练 → 2014-2016测试
  2000-2016训练 → 2016-2018测试
  2000-2018训练 → 2018-2020测试
  2000-2020训练 → 2020-2022测试
  2000-2022训练 → 2022-2024测试

输出：
  walk_forward_results.json — 每个测试期的性能
  optimized_lr.json         — 从全量数据学到的最优LR
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from scipy import stats
from datetime import date, timedelta

# 模型核心原语统一来自 signal_model（与 build_signals.py 生产打分共用，禁止本地复制）。
# 打分时对学到的 LR 套用与生产相同的收缩——验证的配置必须等于部署的配置。
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from signal_model import (
    tier as _tier, bayesian_update as bayesian_prob,
    week_of_month as _week_of_month, rsi as _rsi, shrink_lr,
    build_design_matrix,
    BTC_MOM_THRESH, DXY_TREND_THRESH, VOL_HIGH, VOL_LOW,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
)

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

HORIZON = 20  # 主要关注20日前向胜率


# ══════════════════════════════════════════════════════════════════
# 1. 构建特征数据集（每天的原始特征 + 前向收益）
# ══════════════════════════════════════════════════════════════════
def build_feature_df():
    """
    读取价格数据，计算每天的特征（日历 + 技术），
    和后续20日 S&P 500 收益
    """
    print("构建特征数据集...")
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True).ffill()
    # 特征基于纳指 → 前向收益也用纳指（不再用标普验证纳指信号）
    sp_long = pd.read_csv(RAW_DIR / "NASDAQ_COMP_long.csv",
                          index_col=0, parse_dates=True).squeeze().dropna()
    sp_long = sp_long[sp_long > 0].sort_index()

    # 日频收益
    ret = prices.pct_change()

    # ── 预计算所有滚动指标（循环内只做索引，避免 O(n²)）──────────
    ind = {}
    for asset in ["NASDAQ", "BTC", "DXY"]:
        if asset not in prices.columns:
            continue
        p = prices[asset]
        ind[asset] = {
            "ma50":  p.rolling(50).mean(),
            "ma200": p.rolling(200).mean(),
            "r20":   p.pct_change(20),
        }
    rsi_nasdaq = vol_nasdaq = None
    if "NASDAQ" in ret.columns:
        r = ret["NASDAQ"]
        rsi_nasdaq = _rsi(r, 14)
        vol_nasdaq = r.rolling(20).std() * np.sqrt(252)
    dxy_tr = prices["DXY"].pct_change(20) if "DXY" in prices.columns else None

    # VIX期限结构（2009+）
    vix_bwd = None
    if "VIX" in prices.columns and "VIX3M" in prices.columns:
        vix_bwd = (prices["VIX"] >= prices["VIX3M"]).where(prices["VIX3M"].notna())
    # 隔夜动量（QQQ隔夜段近20日累计，overnight_analysis.py 生成）
    ov_mom = None
    try:
        ov = pd.read_csv(PROC_DIR / "overnight_daily.csv",
                         index_col="Date", parse_dates=True)
        col = "NASDAQ100" if "NASDAQ100" in ov.columns else ov.columns[-1]
        ov_mom = ov[col].rolling(20).sum().reindex(prices.index)
    except Exception:
        pass

    rows = []
    dates = prices.index

    for i, ts in enumerate(dates):
        if ts.weekday() >= 5:
            continue
        if ts not in sp_long.index:
            continue

        # ── 日历特征 ──────────────────────────────────────────────
        month = ts.month
        dow   = ts.weekday()
        wom   = _week_of_month(ts)

        # ── 技术特征（二值化）────────────────────────────────────
        feats = {}

        for asset, d in ind.items():
            p = prices[asset]
            ma50, ma200, r20 = d["ma50"].iloc[i], d["ma200"].iloc[i], d["r20"].iloc[i]
            feats[f"{asset}_above_ma200"] = int(p.iloc[i] > ma200) if not pd.isna(ma200) else None
            feats[f"{asset}_above_ma50"]  = int(p.iloc[i] > ma50)  if not pd.isna(ma50)  else None
            feats[f"{asset}_mom20_pos"]   = int(r20 > BTC_MOM_THRESH)  if not pd.isna(r20) else None
            feats[f"{asset}_mom20_neg"]   = int(r20 < -BTC_MOM_THRESH) if not pd.isna(r20) else None

        if rsi_nasdaq is not None:
            rv = rsi_nasdaq.iloc[i]
            feats["nasdaq_rsi_overbought"] = int(rv > RSI_OVERBOUGHT) if not pd.isna(rv) else None
            feats["nasdaq_rsi_oversold"]   = int(rv < RSI_OVERSOLD)   if not pd.isna(rv) else None
        if vol_nasdaq is not None:
            vv = vol_nasdaq.iloc[i]
            feats["nasdaq_high_vol"] = int(vv > VOL_HIGH) if not pd.isna(vv) else None
            feats["nasdaq_low_vol"]  = int(vv < VOL_LOW)  if not pd.isna(vv) else None

        if dxy_tr is not None:
            dv = dxy_tr.iloc[i]
            feats["dxy_rising"]  = int(dv > DXY_TREND_THRESH)  if not pd.isna(dv) else None
            feats["dxy_falling"] = int(dv < -DXY_TREND_THRESH) if not pd.isna(dv) else None

        if vix_bwd is not None:
            vb = vix_bwd.iloc[i]
            feats["vix_backwardation"] = int(bool(vb)) if not pd.isna(vb) else None
        if ov_mom is not None:
            om = ov_mom.iloc[i]
            feats["overnight_mom_pos"] = int(om > 0) if not pd.isna(om) else None
            feats["overnight_mom_neg"] = int(om < 0) if not pd.isna(om) else None

        # ── 前向收益 ──────────────────────────────────────────────
        pos = sp_long.index.get_loc(ts) if ts in sp_long.index else None
        fwd_ret = None
        fwd_up  = None
        if pos is not None and pos + HORIZON < len(sp_long):
            fwd_ret = float((sp_long.iloc[pos + HORIZON] - sp_long.iloc[pos]) / sp_long.iloc[pos])
            fwd_up  = int(fwd_ret > 0)

        row = {
            "date":  ts.strftime("%Y-%m-%d"),
            "year":  ts.year,
            "month": month,
            "dow":   dow,
            "wom":   wom,
            "fwd_ret_20d": round(fwd_ret * 100, 4) if fwd_ret is not None else None,
            "fwd_up_20d":  fwd_up,
        }
        row.update(feats)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["fwd_up_20d"])
    print(f"  特征数据集：{len(df)} 天（{df['year'].min()}-{df['year'].max()}）")
    return df


# ══════════════════════════════════════════════════════════════════
# 2. 从训练期学习经验LR
# ══════════════════════════════════════════════════════════════════
BINARY_FEATURES = [
    ("NASDAQ_above_ma200",   "NASDAQ在MA200上方"),
    ("NASDAQ_mom20_pos",     "NASDAQ近20日涨>5%"),
    ("NASDAQ_mom20_neg",     "NASDAQ近20日跌<-5%"),
    ("BTC_above_ma200",      "BTC在MA200上方"),
    ("BTC_mom20_pos",        "BTC近20日涨>5%"),
    ("BTC_mom20_neg",        "BTC近20日跌<-5%"),
    ("dxy_rising",           "美元走强"),
    ("dxy_falling",          "美元走弱"),
    ("nasdaq_rsi_overbought","NASDAQ RSI超买>75"),
    ("nasdaq_rsi_oversold",  "NASDAQ RSI超卖<35"),
    ("nasdaq_high_vol",      "NASDAQ高波动>25%"),
    ("nasdaq_low_vol",       "NASDAQ低波动<15%"),
    ("vix_backwardation",    "VIX期限结构倒挂(恐慌)"),
    ("overnight_mom_pos",    "隔夜动量为正(20日)"),
    ("overnight_mom_neg",    "隔夜动量为负(20日)"),
]

CALENDAR_FEATURES = {
    "month": list(range(1, 13)),
    "dow":   list(range(0, 5)),
    "wom":   [1, 2, 3, 4, 5],
}

def learn_lrs(train_df):
    """从训练集经验性地估计每个特征的LR"""
    base_wr = float(train_df["fwd_up_20d"].mean())
    learned = {"base_win_rate": round(base_wr, 4),
               "n_total": int(len(train_df)), "factors": {}}

    # 技术因子（二值）。审计 S6：LR 的基准率按**本因子可观测窗口**算,而非全 train——
    # 晚出现因子(vix_backwardation 2009+/overnight_mom 等)col 前期为 NaN,全 train 基准会错配、LR 偏差。
    # 与 factor_pruning(pool[col].notna())一致。
    for col, name in BINARY_FEATURES:
        if col not in train_df.columns:
            continue
        obs = train_df[train_df[col].notna()]                  # 该因子可观测窗口
        base_f = float(obs["fwd_up_20d"].mean()) if len(obs) else base_wr
        sub = obs[obs[col] == 1]["fwd_up_20d"].dropna()
        if len(sub) < 50:
            continue
        wr = float(sub.mean())
        lr = wr / base_f if base_f > 0 else 1.0
        learned["factors"][col] = {
            "name": name,
            "win_rate": round(wr, 4),
            "base_win_rate": round(base_f, 4),                 # 本因子窗口基准(透明,审计S6)
            "lr": round(lr, 4),
            "n": len(sub),
        }

    # 日历因子（分组）
    for feat, vals in CALENDAR_FEATURES.items():
        learned["factors"][feat] = {}
        for v in vals:
            sub = train_df[train_df[feat] == v]["fwd_up_20d"].dropna()
            if len(sub) < 20:
                continue
            wr = float(sub.mean())
            lr = wr / base_wr if base_wr > 0 else 1.0
            learned["factors"][feat][str(v)] = {
                "win_rate": round(wr, 4),
                "lr": round(lr, 4),
                "n": len(sub),
            }
    return learned


# ══════════════════════════════════════════════════════════════════
# 3. 用学到的LR在测试期生成信号并验证
# ══════════════════════════════════════════════════════════════════
def score_row(row, lrs_dict):
    """用学到的LR对单行打分，返回概率。

    所有经验 LR 都先经 shrink_lr 收缩——与 build_signals._learned_on/_learned_off
    的生产路径一致，保证验证评估的就是部署配置。
    """
    base_wr = lrs_dict["base_win_rate"]
    factors = lrs_dict["factors"]
    likelihoods = []

    # 日历因子 LR（month/dow/wom，收缩后）
    for feat, key in [("month", "month"), ("dow", "dow"), ("wom", "wom")]:
        f = factors.get(feat, {}).get(str(int(row[key])))
        likelihoods.append(shrink_lr(f["lr"], f["n"]) if f else 1.0)

    # 技术因子 LR
    n_total = lrs_dict.get("n_total", 0)
    for col, _ in BINARY_FEATURES:
        val = row.get(col)
        if val == 1 and col in factors:
            likelihoods.append(shrink_lr(factors[col]["lr"], factors[col]["n"]))
        elif val == 0 and col in factors:
            # 反面：由全概率公式从收缩后的触发侧还原 wr_neg = (base - p1*wr_pos) / (1-p1)
            p1 = factors[col]["n"] / n_total if n_total > 0 else 0.5
            if p1 < 1.0:
                wr_on  = shrink_lr(factors[col]["lr"], factors[col]["n"]) * base_wr
                inv_wr = (base_wr - p1 * wr_on) / (1 - p1)
                inv_lr = inv_wr / base_wr if base_wr > 0 else 1.0
                likelihoods.append(max(inv_lr, 0.5))

    return bayesian_prob(base_wr, likelihoods)


# ══════════════════════════════════════════════════════════════════
# P2-2 候选模型：L2 逻辑回归（与朴素贝叶斯同折对决，数据决定 v3.0 用谁）
# ══════════════════════════════════════════════════════════════════
def fit_logit(train_df):
    X, cols = build_design_matrix(train_df)
    y = train_df["fwd_up_20d"].astype(int).values
    m = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000)  # 默认 L2
    m.fit(X, y)
    return m, cols


def block_bootstrap_diff(sel, y, block=20, B=2000, seed=42):
    """循环块自助（块长=前向窗口20日）：Tier≥4 子集胜率 - 全体胜率 的 CI 与 p 值。

    P2-4：重叠20日窗口让 t 检验 p 值乐观约一个数量级，这里按日序列整块重采样，
    保留序列相关结构。p 值 = 自助分布穿越 0 的双侧份额（CI 反演法）。
    """
    sel = np.asarray(sel, dtype=bool)
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n == 0 or sel.sum() < 10:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    diffs = []
    n_dropped = 0                       # 重采样未抽到任何 sel 日 → diff 无定义,跳过
    for _ in range(B):
        starts = rng.integers(0, n, n_blocks)
        idx = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]   # 向量化(替 Python 推导式)：block=1 时 128s→秒级，索引/结果完全不变
        ys, ss = y[idx], sel[idx]
        if ss.sum() == 0:
            n_dropped += 1
            continue
        diffs.append(ys[ss].mean() - ys.mean())
    diffs = np.array(diffs)
    obs = float(y[sel].mean() - y.mean())
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    p = 2 * min(float((diffs <= 0).mean()), float((diffs >= 0).mean()))
    # n_dropped 透明化(诚实):有 sel.sum()>=10 门槛,抽到零-sel 重采样概率≈e^-10,故通常为 0;
    # 若某用法 n_dropped 占比大,说明该 sel 太稀疏、CI 被非对称截断,需警惕(审计 B1)。
    return {"diff": round(obs * 100, 2),
            "ci95": [round(lo * 100, 2), round(hi * 100, 2)],
            "p_boot": round(min(p, 1.0), 4),
            "n_dropped": n_dropped, "n_used": int(len(diffs))}


def evaluate_probs(test_df, probs, label):
    """对任一模型的测试期概率算统一指标：AUC + Tier≥4 块自助评估"""
    y = test_df["fwd_up_20d"].astype(int).values
    out = {"auc": round(float(roc_auc_score(y, probs)), 4) if len(set(y)) > 1 else None}
    sel = np.array([_tier(p) >= 4 for p in probs])
    out["n_tier4"] = int(sel.sum())
    bb = block_bootstrap_diff(sel, y)
    if bb:
        out["tier4_boot"] = bb
    return out


def evaluate_on_test(test_df, probs):
    """在测试期计算各档位实际胜率（probs 由调用方算好，避免与下方对决重复算 score_row）"""
    tiers = probs.apply(_tier)
    actual = test_df["fwd_up_20d"].values
    base_wr = float(actual.mean() * 100)

    result = {"baseline_wr": round(base_wr, 1), "n_total": len(test_df), "tiers": {}}
    for tier in [2, 3, 4, 5]:
        mask = tiers == tier
        if mask.sum() < 10:
            continue
        sub = actual[mask]
        wr  = float(sub.mean() * 100)
        t_stat, p_val = stats.ttest_1samp(sub, actual.mean())
        # 2026-08-25:分档显著性此前只用 t 检验,但 fwd_up_20d 是逐日采样的 20 日前向、
        # 相邻样本共享 19 天 → t 检验乐观约一个数量级(本文件 P2-4 早已在 Tier≥4 汇总处指出并用块自助,
        # 分档这里是漏网)。复用同一个 block_bootstrap_diff(它对任意 mask 通用,不限 Tier≥4),
        # significant 收紧为「t 检验与块自助都过」;两个 p 都照登,可复核。
        bb_t = block_bootstrap_diff(mask.values if hasattr(mask, "values") else np.asarray(mask), actual)
        p_boot = (bb_t or {}).get("p_boot")
        result["tiers"][tier] = {
            "n":        int(mask.sum()),
            "win_rate": round(wr, 1),
            "diff":     round(wr - base_wr, 1),
            "p_value":  round(float(p_val), 4),
            "p_boot":   p_boot,
            "boot_ci95": (bb_t or {}).get("ci95"),
            "significant": bool(p_val < 0.10 and p_boot is not None and p_boot < 0.10),
            "significant_ttest_only": bool(p_val < 0.10),
        }

    # Tier≥4 汇总
    mask4 = tiers >= 4
    if mask4.sum() >= 10:
        sub4 = actual[mask4]
        t_stat4, p_val4 = stats.ttest_1samp(sub4, actual.mean())
        bb4 = block_bootstrap_diff(mask4.values if hasattr(mask4, "values") else np.asarray(mask4), actual)
        p_boot4 = (bb4 or {}).get("p_boot")
        result["tier4_plus"] = {
            "n":        int(mask4.sum()),
            "win_rate": round(float(sub4.mean() * 100), 1),
            "diff":     round(float(sub4.mean() * 100) - base_wr, 1),
            "p_value":  round(float(p_val4), 4),
            "p_boot":   p_boot4,
            "boot_ci95": (bb4 or {}).get("ci95"),
            "significant": bool(p_val4 < 0.10 and p_boot4 is not None and p_boot4 < 0.10),
            "significant_ttest_only": bool(p_val4 < 0.10),
        }
    return result


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
FOLDS = [
    (2000, 2012, 2014),
    (2000, 2014, 2016),
    (2000, 2016, 2018),
    (2000, 2018, 2020),
    (2000, 2020, 2022),
    (2000, 2022, 2024),
]

def run():
    df = build_feature_df()

    fold_results = []
    naive_pool, logit_pool, y_pool = [], [], []
    coef_signs, coef_values = [], []
    print("\n=== Walk-Forward 滚动验证：朴素贝叶斯 vs 逻辑回归（P2 对决）===")
    print(f"{'测试期':<12}{'基准WR':>8}{'NB diff':>10}{'NB p_boot':>10}"
          f"{'LR diff':>10}{'LR p_boot':>10}{'NB AUC':>8}{'LR AUC':>8}")
    print("-" * 80)

    for (train_start, train_end, test_end) in FOLDS:
        train = df[(df["year"] >= train_start) & (df["year"] <  train_end)].copy()
        test  = df[(df["year"] >= train_end)   & (df["year"] <  test_end)].copy()

        if len(train) < 200 or len(test) < 50:
            continue

        lrs = learn_lrs(train)
        naive_probs_s = test.apply(lambda r: score_row(r, lrs), axis=1)  # 朴素概率每折算一次，评分与对决共用
        perf = evaluate_on_test(test, naive_probs_s)

        # ── 双模型同折对决：统一用 AUC + Tier≥4 块自助评估 ──────────
        naive_probs = naive_probs_s.values
        logit, logit_cols = fit_logit(train)
        Xt, _ = build_design_matrix(test)
        logit_probs = logit.predict_proba(Xt)[:, 1]
        y_test = test["fwd_up_20d"].astype(int).values

        duel = {"naive": evaluate_probs(test, naive_probs, "naive"),
                "logit": evaluate_probs(test, logit_probs, "logit")}

        naive_pool.append(naive_probs); logit_pool.append(logit_probs); y_pool.append(y_test)
        coef_signs.append(dict(zip(logit_cols, np.sign(logit.coef_[0]))))
        coef_values.append(dict(zip(logit_cols, logit.coef_[0])))

        def _fmt(bb):
            return (f"{bb['diff']:>+9.1f}pp{bb['p_boot']:>10.3f}" if bb
                    else f"{'n<10':>11}{'—':>10}")
        print(f"  {train_end}-{test_end:<6}{perf['baseline_wr']:>7.1f}%"
              f"{_fmt(duel['naive'].get('tier4_boot'))}"
              f"{_fmt(duel['logit'].get('tier4_boot'))}"
              f"{duel['naive']['auc']:>8.3f}{duel['logit']['auc']:>8.3f}")

        fold_results.append({
            "train": f"{train_start}-{train_end}",
            "test":  f"{train_end}-{test_end}",
            "n_train": len(train),
            "n_test":  len(test),
            "baseline_wr": perf["baseline_wr"],
            "performance": perf,
            "duel": duel,
        })

    # ── 全量数据学习最优LR（用于实际部署）──────────────────────────
    print("\n=== 全量数据学习最优LR（2000-2024）===")
    full_train = df[df["year"] <= 2024].copy()
    optimized_lrs = learn_lrs(full_train)

    print(f"\n  基准胜率：{optimized_lrs['base_win_rate']*100:.1f}%")
    print("  关键技术因子LR（前8）：")
    tech = {k: v for k, v in optimized_lrs["factors"].items()
            if isinstance(v, dict) and "lr" in v}
    for k, v in sorted(tech.items(), key=lambda x: abs(x[1]["lr"]-1), reverse=True)[:8]:
        print(f"    {k:<28}: LR={v['lr']:.4f}  胜率={v['win_rate']*100:.1f}%  n={v['n']}")

    # ── 汇总统计 ────────────────────────────────────────────────────
    tier4_diffs = [f["performance"].get("tier4_plus", {}).get("diff", 0)
                   for f in fold_results if "tier4_plus" in f["performance"]]
    tier4_sigs  = [f["performance"].get("tier4_plus", {}).get("significant", False)
                   for f in fold_results if "tier4_plus" in f["performance"]]

    print(f"\n=== 汇总 ===")
    print(f"  折数：{len(fold_results)}")
    if tier4_diffs:
        print(f"  Tier≥4 样本外平均优势：{np.mean(tier4_diffs):+.1f}pp")
        print(f"  显著折数：{sum(tier4_sigs)} / {len(tier4_sigs)}")

    # ── P2 对决汇总：拼接全部测试折 = 2012-2024 连续样本外序列 ──────
    y_all = np.concatenate(y_pool)
    nb_all = np.concatenate(naive_pool)
    lg_all = np.concatenate(logit_pool)
    duel_summary = {}
    for name, probs in [("naive", nb_all), ("logit", lg_all)]:
        sel = np.array([_tier(p) >= 4 for p in probs])
        duel_summary[name] = {
            "auc_pooled": round(float(roc_auc_score(y_all, probs)), 4),
            "n_tier4": int(sel.sum()),
            "tier4_boot": block_bootstrap_diff(sel, y_all),
            "mean_auc_folds": round(float(np.mean(
                [f["duel"][name]["auc"] for f in fold_results])), 4),
        }
    print(f"\n=== 拼接样本外对决（2012-2024，n={len(y_all)}）===")
    for name, s in duel_summary.items():
        bb = s["tier4_boot"] or {}
        print(f"  {name:>6}: AUC={s['auc_pooled']:.3f}  Tier≥4 diff={bb.get('diff','—')}pp  "
              f"CI95={bb.get('ci95','—')}  p_boot={bb.get('p_boot','—')}  n_t4={s['n_tier4']}")

    # ── 样本外校准（P2-3 地基）：测试折预测按分位分箱 → 实际20日胜率 ──
    oos_cal = {}
    for name, probs in [("naive", nb_all), ("logit", lg_all)]:
        qs = np.quantile(probs, np.linspace(0, 1, 8))
        rows = []
        for i in range(7):
            m = (probs >= qs[i]) & (probs <= qs[i + 1] if i == 6 else probs < qs[i + 1])
            if m.sum() < 30:
                continue
            rows.append({"prob_mean": round(float(probs[m].mean()), 4),
                         "actual_wr": round(float(y_all[m].mean()), 4),
                         "n": int(m.sum())})
        oos_cal[name] = rows

    # ── 校准漂移（#3）：逐折(各前向时间窗)校准是否随时间系统性偏移 ──
    from stats_util import calibration_drift
    cal_drift = calibration_drift(naive_pool, y_pool, [f["test"] for f in fold_results])
    if cal_drift.get("status") == "ok":
        print(f"\n=== 校准漂移（naive，逐折）：{cal_drift['verdict']} ===")
        print(f"  平均|缺口|={cal_drift['mean_abs_gap_pct']}pp  最大={cal_drift['max_abs_gap_pct']}pp  "
              f"趋势 ρ={cal_drift['trend_rho']} p={cal_drift['trend_p']}")

    # ── 系数稳定性（P2-5 地基）：跨折符号一致的特征才值得信 ─────────
    feats = list(coef_values[0].keys())
    stability = []
    for c in feats:
        vals = [cv[c] for cv in coef_values]
        signs = [cs[c] for cs in coef_signs]
        stability.append({
            "feature": c,
            "mean_coef": round(float(np.mean(vals)), 4),
            "sign_consistent": bool(len(set(s for s in signs if s != 0)) <= 1),
            "n_folds": len(vals),
        })
    stability.sort(key=lambda r: -abs(r["mean_coef"]))
    consistent = [r for r in stability if r["sign_consistent"] and abs(r["mean_coef"]) > 0.02]
    print(f"\n  跨折符号一致且 |coef|>0.02 的特征（{len(consistent)} 个）：")
    for r in consistent[:10]:
        print(f"    {r['feature']:<26} coef={r['mean_coef']:+.3f}")

    # ── 全量数据逻辑回归（若 v3.0 采纳，这就是部署系数）──────────────
    logit_full, full_cols = fit_logit(full_train)
    logit_full_coefs = {c: round(float(v), 4)
                        for c, v in zip(full_cols, logit_full.coef_[0])}
    logit_full_coefs["_intercept"] = round(float(logit_full.intercept_[0]), 4)

    # ── 写入结果 ────────────────────────────────────────────────────
    output = {
        "folds": fold_results,
        "optimized_lr": optimized_lrs,
        "summary": {
            "index":   "NASDAQ",
            "n_folds": len(fold_results),
            "mean_tier4_advantage_pp": round(float(np.mean(tier4_diffs)), 2) if tier4_diffs else None,
            "n_significant_folds":     sum(tier4_sigs),
            "horizon_days":            HORIZON,
        },
        # ── P2 对决产物 ──
        "duel_summary": duel_summary,
        "oos_calibration": oos_cal,
        "calibration_drift": cal_drift,
        "logit_coef_stability": stability,
        "logit_full_coefs": logit_full_coefs,
    }

    out = PROC_DIR / "walk_forward_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 结果写入 {out}（重跑 build_signals.py 后嵌入 signals.json）")

    return output


if __name__ == "__main__":
    run()
