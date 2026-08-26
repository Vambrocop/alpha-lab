"""regime_forward.py — 体制→前向收益分布（红线审计 🟡#2·出格区）。

此前 market_regime 只算「当前体制 + 历史分位」，从没算「给定体制下市场未来收益/回撤的分布」。
这里补上：曲线倒挂 / VIX 高低 / 信用利差宽紧 → SP500 未来 1/3/6/12 月收益分布（均值/上涨率/p10/最差）。

诚实红线（都在 caveat）：稀有体制（倒挂）日高度自相关 → 独立「事件段」很少（就 3-4 段），
分布看着精确实则不可靠 → 同时报 n_days 与 n_episodes(连续段数)，段数少的别当可靠。
描述性、非预测、非建议；重叠窗口只看分布不算显著性。每跑 append 计分。
"""
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from stats_util import forward_returns

BASE = Path(__file__).parent.parent
RAW = BASE / "data" / "raw" / "combined_prices.csv"
LOG = BASE / "data" / "regime_forward_log.csv"
HORIZONS = [21, 63, 126, 252]          # 交易日 ≈ 1/3/6/12 月
ASSET = "SP500"


def _episodes(mask, min_gap=21):
    """宏观独立事件段数：间隔 < min_gap 个交易日的 True 段合并为一段（滤掉日级噪声穿越阈值，
    否则倒挂等会被噪声灌水成几十段、高估可靠性）。稀有体制的真实样本量看这个，不是天数。"""
    m = np.asarray(mask, bool)
    pos = np.where(m)[0]
    if len(pos) == 0:
        return 0
    return 1 + int(np.sum(np.diff(pos) > min_gap))


def _dist(fwd, mask):
    f = fwd[mask].dropna().values * 100
    if len(f) < 20:
        return None
    return {"mean": round(float(f.mean()), 1), "up": round(float((f > 0).mean() * 100)),
            "p10": round(float(np.percentile(f, 10)), 1), "median": round(float(np.median(f)), 1),
            "worst": round(float(f.min()), 1), "n": int(len(f))}


def run(write=True):
    df = pd.read_csv(RAW, index_col="Date", parse_dates=True).sort_index()
    px = df[ASSET].dropna()
    idx = px.index
    fwd = {h: forward_returns(px, h) for h in HORIZONS}         # 前向 h 日收益

    def _align(col):
        return df[col].reindex(idx).ffill(limit=5)

    t10y2y = _align("T10Y2Y")
    vix = _align("VIX")
    credit = _align("CREDIT_SPREAD")
    states = {
        "曲线倒挂 (T10Y2Y<0)": (t10y2y < 0),
        "曲线正常 (T10Y2Y≥0.5)": (t10y2y >= 0.5),
        "VIX 高 (>70分位)": (vix > np.nanpercentile(vix, 70)),
        "VIX 低 (<30分位)": (vix < np.nanpercentile(vix, 30)),
        "信用利差宽 (>70分位)": (credit > np.nanpercentile(credit, 70)),
        "信用利差紧 (<30分位)": (credit < np.nanpercentile(credit, 30)),
    }
    base = {str(h): _dist(fwd[h], pd.Series(True, index=idx)) for h in HORIZONS}
    regimes = []
    for name, mask in states.items():
        m = mask.fillna(False).values
        dist = {str(h): _dist(fwd[h], pd.Series(m, index=idx)) for h in HORIZONS}
        if not any(dist.values()):
            continue
        regimes.append({"state": name, "n_days": int(m.sum()), "n_episodes": _episodes(m), "dist": dist})

    inv = next((r for r in regimes if r["state"].startswith("曲线倒挂")), None)
    verdict = _verdict(inv, base)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asset": ASSET, "date_range": [str(idx[0].date()), str(idx[-1].date())],
        "horizons_td": HORIZONS, "horizon_labels": ["1月", "3月", "6月", "12月"],
        "base": base, "regimes": regimes, "verdict": verdict,
        "verdict_en": _verdict(inv, base, lang="en"),
        "caveat": "出格区·把「当前体制」补成「体制→未来收益分布」。描述性、非预测、非建议。"
                  "稀有体制(倒挂)日高度自相关 → 看 n_episodes(独立事件段)而非 n_days：段数少(就几段)的分布不可靠、"
                  "别当规律；相关≠因果(体制与收益可能同被第三因素驱动)；重叠窗口只看分布不算显著性。每跑 append 计分。",
    }
    if write:
        from util_io import write_json
        write_json("regime_forward.json", out)
        _log(out)
        print(f"[OK] regime_forward.json — {verdict}")
        for r in regimes:
            d12 = r["dist"].get("252") or {}
            print(f"  {r['state']}: {r['n_days']}日/{r['n_episodes']}段 · 12月 中位{d12.get('median')}% 上涨{d12.get('up')}% 最差{d12.get('worst')}%")
    return out


def _verdict(inv, base, lang="zh"):
    """lang="en" 出英文版(数据层双语·2026-08-25):evidence_ledger 等下游透传本裁决,
    此前它们在 EN 模式只能回落中文。英文与中文由**同一份数字**拼出,不会漂移。"""
    if not inv:
        return "样本不足" if lang == "zh" else "Insufficient sample"
    d12 = inv["dist"].get("252") or {}
    b12 = base.get("252") or {}
    if d12.get("median") is None:
        return "倒挂段样本不足，无定论" if lang == "zh" else "Too few inversion episodes — inconclusive"
    if lang == "en":
        return (f"After a curve inversion, S&P 500 over the next 12 months: median {d12['median']}%, "
                f"up-rate {d12['up']}% (vs base-rate median {b12.get('median')}%) — but only "
                f"{inv['n_episodes']} independent inversion episodes, so the distribution is unreliable; "
                f"do not treat it as a rule")
    return (f"曲线倒挂后 SP500 未来12月：中位 {d12['median']}%、上涨率 {d12['up']}%（vs 基率中位 {b12.get('median')}%）"
            f"——但仅 {inv['n_episodes']} 个独立倒挂段，分布不可靠，别当规律")


def _log(out):
    from util_io import append_daily_log
    today = datetime.date.today().isoformat()
    append_daily_log(LOG, ["date", "verdict"], [[today, out["verdict"]]], date=today)


if __name__ == "__main__":
    run()
