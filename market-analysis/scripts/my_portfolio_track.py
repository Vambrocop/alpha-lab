"""my_portfolio_track.py — 自选组合前向跟踪(私人·不可回填·非公开计分)

用户 2026-08-26 提的需求:「我模拟选几个股票持有」。已有的 💼 持仓计算器只算**当下**盈亏
(输股数→实时价),缺的是**从某天起按真实价格前向跟踪**。本脚本补这一半。

与 pick_ledger / au_pick_ledger 的关键差异(**刻意不同,别照抄**):
  - 那两个是**固定持有期**(20 交易日)的信号计分,用 forward_ledger.settle;
  - 本脚本是**开放式持有**(拿到你从清单里删掉为止),没有"结算窗口",每跑一次做一次
    mark-to-market。故只复用 forward_ledger.fetch_prices 取价,不用 settle。

诚实设计(为什么这么定):
  1. **入场不可回填**:某只票的入场日/入场价一旦写进账本,**永不重写**——防止事后挑一个
     好看的起点。新加的票按「首次出现的次日首个交易日」入场(与全站账本同一防抢跑规矩)。
  2. **删掉即离场**:从清单里移除 → 记下离场日/价,行保留(不删历史),从此不再更新。
  3. **基准同期对比**:美股对 QQQ、`.AX` 结尾对 ^AXJO(不混算),用**同一段持有期**的
     基准收益,回答「自己选 vs 干脆买指数」。
  4. **默认不进公开计分**:这是你的个人组合、不是模型主张,`public=false` 写在产物里;
     要公开是另一个决定(账本 append-only,公开了不能反悔)。
  5. 非荐股、非预测:只如实记录「你说要拿什么、从哪天起、后来怎么样」。会错,过去≠未来。

输入:`data/my_portfolio.txt`(每行 `代码 [股数]`,# 注释,空行忽略;股数省略=等权 1 份)
账本:`data/my_portfolio_ledger.csv`(append-only,入场行永不改)
输出:`web/my_portfolio.json`(+docs)

运行:$env:PYTHONUTF8='1'; py market-analysis/scripts/my_portfolio_track.py
"""
import datetime
import sys
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import forward_ledger as fl          # 只用它的 fetch_prices(取价单一实现,不重造)

BASE = SCRIPTS.parent
REQ_FILE = BASE / "data" / "my_portfolio.txt"
LOG = BASE / "data" / "my_portfolio_ledger.csv"

BENCH_US = "QQQ"
BENCH_AU = "^AXJO"
FX_SYM = "AUDUSD=X"          # 1 AUD 值多少 USD;美股价 ÷ 它 = 澳元价
HEADER = ["portfolio", "symbol", "aud_invested", "shares", "first_seen", "entry_date",
          "entry_px", "fx_entry", "bench", "bench_entry_px", "exit_date", "exit_px", "status"]


def _bench_for(symbol):
    """澳股(.AX)对 ^AXJO,其余对 QQQ——两市场基准不混算(同 au_pick_ledger 的红线)。"""
    return BENCH_AU if str(symbol).upper().endswith(".AX") else BENCH_US


def read_requests(path=REQ_FILE):
    """读清单 → {(组合名, 代码): 投入澳元}。

    格式 `组合名 代码 澳元`(2026-08-26 起,支持多个盘同台竞技);
    只有两列时视为单盘(组合名默认「我的组合」、第二列当澳元)。文件缺失 → 空(fail-soft)。"""
    out = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            pf, sym, amt = parts[0], parts[1].upper(), parts[2]
        elif len(parts) == 2:
            pf, sym, amt = "我的组合", parts[0].upper(), parts[1]
        else:
            pf, sym, amt = "我的组合", parts[0].upper(), "0"
        try:
            aud = float(amt)
        except ValueError:
            aud = 0.0
        if sym and aud > 0:
            out[(pf, sym)] = aud
    return out


def _next_trading_px(series, after_date, not_after=None):
    """`after_date` **之后**、且不晚于 `not_after` 的首个交易日 (日期, 收盘价);没有 → None。

    用『次日』而非当日:与全站账本同一防抢跑规矩——你今天写下,最早明天才买得到。
    **not_after 是防前视的显式护栏**(测试逼出来的):生产里"明天的收盘价"本来就不存在,
    但绝不能靠"数据恰好没有"来保证正确性——若谁拿历史价格回跑或数据源提前给了未来价,
    没有这道闸就会用未来价入场。故显式钉死:入场价的日期不得晚于 today。"""
    if series is None or not len(series):
        return None
    later = series[series.index > pd.Timestamp(after_date)]
    if not_after is not None:
        later = later[later.index <= pd.Timestamp(not_after)]
    if not len(later):
        return None
    return later.index[0], float(later.iloc[0])


