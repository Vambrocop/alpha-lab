"""au_pick_backtest.py — 澳股荐股「同一规则·零调参」历史轨迹披露（B3·SPEC_AU_PICKS §2）。

**这不是策略验证,是同一规则的历史轨迹披露**（§2.1 页面大字）：回测池 = 今天的 ~ASX100 成分回望(③扩池),
含严重幸存者偏差 → 结果系统性偏乐观;前向公开计分账本(au_pick_ledger)才是真裁决。结果好坏照登,
披露门与荐股区同一 commit 上线(§0)。

零调参 = 只用 §1 同款常量 + **同一** `_select_picks/_outcome/_followable`（`from pick_ledger import`,
零克隆·防漂移),入场/出场复用 `fl.fwd`（与 live 账本逐字节同逻辑·S-2,禁手搓入场循环）。
统计边界(§2.4)：不做 p 值/显著性、不做参数扫描/相位扫描、不与美股回测比较排名。

数据单一真相源 = `raw/au/au_stocks_prices.csv`（fetch_data_au 落的宽表,FMG 身份真起点前置 NaN·§2.2 B-1）
+ 基准 `raw/au/AXJO.csv`（^AXJO 除息价格指数）。fail-soft：缺失票该缺席 + 计数,不崩(N-5)。

运行：$env:PYTHONUTF8='1'; py market-analysis/scripts/au_pick_backtest.py
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forward_ledger as fl
# 规则/命中口径/可跟单日/窗口常量：**同一对象,零克隆**（S-1·防漂移命门）——绝不复制函数体。
from pick_ledger import _select_picks, _outcome, _followable, MOM_WIN, VOL_WIN, N_PICKS, HOLD_TD
from au_pick_ledger import PICK_RULE   # NIT-1(双审):公开文案用 AU 版(ASX100 大中盘池),不用美股'观察池'措辞
from fetch_data_au import FMG_TRUE_START, STOCK_TICKERS

BASE = SCRIPTS.parent
RAW_AU = BASE / "data" / "raw" / "au"
UNIVERSE = RAW_AU / "au_stocks_prices.csv"     # 宽表面板（date×.AX ticker,单一真相源,FMG 已截断）
BENCH = "^AXJO"                                 # 基准:ASX200 除息价格指数（B-2 股息口径不对称·必披露）
BENCH_CSV = RAW_AU / "AXJO.csv"
EXPECTED = set(STOCK_TICKERS.values())          # 期望的 ~108 只 .AX ticker（③ 扩池·fail-soft 缺席计数基准）

# ── §2.1 五条诚实声明（页面大字 + 全进 meta 供 S-6 机器守门·test #9）──────────────────
DECLARATIONS = {
    "survivorship": {
        "key": "幸存者偏差",
        "zh": "⚠ 回测池 = 今天的 ~ASX100 成分回望（1993 年的你不可能知道今天谁在池里）——含严重幸存者偏差,"
              "结果系统性偏乐观。前向公开计分（账本）才是真裁决。",
        "en": "WARNING: the backtest universe = today's ~ASX100 constituents looking backward (in 1993 you could "
              "not have known who is in the pool today) — heavy survivorship bias, results are systematically "
              "optimistic. Forward public scoring (the ledger) is the real verdict.",
    },
    "dividend_basis": {
        "key": "股息口径",
        "zh": "股息口径不对称（B-2）：个股序列=含息复权总回报,基准 ^AXJO=除息价格指数 → 存在 ≈股息率"
              "（AU ~4%/年 ≈0.3%/20td）的持续性口径顺风,对「看好」侧系统性有利——这不是 edge。",
        "en": "Dividend-basis asymmetry (B-2): the stock series are total-return (dividends reinvested) while "
              "the ^AXJO benchmark is an ex-dividend price index — a persistent ~dividend-yield tailwind "
              "(AU ~4%/yr ≈0.3%/20td) that systematically favours the bullish side. This is NOT an edge.",
    },
    "non_independence": {
        "key": "非独立性",
        "zh": "非独立性（S-5）：同一决策日 6 只同截面强相关 + AU 银行/矿业高度集中 → 有效独立样本 ≪ 记录条数,"
              "hit% 只作描述、不可当胜率精度。",
        "en": "Non-independence (S-5): 6 picks per decision day share the same cross-section and AU is heavily "
              "concentrated in banks/miners → effective independent samples are far fewer than the record count; "
              "hit% is descriptive only, not a precision win-rate.",
    },
    "phase_lock": {
        "key": "相位锁定",
        "zh": "相位锁定（S-4）：决策日从最早可行日起每 HOLD_TD 交易日一个（确定性、预注册、无挑选）;结果对 20 个"
              "相位起点敏感,本回测锁最早可行相位、不做相位扫描（扫描=调参,§2.4 禁）——已披露局限。",
        "en": "Phase lock (S-4): decision days step every HOLD_TD trading days from the earliest feasible day "
              "(deterministic, pre-registered, no cherry-picking). Results are sensitive to which of the 20 phase "
              "offsets you start on; this backtest locks the earliest-feasible phase and does NOT sweep phases "
              "(sweeping = tuning, forbidden by §2.4) — a disclosed limitation.",
    },
    "leg_calendars": {
        "key": "两腿日历",
        "zh": "两腿日历（双审 SHOULD-1）：个股腿与基准腿各按自身交易日历计 20 个交易日——1990 年代稀疏数据下"
              "约 14% 记录两腿出场日相差 1–4 个交易日（多在 1992–2003）。双审重对齐复算:总体 mean_ce 差异"
              "<0.005pp、hit 率差 0.1pp,已发布数字稳健;此为与 live 账本同机制的忠实镜像,非回测独有。",
        "en": "Leg calendars (audit SHOULD-1): each leg counts 20 trading days on its own calendar — with sparse "
              "1990s data ~14% of records have exit dates 1-4 trading days apart (mostly 1992-2003). Re-aligned "
              "recomputation: overall mean_ce differs by <0.005pp, hit rate by 0.1pp — published figures are robust. "
              "This mirrors the live ledger mechanism; not a backtest-specific artifact.",
    },
    "descriptive": {
        "key": "描述性",
        "zh": "非重叠窗口、无多重校正（单一预注册规则）、纯描述性、过去≠未来。非投资建议、不可交易（成本/滑点/税）、会错。",
        "en": "Non-overlapping windows, no multiple-comparison correction (single pre-registered rule), purely "
              "descriptive, past != future. Not investment advice, not tradeable (costs/slippage/tax), can be wrong.",
    },
}

FMG_TRUNCATION = {
    "key": "FMG 截断",
    "cutoff": FMG_TRUE_START,
    "zh": f"FMG 身份真起点截断 @ {FMG_TRUE_START}（§2.2 B-1）：1988–2002 为壳公司亚分币价（$0.0006–0.005,非真实 "
          f"Fortescue）,yfinance auto_adjust 令壳→真为 2003–2007 平滑爬坡、无单日跳变。取 2005 首个交易日"
          f"（首个连续流动真股年）为真起点,此前宽表全 NaN;配合 126 日动量窗 dropna,FMG ≈2005-07 才首次可选"
          f"（动量窗全落真区,不含壳基数假象）。",
    "en": f"FMG identity-true-start truncation @ {FMG_TRUE_START} (§2.2 B-1): 1988–2002 is shell-company sub-cent "
          f"pricing ($0.0006–0.005, not real Fortescue); yfinance auto_adjust makes the shell->real transition a "
          f"smooth 2003–2007 ramp with no single-day jump. The true start is the first 2005 trading day (first year "
          f"of continuous liquid real trading); the wide table is all-NaN before it, so with the 126-day momentum "
          f"dropna FMG only becomes selectable ~2005-07 (its momentum window lies wholly in the real regime).",
}

STAT_BOUNDARIES = {
    "zh": "统计边界（§2.4·不越）：不做显著性检验/p 值、不做参数扫描/相位扫描、不与美股回测比较排名。",
    "en": "Statistical boundaries (§2.4): no significance tests / p-values, no parameter sweep / phase sweep, "
          "no cross-ranking against the US backtest.",
}


# ── 数据装载（宽表 + 基准,fail-soft）────────────────────────────────────────────────
def _load_panel():
    """读宽表(单一真相源) + 基准 ^AXJO;缺失票该缺席 + 计数(N-5)。返回 (panel, bench, absent)。"""
    panel = pd.read_csv(UNIVERSE, index_col=0, parse_dates=True)
    panel = panel.apply(pd.to_numeric, errors="coerce")
    absent = sorted(EXPECTED - set(panel.columns))              # 抓取失败票 → 宽表无此列
    all_nan = [c for c in panel.columns if panel[c].notna().sum() == 0]  # 有列但全空 → 也算缺席
    if all_nan:
        panel = panel.drop(columns=all_nan)
        absent = sorted(set(absent) | set(all_nan))
    bench = pd.read_csv(BENCH_CSV, index_col=0, parse_dates=True).iloc[:, 0]
    bench = pd.to_numeric(bench, errors="coerce").dropna()
    bench.name = BENCH
    return panel, bench, absent


# ── 可选池计数（display-only·N-2 早年池薄）——精确镜像 _select_picks 的 mom/vol/dropna,只用于展示 ──
def _n_eligible(sub):
    px = sub.apply(pd.to_numeric, errors="coerce")
    if len(px) < MOM_WIN + 1:
        return 0
    mom = px.iloc[-1] / px.iloc[-1 - MOM_WIN] - 1
    vol = px.pct_change().iloc[-VOL_WIN:].std()
    return int(pd.DataFrame({"mom": mom, "vol": vol}).dropna().shape[0])


# ── 决策日网格：锚点=最早可行日,每 HOLD_TD 交易日一个,末端护栏(S-7)──────────────────
def _decision_days(panel, bench):
    """确定性、预注册、无挑选（§2.2 相位锁定 S-4）。
    锚点 = 动量窗就绪(≥MOM_WIN+1 行) 且 基准已开市 的最早交易日;此后每 HOLD_TD 交易日一个;
    末端护栏(S-7)：入场(次日)后满 HOLD_TD 交易日的出场须落在面板内,否则不生成（历史回测无 pending）。"""
    idx = panel.index
    if len(idx) < MOM_WIN + 1 or len(bench) == 0:
        return []
    warm = idx[MOM_WIN:]                          # 从第 MOM_WIN+1 行起,切片必有 ≥MOM_WIN+1 行
    feasible = warm[warm >= bench.index[0]]        # 基准已有数据（结算腿需要）
    if len(feasible) == 0:
        return []
    anchor_pos = idx.get_indexer([feasible[0]])[0]
    days = []
    p = anchor_pos
    while p + 1 + HOLD_TD < len(idx):              # idx[p+1]=入场日、idx[p+1+HOLD_TD]=出场日 须存在
        days.append(idx[p])
        p += HOLD_TD
    return days


# ── 核心回测：每决策日 _select_picks + fl.fwd 结算（与 live 逐字节同逻辑）──────────────
def _backtest(panel, bench):
    """返回 (days, records, eligible_by_day)。
    records 每条 = 一个荐股的结算结果（status ∈ settled/dropped/pending/bench_pending）。
    入场/出场复用 `fl.fwd`（followable=决策日次日、hold=HOLD_TD、trading_days=True）——禁手搓循环(S-2)。"""
    days = _decision_days(panel, bench)
    records, eligible_by_day = [], {}
    for asof in days:
        sub = panel.loc[:asof]                     # PIT 切片：决策只看 asof 及之前（零前瞻·§2.2）
        eligible_by_day[asof] = _n_eligible(sub)
        picks = _select_picks(sub)                 # 同一对象·零克隆
        followable = _followable({"pick_date": asof})   # 决策日次日（与 live 账本同一函数·防抢跑 S-2）
        b = fl.fwd(bench, followable, HOLD_TD, trading_days=True)
        bok = isinstance(b, tuple)
        bret = b[0] if bok else None
        for p in picks:
            rec = {"asof": asof, "symbol": p["symbol"], "view": p["view"], "mom_pct": p["mom_pct"]}
            if not bok:                            # 基准窗未走完 → 整决策日无法结算（护栏后不应发生）
                rec["status"] = "bench_pending"
                records.append(rec)
                continue
            s = fl.fwd(panel[p["symbol"]].dropna(), followable, HOLD_TD, trading_days=True)
            if isinstance(s, tuple):
                sret, ed, xd, epx, xpx = s
                rec.update({"status": "settled",
                            "entry_date": ed, "exit_date": xd, "entry_px": epx, "exit_px": xpx,
                            "bench_ret": bret, "bench_entry": b[1], "bench_exit": b[2],
                            **_outcome(sret, bret, p)})   # 命中/超额口径:同一 _outcome
            else:
                # 基准窗已走完（护栏保证），个股腿仍 pending/None ⇒ 该票窗内缺价/退市（历史回测非"待结算"）
                # → 透明丢弃 + 计数（§2.2：退市/窗内缺价 该条 dropped）。live 前向账本里 pending=等待,
                # 回测里时间已过、基准已结算 ⇒ 个股走不完窗 = 真退市 ⇒ dropped（两处语义差异·刻意）。
                rec["status"] = "dropped"
            records.append(rec)
    return days, records, eligible_by_day


def _d(ts):
    return pd.Timestamp(ts).date().isoformat()


def _side(settled, view):
    s = [r for r in settled if r["view"] == view]
    if not s:
        return {"n": 0, "hit_pct": None, "mean_call_excess_pct": None}
    nh = sum(1 for r in s if r["hit"])
    ce = np.array([r["call_excess_pct"] for r in s], float)
    return {"n": len(s), "hit_pct": round(nh / len(s) * 100, 1),
            "mean_call_excess_pct": round(float(ce.mean()), 3)}


def run(write=True, panel=None, bench=None):
    """跑回测 → au_backtest.json（web+docs）。panel/bench 可注入（测试用合成面板,不联网）。"""
    absent = []
    if panel is None:
        panel, bench, absent = _load_panel()

    days, records, eligible_by_day = _backtest(panel, bench)
    settled = [r for r in records if r["status"] == "settled"]
    dropped = [r for r in records if r["status"] == "dropped"]
    n_calls = len(settled) + len(dropped)          # 一个「荐股」=一次到达结算尝试的挑票
    n_settled = len(settled)

    n_hit = sum(1 for r in settled if r["hit"])
    ce_all = np.array([r["call_excess_pct"] for r in settled], float) if settled else np.array([])

    # 分年（按决策日年份·N-2 附当年可选池）
    by_year = []
    for y in sorted({r["asof"].year for r in settled}):
        yr = [r for r in settled if r["asof"].year == y]
        nh = sum(1 for r in yr if r["hit"])
        yce = np.array([r["call_excess_pct"] for r in yr], float)
        yd = [d for d in days if d.year == y]
        nsel = int(round(float(np.mean([eligible_by_day[d] for d in yd])))) if yd else 0
        by_year.append({"year": y, "n": len(yr), "hit_pct": round(nh / len(yr) * 100, 1),
                        "mean_call_excess_pct": round(float(yce.mean()), 3),
                        "n_selectable": nsel})

    entries = [r["entry_date"] for r in settled]
    exits = [r["exit_date"] for r in settled]
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": _d(max(exits)) if exits else None,     # 数据现势 = 最新一笔结算的出场日（as-of 铁律）
        "title_zh": "澳股荐股·同一规则零调参历史轨迹披露（非策略验证·含幸存者偏差·系统性偏乐观）",
        "title_en": "AU picks — same-rule zero-tuning historical trace disclosure (NOT strategy validation; "
                    "survivorship-biased, systematically optimistic)",
        "rule": PICK_RULE,
        "hold_td": HOLD_TD,
        "benchmark": BENCH,
        "period": {
            "first_decision": _d(days[0]) if days else None,
            "last_decision": _d(days[-1]) if days else None,
            "first_entry": _d(min(entries)) if entries else None,
            "last_exit": _d(max(exits)) if exits else None,
        },
        "overall": {
            "n_decision_days": len(days),
            "n_calls": n_calls,
            "n_settled": n_settled,
            "n_dropped": len(dropped),
            "dropped_pct": round(len(dropped) / max(1, n_calls) * 100, 1),
            "hit_pct_total": round(n_hit / n_settled * 100, 1) if n_settled else None,
            "mean_call_excess_pct": round(float(ce_all.mean()), 3) if n_settled else None,
            "median_call_excess_pct": round(float(np.median(ce_all)), 3) if n_settled else None,
            "bullish": _side(settled, "看好"),
            "bearish": _side(settled, "看淡"),
        },
        "by_year": by_year,
        "meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule": PICK_RULE,
            "hold_td": HOLD_TD,
            "benchmark": BENCH,
            "n_stocks_absent": len(absent),
            "stocks_absent": absent,               # fail-soft 缺席票（N-5）
            "declarations": DECLARATIONS,          # §2.1 五条全文（S-6 机器门·test #9）
            "fmg_truncation": FMG_TRUNCATION,      # FMG 实证截断日 + 依据
            "stat_boundaries": STAT_BOUNDARIES,    # §2.4 边界声明
        },
    }

    if write:
        from util_io import write_json
        written = write_json("au_backtest.json", out, allow_nan=False)
        _print_summary(out)
        print(f"[OK] au_backtest.json → {[str(d) for d in written]}")
    return out


def _print_summary(out):
    o = out["overall"]
    print("\n=== AU 荐股零调参回测（同一规则历史轨迹·结果好坏照登）===")
    print(f"期间 {out['period']['first_entry']} ~ {out['period']['last_exit']}  "
          f"决策日 {o['n_decision_days']}  荐股 {o['n_calls']}  已结算 {o['n_settled']}  丢弃 {o['n_dropped']}")
    print(f"判断对(hit) 总 {o['hit_pct_total']}%  |  看好 {o['bullish']['hit_pct']}% (n={o['bullish']['n']})  "
          f"看淡 {o['bearish']['hit_pct']}% (n={o['bearish']['n']})")
    print(f"call_excess 均值 {o['mean_call_excess_pct']}%  中位 {o['median_call_excess_pct']}%")
    print(f"{'年':>6} {'n':>5} {'hit%':>7} {'均call_ex%':>12} {'可选池':>7}")
    for r in out["by_year"]:
        print(f"{r['year']:>6} {r['n']:>5} {str(r['hit_pct']):>7} "
              f"{str(r['mean_call_excess_pct']):>12} {r['n_selectable']:>7}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:                          # fail-soft:独立区不阻断流水线
        print(f"[AU 回测] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        sys.exit(0)
