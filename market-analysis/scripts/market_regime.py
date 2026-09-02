"""
market_regime.py — 当前市场风险/流动性体制盘(R1，描述性,非预测)

诚实定位:回答"现在处于什么风险环境"——把波动率、收益率曲线、VIX 期限结构几个
**够长、跨完整周期**的指标各自定位(现值 + 历史分位 + 体制标签),给一句综合描述。
🔴 红线:**只描述当前环境,绝不预测方向、不构成操作建议**。"曲线倒挂与衰退相关"等是
历史关联的【描述】,非"会跌"的预测。

指标(均跨完整周期):VIX(2000+)/收益率曲线 10Y-2Y(2000+)/**信用利差 Baa-10Y(2000+)**/VIX 期限结构(2006+)/**个股共动羊群(2004+)**。
注:ICE 高收益利差(BAMLH0A0HYM2)在 FRED 仅开放~2年(访问限制),故信用维度改用穆迪 Baa-10Y(全史、无限制、等价的信用压力代理)。

依赖 numpy/pandas。输出 market_regime.json(PROC+WEB+DOCS 三处, allow_nan=False)。
"""
import datetime
import json
import pandas as pd
from pathlib import Path

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)


def _col(df, name):
    return pd.to_numeric(df[name], errors="coerce").dropna() if name in df.columns else None


def _pct(series, val):
    return round(float((series < val).mean()) * 100, 1)


HERDING_BASKET = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "COST", "LLY", "BRK-B"]  # 长历史(~2004+)大盘股


def _avg_pairwise_corr(rets, win):
    """日收益 DataFrame → 各日"近 win 日平均两两相关"的时间序列(纯函数,可测)。"""
    cols = list(rets.columns)
    pair = [rets[cols[i]].rolling(win).corr(rets[cols[j]])
            for i in range(len(cols)) for j in range(i + 1, len(cols))]
    return pd.concat(pair, axis=1).mean(axis=1).dropna()


def compute_herding(win=60):
    """羊群/共动体制:一篮大盘股【近 win 日平均两两相关】,当前值 + 历史分位。
    高=危机式趋同(everything moves together,分散失效);描述当前结构,非预测。"""
    f = RAW_DIR / "stocks_prices.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    cols = [c for c in HERDING_BASKET if c in df.columns]
    if len(cols) < 4:
        return None
    rets = df[cols].apply(pd.to_numeric, errors="coerce").pct_change().dropna(how="any")
    if len(rets) < 300:
        return None
    avg = _avg_pairwise_corr(rets, win)
    if len(avg) < 250:
        return None
    cur = float(avg.iloc[-1])
    return {"value": round(cur, 2), "percentile": round(float((avg < cur).mean()) * 100, 1),
            "history_start": str(avg.index[0].date()), "n_stocks": len(cols)}


# ── 数据层双语(2026-09-01)：档位**只判一次**,中英从同一张表取两列 ──────────────
# 不写两套 if/elif:那样改了中文档位忘改英文,英文读者看到的体制标签就与中文不一致
# (同 cpcv.py 的做法)。表里第 0 列中文、第 1 列英文。
_VIX_BANDS = {"extreme": ("极端高", "Extremely high"), "high": ("偏高", "Elevated"),
              "low": ("偏低", "Low"), "mid": ("中性", "Neutral")}
_CURVE_BANDS = {"inv": ("倒挂", "Inverted"), "flat": ("正斜率偏平", "Positive but flat"),
                "normal": ("正常(正斜率)", "Normal (positively sloped)")}
_CREDIT_BANDS = {"extreme": ("极端高(信用紧张)", "Extremely wide (credit stress)"),
                 "high": ("偏高", "Elevated"), "low": ("偏低(信用宽松)", "Narrow (easy credit)"),
                 "mid": ("中性", "Neutral")}
_TERM_BANDS = {"back": ("倒挂(近月恐慌>远月)", "Backwardated (front-month fear > back-month)"),
               "normal": ("正常(远月更高)", "Normal (back month higher)")}
