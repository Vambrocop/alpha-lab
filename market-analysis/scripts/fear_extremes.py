"""fear_extremes.py — 高/极端恐慌事件研究(VIX 尖峰后前向收益·纯描述)

严格实现 docs_internal/SPEC_FEAR_EXTREMES.md(R3·frozen)。**纯描述,不设信号/edge 晋升路径**——
本文件永不产出"edge-candidate/signal"这类状态,只描述"历史上高/极端恐慌之后市场怎么走" + CI + 留一危机稳健性。

数据口径(冻结,§1):
  - VIX 触发器只用 combined_prices.csv 的 VIX 列(2000-01-03+)。
  - 前向收益价格序列用 SP500_long.csv / NASDAQ_COMP_long.csv(与 horizon_stats.py / fomc_study.py 同源同惯例)——
    这两个"_long"文件比 combined_prices 自带的 SP500/NASDAQ 列历史更长、口径更干净,是项目里事件研究的标准价格源。
  - 经验证:2000+ 期间 combined_prices 的 VIX 去 NaN 后与 SP500_long/NASDAQ_COMP_long 同期交易日历几乎完全重合
    (仅 1 天出入),故按各价格序列自己的交易日历找"次一交易日"是安全的。

触发器(§1.2,绝对阈值,frozen):
  T1 高恐慌  VIX 日收盘 ≥ 30 (primary 层)
  T2 极端恐慌 VIX 日收盘 ≥ 40 (~8 次,轶事级,全程 described-only 不出 CI)
  T3 骤升   单日 VIX 涨幅 ≥ +20% 且当日收盘 ≥ 25

去聚集(§1.3,危机重置法,frozen):触发后阻塞新事件,直到 VIX 首次收盘 < 20(RESET_FLOOR)才解除阻塞。
每个触发器各自独立去聚集,产出各自唯一一套事件集,4 个窗口都在这同一套事件上量。

CI(§3):事件级自助(对独立事件有放回重采样),N<10 的(触发器×窗)一律 described-only、不出 CI。
LOCO(§4):按事件所属"危机年"(触发日所在自然年,frozen 的分组口径——见 §6"逐次...所属危机年")分组,
  逐次剔除影响最大的整段危机重算;方向翻转或 CI 跨 0 → crisis-driven-fragile。
verdict(§6):三态,均非 edge —— described-only / robust-across-crises / crisis-driven-fragile。

VXSMH 不在本研究(§0/S4):历史仅约 10 个月、连一个极端事件都凑不出,已在 risk_dashboard.py 保留为纯描述读数。
"""
import sys
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
# 冻结常量(§1/§2/§3 — 不可调,任何"看着显著就改"的冲动 → 停,见 spec §8)
# ══════════════════════════════════════════════════════════════════
HORIZONS = [5, 20, 60, 120]          # 交易日窗口(frozen)
RESET_FLOOR = 20.0                    # 危机重置地板:VIX 首次收盘 < 20 才解除阻塞(frozen §1.3)
T1_THRESH = 30.0
T2_THRESH = 40.0
T3_PCT_JUMP = 0.20                    # 单日涨幅 ≥ +20%
T3_FLOOR = 25.0                       # 骤升地板(②b 修,frozen)
MIN_N_CI = 10                         # N < 10 → described-only,无 CI(②b 从 8 抬到 10,frozen §3)
B_BOOT = 2000                         # 自助重采样次数
SEED_BASE = 20260801                  # 固定种子基数(=spec 定稿日期)供可复现

PRIMARY_CELL = {"trigger": "T1", "index": "SP500", "horizon": 20}   # 事前钉死(§2,frozen)

PRICE_FILES = {"SP500": "SP500_long", "NASDAQ": "NASDAQ_COMP_long"}

