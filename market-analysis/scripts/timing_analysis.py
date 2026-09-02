"""
timing_analysis.py
买入/卖出时机统计分析：
  1. 周内效应（Monday Effect 等）
  2. 月内效应（月初/月末/期权到期日）
  3. 卖出信号（RSI超买 / GARCH波动率 / 动量转负 / 季节性）
  4. 综合评分：每天买入推荐 + 卖出预警
"""

import pandas as pd
import numpy as np
from pathlib import Path

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
PROC_DIR.mkdir(exist_ok=True)

ASSETS = ["NASDAQ", "DXY", "BTC", "ETH"]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五"]


def load():
    df = pd.read_csv(RAW_DIR / "combined_prices.csv",
                     index_col="Date", parse_dates=True)
    return df[ASSETS].dropna(how="all").ffill()


def log_returns(prices):
    return np.log(prices / prices.shift(1)).dropna()


# ── 1. 周内效应 ───────────────────────────────────────────────────
def day_of_week_stats(ret):
    print("\n=== 周内效应 ===")
    rows = []
    for asset in ASSETS:
        r = ret[asset].dropna()
        for dow in range(5):
            vals = r[r.index.dayofweek == dow]
            rows.append({
                "asset":      asset,
                "dow":        dow,
                "day_name":   WEEKDAYS[dow],
                "avg_return": vals.mean(),
                "win_rate":   (vals > 0).mean(),
                "median":     vals.median(),
                "std":        vals.std(),
                "count":      len(vals),
                "sharpe":     vals.mean() / (vals.std() + 1e-10) * np.sqrt(252),
            })
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "dow_stats.csv", index=False)

    print(f"  {'':8} {'周一':>8} {'周二':>8} {'周三':>8} {'周四':>8} {'周五':>8}")
    for asset in ["NASDAQ", "BTC"]:
        sub = df[df["asset"] == asset]
        wins = [f"{v*100:.0f}%" for v in sub["win_rate"]]
        print(f"  {asset:8} {wins[0]:>8} {wins[1]:>8} {wins[2]:>8} {wins[3]:>8} {wins[4]:>8}  ← 胜率")
    return df


# ── 2. 月内效应（周数 + 特殊日） ──────────────────────────────────
def day_of_month_stats(ret):
    print("\n=== 月内效应 ===")
    rows = []
    for asset in ASSETS:
        r = ret[asset].dropna()
        for dom in range(1, 32):
            vals = r[r.index.day == dom]
            if len(vals) < 10: continue
            rows.append({
                "asset": asset, "dom": dom,
                "avg_return": vals.mean(),
                "win_rate":   (vals > 0).mean(),
                "count":      len(vals),
            })
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "dom_stats.csv", index=False)

    # 月初/月末对比
    for asset in ["NASDAQ"]:
        sub = df[df["asset"] == asset]
        first_5  = sub[sub["dom"] <= 5]["win_rate"].mean()
        last_5   = sub[sub["dom"] >= 26]["win_rate"].mean()
        mid      = sub[(sub["dom"] > 5) & (sub["dom"] < 26)]["win_rate"].mean()
        print(f"  {asset} 月初5天胜率={first_5*100:.1f}%  月中胜率={mid*100:.1f}%  月末5天胜率={last_5*100:.1f}%")
    return df


# ── 3. 特殊日期效应 ───────────────────────────────────────────────
def special_day_stats(ret, prices):
    print("\n=== 特殊日期效应 ===")
    results = {}

    # 月初第一个交易日（新资金流入）
    first_trading = []
    for year in ret.index.year.unique():
        for month in range(1, 13):
            idx = ret[(ret.index.year == year) & (ret.index.month == month)].index
            if len(idx): first_trading.append(idx[0])

    # 月末最后一个交易日（窗口装扮）
    last_trading = []
    for year in ret.index.year.unique():
        for month in range(1, 13):
            idx = ret[(ret.index.year == year) & (ret.index.month == month)].index
            if len(idx): last_trading.append(idx[-1])

    special = {
        "月初第一交易日": first_trading,
        "月末最后交易日": last_trading,
    }

    rows = []
    for label, dates in special.items():
        vals = ret["NASDAQ"].loc[ret.index.isin(dates)].dropna()
        rows.append({
            "label":      label,
            "asset":      "NASDAQ",
            "avg_return": vals.mean(),
            "win_rate":   (vals > 0).mean(),
            "count":      len(vals),
        })
        wr = (vals > 0).mean()
        print(f"  {label}: 胜率={wr*100:.1f}%  均值={vals.mean()*100:.2f}%")

    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "special_day_stats.csv", index=False)
    return df


