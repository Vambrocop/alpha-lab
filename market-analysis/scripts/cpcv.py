"""
cpcv.py — 组合对称交叉验证(CSCV)的过拟合概率 PBO(方法 G,审计增强 / Fable 原则:升级验证不加模型)

诚实问题:我们这些"因子边际"有多大概率纯属**过拟合 / 数据挖掘**?
方法:Bailey-Borwein-López de Prado-Zhu (2017) 的 CSCV —— 把时间轴切成 S 段,遍历 C(S, S/2) 种
"半训练半测试"组合;每种组合在训练集选出表现最好的因子(IS-best),看它在测试集的相对排名;
**PBO = IS-best 在 OOS 低于中位的组合占比**。高 PBO = "挑出的'最佳'因子大概率是过拟合"。
purge 掉切片首端 HORIZON 行,防 20 日前向窗口跨片泄漏。**不预测方向**,只量化选择性过拟合风险。
CSCV 枚举全部组合 → 确定性(无需随机种子)。依赖 numpy + walk_forward(core)。输出 cpcv.json。
"""
import datetime
import json
import warnings
from itertools import combinations
from pathlib import Path

import numpy as np

SCRIPTS  = Path(__file__).parent
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

S_SLICES = 10        # 切片数;C(10,5)=252 个对称组合
HORIZON  = 20        # 前向收益窗口(用于 purge 切片边界)
MIN_N    = 20        # 每片/每因子最少有效样本,否则该格 edge=NaN


def _perf_matrix(df, factors):
    """S×F 表现矩阵:每片每因子的 edge = 片内 win_rate(因子触发) − 片内基准率。"""
    y = df["fwd_up_20d"].to_numpy(dtype=float)
    n = len(y)
    bounds = np.linspace(0, n, S_SLICES + 1, dtype=int)
    R = np.full((S_SLICES, len(factors)), np.nan)
    fcols = [df[c].to_numpy() for c in factors]
    for s in range(S_SLICES):
        lo = bounds[s] + (HORIZON if s > 0 else 0)      # purge:去掉与上片前向窗重叠的片首
        hi = bounds[s + 1]
        ys = y[lo:hi]
        if len(ys) < MIN_N:
            continue
        base = ys.mean()
        for j, col in enumerate(fcols):
            fires = col[lo:hi] == 1
            if int(fires.sum()) >= MIN_N:
                R[s, j] = ys[fires].mean() - base       # 该因子在该片的边际(胜率差)
    return R


