"""btc_nasdaq_backtest.py — BTC 动量 → 纳指 诚实回测（出格区·红线审计 🟡#1）。

背景：BTC 20日动量是全站唯一穿过 FDR + 现代段 + holdout 的方向规律（factor_pruning「现代仍有效」
+9.26pp、autodiscovery 唯一 survive、walk_forward LR=1.11），此前被「无向双侧」红线剥掉了方向。
这里把方向亮出来、用诚实回测检验：**带交易成本、多体制稳健性、完整下跌分布、公开计分。**

口径对齐生产（signal_model.BTC_MOM_THRESH=0.05，20日动量）。数据：combined_prices.csv 的 NASDAQ+BTC 对齐日线
（独立纳指综合序列，非 FDR holdout 同一序列，数字不会完全相等；审 P2-b）。
铁律：① 无前瞻（用 t-1 收盘已知的 BTC 动量定 t 日仓位）② 不挑最优规则（预设简单规则，诚实报）
③ FRAGILE（跨折符号一致性 0.8 非 1.0）→ 必须看方向在各体制下是否站得住，别假设。
非荐股、非保证、会错、过去≠未来；每跑 append 计分。
"""
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from stats_util import forward_returns

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw" / "combined_prices.csv"
LOG = BASE / "data" / "btc_backtest_log.csv"
THRESH = 0.05          # ±5%，与 signal_model.BTC_MOM_THRESH 一致
MOM_WIN = 20           # 20 日动量
FWD = 20               # 前向 20 日（与项目 HORIZON 一致）
COST_BPS = 5.0         # 单边交易成本（QQQ 量级保守估计）


def _load():
    df = pd.read_csv(RAW, index_col="Date", parse_dates=True)
    px = df[["NASDAQ", "BTC"]].dropna().sort_index()
    px["nq_ret"] = px["NASDAQ"].pct_change()
    px["btc_mom"] = px["BTC"] / px["BTC"].shift(MOM_WIN) - 1.0     # BTC 20日动量
    return px.dropna(subset=["btc_mom", "nq_ret"])


def _state(mom):
    return np.where(mom > THRESH, "pos", np.where(mom < -THRESH, "neg", "neutral"))


def _dist(fwd):
    """前向收益分布（描述性·完整下跌画像）。"""
    f = fwd.dropna().values * 100
    if len(f) < 20:
        return None
    return {"n": int(len(f)), "mean_pct": round(float(f.mean()), 2),
            "up_rate": round(float((f > 0).mean() * 100), 1),
            "p10": round(float(np.percentile(f, 10)), 2),
            "p90": round(float(np.percentile(f, 90)), 2),
            "worst": round(float(f.min()), 2), "pct_neg": round(float((f < 0).mean() * 100), 1)}


def _conditional(px):
    """① 条件前向 FWD 日收益 by BTC 动量状态（描述性证据，非交易）。"""
    fwd = forward_returns(px["NASDAQ"], FWD)
    st = _state(px["btc_mom"].values)
    out = {"base": _dist(fwd)}
    for s in ("pos", "neutral", "neg"):
        out[s] = _dist(fwd[st == s])
    return out


def _control_nq_mom(px):
    """对照检验（最可能的证伪）：用【纳指自身 20 日动量】做同口径条件分析。
    若纳指自身动量给出的 pos−neg 上涨率差 ≈ 或 ≥ BTC，则 BTC 没给增量领先信息——
    只是大盘动量/风险开关的代理（相关≠独立信号）。"""
    nq_mom = px["NASDAQ"] / px["NASDAQ"].shift(MOM_WIN) - 1.0
    fwd = forward_returns(px["NASDAQ"], FWD)
    st = _state(nq_mom.values)
    cond = {"base": _dist(fwd)}
    for s in ("pos", "neutral", "neg"):
        cond[s] = _dist(fwd[st == s])
    gap = (round(cond["pos"]["up_rate"] - cond["neg"]["up_rate"], 1)
           if cond.get("pos") and cond.get("neg") else None)
    return {"conditional": cond, "pos_minus_neg_uprate_pp": gap}


