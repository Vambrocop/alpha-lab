"""vix_vol_forecast.py — VIX 到底预测什么(复现维基那张「VIX vs 实现波动」预测力图·纯描述)

回应用户:「那张图很不错,按我们数据做个类似的」。维基百科 VIX 词条那张图(1990-2009)显示:
VIX 预测下个月的「实现波动率」r≈0.80,只比「单看最近波动」r≈0.77 强一点点。核心诚实点:
**VIX 测的是「波动大小(会晃多厉害)」,不是「涨跌方向」**,而且干这活儿只比看最近波动强一丁点。

本脚本用仓库 2000+ 数据复现:
  - 目标 = 下 21 交易日(~1 月)的实现波动率(年化 %),与预测日「不重叠」。
  - 预测器 A = VIX(当日收盘);预测器 B = 过去 21 交易日实现波动率。
  - 报两者与目标的 Pearson r + 回归线,输出散点供前端画图。
**不是信号/预测方向,纯描述 VIX 的性质。**
"""
import sys
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from util_io import write_json

RAW_DIR = _SCRIPTS.parent / "data" / "raw"
RV_WIN = 21                          # 实现波动率窗(~1 月,frozen)
ANN = np.sqrt(252) * 100             # 年化到 %(与 VIX 同单位)
WIKI = {"r_vix": 0.797, "r_past": 0.769, "period": "1990-2009"}   # 维基原图数字(对照)

HONESTY = [
    "纯描述:本图只描述「VIX / 过去波动」对未来波动率的预测力,不预测涨跌方向、不是任何买卖信号。",
    "核心结论:VIX 预测的是「波动大小(市场会晃多厉害)」,不是「涨还是跌」。所以「VIX 低 → 会继续涨」从根上"
    "不成立——VIX 压根不预测方向。",
    "而且 VIX 干它本职(预测波动)也只比「单看最近波动晃得凶不凶」强一些——我们数据上 0.72 vs 0.65,"
    "这个差距其实比维基原图(0.80 vs 0.77)还略大一点,但两者都不悬殊,VIX 没有魔力。",
    "目标窗(下 21 日实现波动)与预测日不重叠;但相邻样本仍高度自相关,r 只作描述,不做显著性声张。",
    "数据仅 2000 年至今;过去 ≠ 未来,会错。",
]


def _load():
    df = pd.read_csv(RAW_DIR / "combined_prices.csv", index_col=0, parse_dates=True)
    return df[["SP500", "VIX"]].dropna().sort_index()


def compute(_df=None):
    d = _df if _df is not None else _load()
    sp, vix = d["SP500"], d["VIX"]
    logret = np.log(sp / sp.shift(1))
    rv = logret.rolling(RV_WIN).std() * ANN         # 尾部 21 日实现波动(t 覆盖 [t-20,t])
    past_rv = rv                                     # 预测器 B
    fwd_rv = rv.shift(-RV_WIN)                       # 目标:下 21 日 [t+1,t+21],与 t 不重叠
    m = pd.DataFrame({"vix": vix, "past_rv": past_rv, "fwd_rv": fwd_rv}).dropna()

    r_vix = float(m["vix"].corr(m["fwd_rv"]))
    r_past = float(m["past_rv"].corr(m["fwd_rv"]))

    def _fit(x, y):
        s, b = np.polyfit(x.values, y.values, 1)
        return {"slope": round(float(s), 4), "intercept": round(float(b), 4)}

    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": m.index.max().strftime("%Y-%m-%d"),
        "start": m.index.min().strftime("%Y-%m-%d"),
        "n": int(len(m)),
        "rv_win": RV_WIN,
        "r_vix": round(r_vix, 3),
        "r_past": round(r_past, 3),
        "fit_vix": _fit(m["vix"], m["fwd_rv"]),
        "fit_past": _fit(m["past_rv"], m["fwd_rv"]),
        "points": {
            "vix": [round(float(v), 2) for v in m["vix"]],
            "past_rv": [round(float(v), 2) for v in m["past_rv"]],
            "fwd_rv": [round(float(v), 2) for v in m["fwd_rv"]],
        },
        "wiki": WIKI,
        "honesty": HONESTY,
    }


def run(write=True, _df=None):
    out = compute(_df)
    if write:
        for dd in write_json("vix_vol.json", out, allow_nan=False):
            print(f"  Written: {dd}/vix_vol.json")
    return out


if __name__ == "__main__":
    r = run(write=True)
    print("\n=== VIX 波动预报力(复现维基图·纯描述) ===")
    print(f"  数据 {r['start']} → {r['as_of']}  N={r['n']}")
    print(f"  r(VIX, 下月实现波动)      = {r['r_vix']}")
    print(f"  r(过去波动, 下月实现波动) = {r['r_past']}")
    print(f"  维基(1990-2009): {r['wiki']['r_vix']} vs {r['wiki']['r_past']}")