def pbo(R):
    """CSCV PBO:遍历 C(S,S/2),IS-best 因子的 OOS 相对排名 logit<0(低于中位)占比。"""
    S, F = R.shape
    all_s = list(range(S))
    lambdas = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)     # 全-NaN 切片 nanmean 噪声(下方 valid 已剔除)
        for is_idx in combinations(all_s, S // 2):
            oos_idx = [s for s in all_s if s not in is_idx]
            is_perf  = np.nanmean(R[list(is_idx)], axis=0)
            oos_perf = np.nanmean(R[oos_idx], axis=0)
            valid = ~np.isnan(is_perf) & ~np.isnan(oos_perf)
            if int(valid.sum()) < 2:
                continue
            n_star = int(np.argmax(np.where(valid, is_perf, -np.inf)))   # 训练集最佳因子(并列时取最低索引,确定性)
            ov = oos_perf[valid]
            rank = int((ov <= oos_perf[n_star]).sum())                   # n_star 的 OOS 排名(大=好)
            w = rank / (int(valid.sum()) + 1)                            # 相对排名 ω∈(0,1),1=最好
            w = min(max(w, 1e-6), 1 - 1e-6)
            lambdas.append(float(np.log(w / (1 - w))))                   # logit λ;<0 = OOS 低于中位
    if not lambdas:
        return None
    arr = np.array(lambdas)
    return {"pbo": round(float((arr < 0).mean()), 4),
            "n_combos": len(arr),
            "median_logit": round(float(np.median(arr)), 3)}


def run_all():
    print("=== 方法 G:CSCV 过拟合概率 PBO ===")
    try:
        from walk_forward import build_feature_df, BINARY_FEATURES
        df = build_feature_df()
    except Exception as e:
        print(f"⚠ 无法构建特征 df:{e},跳过")
        return None
    factors = [c for c, _ in BINARY_FEATURES if c in df.columns]
    if df is None or len(df) < 500 or len(factors) < 3:
        print("⚠ 数据/因子不足,跳过")
        return None

    R = _perf_matrix(df, factors)
    res = pbo(R)
    if res is None:
        print("⚠ 无足够有效组合,跳过")
        return None
    p, ml = res["pbo"], res["median_logit"]
    # 数据层双语(2026-09-01)：**先定档、再按同一张表渲染中英**——不写两套 if/elif。
    # 两套分支迟早会漂移(改了中文档位忘了改英文 → 英文读者看到的裁决与中文不一致,这在诚实
    # 计分的项目里是硬伤)。档位只判一次,zh/en 从同一行取。
    band = "high" if p >= 0.5 else "mid" if p >= 0.35 else "low"
    TAG = {
        "high": ("高(严重):挑'最佳'因子样本外≥半数低于中位,≈随机或更差",
                 "High (severe): the 'best' factor lands below the median out-of-sample at least half "
                 "the time — no better than chance, or worse"),
        "mid":  ("中等:样本外泛化只略好于抛硬币、远非稳健",
                 "Moderate: out-of-sample generalisation is only slightly better than a coin flip, "
                 "nowhere near robust"),
        "low":  ("偏低:因子选择有一定样本外泛化(仍需 BY/DSR 佐证)",
                 "Lowish: factor selection does generalise somewhat out-of-sample (still needs BY/DSR "
                 "corroboration)"),
    }
    ML = (("(中位 logit>0:典型最佳因子 OOS 仍在中位之上,故非严重过拟合)",
           "(median logit > 0: the typical best factor still sits above the median out-of-sample, so "
           "this is not severe overfitting)")
          if ml > 0 else
          ("(中位 logit<0:典型最佳因子 OOS 低于中位)",
           "(median logit < 0: the typical best factor falls below the median out-of-sample)"))
    res["n_factors"] = len(factors)
    res["verdict"] = (f"PBO={p*100:.0f}% —— {TAG[band][0]}。中位 logit={ml}{ML[0]}。"
                      "结合 BY/DSR:仍无稳健可外推的因子 alpha。")
    res["verdict_en"] = (f"PBO={p*100:.0f}% — {TAG[band][1]}. Median logit={ml} {ML[1]}. "
                         "Taken together with BY/DSR: still no robust, extrapolatable factor alpha.")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "CSCV(Bailey-Borwein-LdP-Zhu 2017):时间轴切 S 段,遍历 C(S,S/2) 半训半测组合;"
                  "训练选最佳因子,看其测试相对排名;PBO=IS-best 在 OOS 低于中位的占比。purge 切片边界防泄漏。",
        "caveat": "PBO 度量的是**因子选择的过拟合概率**(数据挖掘风险),不是方向预测。"
                  "edge=片内胜率差(小样本噪声大);S=10/purge=20日为口径选择。高 PBO 是诚实信号:别相信'挑出来最好'的因子。",
        "method_en": "CSCV (Bailey-Borwein-Lopez de Prado-Zhu 2017): cut the timeline into S slices, "
                     "enumerate all C(S, S/2) half-train/half-test combinations; pick the best factor on "
                     "the training half, then look at its relative rank on the test half. PBO = the share "
                     "of combinations where the in-sample best falls below the out-of-sample median. "
                     "Slice boundaries are purged to prevent leakage.",
        "caveat_en": "PBO measures the **probability that factor selection is overfitted** (data-mining "
                     "risk); it is not a directional forecast. 'edge' is the within-slice hit-rate "
                     "difference (noisy on small samples); S=10 / purge=20 days are methodology choices. "
                     "A high PBO is an honest warning signal: do not trust whichever factor 'came out "
                     "best'.",
        "source": f"walk_forward 特征 df({len(factors)} 个二值因子)", "s_slices": S_SLICES,
        "horizon": HORIZON, "result": res,
    }
    from util_io import write_json
    write_json("cpcv.json", out, proc=True, allow_nan=False)
    print(f"  {res['verdict']}  (n_combos={res['n_combos']}, 因子={len(factors)})")
    print("[OK] cpcv.json")
    return out


if __name__ == "__main__":
    run_all()
