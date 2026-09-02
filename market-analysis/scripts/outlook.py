"""outlook.py — 📈 观点/预测（用户授权的"出格"区：直接给方向 + 看好/看淡，带免责）。

注：本区【有意】越出全站"不预测方向 / 不荐股"——经用户明确授权，集中放这一页、带免责。
全站其余部分仍守"测风险不测方向"。
- 纳指短期方向：用贝叶斯信号 latest_prob / tier 给直白判断（模型直读）。
- 个股看好/看淡：观察池 6 个月（126 日）动量排序，前 3 看好、后 3 看淡，附动量理由。
准确率不藏：免责里指向 🎲 试胆区的公开战绩（方向预测 ≈ 掷硬币）。
"""
import datetime
import json
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS = Path(__file__).parent
RAW = SCRIPTS.parent / "data" / "raw"
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"

DISCLAIMER = ("⚠️ 本区为【观点 / 预测】，仅供参考、非投资建议；市场有风险，据此操作盈亏自负。"
              "方向预测的历史准确率可在 🎲 试胆区查看（提示：≈ 掷硬币）。")


def _signals():
    try:
        return json.load(open(WEB / "signals.json", encoding="utf-8"))
    except Exception:
        return {}


def _momentum(win=126, n=3):
    try:
        df = pd.read_csv(RAW / "stocks_prices.csv", index_col=0, parse_dates=True)
    except Exception:
        return [], []
    px = df.apply(pd.to_numeric, errors="coerce")
    if len(px) < win + 1:
        return [], []
    mom = (px.iloc[-1] / px.iloc[-1 - win] - 1).dropna().sort_values(ascending=False)
    if len(mom) < 2 * n:
        n = max(1, len(mom) // 2)
    mk = lambda s, v, tag: {"symbol": str(s), "view": tag, "mom_pct": round(float(v) * 100, 1),
                            "reason": f"6 个月动量 {round(float(v) * 100, 1):+}%（观察池{'领先' if tag == '看好' else '垫底'}）"}
    top = [mk(s, v, "看好") for s, v in mom.head(n).items()]
    bot = [mk(s, v, "看淡") for s, v in mom.tail(n).items()][::-1]
    return top, bot


def main():
    sig = _signals()
    prob, tier = sig.get("latest_prob"), sig.get("latest_tier")
    index_call = None
    if prob is not None:
        _bull = float(prob) >= 0.5          # 方向只判一次,中英同源
        index_call = {"target": "纳指", "target_en": "NASDAQ",
                      "horizon": "短期", "horizon_en": "short-term",
                      "call": "看涨" if _bull else "看跌",
                      "call_en": "bullish" if _bull else "bearish",
                      "prob": round(float(prob), 3), "tier": tier,
                      "basis": f"贝叶斯信号 prob={round(float(prob), 3)}、tier={tier}（模型直读，非保证）",
                      "basis_en": f"Bayesian signal prob={round(float(prob), 3)}, tier={tier} "
                                  "(read straight off the model; not a guarantee)"}
    top, bot = _momentum()
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index_call": index_call,
        "bullish": top,
        "bearish": bot,
        "disclaimer": DISCLAIMER,
    }
    from util_io import write_json
    write_json("outlook.json", out, allow_nan=False)
    print(f"[OK] outlook — 纳指{index_call['call'] if index_call else '?'}；看好 {len(top)} / 看淡 {len(bot)}")
    return out


if __name__ == "__main__":
    main()
