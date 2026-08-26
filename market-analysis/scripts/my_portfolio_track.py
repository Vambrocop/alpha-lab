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
HEADER = ["symbol", "shares", "first_seen", "entry_date", "entry_px",
          "bench", "bench_entry_px", "exit_date", "exit_px", "status"]


def _bench_for(symbol):
    """澳股(.AX)对 ^AXJO,其余对 QQQ——两市场基准不混算(同 au_pick_ledger 的红线)。"""
    return BENCH_AU if str(symbol).upper().endswith(".AX") else BENCH_US


def read_requests(path=REQ_FILE):
    """读清单 → {symbol: shares}。文件缺失 → 空(fail-soft,不炸流水线)。"""
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
        sym = parts[0].upper()
        try:
            shares = float(parts[1]) if len(parts) > 1 else 1.0
        except ValueError:
            shares = 1.0
        if sym:
            out[sym] = shares
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


def run(write=True, _px=None, _today=None, _requests=None):
    today = _today or datetime.date.today()
    reqs = read_requests() if _requests is None else dict(_requests)
    rows = fl.read_log(LOG)

    # ── 取价:账本里出现过的 + 清单里的 + 两个基准 ────────────────────────────
    symbols = sorted(set(reqs) | {r["symbol"] for r in rows if r.get("symbol")})
    px = _px
    if px is None:
        if not symbols:
            px = {}
        else:
            start = min([str(r.get("first_seen") or today) for r in rows] + [str(today)])
            start = (pd.Timestamp(start) - pd.Timedelta(days=10)).date().isoformat()
            px = fl.fetch_prices(symbols, start, BENCH_US)
            px.update(fl.fetch_prices([BENCH_AU], start, BENCH_AU))

    by_sym = {r["symbol"]: r for r in rows if r.get("symbol")}

    # ── 新票:只登记 first_seen,入场留给"次日"(不可回填的起点) ──────────────
    n_new = 0
    for sym, shares in reqs.items():
        if sym in by_sym:
            r = by_sym[sym]
            if str(r.get("status")) == "exited":       # 删掉又加回来 → 视为新一段持有
                continue
            r["shares"] = shares                        # 股数可改(不影响已锁定的入场价)
            continue
        row = {"symbol": sym, "shares": shares, "first_seen": str(today),
               "entry_date": "", "entry_px": "", "bench": _bench_for(sym),
               "bench_entry_px": "", "exit_date": "", "exit_px": "", "status": "pending"}
        rows.append(row)
        by_sym[sym] = row
        n_new += 1

    # ── 待入场行:首见日之后首个交易日成交(入场价一旦写入,后续永不重写) ──────
    n_entered = 0
    for r in rows:
        if r.get("entry_px") not in ("", None) or str(r.get("status")) == "exited":
            continue
        got = _next_trading_px(px.get(r["symbol"]), r["first_seen"], not_after=today)
        bgot = _next_trading_px(px.get(r.get("bench") or _bench_for(r["symbol"])),
                                r["first_seen"], not_after=today)
        if not got or not bgot:
            continue                                    # 还没到次日/暂无价 → 保持 pending
        r["entry_date"], r["entry_px"] = got[0].date().isoformat(), round(got[1], 4)
        r["bench_entry_px"] = round(bgot[1], 4)
        r["status"] = "open"
        n_entered += 1

    # ── 从清单删掉 → 记离场(行保留,历史不抹) ────────────────────────────────
    n_exit = 0
    for r in rows:
        if str(r.get("status")) != "open" or r["symbol"] in reqs:
            continue
        s = px.get(r["symbol"])
        if s is not None and len(s):
            r["exit_date"], r["exit_px"] = s.index[-1].date().isoformat(), round(float(s.iloc[-1]), 4)
        r["status"] = "exited"
        n_exit += 1

    # ── mark-to-market:持有期收益 vs 同期基准 ────────────────────────────────
    holdings, closed = [], []
    for r in rows:
        st = str(r.get("status"))
        if st == "pending":
            holdings.append({"symbol": r["symbol"], "status": "pending",
                             "first_seen": r.get("first_seen"), "note_key": "pending"})
            continue
        try:
            epx = float(r["entry_px"]); bepx = float(r["bench_entry_px"])
        except (TypeError, ValueError):
            continue
        bench = r.get("bench") or _bench_for(r["symbol"])
        if st == "exited":
            last = float(r["exit_px"]) if r.get("exit_px") not in ("", None) else None
            bser = px.get(bench)
            blast = float(bser.iloc[-1]) if bser is not None and len(bser) else None
        else:
            s = px.get(r["symbol"]); bser = px.get(bench)
            last = float(s.iloc[-1]) if s is not None and len(s) else None
            blast = float(bser.iloc[-1]) if bser is not None and len(bser) else None
        if last is None or blast is None:
            continue
        ret = (last / epx - 1) * 100
        bret = (blast / bepx - 1) * 100
        item = {"symbol": r["symbol"], "shares": float(r.get("shares") or 1),
                "status": st, "entry_date": r.get("entry_date"), "entry_px": epx,
                "last_px": round(last, 4), "ret_pct": round(ret, 2),
                "bench": bench, "bench_ret_pct": round(bret, 2),
                "excess_pct": round(ret - bret, 2),
                "exit_date": r.get("exit_date") or None}
        (closed if st == "exited" else holdings).append(item)

    live = [h for h in holdings if h.get("status") == "open"]
    tot_cost = sum(h["entry_px"] * h["shares"] for h in live)
    tot_now = sum(h["last_px"] * h["shares"] for h in live)
    port_ret = ((tot_now / tot_cost - 1) * 100) if tot_cost > 0 else None
    # 组合基准:按各持仓成本权重加权同期基准收益(不是简单平均——权重不同结论会变)
    bench_w = (sum(h["bench_ret_pct"] * h["entry_px"] * h["shares"] for h in live) / tot_cost
               if tot_cost > 0 else None)

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "public": False,                    # 私人前向跟踪,**不进公开计分**(要公开是另一个决定)
        "n_open": len(live), "n_pending": sum(1 for h in holdings if h.get("status") == "pending"),
        "n_exited": len(closed),
        "portfolio": {
            "cost": round(tot_cost, 2), "value": round(tot_now, 2),
            "ret_pct": (None if port_ret is None else round(port_ret, 2)),
            "bench_ret_pct": (None if bench_w is None else round(bench_w, 2)),
            "excess_pct": (None if port_ret is None or bench_w is None else round(port_ret - bench_w, 2)),
        },
        "holdings": sorted(holdings, key=lambda h: h.get("excess_pct") if h.get("excess_pct") is not None else -999,
                           reverse=True),
        "closed": closed,
        "honesty": [
            "这是**你自己选的**模拟组合的前向跟踪,不是模型信号、不是荐股、不是任何买卖建议。",
            "入场不可回填:每只票按「写进清单的**次日**首个交易日」的真实收盘价入场,"
            "入场价一旦记入账本永不重写——防止事后挑一个好看的起点。",
            "从清单删掉即记离场(行保留、历史不抹);删掉再加回视为新一段持有。",
            "基准同期对比:美股对 QQQ、澳股(.AX)对 ^AXJO,两市场不混算;组合基准按成本权重加权。",
            "不含成本/滑点/税/股息,是理想化的模拟;真实结果会更差。",
            "样本极小、时间极短——短期跑赢或跑输**都说明不了本事**,别据此下结论。",
            "**未进公开计分**(public=false):个人组合不同于模型主张;要不要公开是另一个决定。",
        ],
    }

    if write:
        from util_io import write_json
        write_json("my_portfolio.json", out, allow_nan=False)
        fl.write_log(LOG, HEADER, rows)
        p = out["portfolio"]
        print(f"[OK] my_portfolio.json — 持有 {out['n_open']} · 待入场 {out['n_pending']} · 已离场 {out['n_exited']}")
        print(f"  新登记 {n_new} · 新入场 {n_entered} · 新离场 {n_exit}")
        if p["ret_pct"] is not None:
            print(f"  组合 {p['ret_pct']:+}% vs 基准 {p['bench_ret_pct']:+}% → 超额 {p['excess_pct']:+}pp")
    return out


if __name__ == "__main__":
    try:
        run()
    except Exception as e:      # 顶层 fail-soft:私人区不阻断流水线
        print(f"[自选组合] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        raise SystemExit(0)