_HERD_BANDS = {"extreme": ("极端抱团(分散失效)", "Extreme herding (diversification fails)"),
               "high": ("偏高(趋同)", "Elevated (converging)"),
               "low": ("偏低(各走各的)", "Low (names moving independently)"),
               "mid": ("中性", "Neutral")}
_NAME_EN = {
    "波动率 VIX": "Volatility (VIX)",
    "收益率曲线 10Y-2Y": "Yield curve 10Y-2Y",
    "信用利差 Baa-10Y": "Credit spread Baa-10Y",
    "VIX 期限结构 (VIX3M-VIX)": "VIX term structure (VIX3M-VIX)",
    "个股共动(羊群)": "Single-stock co-movement (herding)",
}
_NOTE_EN = {
    "波动率 VIX": "Equity volatility / fear level (where today sits in its own history).",
    "收益率曲线 10Y-2Y": "Term spread (monthly GS10/GS2, so the date can lag); inversions have "
                        "historically been associated with recessions (a descriptive association, "
                        "not a directional forecast).",
    "信用利差 Baa-10Y": "Moody's Baa corporate yield minus the 10Y Treasury (a proxy for credit "
                       "stress); a high percentile means tight credit (descriptive, not a forecast).",
    "VIX 期限结构 (VIX3M-VIX)": "Backwardation means front-month fear exceeds back-month, which "
                                "usually corresponds to acute market stress (describes the current "
                                "state, not a forecast).",
}


def compute_regime(df):
    """从 combined_prices.csv 算各风险指标的现值/历史分位/体制标签 + 综合描述。"""
    comps = []
    vix = _col(df, "VIX")
    if vix is None or len(vix) < 500:
        return {"status": "insufficient"}
    v = float(vix.iloc[-1]); vp = _pct(vix, v)
    _k = "extreme" if vp >= 95 else "high" if vp >= 75 else "low" if vp <= 25 else "mid"
    vix_label, vix_label_en = _VIX_BANDS[_k]
    comps.append({"name": "波动率 VIX", "name_en": _NAME_EN["波动率 VIX"],
                  "value": round(v, 1), "percentile": vp,
                  "label": vix_label, "label_en": vix_label_en,
                  "asof": str(vix.index[-1].date()), "history_start": str(vix.index[0].date()),
                  "note": "股市波动/恐慌水平(现值在历史的分位)",
                  "note_en": _NOTE_EN["波动率 VIX"]})

    y10, y2 = _col(df, "YIELD_10Y"), _col(df, "YIELD_2Y")
    if y10 is not None and y2 is not None:
        curve = float(y10.iloc[-1] - y2.iloc[-1])
        c_label, c_label_en = _CURVE_BANDS["inv" if curve < 0 else "flat" if curve < 0.5 else "normal"]
        comps.append({"name": "收益率曲线 10Y-2Y", "name_en": _NAME_EN["收益率曲线 10Y-2Y"],
                      "value": round(curve, 2), "label": c_label, "label_en": c_label_en,
                      "inverted": bool(curve < 0),
                      "asof": str(min(y10.index[-1], y2.index[-1]).date()),     # GS10/GS2 月频,会滞后
                      "history_start": str(max(y10.index[0], y2.index[0]).date()),
                      "note": "期限利差(月频GS10/GS2,日期可能滞后);倒挂在历史上与衰退相关(描述性关联，非方向预测)",
                      "note_en": _NOTE_EN["收益率曲线 10Y-2Y"]})

    credit = _col(df, "CREDIT_SPREAD")
    if credit is not None and len(credit) >= 500:
        cs = float(credit.iloc[-1]); csp = _pct(credit, cs)
        _k = "extreme" if csp >= 95 else "high" if csp >= 75 else "low" if csp <= 25 else "mid"
        cs_label, cs_label_en = _CREDIT_BANDS[_k]
        comps.append({"name": "信用利差 Baa-10Y", "name_en": _NAME_EN["信用利差 Baa-10Y"],
                      "value": round(cs, 2), "percentile": csp,
                      "label": cs_label, "label_en": cs_label_en,
                      "asof": str(credit.index[-1].date()), "history_start": str(credit.index[0].date()),
                      "note": "穆迪 Baa 公司债 减 10Y 国债(信用压力代理);高分位=信用紧张(描述性,非预测)",
                      "note_en": _NOTE_EN["信用利差 Baa-10Y"]})

    vix3m = _col(df, "VIX3M")
    if vix3m is not None and len(vix3m) > 200:
        term = float(vix3m.iloc[-1] - v)
        t_label, t_label_en = _TERM_BANDS["back" if term < 0 else "normal"]
        comps.append({"name": "VIX 期限结构 (VIX3M-VIX)", "name_en": _NAME_EN["VIX 期限结构 (VIX3M-VIX)"],
                      "value": round(term, 2), "label": t_label, "label_en": t_label_en,
                      "backwardation": bool(term < 0),
                      "asof": str(min(vix3m.index[-1], vix.index[-1]).date()),
                      "history_start": str(max(vix3m.index[0], vix.index[0]).date()),
                      "note": "倒挂=近月恐慌高于远月，通常对应急性市场压力(描述当前状态，非预测)",
                      "note_en": _NOTE_EN["VIX 期限结构 (VIX3M-VIX)"]})

    herd = compute_herding()
    if herd:
        hp = herd["percentile"]
        _k = "extreme" if hp >= 95 else "high" if hp >= 75 else "low" if hp <= 25 else "mid"
        h_label, h_label_en = _HERD_BANDS[_k]
        comps.append({"name": "个股共动(羊群)", "name_en": _NAME_EN["个股共动(羊群)"],
                      "value": herd["value"], "percentile": hp,
                      "label": h_label, "label_en": h_label_en,
                      "history_start": herd["history_start"],
                      "note": f"{herd['n_stocks']} 只大盘股近 60 日平均两两相关;高=危机式趋同(分散失效)、低=各走各的(描述性,非预测)",
                      "note_en": f"Average pairwise correlation of {herd['n_stocks']} large-cap names "
                                 "over the last 60 days; high = crisis-style convergence "
                                 "(diversification stops working), low = names moving independently "
                                 "(descriptive, not a forecast)."})

    # 综合(纯描述,不给方向/操作)
    bits = [f"波动率{vix_label}"]
    cv = next((c for c in comps if c["name"].startswith("收益率")), None)
    if cv:
        bits.append("曲线" + cv["label"])
    cr = next((c for c in comps if c["name"].startswith("信用利差")), None)
    if cr:
        bits.append("信用利差" + cr["label"])
    hd = next((c for c in comps if c["name"].startswith("个股共动")), None)
    if hd:
        bits.append("个股共动" + hd["label"])
    tv = next((c for c in comps if c["name"].startswith("VIX 期限")), None)
    if tv and tv.get("backwardation"):
        bits.append("期限结构倒挂(近月恐慌>远月)")
    composite = "当前环境：" + " + ".join(bits) + "。"

    return {"status": "ok", "asof": str(vix.index[-1].date()), "components": comps,
            "composite": composite}


