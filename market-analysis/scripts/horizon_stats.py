"""
horizon_stats.py — 持有期基率统计（"长期视角"页数据源）

统计学的正确用法：不预测"明天涨不涨"（v3.0 实验已证伪），
而是回答"历史上任意一天买入并持有 N 年，结果的完整分布是什么"。
滚动重叠窗口、日频起点，描述性基率——不是置信区间（重叠窗口自相关）。

输出 data/processed/horizon_stats.json，由 build_signals 嵌入 signals.json.horizon_stats。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from label_en import label_en          # 共享规则翻译器(资产/因子中文名 → 英文)

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"

# 持有期（交易日）
HORIZONS = [("6mo", 126), ("1y", 252), ("3y", 756), ("5y", 1260), ("10y", 2520)]

HONESTY = [
    "历史分布 ≠ 未来保证：这是过去 26-98 年美国市场的经验基率，含幸存者偏差（美国恰好是上个世纪表现最好的市场之一）",
    "名义收益，未扣通胀；扣通胀后长期年化约低 2-3 个百分点",
    "重叠滚动窗口（日频起点）自相关——这些是描述性分布，不是统计置信区间",
    "上涨概率随持有期上升是历史上最稳健的规律之一，但它的机制（经济长期增长+通胀）成立的前提是世界大致正常运转",
]
# 数据层双语(2026-09-01)：这四条是**诚实披露**，英文模式下漏译等于英文读者少看到风险提示，
# 比表格里的数字更不能漏。定稿散文（不走 label_en 规则翻译器——那个只管组合生成的短标签）。
HONESTY_EN = [
    "A historical distribution is not a guarantee about the future: these are empirical base rates from "
    "26-98 years of US markets, and they carry survivorship bias (the US happens to be one of the best "
    "performing markets of the last century).",
    "Nominal returns, not inflation-adjusted; after inflation the long-run annualised figures are roughly "
    "2-3 percentage points lower.",
    "Overlapping rolling windows (a new start date every trading day) are autocorrelated — these are "
    "descriptive distributions, not statistical confidence intervals.",
    "'Probability of being up rises with holding period' is one of the most robust regularities in the "
    "historical record, but the mechanism behind it (long-run economic growth + inflation) assumes the "
    "world keeps running roughly normally.",
]


def _load_series():
    out = {}
    sp = pd.read_csv(RAW_DIR / "SP500_long.csv", index_col=0, parse_dates=True).squeeze().dropna()
    out["SP500"] = ("标普500", sp[sp > 0].sort_index())
    nq = pd.read_csv(RAW_DIR / "NASDAQ_COMP_long.csv", index_col=0, parse_dates=True).squeeze().dropna()
    out["NASDAQ"] = ("纳斯达克综合", nq[nq > 0].sort_index())
    comb = pd.read_csv(RAW_DIR / "combined_prices.csv", index_col=0, parse_dates=True)
    if "SOX" in comb.columns:
        sox = comb["SOX"].dropna()
        out["SOX"] = ("费城半导体", sox[sox > 0].sort_index())
    return out


def horizon_table(s, horizons=HORIZONS):
    """每个持有期：滚动总回报分布 → 基率统计"""
    v = s.values.astype(float)
    rows = {}
    for label, h in horizons:
        if len(v) <= h + 50:    # 窗口太少不报告
            continue
        tot = v[h:] / v[:-h] - 1.0           # 重叠窗口总回报
        ann = (1.0 + tot) ** (252.0 / h) - 1.0
        q = lambda arr, p: float(np.percentile(arr, p))
        rows[label] = {
            "trading_days": h,
            "n_windows": int(len(tot)),
            "p_positive": round(float((tot > 0).mean()), 4),
            "p_loss_gt_20": round(float((tot < -0.20).mean()), 4),
            "ann_p5":  round(q(ann, 5) * 100, 1),
            "ann_p25": round(q(ann, 25) * 100, 1),
            "ann_median": round(q(ann, 50) * 100, 1),
            "ann_p75": round(q(ann, 75) * 100, 1),
            "ann_p95": round(q(ann, 95) * 100, 1),
            "worst_total": round(float(tot.min()) * 100, 1),
            "best_total":  round(float(tot.max()) * 100, 1),
        }
    return rows


def run():
    series = _load_series()
    out = {"generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
           "honesty": HONESTY, "honesty_en": HONESTY_EN, "indices": {}}
    print("=== 持有期基率统计 ===")
    for key, (label, s) in series.items():
        tbl = horizon_table(s)
        out["indices"][key] = {
            "label": label,
            "label_en": label_en(label),      # 指数中文名 → 英文(共享规则翻译器,新增指数自动跟上)
            "start": s.index[0].strftime("%Y-%m-%d"),
            "end":   s.index[-1].strftime("%Y-%m-%d"),
            "years": round((s.index[-1] - s.index[0]).days / 365.25, 1),
            "horizons": tbl,
        }
        print(f"\n  {label}（{s.index[0].year}-{s.index[-1].year}）")
        for hl, r in tbl.items():
            print(f"    {hl:>4}: P(涨)={r['p_positive']:.0%}  年化中位={r['ann_median']:+.1f}%"
                  f"  [p25 {r['ann_p25']:+.1f}, p75 {r['ann_p75']:+.1f}]"
                  f"  最差总回报={r['worst_total']:+.1f}%  n={r['n_windows']}")

    path = PROC_DIR / "horizon_stats.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"\n[OK] 写入 {path}")
    return out


if __name__ == "__main__":
    run()
