"""fear_greed.py — 恐慌贪婪合成表 + 逆向情绪检验(纯描述)

严格实现 docs_internal/SPEC_FEAR_GREED.md。**纯描述,不产出买卖/择时信号,不设晋升**——
① 用仓库能算的 ~3-4 个分量合成一个 0-100「恐慌贪婪」当前读数(明标是 CNN 7 分量指数的近似);
② 老实检验民间「别人贪婪我恐惧」——极度贪婪/恐慌之后前向收益是否真的可靠偏离基率。

命门(§0):
  - 纯描述·无晋升:永不输出买卖/edge/择时信号,逆向检验只出「历史上各情绪档之后市场怎么走」+ 基率 + 稳健性。
  - 是近似,不是 CNN 原版:CNN 用 7 个分量,本表只有 ~3-4 个(动量/波动反向/期限结构/避险),
    合成值只作粗略情绪温度,前端须显眼标「近似·非 CNN 官方值」。
  - 逆向情绪择时出了名地弱:极度贪婪/恐慌的独立段本就少(去聚集后十几段量级),多数档必然 described-only。
    重叠日让 N 虚高 → 报 n_days 与 n_stretches(独立段),CI 用聚类自助;独立段 < MIN_STRETCHES_CI 一律 described-only。
  - 基率是诚实参照系:市场本来大概率涨,逆向档要「有料」必须可靠偏离基率(不是绝对涨跌)。
  - 过去 ≠ 未来、会错、非投资建议。
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
from dip_hold_study import cluster_bootstrap  # 段级(整块)聚类自助 CI——单一实现,复用不重写

RAW_DIR = _SCRIPTS.parent / "data" / "raw"

# ══════════════════════════════════════════════════════════════════
# 冻结常量(§5 — 不可调,任何"看着显著就改"的冲动 → 停,见 spec §7)
# ══════════════════════════════════════════════════════════════════
SMA_WIN = 125            # 动量分量:SP500 相对 125 日均线(frozen §1.1)
VIX_PCT_WIN = 252        # 波动分量:VIX 过去 252 日分位(frozen §1.2)
RA_WIN = 20              # 避险分量:SP500/GOLD 20 日收益差(frozen §1.4)
HORIZONS = [20, 60]      # 逆向检验前向窗口(frozen §3)
BAND_EDGES = [25, 45, 55, 75]              # 档位边界(frozen §1)
MIN_STRETCHES_CI = 8     # 独立段 < 8 → described-only 无 CI(frozen §3)
B_BOOT = 2000
SEED_BASE = 20260805     # 固定种子(=spec 定稿日)供可复现

BANDS = ("extreme_fear", "fear", "neutral", "greed", "extreme_greed")   # 五档,顺序=从恐慌到贪婪(frozen §1)

COMPONENTS_META = {
    "momentum": {
        "label_zh": "动量", "label_en": "Momentum",
        "definition_zh": "SP500 相对 125 日均线偏离(+10%→100,−10%→0)",
        "definition_en": "SP500 vs its 125-day moving average (+10% -> 100, -10% -> 0)",
    },
    "volatility": {
        "label_zh": "波动(反向)", "label_en": "Volatility (inverted)",
        "definition_zh": "VIX 在过去 252 日中的分位(越低越贪婪)",
        "definition_en": "VIX's percentile over the trailing 252 days (lower VIX = greedier)",
    },
    "term_structure": {
        "label_zh": "期限结构", "label_en": "Term structure",
        "definition_zh": "VIX3M − VIX(contango 正=贪婪;仅 VIX3M 可得日,2006-07 起)",
        "definition_en": "VIX3M minus VIX (positive/contango = greedy; only on days VIX3M exists, from 2006-07)",
    },
    "risk_appetite": {
        "label_zh": "避险", "label_en": "Risk appetite",
        "definition_zh": "SP500 20 日收益 − 黄金 20 日收益(仅 GOLD 可得日)",
        "definition_en": "SP500 20-day return minus gold's 20-day return (only on days GOLD data exists)",
    },
}
COMPONENT_NAMES = list(COMPONENTS_META.keys())

HONESTY = [
    "纯描述·无晋升:本表不产出「买入/卖出信号」,逆向检验只描述历史上各情绪档之后市场的前向表现——"
    "明确非信号、非荐股、非投资建议。想把它读成「贪婪就卖/恐慌就买」是误读。",
    "近似·非 CNN 官方值:CNN 恐慌贪婪指数用 7 个分量(动量/强度/广度/看跌看涨/波动/避险/垃圾债),"
    "本仓库数据只够算出 ~3-4 个(动量/波动反向/期限结构/避险),合成值只是粗略情绪温度计,不是 CNN 官方读数,"
    "不可与 CNN 网站数字直接对比。",
    "重叠日让 N 虚高:同一档情绪常常连续持续数周甚至数月,逐日计数会把同一段情绪重复计成几十上百个「样本」。"
    "本表用去聚集报独立段数(不是交易日数 n_days),且做了两道:①【迟滞重置】——合成读数在边界(如 75)"
    "日内抖动时不算新段,一段贪婪/恐慌体制只有在读数回到中性或翻到对侧后再次进入该档才算新段,免得同一体制每抖一下"
    "就假装多一个独立样本;②【前向窗口去重叠】——就算两段真正分开,若相隔不足前向窗口天数、其未来收益窗口仍重叠、"
    "共享同一段行情,则并为一个 CI 聚类(报 n_independent)。置信区间用这些互不重叠的聚类做段级自助"
    f"(复用 dip_hold_study.cluster_bootstrap),独立聚类 < {MIN_STRETCHES_CI} 一律 described-only、不出 CI。"
    "即便如此,极度档的独立聚类仍只有十来个量级,数字好看也别当定论。",
    "基率是诚实参照系:市场本来大概率涨,逆向档要算「有料」必须可靠偏离「随便哪天买」的基率"
    "(CI 整段落在基率一侧),不是「涨了就叫赢」。",
    "分量历史长短不一:动量/波动分量从 2000 年附近就有;期限结构(VIX3M)要到 2006-07 才有数据、"
    "避险(GOLD)从 2000-08 才有——早期读数样本更小,合成值只在当日≥2 个分量可得时才输出,"
    "复合读数(composite)整体从两个最早分量都齐备时才开始。",
    "数据仅覆盖 2000 年至今(combined_prices.csv);历史规律 ≠ 未来保证,会出错,过去表现不代表未来结果。",
]

# verdict 三态,均不含 signal/buy/sell/edge 词根(§3 命门·硬保证)。
# (spec 初稿曾用 "no-contrarian-edge",含"edge"词根、与本命门自相矛盾——建造者如实标出、未擅改;
#  作为 spec 作者已改名为 "not-contrarian",spec §3 同步更新。)
ALLOWED_VERDICTS = ("described-only", "contrarian-holds", "not-contrarian")


# ══════════════════════════════════════════════════════════════════
# 数据加载
# ══════════════════════════════════════════════════════════════════
def _load_combined(_df=None):
    if _df is not None:
        return _df
    return pd.read_csv(RAW_DIR / "combined_prices.csv", index_col=0, parse_dates=True)


def _series(df, col):
    """combined_prices.csv 含周末/假日的日历行(NaN)——各分量按自己实际可得的交易日算(§1),
    故各自 dropna 后独立排序,而不是共享一份"缺行即 NaN"的日历(那会让 rolling(window=N) 的
    N 行窗口混进大量周末 NaN,永远凑不满 min_periods)。列间对齐靠 pandas 按 index 自动做(下方各分量)。
    """
    return pd.to_numeric(df[col], errors="coerce").dropna().sort_index()


# ══════════════════════════════════════════════════════════════════
# 分量子分(§1 — 各自纯函数,标量/Series 皆可,供直接单测)
# ══════════════════════════════════════════════════════════════════
def sub_momentum(m):
    """m = SP500/SMA125 − 1(fraction)。+10%→100,−10%→0,0→50。"""
    return np.clip(50 + m * 500, 0, 100)


def sub_volatility(p):
    """p = VIX 过去 252 日分位(fraction 0..1,含当日)。p=0→100(最低分位=最贪婪),p=1→0。"""
    return np.clip((1 - p) * 100, 0, 100)


def sub_term_structure(ts):
    """ts = VIX3M − VIX(points)。contango 正=贪婪。"""
    return np.clip(50 + ts * 10, 0, 100)


def sub_risk_appetite(ra):
    """ra = SP500 20 日收益 − GOLD 20 日收益(fraction)。"""
    return np.clip(50 + ra * 500, 0, 100)


def _rolling_percentile(s, win):
    """s 在过去 win 个自身交易日(含当日)中的分位(fraction 0..1) = 窗内 ≤ 当日值 的比例。"""
    return s.rolling(win, min_periods=win).apply(lambda x: (x <= x[-1]).mean(), raw=True)


def band_for(x):
    """档位(§1,frozen 边界 BAND_EDGES=[25,45,55,75])。边界值归属(本实现明确选择,非研究判断):
    x<=25→extreme_fear;25<x<=45→fear;45<x<=55→neutral;55<x<75→greed;x>=75→extreme_greed。
    None/NaN → None(无 composite 当日不出档位)。
    """
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    if x <= 25:
        return "extreme_fear"
    if x <= 45:
        return "fear"
    if x <= 55:
        return "neutral"
    if x < 75:
        return "greed"
    return "extreme_greed"


# ══════════════════════════════════════════════════════════════════
# 合成(§1 — composite = 可得子分算术平均,要求 ≥2 个可得)
# ══════════════════════════════════════════════════════════════════
def composite_series(subs_df):
    """subs_df: columns=COMPONENT_NAMES 的子分 DataFrame(各列各自 NaN 表示当日不可得)。
    返回 composite Series(1 位小数;可得子分 <2 的日为 NaN)。
    """
    n_avail = subs_df.notna().sum(axis=1)
    comp = subs_df.mean(axis=1, skipna=True)
    comp = comp.where(n_avail >= 2)
    return comp.round(1)


def build_subscores(sp500, vix, vix3m, gold):
    """各分量各自在其"可得的交易日"上算(§1),用 pandas 按 index 自动对齐(不同分量日历不同)。"""
    sma125 = sp500.rolling(SMA_WIN, min_periods=SMA_WIN).mean()
    m = sp500 / sma125 - 1.0
    s_mom = sub_momentum(m).dropna()

    p = _rolling_percentile(vix, VIX_PCT_WIN)
    s_vol = sub_volatility(p).dropna()

    ts = vix3m - vix   # pandas 按 index 自动对齐(vix3m 从 2006-07 起才有值)
    s_ts = sub_term_structure(ts).dropna()

    sp_ret20 = sp500.pct_change(RA_WIN)
    gold_ret20 = gold.pct_change(RA_WIN)
    ra = sp_ret20 - gold_ret20   # 同上按 index 自动对齐(gold 从 2000-08 起才有值)
    s_ra = sub_risk_appetite(ra).dropna()

    subs = pd.concat(
        {"momentum": s_mom, "volatility": s_vol, "term_structure": s_ts, "risk_appetite": s_ra},
        axis=1,
    )
    return subs[COMPONENT_NAMES]   # 固定列序


GREEDY_SIDE = frozenset({"greed", "extreme_greed"})
FEARFUL_SIDE = frozenset({"fear", "extreme_fear"})


def _side_of(band):
    if band in GREEDY_SIDE:
        return GREEDY_SIDE
    if band in FEARFUL_SIDE:
        return FEARFUL_SIDE
    return frozenset({"neutral"})


# ══════════════════════════════════════════════════════════════════
# 去聚集:独立情绪段·迟滞重置(§3·命门)
# ══════════════════════════════════════════════════════════════════
def detect_band_stretches(band_series):
    """band_series: pd.Series(index=日期升序,值=BANDS 中的档名或 None)。
    返回 dict[band] -> list[list[pd.Timestamp]](每段内该档的合格日,按时间序)。

    **迟滞重置(不是"变档即断段")**:合成读数在档位边界会日内抖动(如 74↔76 反复穿过 75),
    若一变档就断段,会把同一段贪婪/恐慌"体制"碎成几十上百段、假装独立段很多、CI 虚窄。故:
    某档 B 的一段,在读数留在【同一侧】(贪婪侧={greed,extreme_greed}/恐慌侧={fear,extreme_fear}/
    中性={neutral})期间持续算作同一段(只收 == B 的日);只有当读数**离开该侧**(回到中性或翻到对侧)
    才重置、下一次进入 B 才算新的独立段。这样一次贪婪体制=一段,而不是它每次抖过 75 就多算一段。
    None 视为离开任何侧(重置)。
    """
    out = {b: [] for b in BANDS}
    for B in BANDS:
        side = _side_of(B)
        episodes = []
        blocked = False
        for date, b in band_series.items():
            if b == B:
                if not blocked:
                    episodes.append([date])
                    blocked = True
                else:
                    episodes[-1].append(date)
            elif b not in side:          # 离开本侧(中性/对侧/None)→ 重置
                blocked = False
            # b in side 但 != B(如追 extreme_greed 时处于 greed):留在同段,不收该日、不重置
        out[B] = episodes
    return out


def _seed_for(*parts):
    # 确定性种子:用 zlib.crc32(跨进程稳定),不用内置 hash()——后者按 PYTHONHASHSEED 每进程加盐,
    # 会让自助 CI 每次跑都抖动、边界处甚至翻转公开 verdict(与 dip_hold_study.py 同一修法,同一命门)。
    s = "|".join(str(p) for p in parts)
    return SEED_BASE + zlib.crc32(s.encode("utf-8")) % 1_000_000


# ══════════════════════════════════════════════════════════════════
# 三态 verdict(§3 — 均非 edge/买卖/信号,硬保证)
# ══════════════════════════════════════════════════════════════════
def verdict_for(band, too_small, diff_mean, ci_below_base, ci_above_base):
    """三态:
      described-only    — 独立段 < MIN_STRETCHES_CI;
      contrarian-holds  — 仅【极度贪婪】diff_mean<0 且 CI 整段落在基率下方,
                          或【极度恐慌】diff_mean>0 且 CI 整段落在基率上方;
      not-contrarian    — 段数够但不满足上一条(含 fear/neutral/greed 三档:永不触发 contrarian-holds)。
    """
    if too_small:
        return "described-only"
    if diff_mean is None:
        return "not-contrarian"
    if band == "extreme_greed" and diff_mean < 0 and ci_below_base:
        return "contrarian-holds"
    if band == "extreme_fear" and diff_mean > 0 and ci_above_base:
        return "contrarian-holds"
    return "not-contrarian"


def _merge_within_horizon(stretches, pos_of, horizon):
    """把「前向窗口会重叠」的相邻段并为一个 CI 聚类(审查 Finding-1·命门)。

    迟滞去聚集只挡住了边界抖动,但两段就算真正分开(读数回过中性),若相隔 < horizon 个交易日,
    它们的 [入场, 入场+horizon] 前向窗口仍然重叠、共享同一段行情——当独立段喂给聚类自助会让 CI 虚窄、
    给未来留下「假 contrarian-holds」的口子。故按交易日位置:下一段首日与当前聚类末日间隔 < horizon → 并入同一聚类。
    返回 list[list[pd.Timestamp]](每个=前向窗口互不重叠的独立聚类)。
    """
    clusters = []
    cur = None
    last_pos = None
    for seg in stretches:
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


# ══════════════════════════════════════════════════════════════════
# 单个(档位×窗口)cell
# ══════════════════════════════════════════════════════════════════
def build_band_cell(band, stretches, fwd_h, base_up, base_mean, seed, horizon):
    """stretches: list[list[pd.Timestamp]](该档全部迟滞独立段,与 horizon 无关)。
    fwd_h: 该 horizon 的前向收益 Series(index=SP500 自身交易日历,可含 NaN 尾部)。horizon: 前向窗口(用于合并重叠窗口段)。
    """
    all_dates = [d for seg in stretches for d in seg]
    day_ret = fwd_h.reindex(all_dates).dropna()
    n_days = int(len(day_ret))
    if n_days:
        up_pct = round(float((day_ret > 0).mean()) * 100, 2)
        mean_pct = round(float(day_ret.mean()) * 100, 2)
    else:
        up_pct = mean_pct = None

    # 原始迟滞段数(仅供透明展示):有 ≥1 有效前向收益日的段
    n_stretches = sum(1 for seg in stretches if len(fwd_h.reindex(seg).dropna()))

    # CI 聚类 = 前向窗口互不重叠的独立聚类(把相隔 < horizon 的段并起来,审查 Finding-1)
    pos_of = {d: i for i, d in enumerate(fwd_h.index)}
    clusters = _merge_within_horizon(stretches, pos_of, horizon)
    seg_day_rets = []
    for cl in clusters:
        r = fwd_h.reindex(cl).dropna()
        if len(r):
            seg_day_rets.append(r.values.astype(float))
    n_independent = len(seg_day_rets)          # 真正前向窗口独立的聚类数——用于 CI 门槛与自助
    too_small = n_independent < MIN_STRETCHES_CI

    base_up_pct = round(base_up * 100, 2) if base_up == base_up else None
    base_mean_pct = round(base_mean * 100, 2) if base_mean == base_mean else None
    diff_mean = (round(mean_pct - base_mean_pct, 2)
                 if (mean_pct is not None and base_mean_pct is not None) else None)

    ci = None
    ci_below_base = False
    ci_above_base = False
    if not too_small:
        ci = cluster_bootstrap(seg_day_rets, seed=seed, B=B_BOOT)   # 日加权均值的 95% CI(不确定性来自 ~N 段独立情绪)
        if base_mean_pct is not None:
            ci_below_base = bool(ci[1] < base_mean_pct)
            ci_above_base = bool(ci[0] > base_mean_pct)
    ci_differs_base = bool(ci_below_base or ci_above_base)

    verdict = verdict_for(band, too_small, diff_mean, ci_below_base, ci_above_base)

    return {
        "band": band,
        "horizon": None,   # 由调用方补
        "n_days": n_days,
        "n_stretches": n_stretches,          # 迟滞独立段(原始,透明用)
        "n_independent": n_independent,      # 前向窗口互不重叠的聚类数(CI 门槛/自助实际用)
        "up_pct": up_pct,
        "mean_pct": mean_pct,
        "base_up_pct": base_up_pct,
        "base_mean_pct": base_mean_pct,
        "diff_mean": diff_mean,
        "ci95_mean": ci,
        "ci_differs_base": ci_differs_base,
        "too_small_no_ci": too_small,
        "verdict": verdict,
    }


def stretches_display(stretches, limit=40):
    """每段 {start, days}(前 limit 段即可,§4)。"""
    out = []
    for seg in stretches[:limit]:
        out.append({"start": seg[0].strftime("%Y-%m-%d"), "days": len(seg)})
    return out


# ══════════════════════════════════════════════════════════════════
# verdict_note(据实际算出的结果生成,不手写猜测的叙事——避免与真实结果不符)
# ══════════════════════════════════════════════════════════════════
def _build_verdict_note(cells):
    """自然语言叙述(不直接拼出 verdict 字面量,如"no-contrarian-edge"含"edge"词根——
    避免让内部状态名泄漏进给用户看的文案,§3 命门:纯描述用语)。"""
    holds = [c for c in cells if c["verdict"] == "contrarian-holds"]
    n_described = sum(1 for c in cells if c["verdict"] == "described-only")
    n_no_edge = sum(1 for c in cells if c["verdict"] == "not-contrarian")
    if holds:
        parts = "、".join(f"{c['band']}×{c['horizon']}日" for c in holds)
        lead = f"描述性总结:{parts} 这 {len(holds)} 格历史上可靠偏离了「随便哪天买」的基率(独立段够多、置信区间整段没跨过基率)——"
    else:
        lead = "描述性总结:本表全部档位×窗口组合,没有一格历史上可靠偏离「随便哪天买」的基率——"
    return (
        f"{lead}其余要么独立段太少只能纯描述({n_described} 格),要么段数虽够但置信区间仍跨过基率、"
        f"说不上有逆向料({n_no_edge} 格)。逆向情绪(别人贪婪我恐惧)择时出了名地弱,极度档的独立段"
        "本就是十几到上百段量级,数字好看也未必稳。以上皆非买卖信号,过去不代表未来。"
    )


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run(write=True, _df=None):
    df = _load_combined(_df)
    sp500 = _series(df, "SP500")
    vix = _series(df, "VIX")
    vix3m = _series(df, "VIX3M")
    gold = _series(df, "GOLD")

    subs = build_subscores(sp500, vix, vix3m, gold)
    comp = composite_series(subs)
    band_series = comp.dropna().apply(band_for)

    fwd = {h: forward_returns(sp500, h) for h in HORIZONS}

    composite_start = comp.dropna().index.min()
    as_of = comp.dropna().index.max()

    # 基率:与档位分析同一分析窗口(composite_start..as_of)内,「随便哪天买」的前向表现(§3)
    base = {}
    for h in HORIZONS:
        v = fwd[h][fwd[h].index >= composite_start].dropna()
        base[h] = {"up": float((v > 0).mean()) if len(v) else float("nan"),
                    "mean": float(v.mean()) if len(v) else float("nan"),
                    "n": int(len(v))}

    stretches_by_band_raw = detect_band_stretches(band_series)

    band_cells = []
    for band in BANDS:
        stretches = stretches_by_band_raw.get(band, [])
        for h in HORIZONS:
            cell = build_band_cell(band, stretches, fwd[h], base[h]["up"], base[h]["mean"],
                                   seed=_seed_for(band, h), horizon=h)
            cell["horizon"] = h
            band_cells.append(cell)

    stretches_by_band = {band: stretches_display(stretches_by_band_raw.get(band, []))
                          for band in BANDS}

    # 当前读数(gauge,§2)——取 composite 最后可得日
    cur_composite = float(comp.loc[as_of])
    cur_band = band_for(cur_composite)
    cur_components = []
    for name in COMPONENT_NAMES:
        col = subs[name]
        available = (as_of in col.index) and not pd.isna(col.loc[as_of])
        raw_value = None
        subscore = None
        if available:
            subscore = round(float(col.loc[as_of]), 2)
        # raw_value 单独重算(subs 只存子分,不存原始量;用同一批基础 Series 现算当日原始值)
        if name == "momentum" and as_of in sp500.index:
            sma = sp500.rolling(SMA_WIN, min_periods=SMA_WIN).mean()
            if as_of in sma.index and not pd.isna(sma.loc[as_of]) and sma.loc[as_of] != 0:
                raw_value = round(float(sp500.loc[as_of] / sma.loc[as_of] - 1.0), 4)
        elif name == "volatility" and as_of in vix.index:
            p = _rolling_percentile(vix, VIX_PCT_WIN)
            if as_of in p.index and not pd.isna(p.loc[as_of]):
                raw_value = round(float(p.loc[as_of]), 4)
        elif name == "term_structure" and as_of in vix3m.index and as_of in vix.index:
            raw_value = round(float(vix3m.loc[as_of] - vix.loc[as_of]), 3)
        elif name == "risk_appetite" and as_of in sp500.index and as_of in gold.index:
            sp_r = sp500.pct_change(RA_WIN)
            gold_r = gold.pct_change(RA_WIN)
            if as_of in sp_r.index and as_of in gold_r.index and not (pd.isna(sp_r.loc[as_of]) or pd.isna(gold_r.loc[as_of])):
                raw_value = round(float(sp_r.loc[as_of] - gold_r.loc[as_of]), 4)
        cur_components.append({
            "name": name, "label_zh": COMPONENTS_META[name]["label_zh"], "label_en": COMPONENTS_META[name]["label_en"],
            "definition_zh": COMPONENTS_META[name]["definition_zh"], "definition_en": COMPONENTS_META[name]["definition_en"],
            "raw_value": raw_value, "subscore": subscore, "available": bool(available),
        })

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of.strftime("%Y-%m-%d"),
        "composite_start": composite_start.strftime("%Y-%m-%d"),
        "components_used": COMPONENT_NAMES,
        "min_stretches_ci": MIN_STRETCHES_CI,
        "current": {
            "composite": round(cur_composite, 1),
            "band": cur_band,
            "components": cur_components,
        },
        "contrarian": {
            "bands": band_cells,
            "stretches_by_band": stretches_by_band,
        },
        "honesty": HONESTY,
        "verdict_note": _build_verdict_note(band_cells),
    }

    if write:
        for d in write_json("fear_greed.json", out, allow_nan=False):
            print(f"  Written: {d}/fear_greed.json")
    return out


if __name__ == "__main__":
    r = run(write=True)
    print("\n=== 恐慌贪婪合成表(近似·非 CNN 官方值,纯描述) ===")
    cur = r["current"]
    print(f"  as_of {r['as_of']}  composite = {cur['composite']}  band = {cur['band']}")
    for c in cur["components"]:
        avail = "✓" if c["available"] else "—"
        print(f"    [{avail}] {c['name']:>15}: raw={c['raw_value']}  subscore={c['subscore']}")
    print(f"  composite 起点: {r['composite_start']}   分量: {r['components_used']}")
    print("\n  --- 逆向情绪检验(纯描述) ---")
    for c in r["contrarian"]["bands"]:
        print(f"    {c['band']:>13} / {c['horizon']:>2}d: n_days={c['n_days']:>5} "
              f"stretch={c['n_stretches']:>3} indep={c['n_independent']:>3} "
              f"up={c['up_pct']}%  mean={c['mean_pct']}%  vs base {c['diff_mean']}  "
              f"CI={c['ci95_mean']}  verdict={c['verdict']}")
    print(f"\n  {r['verdict_note']}")