def run_all():
    print("=== R1 当前市场风险体制盘(描述性,非预测)===")
    f = RAW_DIR / "combined_prices.csv"
    if not f.exists():
        print("⚠ 无 combined_prices.csv，跳过")
        return None
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    res = compute_regime(df)
    if res.get("status") != "ok":
        print("⚠ 数据不足，跳过")
        return None
    for c in res["components"]:
        print(f"  {c['name']:<22} {c['value']}  [{c['label']}]")
    print("  " + res["composite"])

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "这是【当前风险环境的客观描述】——现值在历史的位置 + 体制标签,"
                  "**绝不预测方向、不构成买卖建议**。如'曲线倒挂与衰退相关'是历史关联的描述,非'会跌'。"
                  "用 VIX(2000+)/收益率曲线(2000+)/信用利差 Baa-10Y(2000+)/VIX 期限结构(2006+)/个股共动羊群(2004+),均跨 2008、2020。"
                  "信用维度用穆迪 Baa-10Y(ICE 高收益利差在 FRED 仅~2年,访问受限);羊群=8 只大盘股近60日平均两两相关。",
        **res,
    }
    from util_io import write_json
    write_json("market_regime.json", out, proc=True, allow_nan=False)
    print("[OK] market_regime.json")
    return out


if __name__ == "__main__":
    run_all()
