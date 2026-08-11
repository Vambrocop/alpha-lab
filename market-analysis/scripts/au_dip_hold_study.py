"""au_dip_hold_study.py — 澳股版「跌了买·持有一年」诚实账(ASX200·CGT 满1年·纯描述)

复用美股 dip_hold_study 的【已审统计方法】(去聚集/聚类自助/前向窗去重叠/分时代/幸存者守门),
换数据源=^AXJO(ASX200·1992+·全历史)、换框架=澳洲税务居民持有 >12 个月拿 CGT 50% 折扣的持有期。
**纯描述·非买入信号**,与 [[SPEC_DIP_HOLD]] 同红线。个股(ASX 蓝筹)只出当前快照 + 幸存者偏差警告,绝不回测。

首发动机(用户 2026-08-07):用户是澳洲税务居民、美股澳股都持有、为 CGT 折扣持有 1 年;美股版已上线,
本文件补澳股版。快查已见:澳股上"回撤≥10%/持有1年"过 robust-across-crises 门(美股无一格过)——本文件用全历史核。
"""
import sys
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# 复用美股 dip 的已审统计核（单一实现，别复制）
from dip_hold_study import (
    _drawdown, build_dd_cell, build_low_prox_cell, episodes_display, _seed_for,
    DD_THRESHOLDS, LOW_PROX, HORIZONS,
)
from stats_util import forward_returns
from util_io import write_json

RAW_AU = _SCRIPTS.parent / "data" / "raw" / "au"

INDEX_FILE = "AXJO.csv"          # ^AXJO = ASX200(标准基准)
INDEX_COL = "^AXJO"
INDEX_LABEL = "ASX200 (^AXJO)"
STOCKS_FILE = "au_stocks_prices.csv"   # ASX 蓝筹(BHP/CBA/CSL/NAB/WBC…)
LOOKBACK = 252
PRIMARY_CELL = {"index": "ASX200", "dd_threshold_pct": 20, "horizon": 252}

SURVIVORSHIP_NOTE = (
    "个股数据仅 5 只澳洲蓝筹(BHP/CBA/CSL/NAB/WBC·活到今天的赢家):在它们身上回测「跌了买」会因幸存者偏差"
    "严重高估——跌后退市/被并购/塌掉的股不在数据里。故本表只给「当前距自己 52 周高/低多远」的事实快照,"
    "绝不回测、绝不当买入信号。单个公司大跌常「便宜有便宜的原因」;指数跌了会随整个澳洲市场恢复,单股不会都恢复。"
)

HONESTY = [
    "纯描述·无晋升:只描述历史上从 52 周高点回撤 X% 之后、持有 H 天 ASX200 的前向表现——非信号、非荐股、非投资建议。",
    "澳洲税务居民持有 >12 个月可享 CGT 50% 折扣,故用「持有 1 年(252 交易日)」为主口径;这是税务框架,不改任何统计。",
    "基率是诚实参照系:ASX200 光是持有 1 年历史上就约 7 成上涨。「跌了买」要算有料,必须明显跑赢「随便哪天买」。",
    "重叠窗口让 N 虚高:一次深回撤持续几十上百个交易日。报独立回撤段 + n_independent(再把前向窗口重叠、相隔不足"
    "持有天数的段并起来,共享同一段行情不算独立);CI 用互不重叠聚类的段级自助,独立聚类 < 8 一律 described-only。",
    "幸存者偏差(个股):" + SURVIVORSHIP_NOTE,
    "体制依赖:分时代(1992-2009 / 2010-今)报是否同向。澳股以银行/矿业/高股息为主、更均值回归,"
    "与美股(科技动量驱动)结论可能不同——这是市场结构差异,不是普适规律。",
    "数据 ^AXJO 1992 年至今。历史规律 ≠ 未来保证,会出错,过去不代表未来。汇率:本研究按 ASX 本币(AUD)算,"
    "不含美股持仓的 AUD/USD 汇率影响。",
]


def _load_index():
    s = pd.read_csv(RAW_AU / INDEX_FILE, parse_dates=["Date"]).set_index("Date")[INDEX_COL]
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s[s > 0].sort_index()


def _load_stocks():
    f = RAW_AU / STOCKS_FILE
    if not f.exists():
        return None
    return pd.read_csv(f, parse_dates=["Date"]).set_index("Date").sort_index()