TRIGGERS = {
    "T1": {
        "tier": "primary",
        "label_zh": "高恐慌", "label_en": "High fear",
        "definition_zh": "VIX 日收盘 ≥ 30", "definition_en": "VIX daily close ≥ 30",
    },
    "T2": {
        "tier": "anecdotal",
        "label_zh": "极端恐慌", "label_en": "Extreme fear",
        "definition_zh": "VIX 日收盘 ≥ 40(极稀少,轶事级·别当规律)",
        "definition_en": "VIX daily close ≥ 40 (very rare — anecdotal, not a pattern)",
    },
    "T3": {
        "tier": "secondary",
        "label_zh": "骤升", "label_en": "Spike",
        "definition_zh": "单日 VIX 涨幅 ≥ +20% 且当日收盘 ≥ 25",
        "definition_en": "1-day VIX change ≥ +20% and same-day close ≥ 25",
    },
}

VXSMH_NOTE = (
    "VXSMH(半导体波动率)不在本研究内:发布至今历史仅约 10 个月,连一个极端事件都凑不出,"
    "已在 risk_dashboard.py 保留为纯描述读数,不进本研究的 JSON 块/卡片/测试,等它积累数年历史再议。"
)

HONESTY = [
    "纯描述·无晋升:本研究不产出'edge候选/信号',只描述历史上高/极端恐慌之后市场的前向表现——"
    "明确非信号、非荐股、非投资建议。",
    "样本真相:VIX 高企常常持续数月,逐日计数会把同一场危机反复计成几十次'样本'、假装 N 很大。"
    "本研究用危机重置去聚集(§1.3),报告的是有效独立事件数,不是交易日数——有效 N 只有十来次量级。",
    "数据仅覆盖 2000 年至今(VIX 列 2000-01-03 起):仓库里没有 1990 年代的 VIX,故不含 1990-91 储贷危机/"
    "1998 年 LTCM 等更早期危机;分时代对比只能做 2000-09 vs 2010-今两段是否同向的示意性检查,"
    "本质是问两次大反弹是否同向,不是独立验证。",
    VXSMH_NOTE,
    "多窗(5/20/60/120 日)×多触发器(T1/T2/T3)×两指数=多组结果高度相关,'总有一组看着显著'几乎必然。"
    "已事前钉死一个 primary 单元(T1·SP500·20 日)当头条,其余一律标 secondary/探索,不因'哪组好看'改口径。",
    "置信区间是事件级自助(对独立事件有放回重采样),样本小时区间会很宽——这是诚实结果,不做美化;"
    "有效事件数 < 10 的(触发器×窗)一律标 described-only(样本太小无法计算 CI),绝不静默给出置信区间。"
    "极端恐慌(T2·VIX≥40)固定只有约 8 次,全程 described-only、不出 CI。",
    "留一危机稳健检验(LOCO)是本研究的主检:按危机所在自然年分组,逐次剔除影响最大的整段危机重算——"
    "剔单个事件几乎不动、等于没做,所以剔的是整段危机。若方向翻转或区间跨 0,标记'由单次危机驱动·脆弱';"
    "头条数字用剔除影响最大的那段危机后的结果,防止一次 GFC/COVID 一手撑起全部结论。",
    "历史规律 ≠ 未来保证,会出错,过去表现不代表未来结果。",
]


# ══════════════════════════════════════════════════════════════════
# 数据加载
# ══════════════════════════════════════════════════════════════════
def _load_vix():
    f = RAW_DIR / "combined_prices.csv"
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    return df["VIX"].dropna().sort_index()


def _load_price(stem):
    f = RAW_DIR / f"{stem}.csv"
    s = pd.read_csv(f, index_col=0, parse_dates=True).squeeze()
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s[s > 0].sort_index()


# ══════════════════════════════════════════════════════════════════
# 触发器 + 去聚集(§1.2/§1.3)
# ══════════════════════════════════════════════════════════════════
def _trigger_cond(name):
    if name == "T1":
        return lambda v, p: v >= T1_THRESH
    if name == "T2":
        return lambda v, p: v >= T2_THRESH
    if name == "T3":
        return lambda v, p: (p is not None and p > 0
                              and (v / p - 1.0) >= T3_PCT_JUMP and v >= T3_FLOOR)
    raise ValueError(f"unknown trigger {name}")


