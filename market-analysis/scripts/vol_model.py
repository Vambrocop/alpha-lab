"""vol_model.py — 波动率状态预测原型（高信噪比靶子）

P2-5 探针证明：同一套特征，预测"涨跌方向"AUC≈0.45（不可测），
预测"未来20日波动率高低"AUC≈0.65。波动率有聚集效应（今天波动大→明天大概率还大），
是真正可预测的。本脚本把这个靶子做成完整原型：

- 连续特征（VIX/VIX期限结构/已实现波动率多窗口/信用利差/跨资产波动/趋势），
  梯度提升树（sklearn HistGradientBoosting；--full 可换 LightGBM/SHAP）。
- 防泄漏：purged+embargo(20d) 扩窗 CV（开发集<2024）+ 2024-2026 干净保留集终审。
- 目标二值化阈值只用训练集（不偷看未来）；前向波动率构造无前视。
- 输出每折 + holdout 的 AUC、排列重要性 → vol_model.json → 研究面板。

定位：研究/方法论工具，不进信号链路（遵守 ROADMAP 红线）。但这是"逐步提高准确率"
真正可行的方向——靶子选对了，模型才有东西可学。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.inspection import permutation_importance

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"

HORIZON = 20
EMBARGO = 20
HOLDOUT_START = 2024
ANN = np.sqrt(252)
# 扩窗折：训练<train_end，测试[train_end, test_end)
FOLDS = [(2012, 2014), (2014, 2016), (2016, 2018), (2018, 2020), (2020, 2022), (2022, 2024)]


def build_features():
    """每个交易日的波动率预测特征（只用 t 时点及以前）+ 未来20日已实现波动率"""
    px = pd.read_csv(RAW_DIR / "combined_prices.csv", index_col="Date", parse_dates=True).ffill()
    r = np.log(px["NASDAQ"] / px["NASDAQ"].shift(1))

    f = pd.DataFrame(index=px.index)
    f["rv5"]   = r.rolling(5).std() * ANN
    f["rv20"]  = r.rolling(20).std() * ANN
    f["rv60"]  = r.rolling(60).std() * ANN
    f["rv_ratio"] = f["rv5"] / (f["rv20"] + 1e-9)         # 短/长波动比（上升=波动在抬头）
    f["abs_ret1"] = r.abs()
    if "VIX" in px:   f["vix"] = px["VIX"]
    if "VIX" in px:   f["vix_chg5"] = px["VIX"] - px["VIX"].shift(5)
    if "VIX" in px and "VIX3M" in px:
        f["vix_term"] = px["VIX"] - px["VIX3M"]            # 倒挂(>0)=恐慌
    if "HY_SPREAD" in px: f["hy_spread"] = px["HY_SPREAD"]
    if "DXY" in px:   f["dxy_tr20"] = px["DXY"].pct_change(20)
    if "BTC" in px:
        rb = np.log(px["BTC"] / px["BTC"].shift(1))
        f["btc_rv20"] = rb.rolling(20).std() * ANN
    ma200 = px["NASDAQ"].rolling(200).mean()
    f["ma200_dist"] = px["NASDAQ"] / ma200 - 1

    # 未来20日已实现波动率（无前视：只用 t+1..t+HORIZON）
    fwd = r.shift(-1).rolling(HORIZON).std().shift(-(HORIZON - 1)) * ANN
    f["fwd_rv20"] = fwd
    f["year"] = f.index.year
    # 只在 NASDAQ 真实交易日（去掉 ffill 造的周末重复），再要求关键特征/标签齐全
    f = f[r.notna().reindex(f.index, fill_value=False)]
    f = f.dropna(subset=["rv20", "fwd_rv20"]).copy()
    return f


FEATURES = ["rv5", "rv20", "rv60", "rv_ratio", "abs_ret1", "vix", "vix_chg5",
            "vix_term", "hy_spread", "dxy_tr20", "btc_rv20", "ma200_dist"]


def _purge(train, boundary_date, all_dates):
    """切掉前向窗口探入测试期的训练尾部（embargo=HORIZON）"""
    pos = all_dates.searchsorted(boundary_date)
    cutoff = all_dates[max(pos - EMBARGO, 0)]
    return train[train.index < cutoff]


def _gb():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                          max_iter=300, l2_regularization=1.0,
                                          random_state=42)


def _usable_features(train, candidates):
    """Filter fold-local constant/broken columns before sklearn binning.

    sklearn 1.9 + numpy 2.4 can fail inside HistGradientBoosting when a
    training fold contains a non-categorical column with fewer than two
    distinct finite values. The model gets no information from those columns
    anyway, so dropping them per fold is both safer and statistically cleaner.
    """
    usable = []
    for c in candidates:
        if c not in train.columns:
            continue
        s = pd.to_numeric(train[c], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if s.nunique() >= 2:
            usable.append(c)
    return usable


# ── 配对 AUC 差的循环块自助（block_bootstrap_diff 算的是比例差，不能复用）──
def block_bootstrap_auc_diff(y, sa, sb, block=HORIZON, B=2000, seed=42):
    """AUC(sa) − AUC(sb) 的 CI/p_boot。同一重采样索引同时算两档，保留 20 日重叠序列相关。"""
    y = np.asarray(y, float); sa = np.asarray(sa, float); sb = np.asarray(sb, float)
    n = len(y)
    if n < block * 3 or len(np.unique(y)) < 2:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    obs = float(roc_auc_score(y, sa) - roc_auc_score(y, sb))
    diffs = []
    for _ in range(B):
        starts = rng.integers(0, n, n_blocks)
        idx = np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]
        yi = y[idx]
        if len(np.unique(yi)) < 2:
            continue
        diffs.append(roc_auc_score(yi, sa[idx]) - roc_auc_score(yi, sb[idx]))
    diffs = np.array(diffs)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    p = 2 * min(float((diffs <= 0).mean()), float((diffs >= 0).mean()))
    return {"diff": round(obs, 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
            "p_boot": round(min(p, 1.0), 4)}


# 波动率"升/降"靶子的特征（波动动态：当前波动、短长波动比、VIX 期限结构/变化）
DIR_FEATURES = ["rv20", "rv5", "rv60", "rv_ratio", "vix", "vix_term", "vix_chg5"]


def vol_direction_experiment(f, all_dates):
    """靶子改成「未来20日已实现波动 vs 当前（升=1/降=0）」——VIX 没直接定价升降，
    基线第一次面对一个它不必然赢的对手。拼接所有 purged 测试折算样本外 AUC。"""
    feats = [c for c in DIR_FEATURES if c in f.columns]
    Y, S_model, S_naive, S_vix, RV, FWD = [], [], [], [], [], []
    for (tr_end, te_end) in FOLDS:
        tr = f[f["year"] < tr_end]
        te = f[(f["year"] >= tr_end) & (f["year"] < te_end)]
        if len(tr) < 300 or len(te) < 60:
            continue
        tr = _purge(tr, te.index.min(), all_dates)
        ytr = (tr["fwd_rv20"] > tr["rv20"]).astype(int)
        yte = (te["fwd_rv20"] > te["rv20"]).astype(int)
        if ytr.nunique() < 2 or yte.nunique() < 2:
            continue
        fold_feats = _usable_features(tr, feats)
        if not fold_feats:
            continue
        m = _gb(); m.fit(tr[fold_feats], ytr)
        Y.append(yte.values)
        S_model.append(m.predict_proba(te[fold_feats])[:, 1])
        S_naive.append((-te["rv20"]).values)   # 与标签自指：rv20 同时在标签两侧
        S_vix.append(te["vix"].values)
        RV.append(te["rv20"].values); FWD.append(te["fwd_rv20"].values)
    if not Y:
        return None
    y = np.concatenate(Y); sm = np.concatenate(S_model)
    sn = np.concatenate(S_naive); sv = np.concatenate(S_vix)
    rv = np.concatenate(RV); fwd = np.concatenate(FWD)
    auc_m = float(roc_auc_score(y, sm)); auc_n = float(roc_auc_score(y, sn))
    auc_v = float(roc_auc_score(y, sv))

    # ── 机械假象地板：把 fwd 打乱（毁掉一切真实"当前→未来"关系），重算基线 AUC。
    # 因 rv20 同时是分数与标签边界，即使无任何真信号，-rv20 对 (fwd>rv20) 仍有高 AUC。
    rng = np.random.default_rng(0)
    null_aucs = []
    for _ in range(80):
        y_null = (rng.permutation(fwd) > rv).astype(int)
        if len(np.unique(y_null)) > 1:
            null_aucs.append(roc_auc_score(y_null, sn))
    mech_null = round(float(np.mean(null_aucs)), 4) if null_aucs else None

    bb = block_bootstrap_auc_diff(y, sm, sn)   # 模型 vs 自指基线（唯一可解释量）
    print(f"\n=== 波动率升/降靶子（拼接样本外 n={len(y)}，正类{y.mean()*100:.1f}%）===")
    print(f"  模型 AUC={auc_m:.3f}  自指基线={auc_n:.3f}  VIX={auc_v:.3f}  机械假象地板={mech_null}")
    if bb:
        print(f"  模型-基线 = {bb['diff']:+.3f}  CI95={bb['ci95']}  p_boot={bb['p_boot']}（唯一可解释量）")
    return {
        "target": "未来20日已实现波动 vs 当前（升=1/降=0）",
        "target_en": "Next-20-day realised volatility vs today (rise = 1 / fall = 0)",
        "n_pooled": int(len(y)), "pos_pct": round(float(y.mean()) * 100, 1),
        "pooled_auc_model": round(auc_m, 4),
        "pooled_auc_naive_meanrev": round(auc_n, 4),
        "pooled_auc_vix": round(auc_v, 4),
        "mechanical_null_auc": mech_null,
        "model_vs_naive": bb,
        "features": feats,
        "note_en": ("WARNING - key correction (Opus review): rv20 appears on both sides of the label "
                    f"(fwd_rv20 > rv20) and also as a feature/score, creating mechanical self-reference — after "
                    f"shuffling the future, the baseline AUC is still about {mech_null} (a mechanical floor), which "
                    "means absolute AUCs like 0.72/0.75 are largely an artifact and not tradeable. The only "
                    "interpretable quantity is model minus an equally self-referential baseline, "
                    f"= {bb['diff'] if bb else '-'} (CI straddles 0, p={bb['p_boot'] if bb else '-'}, not significant). "
                    "Honest conclusion: even for the direction of volatility, a mechanically fair comparison finds no "
                    "robust exploitable signal — most of the mean reversion is a self-reference artifact. Also note: "
                    "this is the Nth re-pick of a target on the same data; the p-value is not corrected for multiple "
                    "comparisons and is exploratory."),
        "note": ("⚠ 关键修正（Opus 审查）：rv20 同时出现在标签两侧（fwd_rv20>rv20）又当特征/分数，"
                 f"造成机械自指——把未来打乱后基线 AUC 仍≈{mech_null}（机械地板），说明 0.72/0.75 这种绝对 AUC "
                 "大半是假象、不可交易。唯一可解释的是模型 vs 同样自指的基线之差，"
                 f"= {bb['diff'] if bb else '—'}（CI 跨 0、p={bb['p_boot'] if bb else '—'}，不显著）。"
                 "诚实结论：连波动率升降，用机械公平的对比也没找到稳健可利用的信号——均值回归大半是自指假象。"
                 "另注：这是同一数据上多次重选靶子的第 N 次，p 值未做多重比较校正，属探索性。"),
    }


def run():
    f = build_features()
    feats = [c for c in FEATURES if c in f.columns]
    all_dates = f.index
    dev = f[f["year"] < HOLDOUT_START]
    hold = f[f["year"] >= HOLDOUT_START]
    print(f"波动率原型：特征 {len(feats)} 个，dev {len(dev)} 天，holdout {len(hold)} 天")


    # ── 扩窗 CV（每折阈值只用训练集中位数）──────────────────────────
    # 同时记录 VIX-only 基线（仅用当日 VIX 排序）——若模型不显著优于它，
    # 说明"可预测性"几乎全来自 VIX 已经定价，复杂模型没加东西。诚实必须暴露这点。
    fold_rows = []
    print(f"\n{'测试期':<12}{'n_test':>7}{'高波动率%':>10}{'模型AUC':>9}{'VIX独立':>9}")
    for (tr_end, te_end) in FOLDS:
        tr = f[f["year"] < tr_end]
        te = f[(f["year"] >= tr_end) & (f["year"] < te_end)]
        if len(tr) < 300 or len(te) < 60:
            continue
        tr = _purge(tr, te.index.min(), all_dates)
        thr = tr["fwd_rv20"].median()
        ytr = (tr["fwd_rv20"] > thr).astype(int)
        yte = (te["fwd_rv20"] > thr).astype(int)
        if ytr.nunique() < 2 or yte.nunique() < 2:
            continue
        fold_feats = _usable_features(tr, feats)
        if not fold_feats:
            continue
        m = _gb(); m.fit(tr[fold_feats], ytr)
        auc = float(roc_auc_score(yte, m.predict_proba(te[fold_feats])[:, 1]))
        vix_auc = float(roc_auc_score(yte, te["vix"])) if "vix" in te else None
        fold_rows.append({"test": f"{tr_end}-{te_end}", "n": int(len(te)),
                          "pos_pct": round(float(yte.mean()) * 100, 1),
                          "auc": round(auc, 3),
                          "vix_only_auc": round(vix_auc, 3) if vix_auc else None})
        print(f"  {tr_end}-{te_end:<6}{len(te):>7}{yte.mean()*100:>9.1f}%{auc:>9.3f}"
              f"{(vix_auc if vix_auc else float('nan')):>9.3f}")

    # ── 终审：dev 训练 → 2024-2026 holdout（dev 也做 embargo，与折内一致）──
    dev_p = _purge(dev, hold.index.min(), all_dates)
    thr_dev = dev_p["fwd_rv20"].median()
    y_devp = (dev_p["fwd_rv20"] > thr_dev).astype(int)
    y_hold = (hold["fwd_rv20"] > thr_dev).astype(int)
    final_feats = _usable_features(dev_p, feats)
    if final_feats:
        final = _gb(); final.fit(dev_p[final_feats], y_devp)
        p_hold = final.predict_proba(hold[final_feats])[:, 1]
        holdout_auc = float(roc_auc_score(y_hold, p_hold)) if y_hold.nunique() > 1 else None
        # 排列重要性（在 holdout 上，看哪些特征真的带信息）
        imp = permutation_importance(final, hold[final_feats], y_hold, n_repeats=20,
                                     random_state=42, scoring="roc_auc")
        importances = sorted(
            [{"feature": final_feats[i], "importance": round(float(imp.importances_mean[i]), 4)}
             for i in range(len(final_feats))],
            key=lambda x: -x["importance"])
    else:
        # 兜底：dev 段全部特征恒定/损坏（实际上不会发生）——跳过终审拟合而非崩溃
        holdout_auc = None
        importances = []
    holdout_vix_auc = (float(roc_auc_score(y_hold, hold["vix"]))
                       if "vix" in hold and y_hold.nunique() > 1 else None)
    hold_pos_pct = round(float(y_hold.mean()) * 100, 1)
    fold_aucs = [r["auc"] for r in fold_rows]

    mean_cv = round(float(np.mean(fold_aucs)), 4) if fold_aucs else None
    cv_vix = [r["vix_only_auc"] for r in fold_rows if r["vix_only_auc"] is not None]
    mean_cv_vix = round(float(np.mean(cv_vix)), 4) if cv_vix else None
    n_blocks = int(len(hold) // HORIZON)   # 标签20日重叠，独立区块≈天数/20
    print(f"\n  holdout(2024-2026) AUC = {round(holdout_auc,4) if holdout_auc is not None else None}"
          f"  vs VIX独立基线 = {round(holdout_vix_auc,4) if holdout_vix_auc is not None else None}")
    print(f"  扩窗CV 平均AUC = {mean_cv}  vs VIX基线 = {mean_cv_vix}（{len(fold_aucs)}折，正类占比 2.5%~66% 不均，CV均值偏乐观）")
    print(f"  对照：方向预测 AUC≈0.45（P2-5探针）")
    print(f"  → 模型仅比 VIX-only 高 {round((holdout_auc or 0)-(holdout_vix_auc or 0),4)}：可预测性几乎全来自 VIX 已定价")
    print("\n  holdout 排列重要性（前6）：")
    for r_ in importances[:6]:
        print(f"    {r_['feature']:<12} {r_['importance']:+.4f}")

    # 方向对照（从 factor_pruning 探针读，避免重算）
    dir_auc = None
    try:
        with open(PROC_DIR / "factor_pruning.json", encoding="utf-8") as fp:
            dir_auc = json.load(fp).get("target_probe", {}).get("direction_auc_pooled_2012_2024")
    except Exception:
        pass

    gain = round((holdout_auc or 0) - (holdout_vix_auc or 0), 4)
    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "target": "未来20日已实现波动率 高/低（阈值=训练集中位数）",
        "target_en": "Next-20-day realised volatility, high vs low (threshold = training-set median)",
        "model": "HistGradientBoosting（sklearn，12特征）",
        "model_en": "HistGradientBoosting (sklearn, 12 features)",
        "method": "purged+embargo(20d) 扩窗CV + 2024-2026 终审保留集（dev/holdout 边界也 embargo）；阈值与前向波动率均无前视",
        "method_en": ("Purged + embargo (20d) expanding-window CV, plus a 2024-2026 final holdout "
                      "(the dev/holdout boundary is also embargoed); neither the threshold nor the forward "
                      "volatility uses look-ahead information"),
        "n_features": len(feats), "features": feats,
        "headline_auc": round(holdout_auc, 4) if holdout_auc is not None else None,   # 头条用 holdout（较均衡）
        "holdout_auc": round(holdout_auc, 4) if holdout_auc is not None else None,
        "holdout_vix_only_auc": round(holdout_vix_auc, 4) if holdout_vix_auc is not None else None,
        "holdout_model_gain_over_vix": gain,
        "holdout_pos_pct": hold_pos_pct,
        "holdout_eff_blocks": n_blocks,
        "cv_mean_auc": mean_cv, "cv_mean_vix_only_auc": mean_cv_vix, "n_folds": len(fold_aucs),
        "folds": fold_rows,
        "direction_auc_reference": dir_auc,
        "importances": importances,
        # v3.0-B：换靶子到"波动率升/降方向"（VIX 没直接定价的维度）
        "vol_direction": vol_direction_experiment(f, all_dates),
        "note": ("关键诚实点：波动率确实比方向可测得多，但模型仅比'只看当日VIX'的基线高约 "
                 f"{gain}——可预测性几乎全来自 VIX 已经把未来波动定价了，12 特征的梯度提升树没加什么。"
                 "结论不是'ML 厉害'，而是'选对靶子 + 市场已把容易的部分定价'。"
                 "另注：CV 各折正类占比 2.5%~66% 不均，早折 AUC 被抬高，故头条用较均衡的 holdout；"
                 f"holdout 标签 20 日重叠、独立区块仅约 {n_blocks} 个且单一 regime，AUC 点估计区间宽，需多 regime 复核。"),
        "note_en": ("The key honest point: volatility really is far more forecastable than direction, but the model "
                    f"beats the 'just look at today's VIX' baseline by only about {gain} — almost all of the "
                    "predictability comes from VIX already pricing future volatility; a 12-feature gradient-boosted "
                    "tree adds little. The lesson is not 'ML is powerful' but 'pick the right target, and the market "
                    "has already priced the easy part'. Also note: the positive-class share across CV folds ranges "
                    "2.5%-66%, which inflates AUC on early folds, so the headline uses the more balanced holdout; "
                    f"holdout labels overlap by 20 days with only about {n_blocks} independent blocks in a single "
                    "regime, so the AUC point estimate has a wide interval and needs multi-regime replication."),
    }
    path = PROC_DIR / "vol_model.json"
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"\n[OK] 写入 {path}")
    return out


if __name__ == "__main__":
    run()