def _backtest(px, cost_bps=COST_BPS):
    """② 预设简单 overlay：BTC 动量 neg(<-5%) → 空仓，否则满仓纳指；次日生效（无前瞻）；带单边成本。"""
    mom = px["btc_mom"]
    sig = np.where(mom < -THRESH, 0.0, 1.0)                  # 不是「挑阈值」：就用生产同款 -5% 门
    pos = pd.Series(sig, index=px.index).shift(1).fillna(1.0)  # t-1 信号定 t 仓位 → 无前瞻
    turn = pos.diff().abs().fillna(0.0)
    cost = turn * (cost_bps / 10000.0)
    strat = pos * px["nq_ret"] - cost
    bh = px["nq_ret"]
    return pos, strat, bh


def _perf(ret, idx=None):
    r = ret.dropna()
    if len(r) < 60:
        return None
    yrs = (r.index[-1] - r.index[0]).days / 365.25     # 用 r 自身跨度(防 NaN 时年化口径错·审 P2-a)
    cum = float((1 + r).prod())
    cagr = cum ** (1 / yrs) - 1 if yrs > 0 else 0.0
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    return {"total_return_pct": round((cum - 1) * 100, 1), "cagr_pct": round(cagr * 100, 2),
            "sharpe": round(sharpe, 2), "max_dd_pct": round(dd * 100, 1)}


def _regimes(px):
    """③ 多体制稳健性：分时段看「条件优势(pos上涨率−neg上涨率)」与策略 vs 买入持有 是否各段都站得住。"""
    fwd = forward_returns(px["NASDAQ"], FWD)
    st = _state(px["btc_mom"].values)
    pos, strat, bh = _backtest(px)
    rows = []
    bounds = [(2014, 2018), (2018, 2021), (2021, 2024), (2024, 2027)]
    for a, b in bounds:
        m = (px.index.year >= a) & (px.index.year < b)
        if m.sum() < 120:
            continue
        fp = fwd[m][st[m] == "pos"].dropna()
        fn = fwd[m][st[m] == "neg"].dropna()
        gap = (float((fp > 0).mean()) - float((fn > 0).mean())) * 100 if len(fp) >= 10 and len(fn) >= 10 else None
        sp = _perf(strat[m], px.index[m])
        bp = _perf(bh[m], px.index[m])
        rows.append({"period": f"{a}-{b-1}", "n": int(m.sum()),
                     "cond_pos_minus_neg_uprate_pp": (None if gap is None else round(gap, 1)),
                     "strat_cagr_pct": (sp or {}).get("cagr_pct"), "buyhold_cagr_pct": (bp or {}).get("cagr_pct"),
                     "edge_holds": (None if gap is None else bool(gap > 0))})
    return rows


def _append_log(today, verdict, excess):
    from util_io import append_daily_log
    append_daily_log(LOG, ["date", "verdict", "excess_cagr_pp"],
                     [[today, verdict, excess]], date=today)