def _aud_px(symbol, px_map, fx, when=None):
    """把某票在 `when`(默认最新)的价格换成**澳元**。
    澳股(.AX)本币即澳元;美股用当日 AUD/USD 折算——汇率波动会真实改变澳元收益,不能忽略。
    返回 (澳元价, 原币价, 汇率) 或 None。"""
    s_ = px_map.get(symbol)
    if s_ is None or not len(s_):
        return None
    if when is None:
        d, raw = s_.index[-1], float(s_.iloc[-1])
    else:
        sub = s_[s_.index <= pd.Timestamp(when)]
        if not len(sub):
            return None
        d, raw = sub.index[-1], float(sub.iloc[-1])
    if str(symbol).upper().endswith(".AX"):
        return raw, raw, 1.0
    f = fx[fx.index <= d] if fx is not None and len(fx) else None
    if f is None or not len(f):
        return None
    rate = float(f.iloc[-1])                       # 1 AUD = rate USD
    if rate <= 0:
        return None
    return raw / rate, raw, rate


def run(write=True, _px=None, _today=None, _requests=None, _fx=None):
    today = _today or datetime.date.today()
    reqs = read_requests() if _requests is None else dict(_requests)
    rows = fl.read_log(LOG)

    symbols = sorted({sym for (_pf, sym) in reqs} | {r["symbol"] for r in rows if r.get("symbol")})
    px = _px
    fx = _fx
    if px is None:
        if not symbols:
            px = {}
        else:
            start = min([str(r.get("first_seen") or today) for r in rows] + [str(today)])
            start = (pd.Timestamp(start) - pd.Timedelta(days=10)).date().isoformat()
            px = fl.fetch_prices(symbols, start, BENCH_US)
            px.update(fl.fetch_prices([BENCH_AU, FX_SYM], start, BENCH_AU))
    if fx is None:
        fx = px.get(FX_SYM)
        if fx is None:                              # 兜底:本地 AUDUSD.csv(fetch_data_au 产)
            try:
                f = pd.read_csv(BASE / "data" / "raw" / "au" / "AUDUSD.csv",
                                index_col=0, parse_dates=True).iloc[:, 0]
                fx = pd.to_numeric(f, errors="coerce").dropna()
            except Exception:
                fx = None

    def key_of(r):
        return (r.get("portfolio") or "我的组合", r.get("symbol"))

    by_key = {key_of(r): r for r in rows if r.get("symbol")}

    # ── 新行:只登记,入场留给"次日"(不可回填的起点) ────────────────────────
    n_new = 0
    for (pf, sym), aud in reqs.items():
        r = by_key.get((pf, sym))
        if r is not None:
            if str(r.get("status")) != "exited":
                r["aud_invested"] = aud             # 计划投入可改;已锁定的股数/入场价不受影响
            continue
        row = {"portfolio": pf, "symbol": sym, "aud_invested": aud, "shares": "",
               "first_seen": str(today), "entry_date": "", "entry_px": "", "fx_entry": "",
               "bench": _bench_for(sym), "bench_entry_px": "", "exit_date": "", "exit_px": "",
               "status": "pending"}
        rows.append(row)
        by_key[(pf, sym)] = row
        n_new += 1

    # ── 待入场:次日首个交易日成交,按当日澳元价把投入额换成股数(此后永不重写) ──
    n_entered = 0
    for r in rows:
        if r.get("entry_px") not in ("", None) or str(r.get("status")) == "exited":
            continue
        got = _next_trading_px(px.get(r["symbol"]), r["first_seen"], not_after=today)
        bgot = _next_trading_px(px.get(r.get("bench") or _bench_for(r["symbol"])),
                                r["first_seen"], not_after=today)
        if not got or not bgot:
            continue
        conv = _aud_px(r["symbol"], px, fx, when=got[0])
        if conv is None:
            continue                                # 汇率暂缺 → 保持 pending,不瞎折算
        aud_px, raw_px, rate = conv
        try:
            aud = float(r.get("aud_invested") or 0)
        except (TypeError, ValueError):
            aud = 0.0
        if aud <= 0 or aud_px <= 0:
            continue
        r["shares"] = round(aud / aud_px, 6)        # 股数锁定(允许小数股:模拟盘)
        r["entry_date"], r["entry_px"] = got[0].date().isoformat(), round(raw_px, 4)
        r["fx_entry"] = round(rate, 6)
        r["bench_entry_px"] = round(bgot[1], 4)
        r["status"] = "open"
        n_entered += 1

    # ── 从清单删掉 → 记离场(行保留) ─────────────────────────────────────────
    n_exit = 0
    for r in rows:
        if str(r.get("status")) != "open" or key_of(r) in reqs:
            continue
        s_ = px.get(r["symbol"])
        if s_ is not None and len(s_):
            r["exit_date"], r["exit_px"] = s_.index[-1].date().isoformat(), round(float(s_.iloc[-1]), 4)
        r["status"] = "exited"
        n_exit += 1

    # ── mark-to-market:每个盘的澳元市值 vs 起始本金 ─────────────────────────
    books, pend = {}, []
    for r in rows:
        pf = r.get("portfolio") or "我的组合"
        st = str(r.get("status"))
        if st == "pending":
            pend.append({"portfolio": pf, "symbol": r["symbol"],
                         "aud_invested": float(r.get("aud_invested") or 0), "status": "pending"})
            continue
        try:
            shares = float(r["shares"]); aud_in = float(r["aud_invested"])
        except (TypeError, ValueError):
            continue
        when = r.get("exit_date") if st == "exited" else None
        conv = _aud_px(r["symbol"], px, fx, when=when)
        if conv is None:
            continue
        aud_now = conv[0] * shares
        b = books.setdefault(pf, {"portfolio": pf, "invested_aud": 0.0, "value_aud": 0.0,
                                  "positions": [], "closed": []})
        item = {"symbol": r["symbol"], "shares": shares, "aud_invested": round(aud_in, 2),
                "value_aud": round(aud_now, 2),
                "ret_pct": round((aud_now / aud_in - 1) * 100, 2) if aud_in > 0 else None,
                "entry_date": r.get("entry_date"), "entry_px": r.get("entry_px"),
                "fx_entry": r.get("fx_entry"), "status": st,
                "exit_date": r.get("exit_date") or None}
        if st == "exited":
            b["closed"].append(item)
        else:
            b["positions"].append(item)
            b["invested_aud"] += aud_in
            b["value_aud"] += aud_now

    for b in books.values():
        b["invested_aud"] = round(b["invested_aud"], 2)
        b["value_aud"] = round(b["value_aud"], 2)
        b["ret_pct"] = (round((b["value_aud"] / b["invested_aud"] - 1) * 100, 2)
                        if b["invested_aud"] > 0 else None)
        b["positions"].sort(key=lambda x: x["ret_pct"] if x["ret_pct"] is not None else -999,
                            reverse=True)

    ranked = sorted(books.values(),
                    key=lambda b: b["ret_pct"] if b["ret_pct"] is not None else -999, reverse=True)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "public": False,
        "currency": "AUD",
        "fx_note": "美股按各自入场日/当日 AUD/USD 折成澳元;汇率波动会真实改变澳元收益,已计入。",
        "n_portfolios": len(ranked), "n_pending": len(pend),
        "portfolios": ranked, "pending": pend,
        "honesty": [
            "这是**你自己定的**模拟盘对决,不是荐股、不是预测、不是买卖建议。",
            "入场不可回填:每笔按「写进清单的**次日**首个交易日」真实收盘价成交,股数与入场价"
            "一旦记入账本永不重写——防止事后挑一个好看的起点。",
            "澳元记账:美股价按当日 AUD/USD 折算,**汇率影响已计入**(澳洲税务居民的真实体验)。",
            "不含手续费/买卖价差/税/股息(含息会让指数盘更占优),是理想化模拟,真实结果更差。",
            "**样本极小、时间极短**——三个月内谁领先都说明不了本事,别据此加码或改主意。",
            "对照的意义在于:一年后你能亲眼看到「自己选」和「干脆买指数」差多少。",
            "未进公开计分(public=false);会错,过去≠未来。",
        ],
    }

    if write:
        from util_io import write_json
        write_json("my_portfolio.json", out, allow_nan=False)
        fl.write_log(LOG, HEADER, rows)
        print(f"[OK] my_portfolio.json — {len(ranked)} 个盘 · 待入场 {len(pend)} 笔")
        print(f"  新登记 {n_new} · 新入场 {n_entered} · 新离场 {n_exit}")
        for b in ranked:
            r_ = ("%+.2f%%" % b["ret_pct"]) if b["ret_pct"] is not None else "—"
            print(f"    {b['portfolio']:<10} A${b['value_aud']:>10,.2f} / A${b['invested_aud']:>10,.2f}  {r_}")
    return out


if __name__ == "__main__":
    try:
        run()
    except Exception as e:      # 顶层 fail-soft:私人区不阻断流水线
        print(f"[自选组合] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        raise SystemExit(0)
