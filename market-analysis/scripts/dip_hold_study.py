"""dip_hold_study.py — 「跌了买、持有一年」的诚实账(回撤深度 → 前向收益·纯描述)

严格实现 docs_internal/SPEC_DIP_HOLD.md。**纯描述,不产出买入信号/edge/晋升**——只描述「历史上从 52 周高点
回撤 X% 之后、持有 H 天,市场怎么走」+ 基率参照 + 段级 CI + 分时代稳健性。

命门(§0):
  - 基率是诚实参照系:大盘持有 1 年历史上约 75% 上涨,「跌了买」要有料必须明显跑赢基率。
  - 重叠窗口 → N 虚高:一次深回撤持续几十上百日。报 n_days(重叠) 与 n_episodes(去聚集独立段);
    CI 用段级自助,独立段 < MIN_EPISODES_CI 一律 described-only 不出 CI。
  - 幸存者偏差:stocks_prices.csv 只有 20 只活到今天的赢家 → 单股永不回测,只出「当前距 52 周高/低」描述快照。
"""
import sys
import zlib
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from stats_util import forward_returns
from util_io import write_json

RAW_DIR = _SCRIPTS.parent / "data" / "raw"

# ══════════════════════════════════════════════════════════════════
# 冻结常量(§1 — 不可调,任何"看着显著就改"的冲动 → 停,见 spec §7)
# ══════════════════════════════════════════════════════════════════
LOOKBACK = 252                       # 52 周 = 252 交易日 rolling 窗(frozen)
HORIZONS = [60, 252]                 # 前向窗口:60 短、252(~1年)长(frozen);primary=252
DD_THRESHOLDS = [5, 10, 15, 20, 30]  # 距 52 周高点回撤阈值 %(frozen,round number 无 DoF)
LOW_PROX = [2, 5, 10]                # 距 52 周低点邻近阈值 %(frozen,接飞刀对照)
RECOVERY_FLOOR = -0.03               # 去聚集:dd 回升到 ≥ −3%(距高点 3% 内≈已恢复)才解除阻塞(frozen §1.3)
MIN_EPISODES_CI = 8                  # 独立段 < 8 → described-only 无 CI(frozen §2)
B_BOOT = 2000
SEED_BASE = 20260805                 # 固定种子(=spec 定稿日)供可复现

PRICE_STEM = "SP500_long"
HISTORY_START = "2000-01-03"         # 分析窗起点(frozen §1;与 [[SPEC_FEAR_EXTREMES]] 同「现代市场」口径)。
                                     # rolling252 用全史暖机(2000 年的 52 周高来自 1999),仅把「分析日」限到 2000+。
PRIMARY_CELL = {"index": "SP500", "dd_threshold_pct": 20, "horizon": 252}  # 事前钉死(§1,frozen)
STOCKS_FILE = "stocks_prices.csv"

SURVIVORSHIP_NOTE = (
    "单股数据仅 20 只活到今天的赢家(AAPL/NVDA/TSLA…):在它们身上回测「跌了买」会因幸存者偏差严重高估"
    "——跌 20% 后归零/退市的股(雷曼、Enron、SVB、一堆 SPAC)根本不在数据里。故本表只给「当前距自己 52 周"
    "高/低多远」的事实快照,绝不回测、绝不当买入信号。单个公司大跌常是「便宜有便宜的原因」(价值陷阱),"
    "指数跌了会随整个美国市场恢复,单股不会都恢复。"
)