def detect_events(vix, trigger):
    """危机重置去聚集(§1.3):触发后阻塞新事件,直到 VIX 首次收盘 < RESET_FLOOR 才解除。

    vix: pd.Series,升序 DatetimeIndex,已 dropna(日收盘)。
    返回:list[pd.Timestamp],触发日期(升序)。
    """
    cond = _trigger_cond(trigger)
    events = []
    blocked = False
    prev = None
    for date, val in vix.items():
        if not blocked and cond(val, prev):
            events.append(date)
            blocked = True
        elif blocked and val < RESET_FLOOR:
            blocked = False
        prev = val
    return events


# ══════════════════════════════════════════════════════════════════
# 事件级自助 CI(§3)
# ══════════════════════════════════════════════════════════════════
def event_bootstrap(values, base_mean, seed, B=B_BOOT):
    """对独立事件的前向收益有放回重采样 B 次,报均值/up 率/差(vs base_mean)的 95% CI。

    values: 1-D array(fraction,非百分比),已去 NaN。base_mean:全样本基率均值(fraction,固定不重采样——
    §3:"差的 CI 由事件侧小 N 主导",base 侧不贡献方差,如实标)。
    返回 dict(百分比单位,已四舍五入),调用方须先用 MIN_N_CI 判断是否该调用本函数。
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n, size=(B, n))
    samples = values[draws]
    means = samples.mean(axis=1)
    ups = (samples > 0).mean(axis=1)
    diffs = means - base_mean

    def _ci(arr):
        lo, hi = np.percentile(arr, [2.5, 97.5])
        return [round(float(lo) * 100, 2), round(float(hi) * 100, 2)]

    return {"ci95_mean": _ci(means), "ci95_up": _ci(ups), "ci95_diff": _ci(diffs)}


# ══════════════════════════════════════════════════════════════════
# 留一危机稳健(LOCO,§4)—— 粒度 = 整段危机(按危机所在自然年分组),非单事件
# ══════════════════════════════════════════════════════════════════
def loco_analysis(groups, full_mean, seed, min_n_ci=MIN_N_CI, B=B_BOOT):
    """groups: dict[crisis_year -> list[float]](fraction)。full_mean: 全事件均值(fraction)。

    逐次剔除一整段危机(=一个 crisis_year 组的全部事件)重算;方向翻转或(可算时)CI 跨 0 → 判不稳。
    headline = 剔除"影响最大"(|剔除后均值 − 全样本均值| 最大)那一整段危机后的均值。
    组数 < 2 或 full_mean 为 None → 无法留一危机,返回 None 字段。
    """
    years = sorted(groups.keys())
    if len(years) < 2 or full_mean is None:
        return {"loco_headline_mean": None, "loco_sign_stable": None,
                "loco_most_influential_crisis_year": None}

    detail = {}
    for i, y in enumerate(years):
        remaining = np.array([r for yy, lst in groups.items() if yy != y for r in lst], dtype=float)
        if len(remaining) == 0:
            detail[y] = {"mean_without": None, "delta": -1.0, "sign_flip": None, "ci_cross0": None}
            continue
        mean_without = float(remaining.mean())
        delta = abs(mean_without - full_mean)
        if full_mean != 0:
            sign_flip = bool(np.sign(mean_without) != np.sign(full_mean))
        else:
            sign_flip = bool(mean_without != 0)
        ci_cross0 = None
        if len(remaining) >= min_n_ci:
            rng = np.random.default_rng(seed + i + 1)
            draws = rng.integers(0, len(remaining), size=(B, len(remaining)))
            boot_means = remaining[draws].mean(axis=1)
            lo, hi = np.percentile(boot_means, [2.5, 97.5])
            ci_cross0 = bool(lo <= 0 <= hi)
        detail[y] = {"mean_without": mean_without, "delta": delta,
                      "sign_flip": sign_flip, "ci_cross0": ci_cross0}

    influential = max(years, key=lambda y: detail[y]["delta"] if detail[y]["delta"] is not None else -1)
    headline = detail[influential]["mean_without"]
    any_unstable = any((d["sign_flip"] is True) or (d["ci_cross0"] is True) for d in detail.values())

    return {
        "loco_headline_mean": round(headline * 100, 2) if headline is not None else None,
        "loco_sign_stable": (not any_unstable),
        "loco_most_influential_crisis_year": int(influential),
    }


# ══════════════════════════════════════════════════════════════════
# 三态 verdict(§6)—— 均非 edge/信号,硬保证
# ══════════════════════════════════════════════════════════════════
ALLOWED_VERDICTS = ("described-only", "robust-across-crises", "crisis-driven-fragile")


def verdict_for_cell(too_small_no_ci, loco_sign_stable):
    if too_small_no_ci:
        return "described-only"
    if loco_sign_stable is None:
        return "described-only"
    return "robust-across-crises" if loco_sign_stable else "crisis-driven-fragile"


def _seed_for(*parts):
    """确定性派生种子(不同 cell 用不同但可复现的种子)。"""
    h = 0
    for p in parts:
        h = (h * 1000003 + hash(str(p))) & 0xFFFFFFFF
    return SEED_BASE + h % 1_000_000


# ══════════════════════════════════════════════════════════════════
# 单个(触发器×指数×窗口)cell
# ══════════════════════════════════════════════════════════════════
def build_cell(pairs, base_mean, base_up, seed):
    """pairs: list[(crisis_year:int, ret:float)](fraction,已去 NaN)。

    返回 §6 定义的 cell 字段(+ 若干additive透明字段,不覆盖/不改名任何冻结字段)。
    """
    n = len(pairs)
    vals = np.array([r for _, r in pairs], dtype=float)
    too_small = n < MIN_N_CI

    if n == 0:
        mean_pct = median_pct = up_pct = None
    else:
        mean_pct = round(float(vals.mean()) * 100, 2)
        median_pct = round(float(np.median(vals)) * 100, 2)
        up_pct = round(float((vals > 0).mean()) * 100, 2)

    base_mean_pct = round(base_mean * 100, 2) if base_mean == base_mean else None   # NaN-safe
    base_up_pct = round(base_up * 100, 2) if base_up == base_up else None
    diff_mean = (round(mean_pct - base_mean_pct, 2)
                 if (mean_pct is not None and base_mean_pct is not None) else None)

    boot = None
    if n > 0 and not too_small:
        boot = event_bootstrap(vals, base_mean, seed=seed)
    ci95_mean = boot["ci95_mean"] if boot else None
    ci95_up = boot["ci95_up"] if boot else None
    ci95_diff = boot["ci95_diff"] if boot else None

    groups = {}
    for y, r in pairs:
        groups.setdefault(y, []).append(r)
    full_mean = float(vals.mean()) if n > 0 else None
    loco = loco_analysis(groups, full_mean, seed=seed)

    era1 = [r for y, r in pairs if y <= 2009]
    era2 = [r for y, r in pairs if y >= 2010]
    era1_mean_pct = round(float(np.mean(era1)) * 100, 2) if era1 else None
    era2_mean_pct = round(float(np.mean(era2)) * 100, 2) if era2 else None
    era_same_sign = None
    if era1 and era2:
        era_same_sign = bool(np.sign(era1_mean_pct) == np.sign(era2_mean_pct))

    verdict = verdict_for_cell(too_small, loco["loco_sign_stable"])

    return {
        "n_events": n,
        "up_pct": up_pct,
        "mean_pct": mean_pct,
        "median_pct": median_pct,
        "base_up_pct": base_up_pct,
        "base_mean_pct": base_mean_pct,
        "diff_mean": diff_mean,
        "ci95_mean": ci95_mean,
        "ci95_up": ci95_up,
        "ci95_diff": ci95_diff,
        "too_small_no_ci": too_small,
        "loco_headline_mean": loco["loco_headline_mean"],
        "loco_sign_stable": loco["loco_sign_stable"],
        "loco_most_influential_crisis_year": loco["loco_most_influential_crisis_year"],
        "era1_mean_pct": era1_mean_pct,
        "era2_mean_pct": era2_mean_pct,
        "era_same_sign": era_same_sign,
        "verdict": verdict,
    }


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run(write=True, _vix=None, _prices=None):
    """跑全量分析,返回 payload dict(= 写入 fear_extremes.json 的内容)。

    _vix / _prices 可注入合成数据(测试用,§7 "合成/固定不碰网络")。
    _prices: dict[index_name -> pd.Series](价格水平,已 sort_index/dropna)。
    """
    vix = _vix if _vix is not None else _load_vix()
    prices = _prices if _prices is not None else {
        name: _load_price(stem) for name, stem in PRICE_FILES.items()
    }
    # 限定到 VIX 覆盖窗口起点(2000+),避免更早历史悄悄混进"全样本基率"参照系(§0 数据 2000+)。
    start = vix.index.min()
    prices = {k: v[v.index >= start] for k, v in prices.items()}

    fwd = {idx: {h: forward_returns(s, h) for h in HORIZONS} for idx, s in prices.items()}

    base_stats = {}
    for idx in prices:
        base_stats[idx] = {}
        for h in HORIZONS:
            vals = fwd[idx][h].dropna().values.astype(float)
            base_stats[idx][h] = {
                "mean": float(vals.mean()) if len(vals) else float("nan"),
                "up": float((vals > 0).mean()) if len(vals) else float("nan"),
                "n": int(len(vals)),
            }

    triggers_out = {}
    for tname, meta in TRIGGERS.items():
        ev_dates = detect_events(vix, tname)

        events_out = []
        collected = {idx: {h: [] for h in HORIZONS} for idx in prices}   # idx -> h -> list[(year,ret)]
        for d in ev_dates:
            cy = int(d.year)
            rec = {"date": d.strftime("%Y-%m-%d"), "crisis_year": cy}
            for idx, s in prices.items():
                pos = int(s.index.searchsorted(d, side="right"))
                per_h = {}
                valid_entry = pos < len(s.index)
                for h in HORIZONS:
                    r = fwd[idx][h].iloc[pos] if valid_entry else np.nan
                    if pd.isna(r):
                        per_h[str(h)] = None
                    else:
                        per_h[str(h)] = round(float(r) * 100, 3)
                        collected[idx][h].append((cy, float(r)))
                rec[idx] = per_h
            events_out.append(rec)

        by_index = {}
        for idx in prices:
            by_index[idx] = {}
            for h in HORIZONS:
                pairs = collected[idx][h]
                base = base_stats[idx][h]
                seed = _seed_for(tname, idx, h)
                by_index[idx][str(h)] = build_cell(pairs, base["mean"], base["up"], seed)

        n_crisis_years = len({d.year for d in ev_dates})
        triggers_out[tname] = {
            **meta,
            "n_events": len(ev_dates),
            "n_crisis_years": n_crisis_years,
            "events": events_out,
            "by_index": by_index,
        }

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": vix.index.max().strftime("%Y-%m-%d"),
        "vix_start": vix.index.min().strftime("%Y-%m-%d"),
        "reset_floor": RESET_FLOOR,
        "min_n_ci": MIN_N_CI,
        "primary_cell": dict(PRIMARY_CELL),
        "triggers": triggers_out,
        "honesty": HONESTY,
        "vxsmh_note": VXSMH_NOTE,
    }

    if write:
        written = write_json("fear_extremes.json", out, allow_nan=False)
        for d in written:
            print(f"  Written: {d}/fear_extremes.json")

    return out


if __name__ == "__main__":
    result = run(write=True)
    print("\n=== 高/极端恐慌事件研究(纯描述) ===")
    print(f"  VIX 起点: {result['vix_start']}   数据至: {result['as_of']}")
    for tname, tblock in result["triggers"].items():
        print(f"\n  [{tname}] {tblock['label_zh']} ({tblock['definition_zh']})"
              f" — n_events={tblock['n_events']}  危机年数={tblock['n_crisis_years']}")
        for idx, horizons in tblock["by_index"].items():
            for h, cell in horizons.items():
                tag = "  <<< PRIMARY" if (tname == PRIMARY_CELL["trigger"] and idx == PRIMARY_CELL["index"]
                                            and int(h) == PRIMARY_CELL["horizon"]) else ""
                print(f"    {idx:>7} {h:>3}d: N={cell['n_events']:>3} "
                      f"mean={cell['mean_pct']}%  up={cell['up_pct']}%  "
                      f"base_mean={cell['base_mean_pct']}%  "
                      f"CI_mean={cell['ci95_mean']}  "
                      f"LOCO_headline={cell['loco_headline_mean']}%  "
                      f"verdict={cell['verdict']}{tag}")
    print(f"\nprimary_cell = {result['primary_cell']}")
