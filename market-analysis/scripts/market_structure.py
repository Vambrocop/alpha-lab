"""market_structure.py — 市场结构解释（PCA 共动 + 相关性体制 + 因果回路）

纯解释层，不预测涨跌（遵守 ROADMAP 红线）。回答用户反复问的"哪个方法告诉你
什么在驱动市场"：
- PCA：跨资产日变动的主成分 = 市场的"共同因子"（PC1 通常是 risk-on/off）。
  无监督地告诉你"谁和谁一起动"，以及每个资产在各主成分上的载荷。
- 相关性体制：关键资产对当前 60 日相关性 vs 全历史——结构是否在变（如股债从负相关转正）。
- 因果回路（定性，前端画）：波动聚集平衡环、强平螺旋增强环——系统动力学视角。

只用 sklearn + pandas（核心依赖），CI 能跑。输出 market_structure.json → 研究面板。
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"

# 日变动：收益率类用 pct_change，利率/利差/VIX 用差分（水平更合理）
RET = {"NASDAQ", "SP500", "SOX", "BTC", "GOLD", "OIL", "DXY"}
DIFF = {"VIX", "TNX", "HY_SPREAD"}
# PCA 只用长历史(2014+)资产——HY_SPREAD 只有 2023+，混进去会把"近10年"偷偷缩成3年
PCA_ASSETS = ["NASDAQ", "SP500", "SOX", "BTC", "GOLD", "OIL", "DXY", "VIX", "TNX"]
LABELS = {"NASDAQ": "纳指", "SP500": "标普", "SOX": "费城半导体", "BTC": "比特币",
          "GOLD": "黄金", "OIL": "原油", "DXY": "美元", "VIX": "VIX", "TNX": "10Y利率",
          "HY_SPREAD": "高收益利差"}
# 数据层双语(2026-08-26):同一份键,英文标签单独一表(label/pair/assets 三处共用,不各写各的)
LABELS_EN = {"NASDAQ": "NASDAQ", "SP500": "S&P 500", "SOX": "PHLX Semis", "BTC": "Bitcoin",
             "GOLD": "Gold", "OIL": "Oil", "DXY": "US Dollar", "VIX": "VIX", "TNX": "10Y yield",
             "HY_SPREAD": "HY spread"}
# 相关性对：各自用各对自身可得的完整历史（不做全局 dropna）
PAIRS = [("NASDAQ", "BTC"), ("NASDAQ", "VIX"), ("NASDAQ", "DXY"),
         ("NASDAQ", "TNX"), ("NASDAQ", "GOLD"), ("SP500", "HY_SPREAD")]
RECENT_N = 60
CORR_SE = round(1 / np.sqrt(RECENT_N), 2)   # 60日相关性的近似标准误≈0.13


def _change_series(px, a):
    return px[a].pct_change() if a in RET else px[a].diff()


def _changes(px, assets):
    return pd.DataFrame({a: _change_series(px, a) for a in assets if a in px})


def run():
    px = pd.read_csv(RAW_DIR / "combined_prices.csv", index_col="Date", parse_dates=True).ffill()

    # ── PCA：真·近10年，只用长历史资产，complete-case ────────────────
    pca_assets = [a for a in PCA_ASSETS if a in px]
    pdf = _changes(px, pca_assets)
    pdf = pdf[pdf.index >= pdf.index[-1] - pd.DateOffset(years=10)].dropna()
    pca_years = round((pdf.index[-1] - pdf.index[0]).days / 365.25, 1)

    X = StandardScaler().fit_transform(pdf.values)
    pca = PCA(n_components=min(5, len(pca_assets))).fit(X)
    comps_ = pca.components_.copy()
    # 锚定符号：PCA 符号本身不唯一，统一翻成"股票多头为正"，否则下次刷新可能整体翻号、
    # 前端写死的解读会反过来。以 纳指+标普+费半 载荷之和的符号为准。
    eq = [pca_assets.index(a) for a in ("NASDAQ", "SP500", "SOX") if a in pca_assets]
    for i in range(len(comps_)):
        if comps_[i][eq].sum() < 0:
            comps_[i] *= -1
    evr = [round(float(v) * 100, 1) for v in pca.explained_variance_ratio_]
    comps = []
    for i in range(min(3, len(evr))):
        load = sorted(
            [{"asset": pca_assets[j], "label": LABELS.get(pca_assets[j], pca_assets[j]),
              "label_en": LABELS_EN.get(pca_assets[j], pca_assets[j]),
              "loading": round(float(comps_[i][j]), 2)}
             for j in range(len(pca_assets))],
            key=lambda x: -abs(x["loading"]))
        comps.append({"pc": i + 1, "explained_pct": evr[i], "loadings": load})

    # ── 相关性体制：每对用各自完整历史（pairwise dropna）vs 近60日 ──────
    corr_rows = []
    for a, b in PAIRS:
        if a not in px or b not in px:
            continue
        pair = pd.concat([_change_series(px, a), _change_series(px, b)],
                         axis=1, keys=["a", "b"]).dropna()
        if len(pair) < RECENT_N + 30:
            continue
        full = float(pair["a"].corr(pair["b"]))
        recent = float(pair["a"].tail(RECENT_N).corr(pair["b"].tail(RECENT_N)))
        full_years = round((pair.index[-1] - pair.index[0]).days / 365.25, 1)
        corr_rows.append({
            "pair": f"{LABELS.get(a,a)}–{LABELS.get(b,b)}",
        "pair_en": f"{LABELS_EN.get(a,a)}-{LABELS_EN.get(b,b)}",
            "recent_60d": round(recent, 2), "full_history": round(full, 2),
            "full_years": full_years, "shift": round(recent - full, 2),
        })

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "window": f"PCA：近{pca_years}年日变动（收益/差分）标准化；相关性：每对各自完整历史 vs 近60日",
        "window_en": (f"PCA: daily changes (returns/differences) over the last {pca_years} years, standardised; "
                      f"correlations: each pair's full history vs the last 60 days"),
        "corr_se": CORR_SE,
        "assets": [LABELS.get(a, a) for a in pca_assets],
        "assets_en": [LABELS_EN.get(a, a) for a in pca_assets],
        "pca": {"n_assets": len(pca_assets), "pca_years": pca_years, "components": comps,
                "sign_anchor": "已锚定符号：股票多头为正（PC 符号本不唯一，锚定后可安全解读）",
                "sign_anchor_en": ("Sign is anchored so that being long equities is positive (a PC's sign is not "
                                   "unique; once anchored it can be read safely)"),
                "pc1_note": "PC1 = risk-on/off 共同因子：股票/半导体/BTC 正、VIX 负（已按此约定锚定）",
                "pc1_note_en": ("PC1 = the risk-on/off common factor: equities / semis / BTC positive, VIX negative "
                                "(anchored to this convention)")},
        "correlation_regime": corr_rows,
        "note": (f"解释层，不预测涨跌。注意：近60日相关性是小样本，标准误≈±{CORR_SE}，"
                 "单看一格 0.3 量级的变化可能只是噪声——只把它当'值得留意'，别当确证的结构突变。"
                 "PCA 告诉你谁和谁一起动；相关性体制提示结构可能在变。"
                 "用途是理解'波动生态'（危机时相关性趋同、分散失效），不是择时。"),
        "note_en": (f"An interpretive layer; it does not predict direction. Note: a 60-day correlation is a small "
                    f"sample with a standard error of about +/-{CORR_SE}, so a single cell moving by ~0.3 may be "
                    "noise — treat it as 'worth watching', not as a confirmed structural break. PCA tells you what "
                    "moves together; the correlation regime hints that structure may be shifting. Its use is to "
                    "understand the volatility ecosystem (correlations converge in a crisis and diversification "
                    "fails), not to time the market."),
    }
    print(f"市场结构 PCA（{len(pca_assets)}资产，{pca_years}年）：")
    for c in comps:
        top = "、".join(f"{l['label']}{l['loading']:+}" for l in c["loadings"][:4])
        print(f"  PC{c['pc']} 解释 {c['explained_pct']}%： {top}")
    print(f"\n相关性体制（近60日 vs 各对完整历史，SE≈±{CORR_SE}）：")
    for r in corr_rows:
        print(f"  {r['pair']:<14} 近期{r['recent_60d']:+.2f}  历史({r['full_years']}年){r['full_history']:+.2f}  变化{r['shift']:+.2f}")

    path = PROC_DIR / "market_structure.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(f"\n[OK] 写入 {path}")
    return out


if __name__ == "__main__":
    run()
