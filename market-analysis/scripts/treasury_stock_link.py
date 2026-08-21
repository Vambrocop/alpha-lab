"""treasury_stock_link.py — 10Y 收益率「连续水平 × 20日涨跌方向」→ 美股前向收益(纯描述·填现有空白)

现有三脚本各自覆盖了什么、本脚本填的空白是什么(先查后动,不重造轮子):
  - regime_forward.py:只做「T10Y2Y **二元**倒挂(<0)」这一种体制 → SP500 未来 1/3/6/12 月收益分布。
    不看收益率的连续水平,也不看收益率涨跌方向,只看 SP500,不看 NASDAQ。
  - market_regime.py:把「收益率曲线现在倒挂/正常」纳入「当前风险体制」的**描述**(现值+历史分位),
    从不算「给定收益率状态 → 未来股票收益分布」——它只回答"现在什么环境",不回答"这种环境后市场怎么走"。
  - factor_model.py:用 FED_RATE(联储基准利率,不是 10Y 收益率本身)做月度特征相关/PCA/模型输入,
    是"利率作为众多特征之一喂给分类模型",不是"10Y 收益率水平/方向 → 前向收益分布"的直接描述表。
  → 三者都没做的:【10Y 收益率本身的"连续水平(低/中/高档)"以及"20交易日涨跌方向(降/平/升档)"】
    分别对 NASDAQ 和 SP500(现有只 SP500)前向收益的关系。本脚本填这块空白。

方法论与既有描述性研究同源(dip_hold_study.py / fear_greed.py):去重叠段级自助 CI、基率对照、
分时代稳健性检查,直接复用 stats_util.forward_returns + dip_hold_study.cluster_bootstrap /
dip_hold_study._merge_within_horizon(单一实现,不重写)。

【口径判断,工程非统计,已披露供审查】不用 YIELD_10Y、改用 TNX 代理:
combined_prices.csv 里 YIELD_10Y(FRED GS10)是月频序列(全样本仅 341 点,最大缺口 151 天≈100 交易日)——
拿它算"20 交易日变化"会被巨大的月度阶梯 ffill 假象污染。TNX(CBOE 10 年期收益率指数)是日频
(全样本 6681 点,2000-01-03 起,与 NASDAQ/SP500 同起点),与 YIELD_10Y 在两者共有的月度对齐点上
相关系数 0.993(几乎同一量、同为百分比单位)。故本研究用 TNX 作连续日频 10Y 收益率代理。

【重要:按列取数,不对宽表整表 dropna】——已修过的 bug:对 combined_prices.csv 整表 .dropna() 会
因某一列(如 BTC/ETH 早期无数据)整列 NaN 而连坐删光其它列的历史。本脚本每个序列都用
pd.to_numeric(df[col], errors="coerce").dropna() 单独取,参考 analyze.py:29 / fear_greed._series。

纯描述,不产出买卖信号/edge/预测。相关≠因果、体制样本少、过去≠未来、会错。不改任何 append-only 账本、
不碰其它脚本逻辑。
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
from dip_hold_study import cluster_bootstrap, _merge_within_horizon  # 单一实现,复用不重写

RAW_DIR = _SCRIPTS.parent / "data" / "raw"

# ══════════════════════════════════════════════════════════════════
# 冻结常量
# ══════════════════════════════════════════════════════════════════
YIELD_COL = "TNX"                 # 见模块 docstring:不用 YIELD_10Y(月频·最大缺口151天)
HORIZONS = [20, 60, 252]          # 前向窗口:20≈1月/60≈3月/252≈12月(用户指定口径,frozen)
HORIZON_LABELS = {20: "1月", 60: "3月", 252: "12月"}
CHANGE_WINDOW = 20                # "20交易日涨跌方向"的窗口(用户指定,frozen)
ASSETS = ["NASDAQ", "SP500"]
MIN_INDEPENDENT = 8               # 独立段 < 8 → described-only 无 CI(与 dip_hold_study/fear_greed 同一门槛)
B_BOOT = 2000
SEED_BASE = 20260822              # 固定种子(=本脚本定稿日,供可复现;同 dip_hold_study 惯例)
ERA_SPLIT_YEAR = 2013             # 分时代口径:<=2012 / >=2013(与 dip_hold_study 同一切法)

LEVEL_ORDER = ["low", "mid", "high"]
DIR_ORDER = ["falling", "flat", "rising"]

YIELD_PROXY_NOTE = (
    "combined_prices.csv 里 YIELD_10Y(FRED GS10)是月频序列(全样本仅341点,最大缺口151天≈100交易日)——"
    "拿它算「20交易日变化」会被巨大的月度阶梯 ffill 假象污染(21个交易日的窗口里可能0次真实更新或1次跳变)。"
    "TNX(CBOE 10年期收益率指数)是日频(全样本6681点,2000-01-03起),与 YIELD_10Y 在两者共有的对齐点上"
    "相关系数0.993(几乎同一量,同为百分比单位),故本研究用 TNX 作连续日频10Y收益率代理,YIELD_10Y 仅供交叉核对。"
    "这是工程口径选择,不是统计判断——如果换回 YIELD_10Y,「20日变化」的含义会退化成「距上次月度更新以来变化」。"
)

HONESTY = [
    "纯描述·非预测非荐股:本表只描述历史上 10Y 收益率(TNX 代理)所处「水平档位」和「20日涨跌方向档位」"
    "之后,NASDAQ/SP500 前向收益的分布——不产出买卖信号、不给操作建议、不预测方向。",
    "口径:" + YIELD_PROXY_NOTE,
    "分档切点用全样本(见 date_range)三分位算出——是回顾性描述切割,不是当时【已知】的实时信号,"
    "不能拿来当「历史上某一天就知道自己在哪个三分位」的可交易规则。",
    "基率是诚实参照系:市场本身大概率随时间上涨,某档要「有料」必须可靠偏离「随便哪天买」的基率,不是绝对涨跌。",
    "重叠窗口让 N 虚高:同一档常连续持续数月,逐日计数会把同一段行情重复计成几十上百个「样本」。"
    "本表报 n_independent(前向窗口互不重叠的独立聚类数,复用 dip_hold_study._merge_within_horizon),"
    f"独立聚类 < {MIN_INDEPENDENT} 一律 described-only、不出置信区间;CI 用段级自助(dip_hold_study.cluster_bootstrap)。",
    "相关≠因果:利率与股票同被增长/通胀/联储政策等第三因素驱动,不代表利率变化「导致」股票涨跌。",
    "样本可能被一两次事件主导(如2022年联储激进加息周期):附带各档独立段列表(episodes,含起止日/天数),"
    "供人工核对某档是否只是同一场加息周期反复计数,而非多次独立发生的规律。",
    "分时代(2000-2012 / 2013-今)若符号翻转,说明结论体制依赖、不稳健——已如实标 era_same_sign,翻转的桶汇总进 diagnostics.era_flips。",
    "桶间关系若非单调(如中档比高低档都好/差),不代表「水平越高影响越强」这类单调直觉成立——已如实标 diagnostics.monotonic。",
    "数据覆盖 2000 年至今;过去 ≠ 未来,会出错,过去表现不代表未来结果。",
]


# ══════════════════════════════════════════════════════════════════
# 数据加载(按列取数,不对宽表整表 dropna)
# ══════════════════════════════════════════════════════════════════
def _load_combined(_df=None):
    if _df is not None:
        return _df
    return pd.read_csv(RAW_DIR / "combined_prices.csv", index_col=0, parse_dates=True)


def _series(df, col):
    """单列独立取数+排序,不受宽表其它列(哪怕整列 NaN)连坐影响。"""
    return pd.to_numeric(df[col], errors="coerce").dropna().sort_index()


# ══════════════════════════════════════════════════════════════════
# 分档(三分位·与用户指定方法一致;水平/方向用同一套切法,不为方向另挑任意 bp 阈值)
# ══════════════════════════════════════════════════════════════════
def _tercile_cutoffs(values):
    q1, q2 = np.percentile(np.asarray(values, float), [100.0 / 3, 200.0 / 3])
    return float(q1), float(q2)


def level_buckets(level):
    """全样本三分位切点 → 低/中/高档。返回 (bucket_series, (q1,q2))。"""
    q1, q2 = _tercile_cutoffs(level.values)

    def _b(x):
        if x <= q1:
            return "low"
        if x <= q2:
            return "mid"
        return "high"

    return level.apply(_b), (round(q1, 2), round(q2, 2))


def change_buckets(level, window=CHANGE_WINDOW):
    """window 交易日变化(百分点)→ 三分位切成降/平/升档(与水平档同一方法,避免任意选 bp 阈值)。
    返回 (bucket_series, chg_series, (q1,q2))。"""
    chg = level.diff(window).dropna()
    q1, q2 = _tercile_cutoffs(chg.values)

    def _b(x):
        if x <= q1:
            return "falling"
        if x <= q2:
            return "flat"
        return "rising"

    return chg.apply(_b), chg, (round(q1, 4), round(q2, 4))


def _bucket_episodes(bucket_series, target):
    """该桶所有【连续同值】区段(list[list[Timestamp]])。桶是离散三分位标签,没有阈值突破/回撤那种
    「迟滞恢复」概念,故直接按连续同值分段;边界抖动产生的短段会在 _merge_within_horizon(相隔 < 前向
    窗口即合并)时被吸收,不会虚增独立样本(与 dip_hold_study/fear_greed 同一防伪思路,简化版)。
    """
    episodes, cur = [], None
    for date, b in bucket_series.items():
        if b == target:
            if cur is None:
                cur = [date]
            else:
                cur.append(date)
        else:
            if cur is not None:
                episodes.append(cur)
            cur = None
    if cur is not None:
        episodes.append(cur)
    return episodes


def episodes_display(episodes, limit=60):
    """每段 {start, end, days}(供人工核对是否被一两次事件主导)。"""
    out = []
    for seg in episodes[:limit]:
        out.append({"start": seg[0].strftime("%Y-%m-%d"), "end": seg[-1].strftime("%Y-%m-%d"), "days": len(seg)})
    return out


# ══════════════════════════════════════════════════════════════════
# 日级统计(供桶 + 基率共用同一实现)
# ══════════════════════════════════════════════════════════════════
def _day_stats(returns):
    r = returns.dropna()
    if not len(r):
        return None
    vals = r.values.astype(float)
    return {
        "n_days": int(len(vals)),
        "up_pct": round(float((vals > 0).mean()) * 100, 2),
        "mean_pct": round(float(vals.mean()) * 100, 2),
        "median_pct": round(float(np.median(vals)) * 100, 2),
        "p10_pct": round(float(np.percentile(vals, 10)) * 100, 2),
    }


def _seed_for(*parts):
    # 确定性种子:zlib.crc32(跨进程稳定),不用内置 hash()(按 PYTHONHASHSEED 加盐、每进程抖动)。
    # 同 dip_hold_study._seed_for / fear_greed._seed_for 的修法。
    s = "|".join(str(p) for p in parts)
    return SEED_BASE + zlib.crc32(s.encode("utf-8")) % 1_000_000


# ══════════════════════════════════════════════════════════════════
# 单个(资产×变量×桶×窗口)cell
# ══════════════════════════════════════════════════════════════════
def build_cell(asset, variable, bucket, label, episodes, fwd_h, pos_of, base_stats, horizon):
    all_dates = [d for seg in episodes for d in seg]
    day_ret = fwd_h.reindex(all_dates).dropna()
    stats = _day_stats(day_ret)

    n_episodes_raw = sum(1 for seg in episodes if len(fwd_h.reindex(seg).dropna()))

    clusters = _merge_within_horizon(episodes, pos_of, horizon)
    ep_rets = []
    for cl in clusters:
        r = fwd_h.reindex(cl).dropna()
        if len(r):
            ep_rets.append(r.values.astype(float))
    n_independent = len(ep_rets)
    too_small = n_independent < MIN_INDEPENDENT

    diff_mean = None
    if stats and base_stats:
        diff_mean = round(stats["mean_pct"] - base_stats["mean_pct"], 2)

    ci = None
    ci_vs_base = None
    if not too_small and stats:
        ci = cluster_bootstrap(ep_rets, seed=_seed_for(asset, variable, bucket, horizon), B=B_BOOT)
        if base_stats:
            if ci[0] > base_stats["mean_pct"]:
                ci_vs_base = "above_base"
            elif ci[1] < base_stats["mean_pct"]:
                ci_vs_base = "below_base"
            else:
                ci_vs_base = "overlaps_base"

    qual = pd.DatetimeIndex(sorted(all_dates))

    def _era(cond):
        sel = qual[cond(qual.year)]
        r = fwd_h.reindex(sel).dropna()
        if not len(r):
            return None, None
        return round(float((r > 0).mean()) * 100, 2), round(float(r.mean()) * 100, 2)

    era1_up, era1_mean = _era(lambda y: y <= ERA_SPLIT_YEAR - 1)
    era2_up, era2_mean = _era(lambda y: y >= ERA_SPLIT_YEAR)
    era_same_sign = None
    if era1_mean is not None and era2_mean is not None:
        era_same_sign = bool(np.sign(era1_mean) == np.sign(era2_mean))

    return {
        "asset": asset, "variable": variable, "bucket": bucket, "label": label, "horizon": horizon,
        "n_days": stats["n_days"] if stats else 0,
        "n_episodes_raw": n_episodes_raw,
        "n_independent": n_independent,
        "too_small_no_ci": too_small,
        "up_pct": stats["up_pct"] if stats else None,
        "mean_pct": stats["mean_pct"] if stats else None,
        "median_pct": stats["median_pct"] if stats else None,
        "p10_pct": stats["p10_pct"] if stats else None,
        "base_up_pct": base_stats["up_pct"] if base_stats else None,
        "base_mean_pct": base_stats["mean_pct"] if base_stats else None,
        "base_median_pct": base_stats["median_pct"] if base_stats else None,
        "base_p10_pct": base_stats["p10_pct"] if base_stats else None,
        "diff_mean": diff_mean,
        "ci95_mean": ci,
        "ci_vs_base": ci_vs_base,
        "era1_up_pct": era1_up, "era1_mean_pct": era1_mean,
        "era2_up_pct": era2_up, "era2_mean_pct": era2_mean,
        "era_same_sign": era_same_sign,
    }


def _monotonic(order_keys, cells_by_bucket):
    """三档 mean_pct 是否严格单调(升或降);任一档缺失 → None。"""
    means = [cells_by_bucket[k]["mean_pct"] for k in order_keys]
    if any(m is None for m in means):
        return None
    a, b, c = means
    return bool(a < b < c or a > b > c)


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run(write=True, _df=None):
    df = _load_combined(_df)
    level = _series(df, YIELD_COL)
    lvl_bucket, level_cutoffs = level_buckets(level)
    dir_bucket, chg, chg_cutoffs = change_buckets(level)

    date_range = [str(level.index.min().date()), str(level.index.max().date())]

    level_labels = {
        "low": f"低档(TNX≤{level_cutoffs[0]}%)",
        "mid": f"中档({level_cutoffs[0]}%<TNX≤{level_cutoffs[1]}%)",
        "high": f"高档(TNX>{level_cutoffs[1]}%)",
    }
    chg_bp = (round(chg_cutoffs[0] * 100, 1), round(chg_cutoffs[1] * 100, 1))
    dir_labels = {
        "falling": f"降档(20日变化≤{chg_bp[0]}bp)",
        "flat": f"平档({chg_bp[0]}~{chg_bp[1]}bp)",
        "rising": f"升档(20日变化>{chg_bp[1]}bp)",
    }

    assets_out = {}
    diagnostics = {"monotonic": [], "era_flips": [], "low_independent": []}

    for asset in ASSETS:
        px = _series(df, asset)
        fwd = {h: forward_returns(px, h) for h in HORIZONS}
        idx = px.index
        pos_of = {d: i for i, d in enumerate(idx)}

        lvl_al = lvl_bucket.reindex(idx).ffill(limit=5)
        dir_al = dir_bucket.reindex(idx).ffill(limit=5)

        base = {h: _day_stats(fwd[h]) for h in HORIZONS}

        lvl_episodes = {b: _bucket_episodes(lvl_al, b) for b in LEVEL_ORDER}
        dir_episodes = {b: _bucket_episodes(dir_al, b) for b in DIR_ORDER}

        level_cells, dir_cells = [], []
        for h in HORIZONS:
            by_bucket_lvl = {}
            for b in LEVEL_ORDER:
                cell = build_cell(asset, "level", b, level_labels[b], lvl_episodes[b], fwd[h], pos_of, base[h], h)
                level_cells.append(cell)
                by_bucket_lvl[b] = cell
                if cell["too_small_no_ci"]:
                    diagnostics["low_independent"].append({
                        "asset": asset, "variable": "level", "bucket": b, "horizon": h,
                        "n_independent": cell["n_independent"],
                    })
                if cell["era_same_sign"] is False:
                    diagnostics["era_flips"].append({
                        "asset": asset, "variable": "level", "bucket": b, "horizon": h,
                        "era1_mean_pct": cell["era1_mean_pct"], "era2_mean_pct": cell["era2_mean_pct"],
                    })
            mono = _monotonic(LEVEL_ORDER, by_bucket_lvl)
            diagnostics["monotonic"].append({
                "asset": asset, "variable": "level", "horizon": h, "monotonic": mono,
                "means_pct": [by_bucket_lvl[b]["mean_pct"] for b in LEVEL_ORDER],
            })

            by_bucket_dir = {}
            for b in DIR_ORDER:
                cell = build_cell(asset, "direction", b, dir_labels[b], dir_episodes[b], fwd[h], pos_of, base[h], h)
                dir_cells.append(cell)
                by_bucket_dir[b] = cell
                if cell["too_small_no_ci"]:
                    diagnostics["low_independent"].append({
                        "asset": asset, "variable": "direction", "bucket": b, "horizon": h,
                        "n_independent": cell["n_independent"],
                    })
                if cell["era_same_sign"] is False:
                    diagnostics["era_flips"].append({
                        "asset": asset, "variable": "direction", "bucket": b, "horizon": h,
                        "era1_mean_pct": cell["era1_mean_pct"], "era2_mean_pct": cell["era2_mean_pct"],
                    })
            mono = _monotonic(DIR_ORDER, by_bucket_dir)
            diagnostics["monotonic"].append({
                "asset": asset, "variable": "direction", "horizon": h, "monotonic": mono,
                "means_pct": [by_bucket_dir[b]["mean_pct"] for b in DIR_ORDER],
            })

        assets_out[asset] = {
            "date_range": [str(idx.min().date()), str(idx.max().date())],
            "base": {str(h): base[h] for h in HORIZONS},
            "level": level_cells,
            "direction": dir_cells,
            "level_episodes": {b: episodes_display(lvl_episodes[b]) for b in LEVEL_ORDER},
            "direction_episodes": {b: episodes_display(dir_episodes[b]) for b in DIR_ORDER},
        }

    non_monotonic_n = sum(1 for m in diagnostics["monotonic"] if m["monotonic"] is False)
    era_flip_n = len(diagnostics["era_flips"])
    low_indep_n = len(diagnostics["low_independent"])

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": date_range,
        "yield_proxy": YIELD_COL,
        "yield_proxy_note": YIELD_PROXY_NOTE,
        "horizons_td": HORIZONS,
        "horizon_labels": {str(h): HORIZON_LABELS[h] for h in HORIZONS},
        "change_window_td": CHANGE_WINDOW,
        "level_cutoffs_pct": list(level_cutoffs),
        "change_cutoffs_bp": list(chg_bp),
        "min_independent": MIN_INDEPENDENT,
        "era_split_year": ERA_SPLIT_YEAR,
        "assets": assets_out,
        "diagnostics": diagnostics,
        "diagnostics_summary": (
            f"{non_monotonic_n}/{len(diagnostics['monotonic'])} 组(资产×变量×窗口)桶间关系非单调;"
            f"{era_flip_n} 个桶分时代符号翻转;{low_indep_n} 个桶独立段 < {MIN_INDEPENDENT}(只描述、不出CI)。"
        ),
        "honesty": HONESTY,
    }

    if write:
        for d in write_json("treasury_stock_link.json", out, allow_nan=False):
            print(f"  Written: {d}/treasury_stock_link.json")
    return out


def _main():
    r = run(write=True)
    print("\n=== 10Y 收益率水平/涨跌方向 → 美股前向收益(纯描述) ===")
    print(f"  收益率代理: {r['yield_proxy']}  覆盖 {r['date_range'][0]} ~ {r['date_range'][1]}")
    print(f"  水平三分位切点: {r['level_cutoffs_pct']}%   20日变化三分位切点: {r['change_cutoffs_bp']}bp")
    for asset, a in r["assets"].items():
        print(f"\n  --- {asset} ---")
        for h in r["horizons_td"]:
            b = a["base"][str(h)]
            print(f"    基率 {h}日: up {b['up_pct']}%  mean {b['mean_pct']}%  中位 {b['median_pct']}%  p10 {b['p10_pct']}%  N={b['n_days']}")
        print("    水平档:")
        for c in a["level"]:
            print(f"      {c['label']:<26} /{c['horizon']:>3}d: up {c['up_pct']}  mean {c['mean_pct']}  vs base {c['diff_mean']}  "
                  f"n_indep={c['n_independent']}  CI={c['ci95_mean']}  era_same_sign={c['era_same_sign']}")
        print("    方向档:")
        for c in a["direction"]:
            print(f"      {c['label']:<26} /{c['horizon']:>3}d: up {c['up_pct']}  mean {c['mean_pct']}  vs base {c['diff_mean']}  "
                  f"n_indep={c['n_independent']}  CI={c['ci95_mean']}  era_same_sign={c['era_same_sign']}")
    print(f"\n  {r['diagnostics_summary']}")


if __name__ == "__main__":
    # 顶层 fail-soft:一旦接进流水线,读 combined_prices/统计边缘的意外异常不该杀掉整条 refresh
    # (描述性研究·非质量门)。与 au_dip_hold_study/event_causal 同款兜底。
    try:
        _main()
    except Exception as e:
        print(f"[美债→美股前向] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        raise SystemExit(0)