def _au_stock_snapshot(df):
    if df is None:
        return {"as_of": None, "survivorship_note": SURVIVORSHIP_NOTE, "current": []}
    rows, as_of = [], None
    for tk in df.columns:
        s = pd.to_numeric(df[tk], errors="coerce").dropna()
        if len(s) < LOOKBACK:
            continue
        w = s.iloc[-LOOKBACK:]
        cur = float(s.iloc[-1])
        rows.append({"ticker": str(tk),
                     "dd_from_52wk_high_pct": round((cur / float(w.max()) - 1) * 100, 1),
                     "dist_from_52wk_low_pct": round((cur / float(w.min()) - 1) * 100, 1)})
        as_of = s.index[-1]
    rows.sort(key=lambda r: r["dd_from_52wk_high_pct"])
    return {"as_of": as_of.strftime("%Y-%m-%d") if as_of is not None else None,
            "survivorship_note": SURVIVORSHIP_NOTE, "current": rows}


def run(write=True, _price=None, _stocks=None):
    px = _price if _price is not None else _load_index()      # 全历史,不裁剪(澳股无 VIX 约束)
    dd, prox = _drawdown(px)
    dd = dd.dropna()
    prox = prox.dropna()
    fwd = {h: forward_returns(px, h) for h in HORIZONS}

    base = {}
    for h in HORIZONS:
        v = fwd[h].dropna()
        base[h] = {"up": float((v > 0).mean()) if len(v) else float("nan"),
                   "mean": float(v.mean()) if len(v) else float("nan"),
                   "median": float(v.median()) if len(v) else float("nan"), "n": int(len(v))}

    curve = []
    for thr in DD_THRESHOLDS:
        for h in HORIZONS:
            cell = build_dd_cell(dd, fwd[h], thr, base[h]["up"], base[h]["mean"],
                                 seed=_seed_for("audd", thr, h), horizon=h)
            cell["horizon"] = h
            curve.append(cell)

    low_prox = [build_low_prox_cell(prox, fwd[252], w, base[252]["up"], base[252]["mean"]) for w in LOW_PROX]
    episodes_by_thr = {str(thr): episodes_display(dd, thr) for thr in DD_THRESHOLDS}
    any_robust = any(c["verdict"] == "robust-across-crises" for c in curve)

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": px.index.max().strftime("%Y-%m-%d"),
        "price_start": px.index.min().strftime("%Y-%m-%d"),
        "index_label": INDEX_LABEL,
        "lookback": LOOKBACK,
        "min_episodes_ci": 8,
        "primary_cell": dict(PRIMARY_CELL),
        "any_robust": any_robust,
        "base_rate": {f"h{h}": {"up_pct": round(base[h]["up"] * 100, 2),
                                "mean_pct": round(base[h]["mean"] * 100, 2),
                                "median_pct": round(base[h]["median"] * 100, 2),
                                "n": base[h]["n"]} for h in HORIZONS},
        "drawdown_curve": curve,
        "low_proximity": low_prox,
        "episodes": episodes_by_thr,
        "single_stocks": _au_stock_snapshot(_stocks if _stocks is not None else _load_stocks()),
        "honesty": HONESTY,
        "verdict_note": (
            "描述性总结(澳股 ASX200):持有 1 年基率约 7 成;与美股不同,澳股上浅到中回撤历史上就跑赢随便买、"
            "买在 52 周最低点附近也是好入场(美股相反=接飞刀)——ASX 更均值回归。若某档过 robust-across-crises,"
            "那是两个市场里少见的「稳健」;但独立聚类少的档仍 described-only、别当铁律。单股只快照(幸存者偏差)。皆非买入信号。"
        ),
    }
    if write:
        for d in write_json("au_dip_hold.json", out, allow_nan=False):
            print(f"  Written: {d}/au_dip_hold.json")
    return out


if __name__ == "__main__":
    try:                                              # 顶层 fail-soft:独立区缺数据(raw/au/*.csv)绝不阻断流水线
        r = run(write=True)
        print(f"\n=== 澳股「跌了买·持有一年」诚实账(纯描述) ===")
        print(f"  {r['index_label']}  {r['price_start']} → {r['as_of']}")
        b = r["base_rate"]["h252"]
        print(f"  基率 持有1年: up {b['up_pct']}%  mean {b['mean_pct']}%  中位 {b['median_pct']}%  N={b['n']}")
        for c in r["drawdown_curve"]:
            if c["horizon"] == 252:
                print(f"    回撤>={c['dd_threshold_pct']:>2}%: up {c['up_pct']}% mean {c['mean_pct']}% vs基率{c['diff_mean']:+} "
                      f"| 独立聚类 {c['n_independent']} | CI {c['ci95_mean']} | {c['verdict']}")
        print(f"  any_robust = {r['any_robust']}")
        for c in r["low_proximity"]:
            print(f"    距52周低点<={c['within_pct']}%: up {c['up_pct']}% mean {c['mean_pct']}% (基率 {c['base_up_pct']}%)")
    except Exception as e:
        print(f"[AU 跌了买] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        sys.exit(0)
