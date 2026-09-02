"""
paper_trading.py — 多策略模拟盘（四个"基金经理"同台竞技）

每个策略 $10,000，自 2026-06-10 同日起跑，收盘价机械成交，前向实验绝不回填。
账本 append-only 入 git，无法事后修改。

策略（全部低频，无短线）：
  buyhold  🐢长持：全仓纳指永不卖出（对照组）
  trend    📈趋势：纳指收盘 > MA200 持有，跌破清仓（经典趋势过滤）
  signal   🎯信号：贝叶斯信号 tier>=4 全仓 / tier<=2 清仓 / 3 不动
  momentum 🚀动量：观察池6个月动量前3名等权，每月首个交易日调仓
"""
import sys
import pandas as pd
import json
import re
from pathlib import Path
from util_time import is_final_trading_day
from ledger_hash import HASH_COLS, seal_hash_chain

try:
    sys.stdout.reconfigure(encoding="utf-8")   # 中文 note 在 GBK 控制台不致崩溃/乱码
except Exception:
    pass

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"
LEDGER   = PROC_DIR / "paper_ledger.csv"

START_DATE    = "2026-06-10"
START_CAPITAL = 10000.0

STRATS = {
    "buyhold":  {"label": "🐢 长持",   "desc": "全仓纳指，永不卖出（对照组）",
                 "label_en": "🐢 Buy & hold",
                 "desc_en": "Fully invested in the NASDAQ, never sells (control group)"},
    "trend":    {"label": "📈 趋势",   "desc": "纳指>MA200持有，跌破清仓；低频，适合6-12月持有",
                 "label_en": "📈 Trend",
                 "desc_en": "Hold while the NASDAQ is above its MA200, go to cash when it breaks below; "
                            "low turnover, suited to a 6-12 month horizon"},
    "signal":   {"label": "🎯 信号",   "desc": "贝叶斯信号 tier≥4全仓 / ≤2清仓 / 3不动",
                 "label_en": "🎯 Signal",
                 "desc_en": "Bayesian signal: fully invested at tier>=4 / all cash at tier<=2 / "
                            "unchanged at tier 3"},
    "momentum": {"label": "🚀 动量",   "desc": "观察池6月动量前3等权，每月调仓",
                 "label_en": "🚀 Momentum",
                 "desc_en": "Equal-weighted top 3 by 6-month momentum from the watchlist, "
                            "rebalanced monthly"},
    "overnight": {"label": "🌙 隔夜",  "desc": "每日收盘买QQQ次日开盘卖（已扣每日2bp成本）——验证隔夜异象能否活过交易成本",
                  "label_en": "🌙 Overnight",
                  "desc_en": "Buy QQQ at each close, sell at the next open (2bp of daily cost already "
                             "deducted) — tests whether the overnight anomaly survives trading costs"},
}


# ── 数据层双语(2026-09-01):账本里的 note 是**已写入的历史行,绝不回改**(append-only 铁律)。
# 所以英文在**读取时**重建,不碰 paper_ledger.csv 一个字节。note 是模板生成的固定几种形状,
# 按正则还原、数字原样搬运;认不出的形状原样退回中文(宁可露中文,也不编假英文)。
_NOTE_PATTERNS = [
    (r"^全仓纳指@(\d+)$",              lambda m: f"All-in NASDAQ @{m.group(1)}"),
    (r"^站上MA200，买入@(\d+)$",       lambda m: f"Crossed above MA200, bought @{m.group(1)}"),
    (r"^跌破MA200，清仓@(\d+)$",       lambda m: f"Broke below MA200, went to cash @{m.group(1)}"),
    (r"^tier(\d+)，买入@(\d+)$",      lambda m: f"tier{m.group(1)}, bought @{m.group(2)}"),
    (r"^tier(\d+)，清仓@(\d+)$",      lambda m: f"tier{m.group(1)}, went to cash @{m.group(2)}"),
    (r"^调仓→(.+)$",                   lambda m: f"Rebalanced -> {m.group(1)}"),
    # 符号可选:实际值走 f"{...:+.2f}" 必带 +/-,但别让规则依赖格式化细节(格式一改就静默漏译)
    (r"^隔夜([+-]?[\d.]+)%-成本$",     lambda m: f"Overnight {m.group(1)}% minus costs"),
]


def note_en(note):
    """账本 note 的读时英文重建。认不出 → 原样返回中文。"""
    if not isinstance(note, str) or not note:
        return note
    for pat, fn in _NOTE_PATTERNS:
        m = re.match(pat, note.strip())
        if m:
            return fn(m)
    return note


OVERNIGHT_COST = 0.0002   # 每日双边交易成本 2bp（点差+滑点，零佣金时代的乐观估计）
COLS = ["date", "strategy", "action", "holdings", "cash", "equity", "note", "logged_at"] + HASH_COLS
HASH_FIELDS = ["date", "strategy", "action", "holdings", "cash", "equity", "note", "logged_at"]


