"""
build_signals.py
预计算每一天的入场信号，输出 JSON 供前端使用。
信号 = 综合贝叶斯概率（季节性 + 星期 + 月内 + 假日 + 技术 + 事件调整）
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import date, timedelta
from zoneinfo import ZoneInfo

# 模型核心原语统一来自 signal_model（生产与 walk_forward 验证共用，禁止本地复制）
from signal_model import (
    tier as _tier, bayesian_update, week_of_month as _week_of_month,
    rsi as _rsi, shrink_lr, us_holidays as _us_holidays, pav_monotonic,
    HOLIDAY_SET as _HOLIDAY_SET, THANKSGIVING_DATES as _THANKSGIVING_DATES,
    BTC_MOM_THRESH, DXY_TREND_THRESH, VOL_HIGH, VOL_LOW,
    RSI_OVERBOUGHT, RSI_OVERSOLD, TIER_THRESHOLDS,
)


def us_today():
    """美东当前日期。用户在澳洲阿德莱德(UTC+9:30)，本地日期比美国快一天，
    所有「今天/未来」的判断必须以美东交易日为准"""
    return pd.Timestamp.now(tz=ZoneInfo("America/New_York")).date()

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"

# 模型版本号：每次调整模型逻辑时更新，供实盘预测追踪区分新旧模型
# v2.1: 新增 VIX期限结构 + 隔夜动量因子
MODEL_VERSION = "2.1"   # 保持2.1:未上新模型(v3稀疏模型经检验被否、未部署);账本按版本号键,无模型变更则不 bump

# ── 宏观事件日历（2026，官方日程）──────────────────────────────────
# CPI：BLS 固定 8:30 ET 发布；FOMC：决议日（会议第2天）14:00 ET
# 方向上无稳定偏向，但当日波动显著放大 → 只做警示，不拍涨跌概率
# 来源：bls.gov/schedule/news_release/cpi.htm；federalreserve.gov FOMC calendar
MACRO_EVENTS = {
    # CPI 发布日（参考月: 发布日）
    "2026-01-13": "CPI发布(12月)", "2026-02-11": "CPI发布(1月)",
    "2026-03-11": "CPI发布(2月)", "2026-04-10": "CPI发布(3月)",
    "2026-05-12": "CPI发布(4月)", "2026-06-10": "CPI发布(5月)",
    "2026-07-14": "CPI发布(6月)", "2026-08-12": "CPI发布(7月)",
    "2026-09-11": "CPI发布(8月)", "2026-10-14": "CPI发布(9月)",
    "2026-11-10": "CPI发布(10月)", "2026-12-10": "CPI发布(11月)",
    # FOMC 决议日
    "2026-01-28": "FOMC决议", "2026-03-18": "FOMC决议(含SEP)",
    "2026-05-06": "FOMC决议", "2026-06-17": "FOMC决议(含SEP)",
    "2026-07-29": "FOMC决议", "2026-09-16": "FOMC决议(含SEP)",
    "2026-11-04": "FOMC决议", "2026-12-16": "FOMC决议(含SEP)",
    # 非农就业（通常每月第一个周五 8:30 ET；7月因独立日休市提前到周四）
    "2026-07-02": "非农就业(6月)", "2026-08-07": "非农就业(7月)",
    "2026-09-04": "非农就业(8月)", "2026-10-02": "非农就业(9月)",
    "2026-11-06": "非农就业(10月)", "2026-12-04": "非农就业(11月)",
}

# ── 月度先验概率（1928-2026 真实统计，后面会从 long_history.json 覆盖）
MONTHLY_PRIOR = {
    1: 0.62, 2: 0.54, 3: 0.62, 4: 0.68,
    5: 0.58, 6: 0.55, 7: 0.60, 8: 0.57,
    9: 0.45, 10: 0.60, 11: 0.65, 12: 0.64,
}

# ── 从 long_history.json 加载更精确的月度先验（1928+）─────────────
def _load_long_priors():
    try:
        with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
            lh = json.load(f)
        rows = lh.get("monthly_by_period", {}).get("1928+", [])
        return {r["month"]: round(r["win_rate"] / 100, 4) for r in rows}
    except Exception:
        return {}

_long_priors = _load_long_priors()
if _long_priors:
    MONTHLY_PRIOR.update(_long_priors)
    print(f"  使用 long_history 月度先验（1928+年历史数据，S&P500）")


def _monthly_prior_from_csv(csv_name, start_year):
    """从长历史 CSV 计算月度胜率先验（月收益>0 的频率）"""
    try:
        s = pd.read_csv(RAW_DIR / csv_name, index_col=0, parse_dates=True).squeeze()
        s = s.sort_index().dropna()
        s = s[s.index.year >= start_year]
        monthly = s.resample("ME").last().pct_change().dropna()
        return {m: round(float((monthly[monthly.index.month == m] > 0).mean()), 4)
                for m in range(1, 13)}
    except Exception:
        return {}


# 纳指自己的月度先验（1971+），不再借用 S&P500 的
NASDAQ_PRIOR = _monthly_prior_from_csv("NASDAQ_COMP_long.csv", 1971) or dict(MONTHLY_PRIOR)
SP500_PRIOR  = dict(MONTHLY_PRIOR)   # S&P500 用 1928+ 长历史先验
print(f"  纳指月度先验（1971+）已加载: 6月={NASDAQ_PRIOR.get(6)}")

# ── 星期效应似然比（日频，1928-2026 真实统计）────────────────────
# 以普通日基准 52.4% 为 1.0，各星期相对调整
DOW_LR = {
    0: 0.940,  # 周一：49.3% — 最弱
    1: 0.981,  # 周二：51.4%
    2: 1.038,  # 周三：54.4% — 最强
    3: 1.004,  # 周四：52.6%
    4: 1.038,  # 周五：54.4%
}

# ── 月内第几周效应（Week-of-Month）─────────────────────────────
# 基准53.2%。第1周最强（59.1%），第4周最弱（50.5%）
_WOM_LR = {1: 1.112, 2: 0.996, 3: 1.015, 4: 0.950, 5: 0.992}

# ── 日历异常综合似然比（税季 + 季末 + 税损）────────────────────
# 来源：S&P 500 日频 1950-2026，n≈19,000
def _calendar_anomaly_lr(ts):
    m, d = ts.month, ts.day

    # ─ 报税季（4月细分）─────────────────────────────────────────
    if m == 4:
        if d == 15:          return 1.242   # 截止日当天：66%，最强单日
        if d <= 14:          return 1.068   # 4月1-14：平均56-57%（纳税前准备期，不跌）
        # 4月16日后恢复正常
        return 1.0

    # ─ 12月税损收割 ──────────────────────────────────────────────
    if m == 12:
        if 11 <= d <= 15:    return 0.889   # 税损收割最密集：47.2%
        if 21 <= d <= 25:    return 1.147   # 圣诞前：61%
        return 1.0

    # ─ 季初建仓（1/4/7/10月前5日）─────────────────────────────
    if m in (1, 4, 7, 10) and d <= 5:
        return 1.117   # 59.4%，机构新季度建仓

    return 1.0

# ── 假日效应 LR（假日日历本身在 signal_model.py）──────────────────
def _holiday_lr(ts):
    """返回该交易日的假日效应似然比"""
    d = ts.date()

    # 感恩节前夕（周三）：76.3%  → LR=1.457
    if d in {tg - timedelta(days=1) for tg in _THANKSGIVING_DATES}:
        return 1.457

    # 感恩节后的黑色星期五：71.1% → LR=1.357
    if d in {tg + timedelta(days=1) for tg in _THANKSGIVING_DATES}:
        return 1.357

    # 圣诞行情窗口 Dec 26 – Jan 3
    if (d.month == 12 and d.day >= 26) or (d.month == 1 and d.day <= 3):
        return 1.105   # 57.9% vs 52.4%

    # 节前（前3天内有假日）：59.0% → LR=1.126
    for offset in range(1, 4):
        if (d + timedelta(days=offset)) in _HOLIDAY_SET:
            return 1.126

    # 节后（后3天内有假日）：58.2% → LR=1.111
    for offset in range(1, 4):
        if (d - timedelta(days=offset)) in _HOLIDAY_SET:
            return 1.111

    return 1.0  # 普通日

# 事件调整因子（乘法，贝叶斯似然比）
# 事件叠加 what-if(旧 EVENT_ADJUSTMENTS / compute_current_signal)已移除:其前端勾选玩具
# 已被真事件研究面板(renderEventRefToday,消费 load_event_study 的 event_study 字段)取代。

# ── 经验似然比（walk_forward 学习值，带收缩）──────────────────────
def _load_learned_lrs():
    try:
        with open(PROC_DIR / "walk_forward_results.json", encoding="utf-8") as f:
            wf = json.load(f)
        opt = wf.get("optimized_lr", {})
        return opt if opt.get("factors") else {}
    except Exception:
        return {}

_LEARNED = _load_learned_lrs()

def _learned_on(keys, fallback):
    """因子触发时的 LR：优先用经验值（收缩后），无数据则用手设默认。
    keys 可传多个候选（如 SP500 无专属学习值时回退到 NASDAQ 的）。"""
    if isinstance(keys, str):
        keys = [keys]
    for k in keys:
        f = _LEARNED.get("factors", {}).get(k)
        if f and isinstance(f, dict) and "lr" in f:
            return round(shrink_lr(f["lr"], f["n"]), 4)
    return fallback

def _learned_off(keys, fallback):
    """因子未触发时的 LR：由全概率公式从触发侧推出，而不是简单取倒数"""
    if isinstance(keys, str):
        keys = [keys]
    n_total = _LEARNED.get("n_total", 0)
    base    = _LEARNED.get("base_win_rate", 0)
    for k in keys:
        f = _LEARNED.get("factors", {}).get(k)
        if f and isinstance(f, dict) and "lr" in f and n_total and base:
            n  = f["n"]
            p1 = n / n_total
            if 0 < p1 < 1:
                wr_on  = shrink_lr(f["lr"], n) * base
                wr_off = (base - p1 * wr_on) / (1 - p1)
                return round(max(wr_off / base, 0.5), 4)
    return fallback


# ── 技术信号计算 ──────────────────────────────────────────────────
def compute_technical_signals(prices, ret):
    df = pd.DataFrame(index=prices.index)

    for asset in ["NASDAQ", "SP500", "BTC", "DXY"]:
        r = ret[asset]
        p = prices[asset]
        df[f"{asset}_above_ma50"]  = (p > p.rolling(50).mean()).astype(float)
        df[f"{asset}_above_ma200"] = (p > p.rolling(200).mean()).astype(float)
        df[f"{asset}_rsi"]         = _rsi(r, 14)
        df[f"{asset}_mom20"]       = p.pct_change(20)
        df[f"{asset}_vol20"]       = r.rolling(20).std() * np.sqrt(252)

    df["btc_nasdaq_corr"] = ret["BTC"].rolling(60).corr(ret["NASDAQ"])
    df["dxy_trend"]       = prices["DXY"].pct_change(20)  # 美元趋势（负=利好）

    # VIX期限结构：现货VIX ≥ 3月VIX = 倒挂（恐慌状态；数据2009+）
    if "VIX" in prices.columns and "VIX3M" in prices.columns:
        df["vix_backwardation"] = (prices["VIX"] >= prices["VIX3M"]).astype(float)
        df.loc[prices["VIX3M"].isna(), "vix_backwardation"] = np.nan

    # 隔夜动量：ETF隔夜段收益近20日累计（overnight_analysis.py 生成）
    try:
        ov = pd.read_csv(PROC_DIR / "overnight_daily.csv",
                         index_col="Date", parse_dates=True)
        mapping = {"NASDAQ": "NASDAQ100", "SP500": "SP500"}
        for idx, col in mapping.items():
            if col in ov.columns:
                df[f"overnight_mom20_{idx}"] = ov[col].rolling(20).sum().reindex(df.index)
    except Exception:
        pass

    return df


def compute_log_returns(prices):
    """按资产独立计算对数收益，保留各列自己的缺失值。

    不能在这里对整个 DataFrame ``dropna()``：任一旁路资产（例如 VIX3M）
    整列抓取失败时，全行删除会连带抹掉 NASDAQ/SP500 的有效收益，最终把最新
    波动率写成 null。滚动指标本身会按列处理 NaN。
    """
    return np.log(prices / prices.shift(1))


def _finite_float(value, default=0.0):
    """把标量转为有限 float；NaN/Inf/None 使用既有的中性回退值。"""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(default)
    return value if np.isfinite(value) else float(default)

# ── 计算每日信号 ──────────────────────────────────────────────────
def compute_daily_signals(prices, ret, tech, trading_days, index="NASDAQ", priors=None):
    """生成某个指数的每日信号流，只在该指数真实交易日上计算。

    index:  "NASDAQ" 或 "SP500" —— 技术因子(MA200/RSI/波动率)取该指数自身；
            BTC/DXY 跨资产因子两个流共用。
    注意：为兼容前端，记录里的字段名固定为 nasdaq_ma200/nasdaq_vol/nasdaq_rsi，
          在 SP500 流中它们的含义是 SP500 自身的对应指标。
    """
    if priors is None:
        priors = MONTHLY_PRIOR
    records = {}
    # ffill 后的价格在交易日间隔上的 pct_change 即「相对上一交易日」收益
    idx_pct = prices[index].pct_change() * 100

    # 技术因子 LR：优先用 walk_forward 经验值（收缩后），否则手设默认
    lr_ma200_on  = _learned_on([f"{index}_above_ma200", "NASDAQ_above_ma200"], 1.15)
    lr_ma200_off = _learned_off([f"{index}_above_ma200", "NASDAQ_above_ma200"], 0.85)
    lr_btc_pos   = _learned_on("BTC_mom20_pos", 1.12)
    lr_btc_neg   = _learned_on("BTC_mom20_neg", 0.90)
    lr_dxy_up    = _learned_on("dxy_rising",  0.88)
    lr_dxy_down  = _learned_on("dxy_falling", 1.12)
    lr_vol_high  = _learned_on("nasdaq_high_vol", 0.85)
    lr_vol_low   = _learned_on("nasdaq_low_vol",  1.10)
    lr_rsi_ob    = _learned_on("nasdaq_rsi_overbought", 0.85)
    lr_rsi_os    = _learned_on("nasdaq_rsi_oversold",   1.10)
    lr_vix_bwd   = _learned_on("vix_backwardation", 0.85)   # 倒挂=恐慌
    lr_vix_norm  = _learned_off("vix_backwardation", 1.0)
    lr_ov_pos    = _learned_on("overnight_mom_pos", 1.05)   # 隔夜动量
    lr_ov_neg    = _learned_on("overnight_mom_neg", 0.95)

    for ts in trading_days:
        if ts not in tech.index:
            continue
        row = tech.loc[ts]
        if row.isnull().all():
            continue

        month = ts.month
        prior = priors[month]

        # ── 似然比列表（贝叶斯连乘）────────────────────────────────
        likelihoods = []

        # 1. 星期效应（日频，1928年统计）
        likelihoods.append(DOW_LR.get(ts.weekday(), 1.0))

        # 2. 月内第几周效应（Week-of-Month，1950+统计）
        likelihoods.append(_WOM_LR.get(_week_of_month(ts), 1.0))

        # 3. 日历异常（税季/税损/季初建仓）
        likelihoods.append(_calendar_anomaly_lr(ts))

        # 4. 假日效应
        likelihoods.append(_holiday_lr(ts))

        # 5. 指数在200日均线上方
        if not pd.isna(row.get(f"{index}_above_ma200")):
            likelihoods.append(lr_ma200_on if row[f"{index}_above_ma200"] else lr_ma200_off)

        # 6. BTC动量（领先效应）
        if not pd.isna(row.get("BTC_mom20")):
            m = row["BTC_mom20"]
            likelihoods.append(lr_btc_pos if m > BTC_MOM_THRESH
                               else (lr_btc_neg if m < -BTC_MOM_THRESH else 1.0))

        # 7. 美元趋势（负相关）
        if not pd.isna(row.get("dxy_trend")):
            d = row["dxy_trend"]
            likelihoods.append(lr_dxy_up if d > DXY_TREND_THRESH
                               else (lr_dxy_down if d < -DXY_TREND_THRESH else 1.0))

        # 8. 指数波动率
        if not pd.isna(row.get(f"{index}_vol20")):
            v = row[f"{index}_vol20"]
            likelihoods.append(lr_vol_high if v > VOL_HIGH else (lr_vol_low if v < VOL_LOW else 1.0))

        # 9. 指数 RSI
        if not pd.isna(row.get(f"{index}_rsi")):
            rsi_val = row[f"{index}_rsi"]
            likelihoods.append(lr_rsi_ob if rsi_val > RSI_OVERBOUGHT
                               else (lr_rsi_os if rsi_val < RSI_OVERSOLD else 1.0))

        # 10. VIX期限结构（倒挂=市场恐慌，2009+）
        if not pd.isna(row.get("vix_backwardation")):
            likelihoods.append(lr_vix_bwd if row["vix_backwardation"] else lr_vix_norm)

        # 11. 隔夜动量（该指数ETF隔夜段近20日累计收益）
        ov = row.get(f"overnight_mom20_{index}")
        if ov is not None and not pd.isna(ov):
            likelihoods.append(lr_ov_pos if ov > 0 else (lr_ov_neg if ov < 0 else 1.0))

        prob = bayesian_update(prior, likelihoods)

        # 当日实际收益（%），用于预测准确率展示
        ar = idx_pct.get(ts)
        actual_ret = round(float(ar), 3) if ar is not None and not pd.isna(ar) else None

        records[ts.strftime("%Y-%m-%d")] = {
            "prob":         round(prob, 4),
            "tier":         _tier(prob),
            "month":        month,
            "dow":          int(ts.weekday()),
            "dom":          int(ts.day),
            "wom":          int(_week_of_month(ts)),
            "prior":        round(prior, 4),
            "holiday_lr":   round(_holiday_lr(ts), 4),
            "cal_lr":       round(_calendar_anomaly_lr(ts), 4),
            "nasdaq_ma200": int(row.get(f"{index}_above_ma200", 0)),
            "btc_mom20":    round(_finite_float(row.get("BTC_mom20")), 4),
            "dxy_trend":    round(_finite_float(row.get("dxy_trend")), 4),
            "nasdaq_vol":   round(_finite_float(row.get(f"{index}_vol20")), 4),
            "nasdaq_rsi":   round(_finite_float(row.get(f"{index}_rsi")), 1),
            "ret":          actual_ret,
        }

    return records

# ── 主流程 ────────────────────────────────────────────────────────
def build():
    print("加载数据...")
    raw = pd.read_csv(RAW_DIR / "combined_prices.csv",
                      index_col="Date", parse_dates=True)
    prices = raw.ffill()
    ret = compute_log_returns(prices)
    # 技术因子整体后移1天：当天的信号只能用前一天收盘算出的指标，
    # 否则「信号 vs 当日收益」的对比存在同日前视偏差
    tech = compute_technical_signals(prices, ret).shift(1)

    # 两套独立信号流：纳指用自己的先验和技术因子，标普用自己的
    streams = {}
    for index, priors in [("NASDAQ", NASDAQ_PRIOR), ("SP500", SP500_PRIOR)]:
        # 该指数真实交易日（ffill 之前记录，避免把 BTC 的周末行算进来）
        trading_days = raw[index].dropna().index
        print(f"计算 {index} 每日信号...")
        streams[index] = compute_daily_signals(
            prices, ret, tech, trading_days, index=index, priors=priors)

    signals   = streams["NASDAQ"]
    latest    = list(signals.values())[-1]
    sp_latest = list(streams["SP500"].values())[-1]
    base_prob = latest["prob"]

    output = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "model_version": MODEL_VERSION,
        # 档位阈值唯一来源（前端 tier()/图例据此渲染）
        "tier_thresholds": TIER_THRESHOLDS,
        # 兼容字段：latest_* 指 NASDAQ 主信号流
        "latest_prob": round(base_prob, 4),
        "latest_tier": _tier(base_prob),
        "indices": {
            "NASDAQ": {"prob": latest["prob"],    "tier": latest["tier"],
                       "date": list(signals)[-1]},
            "SP500":  {"prob": sp_latest["prob"], "tier": sp_latest["tier"],
                       "date": list(streams["SP500"])[-1]},
        },
        "daily_signals": signals,
        # SP500 流只保留核心字段（诊断字段前端只对 NASDAQ 流展示），控制文件体积
        "daily_signals_sp500": {
            d: {"prob": s["prob"], "tier": s["tier"], "ret": s["ret"]}
            for d, s in streams["SP500"].items()
        },
        # 完整 SP500 记录（含技术因子）仅供后续内部计算用，序列化前弹出
        "_sp500_full": streams["SP500"],
    }

    print(f"[OK] 信号计算完成 (NASDAQ {len(signals)} 天 / SP500 {len(streams['SP500'])} 天)")
    print(f"  NASDAQ: {base_prob*100:.1f}% 第{_tier(base_prob)}档 | "
          f"SP500: {sp_latest['prob']*100:.1f}% 第{sp_latest['tier']}档")
    return output

def build_timing_summary():
    """把 timing_analysis 结果汇总为前端用的 JSON 片段"""
    summary = {}

    # DOW 胜率
    try:
        dow = pd.read_csv(PROC_DIR / "dow_stats.csv")
        ndx = dow[dow["asset"] == "NASDAQ"][["dow","day_name","win_rate","avg_return"]].copy()
        ndx["win_rate"] = (ndx["win_rate"] * 100).round(1)
        ndx["avg_return"] = (ndx["avg_return"] * 100).round(3)
        summary["dow"] = ndx.to_dict(orient="records")
    except Exception: pass

    # 卖出信号（最近一行）
    try:
        sell = pd.read_csv(PROC_DIR / "sell_signals.csv")
        last = sell.dropna().iloc[-1]
        summary["sell"] = {
            "date":       last["date"],
            "score":      float(last["sell_score"]),
            "tier":       last["sell_tier"],
            "rsi":        float(last["rsi"]) if not pd.isna(last["rsi"]) else None,
            "mom20":      float(last["mom20"]),
            "ma_cross":   int(last["ma_cross"]),
            "vol_pct":    float(last["vol_pct"]) if not pd.isna(last["vol_pct"]) else None,
        }
    except Exception: pass

    # 月内效应
    try:
        dom = pd.read_csv(PROC_DIR / "dom_stats.csv")
        ndx = dom[dom["asset"] == "NASDAQ"][["dom","win_rate","avg_return"]].copy()
        ndx["win_rate"] = (ndx["win_rate"] * 100).round(1)
        summary["dom"] = ndx.to_dict(orient="records")
    except Exception: pass

    return summary


DOW_CN = {0:"周一", 1:"周二", 2:"周三", 3:"周四", 4:"周五"}

def find_next_opportunities(signals, n_days=45, priors=None):
    """
    扫描未来 n_days 个交易日，计算每天的贝叶斯概率。
    日历因子（星期/月/假日/税季）按历史规律外推（先验，部分未通过 placebo 检验，非已验证边际）；
    技术因子（MA/BTC/DXY/RSI）用最新一天值冻结（30天内通常不会突变）。
    宏观事件日（CPI/FOMC）只做波动警示，不调方向概率。

    Returns:
        dict with top_entry (top 5 buy days), top_exit (5 weakest days),
        and all_forecast (full list sorted by date).
    """
    if priors is None:
        priors = MONTHLY_PRIOR
    today = us_today()

    # 从最新信号提取技术因子LR（冻结）——与每日信号同源：经验LR（收缩后）
    latest = list(signals.values())[-1]
    tech_lrs = []

    nasdaq_ma200 = latest.get("nasdaq_ma200", 1)
    tech_lrs.append(_learned_on("NASDAQ_above_ma200", 1.15) if nasdaq_ma200 == 1
                    else _learned_off("NASDAQ_above_ma200", 0.85))

    btc_mom = latest.get("btc_mom20", 0) or 0
    tech_lrs.append(_learned_on("BTC_mom20_pos", 1.12) if btc_mom > BTC_MOM_THRESH
                    else (_learned_on("BTC_mom20_neg", 0.90) if btc_mom < -BTC_MOM_THRESH else 1.0))

    dxy = latest.get("dxy_trend", 0) or 0
    tech_lrs.append(_learned_on("dxy_rising", 0.88) if dxy > DXY_TREND_THRESH
                    else (_learned_on("dxy_falling", 1.12) if dxy < -DXY_TREND_THRESH else 1.0))

    nasdaq_vol = latest.get("nasdaq_vol", 0.20) or 0.20
    tech_lrs.append(_learned_on("nasdaq_high_vol", 0.85) if nasdaq_vol > VOL_HIGH
                    else (_learned_on("nasdaq_low_vol", 1.10) if nasdaq_vol < VOL_LOW else 1.0))

    nasdaq_rsi = latest.get("nasdaq_rsi", 50) or 50
    tech_lrs.append(_learned_on("nasdaq_rsi_overbought", 0.85) if nasdaq_rsi > RSI_OVERBOUGHT
                    else (_learned_on("nasdaq_rsi_oversold", 1.10) if nasdaq_rsi < RSI_OVERSOLD else 1.0))

    forecast = []
    d = today + timedelta(days=1)
    trading_days_found = 0

    while trading_days_found < n_days:
        # 跳过周末
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        # 跳过假日
        if d in _HOLIDAY_SET:
            d += timedelta(days=1)
            continue

        ts = pd.Timestamp(d)
        month = ts.month
        prior = priors[month]

        cal_lrs = [
            DOW_LR.get(ts.weekday(), 1.0),
            _WOM_LR.get(_week_of_month(ts), 1.0),
            _calendar_anomaly_lr(ts),
            _holiday_lr(ts),
        ] + tech_lrs

        prob = bayesian_update(prior, cal_lrs)

        # 主因子说明（用于前端tooltip）
        reasons = []
        dow_lr = DOW_LR.get(ts.weekday(), 1.0)
        if dow_lr > 1.02: reasons.append(f"{DOW_CN[ts.weekday()]}效应")
        wom_lr = _WOM_LR.get(_week_of_month(ts), 1.0)
        if wom_lr > 1.05: reasons.append(f"月内第{_week_of_month(ts)}周最强")
        if wom_lr < 0.97: reasons.append(f"月内第{_week_of_month(ts)}周偏弱")
        hol_lr = _holiday_lr(ts)
        if hol_lr > 1.10: reasons.append("假日效应")
        cal_lr = _calendar_anomaly_lr(ts)
        if cal_lr > 1.10: reasons.append("税季/季初建仓")
        if cal_lr < 0.95: reasons.append("税损收割期")
        month_prior = priors[month]
        if month_prior >= 0.62: reasons.append(f"{month}月胜率高")
        if month_prior <= 0.50: reasons.append(f"{month}月胜率低")

        # 宏观事件警示（CPI/FOMC：当日波动放大，方向无稳定偏向）
        macro = MACRO_EVENTS.get(d.strftime("%Y-%m-%d"))
        if macro:
            reasons.append(f"⚠ {macro}·波动放大")

        forecast.append({
            "date":      d.strftime("%Y-%m-%d"),
            "dow_cn":    DOW_CN.get(ts.weekday(), ""),
            "month":     month,
            "wom":       int(_week_of_month(ts)),
            "prob":      round(prob, 4),
            "tier":      _tier(prob),
            "prior":     round(prior, 4),
            "dow_lr":    round(dow_lr, 4),
            "wom_lr":    round(wom_lr, 4),
            "hol_lr":    round(hol_lr, 4),
            "cal_lr":    round(cal_lr, 4),
            "macro":     macro,
            "reasons":   reasons,
        })

        d += timedelta(days=1)
        trading_days_found += 1

    # 按概率排序
    sorted_asc  = sorted(forecast, key=lambda x: x["prob"])
    sorted_desc = sorted(forecast, key=lambda x: -x["prob"])

    return {
        "top_entry": sorted_desc[:5],   # 最佳买入：概率最高的5天
        "top_exit":  sorted_asc[:5],    # 最弱/减仓：概率最低的5天
        "all_forecast": forecast,        # 按日期顺序，供日历视图
        "tech_frozen_note": "技术信号使用当前最新值（MA/BTC/DXY/RSI），日历因子基于统计规律精确预测",
        "latest_tech": {
            "nasdaq_ma200": int(nasdaq_ma200),
            "btc_mom20":    round(btc_mom, 4),
            "dxy_trend":    round(dxy, 4),
            "nasdaq_vol":   round(nasdaq_vol, 4),
            "nasdaq_rsi":   round(nasdaq_rsi, 1),
        }
    }


def load_event_study():
    """将 event_study_results.json 中的核心数据嵌入 signals.json"""
    try:
        with open(PROC_DIR / "event_study_results.json", encoding="utf-8") as f:
            es = json.load(f)
        studies = es.get("event_studies", {})
        # 只保留前端需要的字段，去掉 returns 列表（太大）
        out = {}
        labels = {
            "fed_hike_first":      "首次加息",
            "fed_cut_first":       "首次降息",
            "trade_war_escalation":"贸易战升级",
            "trade_war_relief":    "贸易战缓和",
            "geopolitical_shock":  "地缘冲击",
            "pandemic_lockdown":   "疫情封锁",
            "vix_spike_extreme":   "VIX恐慌飙升",
            "banking_crisis":      "银行危机",
            "ai_breakthrough":     "AI突破",
        }
        for k, v in studies.items():
            out[k] = {
                "label":       labels.get(k, k),
                "n":           v["n"],
                "avg_return":  v["avg_return_pct"],
                "median_return": v["median_return_pct"],
                "win_rate":    v["win_rate"],
                "base_win_rate": v["base_win_rate"],
                "lr":          v["lr"],
                "p_value":     v["p_value"],
                # 置换检验(2026-08-24):厚尾+小样本下 t 检验会高估显著性,故 significant 已收紧为
                # 「t 检验与置换检验都过」。两个 p 都透传,前端/复核者能看见依据、而非只看到一个收紧后的旗标。
                "p_permutation": v.get("p_permutation"),
                "significant_ttest_only": v.get("significant_ttest_only"),
                "significant": v["significant"],
                "base_avg":    v["base_avg_pct"],
            }
        return out
    except Exception:
        return {}


def load_year_patterns():
    """从 long_history.json 读取年份规律统计（尾数/任期年/执政党）"""
    try:
        with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
            lh = json.load(f)
        return lh.get("year_patterns", {})
    except Exception:
        return {}

def load_holiday_effects():
    """从 long_history.json 读取假日效应统计"""
    try:
        with open(PROC_DIR / "long_history.json", encoding="utf-8") as f:
            lh = json.load(f)
        he = lh.get("holiday_effects", {})
        # 精简：只保留前端需要的字段
        keep = ["pre_holiday","post_holiday","normal","santa_claus_rally",
                "january_effect","thanksgiving_eve","thanksgiving_friday","dom","dow_daily"]
        return {k: he[k] for k in keep if k in he}
    except Exception:
        return {}


def load_backtest():
    """嵌入 backtest.py 的回测结果（如已运行）"""
    try:
        with open(PROC_DIR / "backtest_results.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_walk_forward():
    """嵌入 walk_forward.py 的滚动验证汇总（如已运行）"""
    try:
        with open(PROC_DIR / "walk_forward_results.json", encoding="utf-8") as f:
            wf = json.load(f)
        tech = {k: v for k, v in wf.get("optimized_lr", {}).get("factors", {}).items()
                if isinstance(v, dict) and "lr" in v}
        return {
            "folds": [
                {
                    "train": f["train"],
                    "test":  f["test"],
                    "baseline_wr": f["baseline_wr"],
                    "tier4_wr":   f["performance"].get("tier4_plus", {}).get("win_rate"),
                    "tier4_diff": f["performance"].get("tier4_plus", {}).get("diff"),
                    "tier4_sig":  f["performance"].get("tier4_plus", {}).get("significant"),
                }
                for f in wf.get("folds", [])
            ],
            "summary": wf.get("summary", {}),
            "optimized_lr_key_factors": {
                k: {"lr": v["lr"], "wr": round(v["win_rate"]*100, 1), "n": v["n"]}
                for k, v in tech.items()
                if abs(v["lr"] - 1) > 0.02
            },
        }
    except Exception:
        return {}


def load_calibration():
    """从样本外校准构造「模型概率 → 实际20日胜率」映射点。
    优先读 walk_forward_results.json 的 oos_calibration.naive；
    失败时回退到回测校准逻辑（backtest_results.json）。
    返回按 prob_mean 升序的 [(prob_mean, actual_wr)] 点列。
    """
    # ── 优先：样本外校准（walk-forward OOS）─────────────────────────
    try:
        with open(PROC_DIR / "walk_forward_results.json", encoding="utf-8") as f:
            wf = json.load(f)
        naive = wf.get("oos_calibration", {}).get("naive", [])
        if naive:
            pts = sorted(
                (item["prob_mean"], item["actual_wr"])
                for item in naive
                if "prob_mean" in item and "actual_wr" in item
            )
            if pts:
                # 样本外校准曲线常非单调甚至倒挂（模型高分→实际低胜率）。
                # 原始插值会把"反向信号"当真展示；PAV 单调化把无区分度的段
                # 坍缩成≈基率的平台，是当前证据下唯一诚实的映射。
                return pav_monotonic(pts)
    except Exception:
        pass

    # ── 回退：回测校准（backtest_results.json）───────────────────────
    try:
        with open(PROC_DIR / "backtest_results.json", encoding="utf-8") as f:
            bt = json.load(f)
        bt = bt.get("NASDAQ", bt)   # 新格式按指数分组，旧格式为平铺
        cal = bt.get("calibration_20d", [])
        pts = sorted((c["prob_mid"], c["actual_wr_20d"] / 100)
                     for c in cal if c.get("n", 0) >= 50)
        return pts
    except Exception:
        return []


def calibrate_prob(p, pts):
    """分段线性插值：原始概率 → 历史同档位实际胜率"""
    if not pts or p is None:
        return None
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    return round(float(np.interp(p, xs, ys)), 4)


def load_live_tracking():
    """嵌入实盘预测追踪汇总（track_predictions.py 生成）"""
    try:
        with open(PROC_DIR / "prediction_log_summary.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _clean(o):
    """递归把 NaN/Inf 换成 null，保证输出是合法 JSON（前端无需再做正则修补）"""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    return o


if __name__ == "__main__":
    result = build()

    # 合并时机摘要
    timing = build_timing_summary()
    result.update(timing)

    # 嵌入事件研究结果
    result["event_study"] = load_event_study()

    # 未来最佳入场/离场窗口（两个指数各一份，40个交易日≈两个月）
    # 上限40：技术因子LR是冻结的当前值，再往后外推就不诚实了（ROADMAP P1-2）
    # SP500 用完整记录（瘦身版没有技术因子，会退化成中性占位值）
    _sp500_full = result.pop("_sp500_full", result["daily_signals_sp500"])
    result["next_opportunities"] = find_next_opportunities(
        result["daily_signals"], n_days=40, priors=NASDAQ_PRIOR)
    result["next_opportunities_sp500"] = find_next_opportunities(
        _sp500_full, n_days=40, priors=SP500_PRIOR)

    # 宏观事件日历（未来90天内的 CPI/FOMC，以美东日期为准）
    _today = us_today()
    result["macro_calendar"] = [
        {"date": d, "label": lbl}
        for d, lbl in sorted(MACRO_EVENTS.items())
        if _today <= date.fromisoformat(d) <= _today + timedelta(days=190)
    ]

    # 年份规律统计
    result["year_patterns"] = load_year_patterns()

    # 假日效应详细统计
    result["holiday_detail"] = load_holiday_effects()

    # 回测与滚动验证（唯一写入者：其他脚本只写 processed/，由这里统一嵌入）
    backtest = load_backtest()
    if backtest:
        result["backtest"] = backtest
    walk_forward = load_walk_forward()
    if walk_forward:
        result["walk_forward"] = walk_forward

    # 概率校准：原始概率 → 样本外实际20日胜率（PAV 单调化后）
    cal_pts = load_calibration()
    if cal_pts:
        result["calibration_points"] = [{"prob": x, "actual_wr": y} for x, y in cal_pts]
        # 校准曲线被 PAV 压平 = 模型无样本外区分度（校准胜率跨度 < 1pp）。
        # 1pp 是刻意设的经济意义下限，不是浮点舍入容差：跨度再小的"单调"也无操作价值。
        # 此时不给"档位"这种暗示把握度的标签，前端改为"基率框架"展示。
        ys = [y for _, y in cal_pts]
        result["calibration_flat"] = bool(max(ys) - min(ys) < 0.01)
        for idx in result.get("indices", {}):
            prob_cal = calibrate_prob(result["indices"][idx]["prob"], cal_pts)
            result["indices"][idx]["prob_cal"] = prob_cal
            # tier_cal：用校准概率算档位；校准失败时回退到原始概率的档位
            result["indices"][idx]["tier_cal"] = _tier(
                prob_cal if prob_cal is not None else result["indices"][idx]["prob"])

    # ── 展示层元数据（P2-3）────────────────────────────────────────
    # base_rate_20d：walk-forward 无条件基率（读失败回退 0.62）
    try:
        with open(PROC_DIR / "walk_forward_results.json", encoding="utf-8") as _f:
            _wf = json.load(_f)
        result["base_rate_20d"] = _wf.get("optimized_lr", {}).get("base_win_rate", 0.62)
        cd = _wf.get("calibration_drift")            # #3 校准漂移(逐折随时间)：随基率一并搬运
        if cd and cd.get("status") == "ok":
            result["calibration_drift"] = cd
    except Exception:
        result["base_rate_20d"] = 0.62
    result["horizon_note"] = "概率含义：未来20个交易日收盘高于今日的概率"
    result["model_status_note"] = "实验性信号：walk-forward 块自助验证未发现样本外优势"

    # 研究面板产物（不进信号链路）：因子尸检 + 波动率原型 + 市场结构
    for _key, _fn in [("factor_audit", "factor_pruning.json"), ("vol_model", "vol_model.json"),
                      ("market_structure", "market_structure.json"), ("benchmark", "benchmark.json"),
                      ("horizon_stats", "horizon_stats.json")]:
        try:
            with open(PROC_DIR / _fn, encoding="utf-8") as _f:
                result[_key] = json.load(_f)
        except (FileNotFoundError, json.JSONDecodeError) as _e:
            print(f"  ⚠ {_fn} 未嵌入（{type(_e).__name__}），研究面板将隐藏该块")

    # 实盘预测追踪
    tracking = load_live_tracking()
    if tracking:
        result["live_tracking"] = tracking

    # ── 发布瘦身（P1-3）────────────────────────────────────────────
    # 全量信号流给内部消费者（backtest 等）；signals.json 只发布近两年，
    # 更早历史拆到 signals_history.json 由前端按需加载
    HISTORY_CUTOFF = "2024-01-01"
    with open(PROC_DIR / "daily_signals_full.json", "w", encoding="utf-8") as f:
        json.dump(_clean({"daily_signals": result["daily_signals"],
                          "daily_signals_sp500": result["daily_signals_sp500"]}),
                  f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    hist = {
        "cutoff": HISTORY_CUTOFF,
        "daily_signals": {d: s for d, s in result["daily_signals"].items()
                          if d < HISTORY_CUTOFF},
        "daily_signals_sp500": {d: s for d, s in result["daily_signals_sp500"].items()
                                if d < HISTORY_CUTOFF},
    }
    out_hist = WEB_DIR / "signals_history.json"
    with open(out_hist, "w", encoding="utf-8") as f:
        json.dump(_clean(hist), f, ensure_ascii=False,
                  separators=(",", ":"), allow_nan=False)

    result["daily_signals"] = {d: s for d, s in result["daily_signals"].items()
                               if d >= HISTORY_CUTOFF}
    result["daily_signals_sp500"] = {d: s for d, s in result["daily_signals_sp500"].items()
                                     if d >= HISTORY_CUTOFF}
    result["history_cutoff"] = HISTORY_CUTOFF

    out = WEB_DIR / "signals.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(_clean(result), f, ensure_ascii=False,
                  separators=(",", ":"), allow_nan=False)
    print(f"[OK] signals.json 已更新（近两年，{out.stat().st_size//1024}KB）"
          f"+ signals_history.json（{out_hist.stat().st_size//1024}KB）")
