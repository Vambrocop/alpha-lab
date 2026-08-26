"""evidence_ledger.py — 证据库总览（吸收 daily_stock 的 regime+evidence 卡片纪律）。

四站都"AI叫你买"、规律不带证据。这里把全站【已测规律族】汇成一张总览：每族一行，
强制带 scope(适用条件) + 证据(live headline) + 裁决 + 详情链接——**没证据进不了库**。
不重复聚合子规律(那些在 self_growing/seasonal 各页已有)；这是"什么成立/什么被证伪"的单一诚实入口。

只读现有产物聚合，非新统计、非荐股。每跑刷新 evidence.json（web+docs）。
"""
import json
import datetime
from pathlib import Path

BASE = Path(__file__).parent.parent
WEB = BASE / "web"


def _load(name):
    try:
        return json.loads((WEB / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def run(write=True):
    rows = []

    ad = _load("autodiscovery.json")
    if ad and ad.get("summary"):
        s = ad["summary"]
        rows.append({"name": "系统自动发现(FDR引擎)", "family": "系统",
                     "scope": "日历/超跌反弹/因子 · 42 预声明候选 · 跨族 BY-FDR",
                     "evidence": f"真存活 {s.get('n_survive', 0)} · 已淡 {s.get('n_faded', 0)} · 死 {s.get('n_dead', 0)} · 无定论 {s.get('n_inconclusive', 0)}",
                     "verdict": "多数是噪声(诚实):预声明全进分母、禁挑好看的", "link": "self_growing.html",
                     "name_en": "Automated discovery (FDR engine)", "family_en": "System",
                     "scope_en": "Calendar / oversold-bounce / factors · 42 pre-registered candidates · cross-family BY-FDR",
                     "evidence_en": f"survived {s.get('n_survive', 0)} · faded {s.get('n_faded', 0)} · dead {s.get('n_dead', 0)} · inconclusive {s.get('n_inconclusive', 0)}",
                     "verdict_en": "Most are noise (honest): every pre-registered candidate counts in the denominator; no cherry-picking"})

    pb = _load("placebo_tests.json")
    if pb and pb.get("tests"):
        ts = pb["tests"]
        faded = sum(1 for t in ts if t.get("recent_significant") is False)
        rows.append({"name": "季节/日历效应", "family": "日历",
                     "scope": "周几/月份/圣诞/节前/十年位/任期年 · 日频 S&P500",
                     "evidence": f"{len(ts)} 项检验 · 多数全样本过但现代段已淡({faded} 项)或检验力不足",
                     "verdict": "民俗日历多被套利/样本不足——别当可交易", "link": "seasonal.html",
                     "name_en": "Seasonal / calendar effects", "family_en": "Calendar",
                     "scope_en": "Day-of-week / month / Christmas / pre-holiday / decade digit / term year · daily S&P 500",
                     "evidence_en": f"{len(ts)} tests · most pass on the full sample but have faded in the modern era ({faded}) or lack power",
                     "verdict_en": "Folk calendar effects are mostly arbitraged away or under-powered — not tradeable"})

    bt = _load("btc_nasdaq.json")
    if bt:
        rows.append({"name": "BTC动量→纳指方向", "family": "动量",
                     "scope": "BTC 20日动量 ±5% · 前向20日",
                     "evidence": f"条件上涨率差 {bt.get('cond_pos_minus_neg_uprate_pp', '—')}pp · 4 体制段同号",
                     "verdict": bt.get("verdict", "—"), "link": "btcread.html",
                     "name_en": "BTC momentum -> NASDAQ direction", "family_en": "Momentum",
                     "scope_en": "BTC 20-day momentum +/-5% · 20-day forward",
                     "evidence_en": f"conditional up-rate gap {bt.get('cond_pos_minus_neg_uprate_pp', '-')}pp · same sign across 4 regimes",
                     "verdict_en": bt.get("verdict_en") or bt.get("verdict", "-")})

    se = _load("senate_signal.json")
    if se:
        ov = se.get("overall") or {}
        rows.append({"name": "政治钱·参议院交易", "family": "另类数据",
                     "scope": "披露后45天再跟 · 持有~3月 vs SPY · 2012-2020",
                     "evidence": f"跟着买中位输SPY · 整体 {ov.get('mean_excess_pct', '—')}% · 7/14议员正≈掷硬币",
                     "verdict": "披露后买/跟卖都不划算,持有大盘最稳", "link": "senate.html",
                     "name_en": "Political money · Senate trades", "family_en": "Alt data",
                     "scope_en": "Copy 45 days after disclosure · ~3-month hold vs SPY · 2012-2020",
                     "evidence_en": f"copying loses to SPY at the median · overall {ov.get('mean_excess_pct', '-')}% · 7 of 14 senators positive = coin-flip",
                     "verdict_en": "Neither copying buys nor following sells pays after disclosure; holding the index is steadier"})

    rf = _load("regime_forward.json")
    if rf:
        inv = next((r for r in (rf.get("regimes") or []) if str(r.get("state", "")).startswith("曲线倒挂")), {})
        rows.append({"name": "体制→前向收益分布", "family": "体制",
                     "scope": "倒挂/VIX/信用利差 → SP500 未来1/3/6/12月 · 2000+",
                     "evidence": f"倒挂仅 {inv.get('n_episodes', '?')} 个独立事件段 · {rf.get('asset', 'SP500')}",
                     "verdict": rf.get("verdict", "—"), "link": "regimefwd.html",
                     "name_en": "Regime -> forward return distribution", "family_en": "Regime",
                     "scope_en": "Curve inversion / VIX / credit spread -> S&P 500 next 1/3/6/12 months · 2000+",
                     "evidence_en": f"only {inv.get('n_episodes', '?')} independent inversion episodes · {rf.get('asset', 'SP500')}",
                     "verdict_en": rf.get("verdict_en") or rf.get("verdict", "-")})

    ts = _load("treasury_stock_link.json")
    if ts:
        nq = ((ts.get("assets") or {}).get("NASDAQ") or {})
        cells = (nq.get("level") or []) + (nq.get("direction") or [])
        sep = [c for c in cells if c.get("ci_vs_base") in ("above_base", "below_base")]
        n_all = len((ts.get("assets", {}).get("NASDAQ", {}).get("level") or [])) \
            + len((ts.get("assets", {}).get("NASDAQ", {}).get("direction") or []))
        low1m = next((c for c in cells if c.get("bucket") == "low" and c.get("horizon") == 20), {})
        rows.append({"name": "美债利率→美股前向", "family": "宏观",
                     "scope": "10Y收益率水平档/20日涨跌方向 → 纳指·标普 未来1/3/12月 · 2000+",
                     "evidence": f"纳指侧 {len(sep)}/{n_all} 格能与基率分开(低档1月 vs基率 "
                                 f"{low1m.get('diff_mean', '?')}pp·CI {low1m.get('ci95_mean', '—')}) · "
                                 f"{ts.get('diagnostics_summary', '')[:60]}",
                     "verdict": "只有「低利率档·1月」分得开;方向档几乎无信号;长窗口其实是宏观年代(高档跨时代翻转)——非可交易edge",
                     "link": "treasury.html",
                     "name_en": "Treasury yields -> US stock forward returns", "family_en": "Macro",
                     "scope_en": "10Y yield level tercile / 20-day change -> NASDAQ & S&P next 1/3/12 months · 2000+",
                     "evidence_en": f"{len(sep)}/{n_all} NASDAQ cells separate from the base rate (low bucket 1-month: "
                                    f"{low1m.get('diff_mean', '?')}pp vs base, CI {low1m.get('ci95_mean', '-')})",
                     "verdict_en": "Only the low-yield 1-month cell separates; the direction dimension shows no reliable signal; "
                                   "longer windows really reflect which macro epoch you are in (high bucket flips sign across eras) — not a tradeable edge"})

    ov = _load("overreaction.json")
    if ov and ov.get("status") == "ok":
        f = ov.get("full") or {}
        rows.append({"name": "跌后反弹(R3短期反转)", "family": "反弹",
                     "scope": "极端下跌日 → 次日 · 全样本+现代段",
                     "evidence": f"现代段 verdict={ov.get('verdict', '—')} · 但仍约半数次日下跌",
                     "verdict": "小条件边际·会被成本吃掉·非抄底信号", "link": "dashboard.html",
                     "name_en": "Post-drop bounce (R3 short-term reversal)", "family_en": "Bounce",
                     "scope_en": "Extreme down days -> next day · full sample + modern era",
                     "evidence_en": f"modern-era verdict={ov.get('verdict', '-')} · yet about half of next days still fall",
                     "verdict_en": "A tiny conditional edge, eaten by costs — not a dip-buying signal"})

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": len(rows), "rows": rows,
        "note": "全站已测规律族总览。每行强制带 scope+证据+裁决+详情链接——没证据不进库。"
                "诚实立场:大多数'规律'测下来是噪声/已淡/不可靠,真存活的极少且都标了不确定性。非荐股·会错·过去≠未来。",
        "note_en": "Overview of every rule family we have tested. Each row must carry scope + evidence + verdict + a detail link — "
                   "no rule enters without evidence. Honest stance: most 'rules' turn out to be noise / faded / unreliable; "
                   "the few that survive all carry their uncertainty. Not advice · can be wrong · the past != the future.",
    }
    if write:
        from util_io import write_json
        write_json("evidence.json", out)
        print(f"[OK] evidence.json — {len(rows)} 个规律族")
        for r in rows:
            print(f"  {r['name']}: {r['verdict'][:40]}")
    return out


if __name__ == "__main__":
    run()