HONESTY = [
    "纯描述·无晋升:本研究不产出「买入信号/edge/抄底建议」,只描述历史上从 52 周高点回撤 X% 之后、持有 H 天"
    "市场的前向表现——明确非信号、非荐股、非投资建议。",
    "基率是诚实参照系:大盘光是持有 1 年,历史上就约 75% 上涨、中位约 +11%。所以一个「跌了买」的口径要算「有料」,"
    "必须明显跑赢「随便哪天买」的基率——不是「涨了就叫赢」,市场本来大概率就涨。",
    "重叠窗口让 N 虚高:一次深回撤会持续几十上百个交易日,逐日计数把同一场危机重复计成几百个「样本」。"
    "本研究报 n_days(重叠日)、原始独立回撤段,以及 n_independent——后者进一步把「前向窗口会重叠」(相隔不足"
    "持有天数)的回撤段并起来,因为它们的未来收益共享同一段行情、不算真正独立(与 fear_greed 同一处理)。"
    "置信区间用这些互不重叠的聚类做段级自助,独立聚类 < 8 一律 described-only、不出 CI。深回撤(≥20/30%)的"
    "独立聚类本就只有 ~3-6 次危机(2008/2020/2022 等),数字再好看也是轶事级,别当规律。",
    "幸存者偏差(单股):" + SURVIVORSHIP_NOTE,
    "体制依赖:回撤买入是否「有料」高度依赖牛熊环境——2000-2012 熊市多的年代买浅跌几乎白买(跌了还继续跌),"
    "好看的数字多来自 2013 后的长牛。本研究报分时代结果并如实标「靠牛市撑着」的风险。",
    "还有一笔账没算进表里:等跌的时候,那些「没等到跌、直接涨上去」的行情会被踏空——本表只统计「跌到了才买」的情形,"
    "不含「干等一个没来的回撤」的机会成本。",
    "数据仅覆盖 2000 年至今(SP500_long)。历史规律 ≠ 未来保证,会出错,过去表现不代表未来结果。",
]

ALLOWED_VERDICTS = ("described-only", "robust-across-crises", "crisis-driven-fragile")


# ══════════════════════════════════════════════════════════════════
# 数据加载
# ══════════════════════════════════════════════════════════════════
def _load_price(stem):
    f = RAW_DIR / f"{stem}.csv"
    s = pd.read_csv(f, index_col=0, parse_dates=True).squeeze()
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s[s > 0].sort_index()


def _drawdown(px):
    """dd[t] = px/rolling252_high − 1 (≤0);prox[t] = px/rolling252_low − 1 (≥0)。< LOOKBACK 日为 NaN。"""
    hi = px.rolling(LOOKBACK, min_periods=LOOKBACK).max()
    lo = px.rolling(LOOKBACK, min_periods=LOOKBACK).min()
    return px / hi - 1.0, px / lo - 1.0


# ══════════════════════════════════════════════════════════════════
# 去聚集(§1.3 危机重置法)
# ══════════════════════════════════════════════════════════════════
def detect_dd_episodes(dd, threshold_frac, recovery=RECOVERY_FLOOR):
    """独立回撤段:dd 首次 ≤ 阈值 开新段;此后阻塞,直到 dd 回升到 ≥ recovery 才解除。

    dd: pd.Series(fraction, ≤0),升序 index,已 dropna。threshold_frac 为负(如 −0.20)。
    返回 list[list[pd.Timestamp]] —— 每段内的合格日(dd ≤ 阈值)。
    """
    episodes = []
    blocked = False
    for date, v in dd.items():
        if v <= threshold_frac:
            if not blocked:
                episodes.append([date])
                blocked = True
            else:
                episodes[-1].append(date)
        elif blocked and v >= recovery:
            blocked = False
    return episodes


# ══════════════════════════════════════════════════════════════════
# 段级(整块危机)聚类自助 CI(§2)
# ══════════════════════════════════════════════════════════════════
def cluster_bootstrap(episode_day_returns, seed, B=B_BOOT):
    """按「整段危机」聚类自助:有放回重采样 n_episodes 段,每段保留其全部合格日,合并后算日加权均值。

    这样点估计 = 日级均值(用户直觉的「跌了买平均怎样」),而不确定性只来自 ~N 段独立危机(不是几百个重叠日)。
    episode_day_returns: list[np.ndarray](每段合格日的前向收益,fraction,已去 NaN、非空)。
    返回日加权均值的 95% CI(百分比)。调用方须先判段数 ≥ MIN_EPISODES_CI。
    """
    n = len(episode_day_returns)
    rng = np.random.default_rng(seed)
    means = np.empty(B, dtype=float)
    for b in range(B):
        idx = rng.integers(0, n, size=n)
        pooled = np.concatenate([episode_day_returns[i] for i in idx])
        means[b] = pooled.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [round(float(lo) * 100, 2), round(float(hi) * 100, 2)]