# ── 4. 卖出信号逻辑 ───────────────────────────────────────────────
def compute_sell_signals(prices, ret):
    print("\n=== 卖出信号系统 ===")
    df = pd.DataFrame(index=prices.index)
    r  = ret["NASDAQ"].reindex(prices.index)
    p  = prices["NASDAQ"]

    # RSI
    gain = r.clip(lower=0).rolling(14).mean()
    loss = (-r.clip(upper=0)).rolling(14).mean()
    rsi  = 100 - 100 / (1 + gain / (loss + 1e-10))

    # 移动均线
    ma50  = p.rolling(50).mean()
    ma200 = p.rolling(200).mean()

    # 动量
    mom20  = p.pct_change(20)
    mom60  = p.pct_change(60)

    # 波动率
    vol20 = r.rolling(20).std() * np.sqrt(252)

    # GARCH波动率分位
    vol_pct = vol20.rank(pct=True)

    # 卖出信号评分（0–100，越高越应卖出）
    sell_score = pd.Series(0.0, index=prices.index)

    # RSI超买
    sell_score += ((rsi - 50) / 50 * 25).clip(0, 25)

    # 动量转负
    sell_score += ((-mom20) * 100).clip(0, 20)
    sell_score += ((-mom60) * 50).clip(0, 15)

    # 均线死叉（50MA跌破200MA）
    death_cross = (ma50 < ma200).astype(float) * 20
    sell_score  += death_cross

    # 波动率飙升（高波动=风险上升）
    sell_score += (vol_pct * 15).clip(0, 15)

    # 季节性惩罚（6月、9月）
    month = prices.index.month
    sell_score += pd.Series(
        [5 if m in [6, 9] else 2 if m in [8] else 0 for m in month],
        index=prices.index
    )

    sell_score = sell_score.clip(0, 100)

    # 卖出等级 —— 档位只判一次,中英从同一张表取两列(两套 if 迟早漂移)
    TIERS = {"strong_sell": ("强烈卖出", "Strong sell"), "trim": ("考虑减仓", "Consider trimming"),
             "risk": ("注意风险", "Mind the risk"), "watch": ("持有观察", "Hold and watch"),
             "safe": ("安全持有", "Safe to hold")}

    def _tier_key(s):
        return ("strong_sell" if s >= 70 else "trim" if s >= 55 else
                "risk" if s >= 40 else "watch" if s >= 25 else "safe")

    def sell_tier(s):
        return TIERS[_tier_key(s)][0]

    def sell_tier_en(s):
        return TIERS[_tier_key(s)][1]

    out = pd.DataFrame({
        "date":       prices.index,
        "sell_score": sell_score.round(1),
        "sell_tier":  sell_score.map(sell_tier),
        "sell_tier_en": sell_score.map(sell_tier_en),
        "rsi":        rsi.round(1),
        "mom20":      (mom20 * 100).round(2),
        "mom60":      (mom60 * 100).round(2),
        "ma_cross":   (ma50 > ma200).astype(int),  # 1=金叉(好), 0=死叉(坏)
        "vol_pct":    (vol_pct * 100).round(1),
    })
    out.to_csv(PROC_DIR / "sell_signals.csv", index=False)

    # 当前状态
    cur = out.dropna().iloc[-1]
    print(f"  当前卖出评分: {cur['sell_score']}/100  → {cur['sell_tier']}")
    print(f"  RSI={cur['rsi']:.1f}  20日动量={cur['mom20']:.1f}%  均线={'金叉' if cur['ma_cross'] else '死叉'}")
    return out


# ── 5. 综合每日时机评分（买入+卖出合并） ─────────────────────────
def compute_daily_timing(prices, ret):
    print("\n=== 综合时机评分 ===")

    # 月度先验
    MONTHLY_PRIOR = {
        1:0.62, 2:0.54, 3:0.62, 4:0.80, 5:0.58, 6:0.40,
        7:0.80, 8:0.54, 9:0.45, 10:0.62, 11:0.80, 12:0.74
    }
    # DOW加成（基于数据，周二/周四略好）
    DOW_BONUS = {0: -0.02, 1: +0.01, 2: +0.01, 3: +0.02, 4: +0.01}

    # 月内加成
    def dom_bonus(dom):
        if dom <= 3:  return +0.03   # 月初强
        if dom >= 28: return +0.02   # 月末窗口装扮
        return 0.0

    p = prices["NASDAQ"].dropna()
    r = ret["NASDAQ"].reindex(prices.index)
    ma200 = p.rolling(200).mean()

    rows = []
    for date in prices.index:
        if pd.isna(p.get(date)): continue
        month = date.month
        dow   = date.dayofweek
        dom   = date.day
        if dow >= 5: continue  # 跳过周末

        prior = MONTHLY_PRIOR.get(month, 0.60)
        adj   = prior + DOW_BONUS.get(dow, 0) + dom_bonus(dom)
        adj   = float(np.clip(adj, 0.05, 0.95))

        rows.append({
            "date":       date.strftime("%Y-%m-%d"),
            "month":      month,
            "dow":        dow,
            "day_name":   WEEKDAYS[dow],
            "dom":        dom,
            "buy_score":  round(adj * 100, 1),
            "is_month_start": int(dom <= 3),
            "is_month_end":   int(dom >= 28),
            "is_options_exp": int(date.weekday() == 4 and 15 <= dom <= 21),  # 每月第3个周五
        })

    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "daily_timing.csv", index=False)
    print(f"  计算完成，{len(df)} 个交易日")
    return df


def run_all():
    prices = load()
    ret    = log_returns(prices)

    day_of_week_stats(ret)
    day_of_month_stats(ret)
    special_day_stats(ret, prices)
    compute_sell_signals(prices, ret)
    compute_daily_timing(prices, ret)

    print("\n✓ 时机分析完成")


if __name__ == "__main__":
    run_all()