def load_ledger():
    if LEDGER.exists():
        raw = pd.read_csv(LEDGER)
        needs_hash_migration = not all(c in raw.columns for c in HASH_COLS)
        if "strategy" in raw.columns:
            # 容忍 CI/本地双写合并产生的乱序与重复（merge=union 后必须去重）
            df = (raw.reindex(columns=COLS)
                    .drop_duplicates(subset=["date", "strategy"], keep="last")
                    .sort_values(["date", "strategy"])
                    .reset_index(drop=True))
            df = seal_hash_chain(df, HASH_FIELDS)
            df.attrs["needs_hash_migration"] = needs_hash_migration
            return df
    return pd.DataFrame(columns=COLS)


def equity_of(holdings, cash, px_map):
    return cash + sum(u * px_map.get(s, 0.0) for s, u in holdings.items())


def main():
    with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
        sig = json.load(f)
    daily_sig = sig["daily_signals"]

    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)
    ndq = prices["NASDAQ"].dropna()
    ma200 = ndq.rolling(200).mean()
    stocks = pd.read_csv(RAW_DIR / "stocks_prices.csv",
                         index_col="Date", parse_dates=True)

    # 隔夜收益序列（overnight_analysis.py 生成，QQQ）
    try:
        ov = pd.read_csv(PROC_DIR / "overnight_daily.csv",
                         index_col="Date", parse_dates=True)
        ov_ret = ov["NASDAQ100"] if "NASDAQ100" in ov.columns else ov.iloc[:, -1]
    except Exception:
        ov_ret = pd.Series(dtype=float)

    ledger = load_ledger()
    needs_hash_migration = bool(ledger.attrs.get("needs_hash_migration", False))
    before_hash = ledger[HASH_COLS].copy() if all(c in ledger.columns for c in HASH_COLS) else None
    # 每个策略的当前状态（重放账本最后一行）
    state = {k: {"cash": START_CAPITAL, "holdings": {}} for k in STRATS}
    done = {k: set() for k in STRATS}
    for _, r in ledger.iterrows():
        st = r["strategy"]
        if st in state:
            state[st] = {"cash": float(r["cash"]),
                         "holdings": json.loads(r["holdings"])}
            done[st].add(str(r["date"]))

    days = [d for d in ndq.index if d.strftime("%Y-%m-%d") >= START_DATE]
    new_rows = []

    for ts in days:
        d = ts.strftime("%Y-%m-%d")
        # 只用官方收盘价成交：盘中临时价(美东16:05前的当日bar)一律跳过，
        # 留给收盘后的下一次运行处理 —— 否则成交价被随机的盘中时刻锚定
        if not is_final_trading_day(d):
            continue
        px_ndq = float(ndq.loc[ts])
        px_map = {"NASDAQ": px_ndq}
        srow = stocks.loc[ts].dropna() if ts in stocks.index else pd.Series(dtype=float)
        px_map.update({s: float(v) for s, v in srow.items()})

        for strat in STRATS:
            if d in done[strat]:
                continue
            s = state[strat]
            action, note = "HOLD", ""

            if strat == "buyhold":
                if not s["holdings"]:
                    s["holdings"] = {"NASDAQ": s["cash"] / px_ndq}
                    s["cash"] = 0.0
                    action, note = "BUY", f"全仓纳指@{px_ndq:.0f}"

            elif strat == "trend":
                above = px_ndq > float(ma200.loc[ts]) if not pd.isna(ma200.loc[ts]) else True
                if above and not s["holdings"]:
                    s["holdings"] = {"NASDAQ": s["cash"] / px_ndq}
                    s["cash"] = 0.0
                    action, note = "BUY", f"站上MA200，买入@{px_ndq:.0f}"
                elif not above and s["holdings"]:
                    s["cash"] = equity_of(s["holdings"], 0.0, px_map)
                    s["holdings"] = {}
                    action, note = "SELL", f"跌破MA200，清仓@{px_ndq:.0f}"

            elif strat == "signal":
                rec = daily_sig.get(d)
                if rec:
                    tier = int(rec["tier"])
                    if tier >= 4 and not s["holdings"]:
                        s["holdings"] = {"NASDAQ": s["cash"] / px_ndq}
                        s["cash"] = 0.0
                        action, note = "BUY", f"tier{tier}，买入@{px_ndq:.0f}"
                    elif tier <= 2 and s["holdings"]:
                        s["cash"] = equity_of(s["holdings"], 0.0, px_map)
                        s["holdings"] = {}
                        action, note = "SELL", f"tier{tier}，清仓@{px_ndq:.0f}"

            elif strat == "overnight":
                # 净值直接按隔夜段收益复利（资金始终隔夜持有、日内空仓）
                r = ov_ret.get(ts)
                if r is None or pd.isna(r):
                    continue   # 数据未到：不写账本行，等数据到了再补（否则永久丢失该日）
                s["cash"] *= (1 + float(r) - OVERNIGHT_COST)
                action, note = "ROLL", f"隔夜{float(r)*100:+.2f}%-成本"

            elif strat == "momentum":
                # 每月首个交易日（或起跑日）调仓：6个月动量前3等权
                is_first = (not s["holdings"] and s["cash"] > 0) or \
                           (ts.month != days[max(0, days.index(ts)-1)].month)
                if is_first and len(srow) >= 3 and ts in stocks.index:
                    pos = stocks.index.get_loc(ts)
                    if pos >= 126:
                        mom = (stocks.iloc[pos] / stocks.iloc[pos-126] - 1).dropna()
                        top3 = mom.sort_values(ascending=False).head(3)
                        cur = set(s["holdings"])
                        if set(top3.index) != cur:
                            total = equity_of(s["holdings"], s["cash"], px_map)
                            s["holdings"] = {sym: (total/3) / px_map[sym]
                                             for sym in top3.index if sym in px_map}
                            s["cash"] = total - sum(u*px_map[sym] for sym, u in s["holdings"].items())
                            action = "REBAL"
                            note = "调仓→" + "+".join(f"{sym}({mom[sym]*100:.0f}%)" for sym in top3.index)

            eq = equity_of(s["holdings"], s["cash"], px_map)
            new_rows.append({
                "date": d, "strategy": strat, "action": action,
                "holdings": json.dumps({k: round(v, 6) for k, v in s["holdings"].items()}),
                "cash": round(s["cash"], 2), "equity": round(eq, 2), "note": note,
                "logged_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            })
            if action not in ("HOLD", "ROLL"):
                print(f"  {d} [{strat}] {action}: {note}  净值=${eq:,.0f}")

    if new_rows:
        ledger = pd.concat([ledger, pd.DataFrame(new_rows)], ignore_index=True)
    ledger = seal_hash_chain(ledger.reindex(columns=COLS), HASH_FIELDS)
    hash_changed = before_hash is None or not before_hash.equals(ledger[HASH_COLS].iloc[:len(before_hash)])
    if new_rows or hash_changed or needs_hash_migration:
        ledger.to_csv(LEDGER, index=False)

    # ── 输出前端 JSON ──────────────────────────────────────────────
    out = {"start_date": START_DATE, "start_capital": START_CAPITAL, "strategies": {}}
    for strat, meta in STRATS.items():
        sub = ledger[ledger["strategy"] == strat].sort_values("date")
        if not len(sub):
            continue
        last = sub.iloc[-1]
        holdings = json.loads(last["holdings"])
        pos_desc = "每日隔夜持有QQQ" if strat == "overnight" else \
                   ("现金" if not holdings else "+".join(holdings))
        pos_desc_en = ("Holds QQQ overnight, every day" if strat == "overnight" else
                       ("Cash" if not holdings else "+".join(holdings)))
        trades = sub[~sub["action"].isin(["HOLD", "ROLL"])]
        out["strategies"][strat] = {
            "label": meta["label"], "desc": meta["desc"],
            "label_en": meta["label_en"], "desc_en": meta["desc_en"],
            "equity": float(last["equity"]),
            "ret_pct": round((float(last["equity"]) / START_CAPITAL - 1) * 100, 2),
            "position": pos_desc, "position_en": pos_desc_en,
            "n_trades": int(len(trades)),
            "last_action": f"{trades.iloc[-1]['date']} {trades.iloc[-1]['note']}" if len(trades) else "—",
            # 英文在**读时**重建(note_en),账本历史行一个字节都不动
            "last_action_en": (f"{trades.iloc[-1]['date']} {note_en(trades.iloc[-1]['note'])}"
                               if len(trades) else "—"),
            "curve": {"dates": sub["date"].tolist(),
                      "equity": [float(x) for x in sub["equity"]]},
            "as_of": str(last["date"]),
        }
    out["note"] = ("五个策略同日起跑、收盘价机械成交、账本不可篡改。"
                   "这是前向实验：时间会告诉我们哪个基金经理称职。")
    out["note_en"] = ("All five strategies started on the same day, trade mechanically at the close, "
                      "and write to a tamper-evident ledger. This is a forward experiment: time will "
                      "tell us which of these fund managers is any good.")
    with open(WEB_DIR / "paper.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    rank = sorted(out["strategies"].items(), key=lambda kv: -kv[1]["ret_pct"])
    print("[OK] 模拟盘：" + " | ".join(
        f"{v['label']} {v['ret_pct']:+.2f}%" for _, v in rank) + " → paper.json")


if __name__ == "__main__":
    main()