def _merge_within_horizon(segments, pos_of, horizon):
    """把「前向窗口会重叠」的相邻段并为一个 CI 聚类(单一实现·fear_greed 也 import 此函数)。

    去聚集(危机重置)只挡住段内重复;但两段就算真正分开,若相隔 < horizon 个交易日,它们的
    [入场, 入场+horizon] 前向窗口仍重叠、共享同一段行情——当独立段喂给聚类自助会让 CI 虚窄。故按交易日位置:
    下一段首日与当前聚类末日间隔 < horizon → 并入同一聚类。返回 list[list[pd.Timestamp]](前向窗口互不重叠)。
    """
    clusters = []
    cur = None
    last_pos = None
    for seg in segments:
        first_pos = pos_of.get(seg[0])
        seg_last_pos = pos_of.get(seg[-1])
        if cur is None:
            cur, last_pos = list(seg), seg_last_pos
        elif first_pos is not None and last_pos is not None and (first_pos - last_pos) < horizon:
            cur.extend(seg)
            last_pos = seg_last_pos if seg_last_pos is not None else last_pos
        else:
            clusters.append(cur)
            cur, last_pos = list(seg), seg_last_pos
    if cur is not None:
        clusters.append(cur)
    return clusters


def _seed_for(*parts):
    # 确定性种子:用 zlib.crc32(跨进程稳定),不用内置 hash()——后者按 PYTHONHASHSEED 每进程加盐,
    # 会让自助 CI 每次跑都抖动、边界处甚至翻转公开 verdict(审查 Important-1 修)。
    s = "|".join(str(p) for p in parts)
    return SEED_BASE + zlib.crc32(s.encode("utf-8")) % 1_000_000


def verdict_for(too_small, diff_mean, era_same_sign, ci_beats_base):
    """三态·均非 edge/买入(§4·硬保证)。

    ci_beats_base:聚类自助 CI 下界是否 > 基率均值(即「可靠跑赢随便买」,而非仅「绝对为正」——
    1 年绝对为正几乎恒真、无信息)。robust 需:跑赢基率 + 段级 CI 可靠跑赢基率 + 分时代同向。
    """
    if too_small:
        return "described-only"
    if diff_mean is not None and diff_mean > 0 and era_same_sign is True and ci_beats_base is True:
        return "robust-across-crises"
    if diff_mean is not None and diff_mean > 0:
        return "crisis-driven-fragile"
    return "described-only"


# ══════════════════════════════════════════════════════════════════
# 单个(回撤阈值 × 窗口)cell
# ══════════════════════════════════════════════════════════════════
def build_dd_cell(dd, fwd_h, threshold_pct, base_up, base_mean, seed, horizon):
    """dd/fwd_h 已对齐同 index。threshold_pct 为正整数(%);内部转负 fraction。horizon 用于合并前向窗口重叠段。"""
    thr = -threshold_pct / 100.0
    episodes = detect_dd_episodes(dd, thr)
    n_episodes = len(episodes)

    qual = dd[dd <= thr].index                      # 所有合格日
    day_ret = fwd_h.reindex(qual).dropna()          # 日级前向收益(去末端 NaN)
    n_days = int(len(day_ret))
    if n_days:
        up_pct = round(float((day_ret > 0).mean()) * 100, 2)
        mean_pct = round(float(day_ret.mean()) * 100, 2)
        median_pct = round(float(day_ret.median()) * 100, 2)
    else:
        up_pct = mean_pct = median_pct = None

    # 原始危机段数(透明用):有 ≥1 有效前向收益日的段
    n_ep_fwd = sum(1 for ep in episodes if len(fwd_h.reindex(ep).dropna()))

    # CI 聚类 = 前向窗口互不重叠的聚类(把相隔 < horizon 的危机段并起来·与 fear_greed 一致·审查 Finding-1)
    pos_of = {d: i for i, d in enumerate(fwd_h.index)}
    clusters = _merge_within_horizon(episodes, pos_of, horizon)
    ep_day_rets = []
    for cl in clusters:
        r = fwd_h.reindex(cl).dropna()
        if len(r):
            ep_day_rets.append(r.values.astype(float))
    n_independent = len(ep_day_rets)         # 前向窗口互不重叠的聚类数——CI 门槛/自助实际用
    too_small = n_independent < MIN_EPISODES_CI

    base_up_pct = round(base_up * 100, 2)
    base_mean_pct = round(base_mean * 100, 2)
    diff_mean = round(mean_pct - base_mean_pct, 2) if mean_pct is not None else None

    ci = None
    ci_beats_base = None
    if not too_small:
        ci = cluster_bootstrap(ep_day_rets, seed=seed)     # 日加权均值的 95% CI(不确定性来自 ~N 段危机)
        ci_beats_base = bool(ci[0] > base_mean_pct)         # 下界 > 基率 → 可靠跑赢随便买

    # 分时代(日级,触发日年份)
    def _era(mask):
        r = fwd_h.reindex(qual[mask]).dropna()
        if not len(r):
            return None, None
        return round(float((r > 0).mean()) * 100, 2), round(float(r.mean()) * 100, 2)
    yr = qual.year
    era1_up, era1_mean = _era(yr <= 2012)
    era2_up, era2_mean = _era(yr >= 2013)
    era_same_sign = None
    if era1_mean is not None and era2_mean is not None:
        era_same_sign = bool(np.sign(era1_mean) == np.sign(era2_mean))

    return {
        "dd_threshold_pct": threshold_pct,
        "horizon": None,  # 由调用方补
        "n_days": n_days,
        "n_episodes": n_episodes,
        "n_episodes_with_fwd": n_ep_fwd,       # 原始危机段(有有效日)
        "n_independent": n_independent,        # 前向窗口去重叠后的聚类数(CI 实际用)
        "up_pct": up_pct,
        "mean_pct": mean_pct,
        "median_pct": median_pct,
        "base_up_pct": base_up_pct,
        "base_mean_pct": base_mean_pct,
        "diff_mean": diff_mean,
        "ci95_mean": ci,                       # 日加权均值的段级聚类自助 CI(百分比)
        "ci_beats_base": ci_beats_base,        # CI 下界 > 基率 → 可靠跑赢随便买
        "too_small_no_ci": too_small,
        "era1_up_pct": era1_up, "era1_mean_pct": era1_mean,
        "era2_up_pct": era2_up, "era2_mean_pct": era2_mean,
        "era_same_sign": era_same_sign,
        "verdict": verdict_for(too_small, diff_mean, era_same_sign, ci_beats_base),
    }


