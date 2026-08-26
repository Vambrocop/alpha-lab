"""
export_stocks.py — 个股观察池数据导出（七姐妹 + 优质龙头）

读取 stocks_prices.csv + combined_prices.csv（指数基准），
为每只股票计算关键指标和近3年归一化周线走势，输出 web/stocks.json。
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from signal_model import rsi as _rsi   # 原语唯一来源（删除本地重复实现）

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
WEB_DIR = Path(__file__).parent.parent / "web"

LABELS = {
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌", "AMZN": "亚马逊",
    "NVDA": "英伟达", "META": "Meta", "TSLA": "特斯拉",
    "AVGO": "博通", "TSM": "台积电", "COST": "好市多",
    "LLY": "礼来", "BRK-B": "伯克希尔", "SNDK": "闪迪", "MU": "美光",
    "AMD": "超微", "INTC": "英特尔", "NFLX": "网飞", "HOOD": "罗宾汉",
}
# 数据层双语(2026-08-26):同键英文表。多数美股本就以英文名为通称,直接用公司英文名;
# 前端 EN 模式取 label_en,缺失回落中文(vpD 的统一约定)。
LABELS_EN = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon",
    "NVDA": "NVIDIA", "META": "Meta", "TSLA": "Tesla",
    "AVGO": "Broadcom", "TSM": "TSMC", "COST": "Costco",
    "LLY": "Eli Lilly", "BRK-B": "Berkshire", "SNDK": "SanDisk", "MU": "Micron",
    "AMD": "AMD", "INTC": "Intel", "NFLX": "Netflix", "HOOD": "Robinhood",
}
MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

YEARS_OF_SERIES = 3   # 走势图年数（周线）


def _stats(s, bench_ret):
    """单只股票的关键指标（s: 日线收盘价序列）"""
    s = s.dropna()
    if len(s) < 260:
        return None
    ret = s.pct_change()
    last = s.index[-1]
    ytd_start = s[s.index.year < last.year]
    out = {
        "last":       round(float(s.iloc[-1]), 2),
        "date":       last.strftime("%Y-%m-%d"),
        "chg_1d":     round(float(ret.iloc[-1] * 100), 2),
        "chg_5d":     round(float((s.iloc[-1] / s.iloc[-6] - 1) * 100), 2),
        "chg_20d":    round(float((s.iloc[-1] / s.iloc[-21] - 1) * 100), 2),
        "ytd":        round(float((s.iloc[-1] / ytd_start.iloc[-1] - 1) * 100), 2)
                      if len(ytd_start) else None,
        "chg_1y":     round(float((s.iloc[-1] / s.iloc[-253] - 1) * 100), 2)
                      if len(s) > 253 else None,
        "from_high_52w": round(float((s.iloc[-1] / s.tail(252).max() - 1) * 100), 2),
        "above_ma50":  bool(s.iloc[-1] > s.rolling(50).mean().iloc[-1]),
        "above_ma200": bool(s.iloc[-1] > s.rolling(200).mean().iloc[-1]),
        "rsi14":       round(float(_rsi(ret).iloc[-1]), 1),
        "vol20_ann":   round(float(ret.rolling(20).std().iloc[-1] * np.sqrt(252) * 100), 1),
    }

    # ── 个股分析模板的标准维度（描述性，非预测）──────────────────────
    # 趋势强度：距MA200百分比（>0 多头排列，越大越强/越可能超买）
    ma200 = s.rolling(200).mean().iloc[-1]
    out["dist_ma200"] = round(float((s.iloc[-1] / ma200 - 1) * 100), 1) if not np.isnan(ma200) else None
    # 波动率分位：当前20日波动在自身近一年中的百分位（>80=异常高波动）
    vol20 = (ret.rolling(20).std() * np.sqrt(252)).dropna()
    if len(vol20) > 60:
        out["vol_pctile_1y"] = round(float((vol20.tail(252) < vol20.iloc[-1]).mean() * 100))
    # 最大回撤（整段历史，风险体感）
    dd = s / s.cummax() - 1
    out["max_dd"] = round(float(dd.min() * 100), 1)
    # 52周区间位置（0=贴近一年最低，100=贴近一年最高）
    hi, lo = s.tail(252).max(), s.tail(252).min()
    out["range_pctile_52w"] = round(float((s.iloc[-1] - lo) / (hi - lo) * 100)) if hi > lo else None
    # 粗略风险调整收益：近1年收益 / 年化波动（>1 性价比好；非夏普但同向）
    if len(s) > 253:
        r1y = s.iloc[-1] / s.iloc[-253] - 1
        v1y = float(ret.tail(252).std() * np.sqrt(252))
        out["ret_vol_1y"] = round(float(r1y / v1y), 2) if v1y > 0 else None

    # 与纳指的1年期 beta / 相关性 / 系统性占比（按共同交易日对齐）
    pair = pd.concat([ret, bench_ret], axis=1, join="inner").dropna().tail(252)
    if len(pair) > 60:
        cov = pair.cov()
        corr = float(pair.corr().iloc[0, 1])
        out["beta_nasdaq_1y"] = round(float(cov.iloc[0, 1] / cov.iloc[1, 1]), 2)
        out["corr_nasdaq_1y"] = round(corr, 2)
        out["r2_nasdaq_1y"] = round(corr * corr, 2)   # 波动有多少由大盘解释（系统性 vs 个股特有）
    return out


def _weekly_norm(s, start):
    """周线 + 归一化到100"""
    w = s.dropna()[start:].resample("W").last().dropna()
    if len(w) < 10:
        return None
    base = w.iloc[0]
    return {
        "dates":  [d.strftime("%Y-%m-%d") for d in w.index],
        "values": [round(float(v / base * 100), 2) for v in w],
    }


def _scale(x, lo, hi):
    """把 x 从 [lo,hi] 线性映射到 0..100（lo>hi 即反向：原值越大分越低），裁剪到 [0,100]。"""
    if x is None:
        return None
    t = (x - lo) / (hi - lo) * 100
    return round(max(0.0, min(100.0, t)))


def _radar(st):
    """6 维 0-100 描述性雷达（非预测、非买卖信号；全部来自 _stats 现成指标）。
    维度：动量/趋势/稳健/性价比/独立性/反弹空间。稳健·独立性·反弹空间为反向（原值越大分越低）。"""
    r = {
        "动量":     _scale(st.get("chg_1y"),          -40, 120),   # 近1年涨幅
        "趋势":     _scale(st.get("dist_ma200"),       -20,  40),  # 距MA200，多头排列强度
        "稳健":     _scale(st.get("vol20_ann"),         80,  15),  # 年化波动，低=稳健（反向）
        "性价比":   _scale(st.get("ret_vol_1y"),       -0.5, 2.5), # 风险调整收益（非夏普，同向）
        "独立性":   _scale(st.get("r2_nasdaq_1y"),      0.8, 0.1),  # 与纳指R²，低=分散价值（反向）
        "反弹空间": _scale(st.get("range_pctile_52w"), 100,   0),   # 52周区间位置，低=空间大（反向）
    }
    return {k: v for k, v in r.items() if v is not None}


# ── SPCX（SpaceX，2026-06-12 上市）────────────────────────────
# 新股历史不足 260 天进不了常规观察池（_stats 直接返回 None），
# 单独导出一个轻量块供"我的"视图 SPCX 监视卡使用。
SPCX_ISSUE_USD = 135.0

def _spcx_block(stocks):
    if "SPCX" not in stocks.columns:
        return None
    s = stocks["SPCX"].dropna()
    if not len(s):
        return None
    out = {
        "last":         round(float(s.iloc[-1]), 2),
        "date":         s.index[-1].strftime("%Y-%m-%d"),
        "issue":        SPCX_ISSUE_USD,
        "vs_issue_pct": round(float((s.iloc[-1] / SPCX_ISSUE_USD - 1) * 100), 2),
        "days_listed":  int(len(s)),
        "high":         round(float(s.max()), 2),
        "low":          round(float(s.min()), 2),
        "series": {
            "dates":  [d.strftime("%Y-%m-%d") for d in s.index],
            "values": [round(float(v), 2) for v in s],
        },
    }
    if len(s) >= 2:
        out["chg_1d"] = round(float((s.iloc[-1] / s.iloc[-2] - 1) * 100), 2)

    # 供给面慢变量（流通盘/做空/机构持仓）——上市初期 Yahoo 可能尚未填充，None 时前端隐藏
    try:
        import math
        import yfinance as yf
        info = yf.Ticker("SPCX").get_info() or {}

        def _num(k, scale=1.0):
            v = info.get(k)
            if isinstance(v, (int, float)) and math.isfinite(v):
                return round(float(v) * scale, 2)
            return None
        supply = {
            "shares_outstanding": _num("sharesOutstanding"),
            "float_shares":       _num("floatShares"),
            "short_pct_float":    _num("shortPercentOfFloat", 100),
            "inst_held_pct":      _num("heldPercentInstitutions", 100),
            "insider_held_pct":   _num("heldPercentInsiders", 100),
        }
        if any(v is not None for v in supply.values()):
            if supply["float_shares"] and supply["shares_outstanding"]:
                supply["float_pct"] = round(
                    supply["float_shares"] / supply["shares_outstanding"] * 100, 1)
            out["supply"] = supply
    except Exception as e:
        print(f"  · SPCX 供给面数据不可用: {e}")
    return out


def main():
    stocks = pd.read_csv(RAW_DIR / "stocks_prices.csv",
                         index_col="Date", parse_dates=True)
    combined = pd.read_csv(RAW_DIR / "combined_prices.csv",
                           index_col="Date", parse_dates=True)
    bench_ret = combined["NASDAQ"].dropna().pct_change()

    start = (stocks.index[-1] - pd.DateOffset(years=YEARS_OF_SERIES))

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "mag7": MAG7,
        "indices": {},
        "stocks": {},
    }
    # 指数基准走势（同窗口归一化）
    for idx in ["NASDAQ", "SP500"]:
        series = _weekly_norm(combined[idx], start)
        if series:
            out["indices"][idx] = series

    out["spcx"] = _spcx_block(stocks)
    if out["spcx"]:
        print(f"  SPCX   SpaceX 最新={out['spcx']['last']}  vs发行价={out['spcx']['vs_issue_pct']:+.1f}%")

    for sym in stocks.columns:
        if sym == "SPCX":
            continue  # 专属块已处理，不进常规观察池
        s = stocks[sym]
        stats = _stats(s, bench_ret)
        series = _weekly_norm(s, start)
        if not stats or not series:
            print(f"  ⚠ {sym} 数据不足，跳过")
            continue
        out["stocks"][sym] = {
            "label":  LABELS.get(sym, sym),
            "label_en": LABELS_EN.get(sym, sym),
            "is_mag7": sym in MAG7,
            "stats":  stats,
            "radar":  _radar(stats),
            "series": series,
        }
        print(f"  {sym:<6} {LABELS.get(sym, sym):<5} 最新={stats['last']:>10}  "
              f"YTD={stats['ytd']:>7}%  RSI={stats['rsi14']}")

    path = WEB_DIR / "stocks.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[OK] {len(out['stocks'])} 只个股 → {path}  ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
