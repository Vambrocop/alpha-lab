"""asian_canary_probe.py — 轻量探针(非正式流水线):亚洲市场(KOSPI/TAIEX/ASX)对次一美股
现金时段是否有**增量信息**——超出隔夜已 priced-in 的部分?

问题拆解(用户 2026-08-01):亚洲收盘领先美股开盘,但美股**开盘价**已把亚洲/期货隔夜信息 price 进去
(=隔夜 gap)。真问题=亚洲是否预测美股**开盘→收盘(盘中·开盘后你还能交易的部分)**,且**超出** gap
已含的信息?
- 控制:用美股隔夜 gap(前收→今开)当"已 priced-in"的代理(现金 gap ≈ 期货隐含开盘;轻量探针用它替代
  ES=F/NQ=F 盘中,精修版再上真期货)。
- 若亚洲只预测 gap、不预测盘中 → 无可交易增量(有效市场,符合预期)。若预测盘中且超 gap → 值得写全 spec。

诚实边界:日频·时区对齐近似(亚洲 date-t 收盘 ~在美股 date-t 开盘前,同日历日对齐)·假日错配未精修·
样本内相关非 OOS·这是**探针非定论**。判无增量则登负结果止步;判有料才写正式 spec。
"""
import numpy as np
import pandas as pd
import yfinance as yf

START = "2010-01-01"
US = {"QQQ": "QQQ", "SPY": "SPY", "SOX": "^SOX"}     # SOX 若挂→回退 SOXX ETF
ASIA = {"KOSPI": "^KS11", "TAIEX": "^TWII", "ASX": "^AXJO"}


def dl(t):
    try:
        df = yf.download(t, start=START, progress=False, auto_adjust=False)
    except Exception as e:
        print(f"  download err {t}: {e}")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "Close"]].dropna()


def asia_overnight(d):
    c = d["Close"]
    return (c / c.shift(1) - 1).rename("asia_on")


def us_parts(d):
    o, c = d["Open"], d["Close"]
    gap = (o / c.shift(1) - 1).rename("gap")          # 前收→今开(隔夜·priced-in 代理)
    intraday = (c / o - 1).rename("intraday")         # 今开→今收(开盘后可交易)
    full = (c / c.shift(1) - 1).rename("full")        # 前收→今收(全日)
    return pd.concat([gap, intraday, full], axis=1)


def ols_r2(X, y):
    b, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ b
    ss_tot = ((y - y.mean()) ** 2).sum()
    return (1 - (resid @ resid) / ss_tot if ss_tot else 0.0), b


def main():
    print("=== Asian-canary probe: incremental info beyond the overnight gap ===")
    print(f"    (start {START}; daily; approximate same-date Asia→US alignment)\n")
    us_data = {}
    for name, t in US.items():
        d = dl(t)
        if d is None and name == "SOX":
            print("  ^SOX empty -> fallback SOXX")
            d = dl("SOXX")
        us_data[name] = d
    asia_data = {name: dl(t) for name, t in ASIA.items()}

    verdicts = []
    for aname, ad in asia_data.items():
        if ad is None:
            print(f"[{aname}] no data (yfinance)"); continue
        aon = asia_overnight(ad)
        for uname, ud in us_data.items():
            if ud is None:
                continue
            df = pd.concat([aon, us_parts(ud)], axis=1).dropna()
            if len(df) < 500:
                print(f"[{aname}->{uname}] too few rows ({len(df)})"); continue
            r_gap = df["asia_on"].corr(df["gap"])
            r_intr = df["asia_on"].corr(df["intraday"])
            r_full = df["asia_on"].corr(df["full"])
            y = df["intraday"].to_numpy()
            X0 = np.c_[np.ones(len(df)), df["gap"].to_numpy()]
            X1 = np.c_[X0, df["asia_on"].to_numpy()]
            r2_0, _ = ols_r2(X0, y)
            r2_1, b1 = ols_r2(X1, y)
            incr = r2_1 - r2_0
            verdicts.append(incr)
            print(f"[{aname:6}->{uname:4}] n={len(df):4}  "
                  f"corr(asia,gap)={r_gap:+.2f}  corr(asia,intraday)={r_intr:+.2f}  corr(asia,full)={r_full:+.2f}")
            print(f"             intraday R^2: gap-only={r2_0:.4f}  +asia={r2_1:.4f}  "
                  f"INCREMENTAL={incr:+.4f}  asia_coef={b1[-1]:+.3f}")

    if verdicts:
        mx = max(verdicts)
        print("\n--- READ ---")
        print(f"max incremental intraday R^2 from Asia (beyond gap) across pairs: {mx:.4f}")
        print("corr(asia,gap) high = Asia already priced into the US open (expected).")
        print("incremental R^2 ~ 0 = Asia adds ~nothing to the TRADEABLE (open->close) part -> no edge, stop.")
        print("incremental R^2 clearly >0 AND stable -> worth a full six-step spec.")


if __name__ == "__main__":
    main()