def build_low_prox_cell(prox, fwd_h, within_pct, base_up, base_mean):
    """距 52 周低点 ≤ within_pct 的日级描述(接飞刀对照,不做 CI)。"""
    lim = within_pct / 100.0
    qual = prox[prox <= lim].index
    r = fwd_h.reindex(qual).dropna()
    n = int(len(r))
    return {
        "within_pct": within_pct,
        "n_days": n,
        "up_pct": round(float((r > 0).mean()) * 100, 2) if n else None,
        "mean_pct": round(float(r.mean()) * 100, 2) if n else None,
        "base_up_pct": round(base_up * 100, 2),
        "base_mean_pct": round(base_mean * 100, 2),
    }


def episodes_display(dd, threshold_pct):
    """每段起始日 + 段内最深 dd + 合格日数(供人看清「就 ~几次危机」)。"""
    thr = -threshold_pct / 100.0
    out = []
    for ep in detect_dd_episodes(dd, thr):
        seg = dd.reindex(ep)
        out.append({
            "start": ep[0].strftime("%Y-%m-%d"),
            "deepest_dd_pct": round(float(seg.min()) * 100, 2),
            "n_days": len(ep),
        })
    return out


# ══════════════════════════════════════════════════════════════════
# 单股当前快照(§3·纯描述·永不回测)
# ══════════════════════════════════════════════════════════════════
def single_stock_snapshot(_stocks=None):
    if _stocks is not None:
        df = _stocks
    else:
        f = RAW_DIR / STOCKS_FILE
        if not f.exists():
            return {"as_of": None, "survivorship_note": SURVIVORSHIP_NOTE, "current": []}
        df = pd.read_csv(f, index_col=0, parse_dates=True).sort_index()
    rows = []
    as_of = None
    for tk in df.columns:
        s = pd.to_numeric(df[tk], errors="coerce").dropna()
        if len(s) < LOOKBACK:
            continue
        window = s.iloc[-LOOKBACK:]
        cur = float(s.iloc[-1])
        rows.append({
            "ticker": str(tk),
            "dd_from_52wk_high_pct": round((cur / float(window.max()) - 1.0) * 100, 1),
            "dist_from_52wk_low_pct": round((cur / float(window.min()) - 1.0) * 100, 1),
        })
        as_of = s.index[-1]
    rows.sort(key=lambda r: r["dd_from_52wk_high_pct"])   # 跌得最狠的在前
    return {
        "as_of": as_of.strftime("%Y-%m-%d") if as_of is not None else None,
        "survivorship_note": SURVIVORSHIP_NOTE,
        "current": rows,
    }


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run(write=True, _price=None, _stocks=None):
    px_full = _price if _price is not None else _load_price(PRICE_STEM)
    dd_full, prox_full = _drawdown(px_full)                 # rolling252 用全史暖机(避免丢掉 2000-2001)
    fwd_full = {h: forward_returns(px_full, h) for h in HORIZONS}

    mask = px_full.index >= pd.Timestamp(HISTORY_START)     # 仅把「分析日」限到 2000+(frozen §1)
    px = px_full[mask]
    dd = dd_full[mask].dropna()
    prox = prox_full[mask].dropna()
    fwd = {h: fwd_full[h][mask] for h in HORIZONS}
    base = {}
    for h in HORIZONS:
        v = fwd[h].dropna()
        base[h] = {
            "up": float((v > 0).mean()) if len(v) else float("nan"),
            "mean": float(v.mean()) if len(v) else float("nan"),
            "median": float(v.median()) if len(v) else float("nan"),
            "n": int(len(v)),
        }

    curve = []
    for thr in DD_THRESHOLDS:
        for h in HORIZONS:
            cell = build_dd_cell(dd, fwd[h], thr, base[h]["up"], base[h]["mean"],
                                 seed=_seed_for("dd", thr, h), horizon=h)
            cell["horizon"] = h
            curve.append(cell)

    low_prox = [build_low_prox_cell(prox, fwd[252], w, base[252]["up"], base[252]["mean"])
                for w in LOW_PROX]

    episodes_by_thr = {str(thr): episodes_display(dd, thr) for thr in DD_THRESHOLDS}
    any_robust = any(c["verdict"] == "robust-across-crises" for c in curve)   # 前端据此措辞,不硬编码(审查 Important-2 修)

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": px.index.max().strftime("%Y-%m-%d"),
        "price_start": px.index.min().strftime("%Y-%m-%d"),
        "lookback": LOOKBACK,
        "recovery_floor": RECOVERY_FLOOR,
        "min_episodes_ci": MIN_EPISODES_CI,
        "primary_cell": dict(PRIMARY_CELL),
        "any_robust": any_robust,
        "base_rate": {
            f"h{h}": {
                "up_pct": round(base[h]["up"] * 100, 2),
                "mean_pct": round(base[h]["mean"] * 100, 2),
                "median_pct": round(base[h]["median"] * 100, 2),
                "n": base[h]["n"],
            } for h in HORIZONS
        },
        "drawdown_curve": curve,
        "low_proximity": low_prox,
        "episodes": episodes_by_thr,
        "single_stocks": single_stock_snapshot(_stocks),
        "honesty": HONESTY,
        "verdict_note": (
            "描述性总结:持有 1 年本身基率就强(约 75% 涨);浅到中回撤(5-15%)历史上并不比随便买强、"
            "有时反而略差;只有深回撤(≥20%,尤其≥30% 崩盘级)才明显跑赢基率——但那是 ~3-6 次危机撑起、样本极小;"
            "在 52 周最低点附近买反而最差(接飞刀)。单股一律只出描述快照(幸存者偏差)。以上皆非买入信号。"
        ),
    }

    if write:
        for d in write_json("dip_hold.json", out, allow_nan=False):
            print(f"  Written: {d}/dip_hold.json")
    return out


