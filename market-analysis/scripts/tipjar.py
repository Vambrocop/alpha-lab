"""tipjar.py — 🎲 试胆区（娱乐/试胆，非建议）。

一个【朴素玩具】方向预测器：每个交易日按 "今天涨→赌明天涨"(naive momentum) 给纳指次日
涨/跌一个判断，进 append-only 擂台、回填真涨跌、公示滚动命中率。

🔴 与全站红线的关系：这里【故意】下方向判断，但被关进"娱乐 + 公开战绩"的笼子——
按本站自己的研究，日方向预测 ≈ 掷硬币；看战绩别看单条，**不构成任何买卖建议**。
诚实保护：规则固定且公开(无 cherry-pick) · 每条都带结果 · 命中率算全部已结算条目 ·
append-only + 哈希链。规则确定性：从 combined_prices.csv 可完全重算（日志丢了 CI 也重建同样结果）。
"""
import datetime
import json
import sys
from pathlib import Path

import pandas as pd

from ledger_hash import HASH_COLS, seal_hash_chain

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS = Path(__file__).parent
RAW = SCRIPTS.parent / "data" / "raw"
PROC = SCRIPTS.parent / "data" / "processed"
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"
LOG = PROC / "tipjar_log.csv"
RULE = "naive_momentum"

DATA_COLS = ["logged_at", "as_of", "target_date", "call", "rule", "actual_ret", "actual", "hit"]
COLS = DATA_COLS + HASH_COLS
HASH_FIELDS = DATA_COLS

CAVEAT = ("🎲 试胆区：一个【朴素玩具】预测器，公开记分给你看准不准。这是娱乐/试胆，"
          "**不是任何买卖建议**；按本站自己的研究，日方向预测 ≈ 掷硬币（命中率贴着 50% 才是常态）。"
          "**看战绩别看单条**——这页的意义就是让你亲眼看预测有多不靠谱。")
CAVEAT_EN = ("TIP-JAR: a deliberately naive toy predictor, scored in public so you can see how (in)accurate it is. "
             "This is entertainment, **not trading advice**; by this site's own research, daily direction "
             "prediction is about a coin flip (a hit rate hugging 50% is the norm). "
             "**Look at the track record, not any single call** — the point of this page is to let you see for "
             "yourself how unreliable predictions are.")


def _nasdaq():
    df = pd.read_csv(RAW / "combined_prices.csv", index_col=0, parse_dates=True)
    return pd.to_numeric(df["NASDAQ"], errors="coerce").dropna()


def _load_old():
    if LOG.exists():
        try:
            return {str(r["as_of"]): r for r in pd.read_csv(LOG).to_dict("records")}
        except Exception:
            return {}
    return {}


def build_log():
    """从价格序列确定性重建擂台：as_of=D 用 ret[D] 作动量信号，赌 D+1 方向；D+1 已知则回填。"""
    nas = _nasdaq()
    ret = nas.pct_change()
    dates = list(nas.index)
    old = _load_old()
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for i in range(1, len(dates)):
        if pd.isna(ret.iloc[i]):
            continue
        ds = dates[i].strftime("%Y-%m-%d")
        prev = old.get(ds)
        if prev is not None and pd.notna(prev.get("hit")):
            rows.append({k: prev.get(k) for k in DATA_COLS})   # 已结算 → 冻结（append-only）
            continue
        call = "UP" if ret.iloc[i] >= 0 else "DOWN"
        logged = prev.get("logged_at") if prev else now
        tgt = dates[i + 1].strftime("%Y-%m-%d") if i + 1 < len(dates) else None
        if i + 1 < len(dates) and pd.notna(ret.iloc[i + 1]):
            ar = float(ret.iloc[i + 1])
            actual = "UP" if ar >= 0 else "DOWN"
            rows.append({"logged_at": logged, "as_of": ds, "target_date": tgt, "call": call,
                         "rule": RULE, "actual_ret": round(ar * 100, 2), "actual": actual,
                         "hit": 1 if actual == call else 0})
        else:
            rows.append({"logged_at": logged, "as_of": ds, "target_date": tgt, "call": call,
                         "rule": RULE, "actual_ret": None, "actual": None, "hit": None})
    df = pd.DataFrame(rows, columns=DATA_COLS)
    return seal_hash_chain(df.reindex(columns=COLS), HASH_FIELDS)


def scorecard(log):
    """纯函数：从擂台算战绩（命中率算全部已结算条目，无 cherry-pick）。"""
    scored = log[log["hit"].notna()]
    n = int(len(scored))
    hits = int(scored["hit"].astype(float).sum()) if n else 0
    last20 = scored.tail(20)
    pend = log[log["hit"].isna()]
    latest = pend.iloc[-1] if len(pend) else (log.iloc[-1] if len(log) else None)
    return {
        "rule": "naive_momentum（今天涨→赌明天涨，朴素玩具）",
        "rule_en": "naive_momentum (up today -> bet up tomorrow; a deliberately naive toy)",
        "n_scored": n, "hits": hits,
        "hit_rate": round(hits / n * 100, 1) if n else None,
        "hit_rate_last20": round(float(last20["hit"].astype(float).mean()) * 100, 1) if len(last20) else None,
        "latest": ({"as_of": str(latest["as_of"]), "target_date": (None if pd.isna(latest["target_date"]) else str(latest["target_date"])),
                    "call": str(latest["call"])} if latest is not None else None),
        "recent": [{"as_of": str(r["as_of"]), "call": str(r["call"]), "actual": (None if pd.isna(r["actual"]) else str(r["actual"])),
                    "hit": (None if pd.isna(r["hit"]) else int(r["hit"]))} for r in scored.tail(12).to_dict("records")],
        "caveat": CAVEAT, "caveat_en": CAVEAT_EN,
    }


def main():
    log = build_log()
    log.to_csv(LOG, index=False)
    out = scorecard(log)
    out["generated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    from util_io import write_json
    write_json("tipjar.json", out, allow_nan=False)
    print(f"[OK] tipjar — 战绩 {out['hits']}/{out['n_scored']}"
          + (f" = {out['hit_rate']}%（≈掷硬币就对了）" if out["hit_rate"] is not None else "")
          + (f"；最新判断 {out['latest']['as_of']}→{out['latest']['call']}" if out["latest"] else ""))
    return out


if __name__ == "__main__":
    main()