def run(write=True):
    px = _load()
    cond = _conditional(px)
    ctrl = _control_nq_mom(px)                                # 对照：纳指自身动量（最可能的证伪）
    pos, strat, bh = _backtest(px)
    sp, bp = _perf(strat, px.index), _perf(bh, px.index)
    regimes = _regimes(px)
    excess = round(sp["cagr_pct"] - bp["cagr_pct"], 2)            # 正=策略年化更高
    dd_better = round(sp["max_dd_pct"] - bp["max_dd_pct"], 1)     # max_dd 为负；正=策略回撤更浅(更接近0)
    sharpe_better = round(sp["sharpe"] - bp["sharpe"], 2)         # 正=策略风险调整更好
    holds = [r["edge_holds"] for r in regimes if r["edge_holds"] is not None]
    n_hold = sum(holds)
    pos_gap = round(cond["pos"]["up_rate"] - cond["neg"]["up_rate"], 1) if cond.get("pos") and cond.get("neg") else None
    # 对照：BTC 动量条件差 vs 纳指自身动量条件差 → BTC 是否真给增量信息
    nq_gap = ctrl["pos_minus_neg_uprate_pp"]
    incr = (round(pos_gap - nq_gap, 1) if pos_gap is not None and nq_gap is not None else None)
    # 数据层双语(2026-08-25):分支只判一次、中英从同一模板渲染,杜绝两套 if 各自漂移。
    if incr is None:
        ctrl_key = "nodata"
    elif incr >= 3:
        ctrl_key = "incremental"
    elif incr <= -1:
        ctrl_key = "proxy"
    else:
        ctrl_key = "overlap"
    _CTRL = {
        "nodata": ("纳指自身动量对照数据不足",
                   "Not enough data to control for NASDAQ's own momentum"),
        "incremental": (f"已对照纳指自身20日动量(同口径差 {nq_gap}pp)：BTC 多给约 {incr}pp 增量、不只是大盘动量代理",
                        f"Controlled for NASDAQ's own 20-day momentum (same-basis gap {nq_gap}pp): BTC adds about "
                        f"{incr}pp on top — not merely a proxy for broad-market momentum"),
        "proxy": (f"已对照纳指自身20日动量(差 {nq_gap}pp)：纳指自身动量差更大、BTC 反没多给——信号大概率只是大盘动量代理",
                  f"Controlled for NASDAQ's own 20-day momentum (gap {nq_gap}pp): NASDAQ's own momentum gap is larger and "
                  f"BTC adds nothing — the signal is most likely just a proxy for broad-market momentum"),
        "overlap": (f"已对照纳指自身20日动量(差 {nq_gap}pp)：BTC 仅多给 {incr}pp(≈持平)——多半与大盘动量重叠、增量有限",
                    f"Controlled for NASDAQ's own 20-day momentum (gap {nq_gap}pp): BTC adds only {incr}pp (≈flat) — "
                    f"it largely overlaps with broad-market momentum; incremental value is limited"),
    }
    control_note, control_note_en = _CTRL[ctrl_key]
    edge_robust = bool(holds) and n_hold == len(holds)
    n_strong = sum(1 for r in regimes if (r.get("cond_pos_minus_neg_uprate_pp") or 0) >= 5.0)
    seg = f"方向同号 {n_hold}/{len(holds)} 段(其中 {n_strong} 段优势≥5pp；早段约3pp接近噪声、强度随期递增)"
    seg_en = (f"same sign in {n_hold}/{len(holds)} regime segments ({n_strong} with an edge ≥5pp; the earliest segment "
              f"is ~3pp and close to noise, strength increases over time)")
    risk = (f"Sharpe {sp['sharpe']} vs {bp['sharpe']}、回撤 {sp['max_dd_pct']}% vs {bp['max_dd_pct']}%(浅 {dd_better}pp)"
            f"——但属单一历史路径、无置信区间，可能不重复")
    risk_en = (f"Sharpe {sp['sharpe']} vs {bp['sharpe']}, drawdown {sp['max_dd_pct']}% vs {bp['max_dd_pct']}% "
               f"({dd_better}pp shallower) — but this is a single historical path with no confidence interval; "
               f"it may not repeat")
    # 诚实裁决：分清「方向可预测」「绝对收益可交易」「风险调整划算」三件事；弱证据要标弱（审 P1）
    if edge_robust and excess > 0:
        v_key = "robust"
    elif edge_robust and (sharpe_better > 0 or dd_better > 0):
        v_key = "tradeoff"
    elif edge_robust:
        v_key = "hard"
    elif holds and n_hold >= max(1, len(holds) - 1):
        v_key = "mostly"
    else:
        v_key = "regime"
    _V = {
        "robust": (f"稳健可用：{seg}，overlay 年化超额 +{excess}pp",
                   f"Robust and usable: {seg_en}; overlay excess CAGR +{excess}pp"),
        "tradeoff": (f"信号真·风险取舍：{seg}；裸 overlay 让出 {abs(excess)}pp 年化，换 {risk}。"
                     f"要风险调整收益的可参考，要最大绝对收益的死拿更好",
                     f"Signal is real, but it is a risk trade-off: {seg_en}; the naive overlay gives up "
                     f"{abs(excess)}pp of annualised return in exchange for {risk_en}. Worth a look if you optimise "
                     f"risk-adjusted return; if you want maximum absolute return, just hold"),
        "hard": (f"信号真但难交易：{seg}，但裸 overlay 年化({excess}pp)/Sharpe/回撤都没占便宜"
                 f"——连弱势期纳指仍约6成上涨，裸 exit 不划算",
                 f"Signal is real but hard to trade: {seg_en}, yet the naive overlay wins on none of annualised "
                 f"return ({excess}pp), Sharpe or drawdown — even in weak regimes NASDAQ still rises ~60% of the "
                 f"time, so simply exiting does not pay"),
        "mostly": (f"多数同号：{seg}", f"Mostly the same sign: {seg_en}"),
        "regime": (f"体制依赖：仅 {n_hold}/{len(holds)} 段同号，别当稳定信号",
                   f"Regime-dependent: only {n_hold}/{len(holds)} segments share the same sign — "
                   f"do not treat it as a stable signal"),
    }
    verdict = f"{_V[v_key][0]}。{control_note}"
    verdict_en = f"{_V[v_key][1]}. {control_note_en}"
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_range": [str(px.index[0].date()), str(px.index[-1].date())], "n_days": int(len(px)),
        "signal": f"BTC {MOM_WIN}日动量，阈值 ±{THRESH*100:.0f}%；前向 {FWD} 日",
        "conditional": cond, "cond_pos_minus_neg_uprate_pp": (None if pos_gap is None else round(pos_gap, 1)),
        "control_nasdaq_own_mom": {"pos_minus_neg_uprate_pp": nq_gap, "btc_incremental_pp": incr},
        "backtest": {"rule": f"BTC动量<-{THRESH*100:.0f}%→空仓，否则满仓纳指；次日生效；单边成本 {COST_BPS:.0f}bps",
                     "cost_bps": COST_BPS, "n_switches": int(pos.diff().abs().sum()),
                     "time_in_market_pct": round(float(pos.mean()) * 100, 1),
                     "strategy": sp, "buyhold": bp, "excess_cagr_pp": excess,
                     "dd_shallower_pp": dd_better, "sharpe_diff": sharpe_better},
        "regimes": regimes, "verdict": verdict, "verdict_en": verdict_en,
        "caveat": ("出格区·把红线此前剥掉的方向亮出来诚实检验。非荐股、非保证、会错、过去≠未来；"
                   "BTC 与纳指同属高风险资产，相关≠因果；" + control_note +
                   "；Sharpe/回撤改善属单一历史路径、无置信区间；FRAGILE(符号一致性0.8)→ 看体制段。每跑 append 计分。"),
    }
    if write:
        from util_io import write_json
        write_json("btc_nasdaq.json", out)
        _append_log(datetime.date.today().isoformat(), verdict, excess)
        print(f"[OK] btc_nasdaq.json — {verdict}")
        print(f"  条件 pos上涨率−neg = {out['cond_pos_minus_neg_uprate_pp']}pp · 年化超额 {excess}pp · "
              f"回撤更浅 {dd_better}pp · Sharpe差 {sharpe_better}")
        for r in regimes:
            print(f"  {r['period']}: 优势{r['cond_pos_minus_neg_uprate_pp']}pp 策略{r['strat_cagr_pct']}% vs 持有{r['buyhold_cagr_pct']}%")
    return out


if __name__ == "__main__":
    run()