if __name__ == "__main__":
    r = run(write=True)
    print("\n=== 「跌了买、持有一年」诚实账(纯描述) ===")
    print(f"  价格 {r['price_start']} → {r['as_of']}")
    for h in HORIZONS:
        b = r["base_rate"][f"h{h}"]
        print(f"  基率 持有{h}日: up {b['up_pct']}%  mean {b['mean_pct']}%  中位 {b['median_pct']}%  N={b['n']}")
    print("  --- 回撤曲线 ---")
    for c in r["drawdown_curve"]:
        print(f"    回撤≥{c['dd_threshold_pct']:>2}% / {c['horizon']:>3}d: "
              f"up {c['up_pct']}%  mean {c['mean_pct']}%  vs base {c['diff_mean']:+}  "
              f"n_days={c['n_days']} n_ep={c['n_episodes_with_fwd']}  "
              f"CI={c['ci95_mean']}  verdict={c['verdict']}")
    print("  --- 距52周低点(接飞刀对照) ---")
    for c in r["low_proximity"]:
        print(f"    距低点≤{c['within_pct']:>2}% / 252d: up {c['up_pct']}%  mean {c['mean_pct']}%  (base up {c['base_up_pct']}%)")
    print(f"\n  primary_cell = {r['primary_cell']}")
    print(f"  单股快照 n={len(r['single_stocks']['current'])} as-of {r['single_stocks']['as_of']}")
