"""
daily_brief.py — 每日盘后简报（规则化生成，GitHub Actions 云端全自动）

读取 signals.json + 价格数据，把当天的数字翻译成中文结论 → web/brief.json
"""
import json
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
WEB_DIR = Path(__file__).parent.parent / "web"

TIER_CN = {1: "回避", 2: "偏弱", 3: "中性", 4: "积极", 5: "强烈"}


def pct(a, b):
    return (a / b - 1) * 100


def _dow_en(date_str):
    """'YYYY-MM-DD' → 'Mon'/'Tue'…

    上游 build_signals 现在会直接给 dow_en(单一真相源);这里是**回落**路径——
    读到旧的 signals.json(还没有 dow_en 那版)时按日期现算,不让英文那行开天窗。
    """
    try:
        return pd.Timestamp(date_str).strftime("%a")
    except Exception:
        return ""


def main():
    with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
        sig = json.load(f)
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)

    lines, lines_en = [], []
    # 数据层双语(2026-09-01)：中英**同一处、同一批取值**渲染两次(不是事后再翻)。
    # 简报每句都带条件分支(校准压平/倒挂/高波动/有无宏观事件),事后翻译必然漏掉分支。

    # ── 1. 市场表现 ───────────────────────────────────────────────
    perf, perf_en = [], []
    for name, label, label_en in [("NASDAQ", "纳指", "NASDAQ"), ("SP500", "标普", "S&P 500"),
                                  ("VIX", "VIX", "VIX"), ("BTC", "BTC", "BTC")]:
        if name not in prices.columns:
            continue
        s = prices[name].dropna()
        if len(s) < 2:
            continue
        chg = pct(s.iloc[-1], s.iloc[-2])
        arrow = "▲" if chg > 0 else "▼"
        perf.append(f"{label} {arrow}{abs(chg):.2f}%")
        perf_en.append(f"{label_en} {arrow}{abs(chg):.2f}%")
    last_day = prices["NASDAQ"].dropna().index[-1].strftime("%m-%d")
    lines.append(f"【市场 {last_day}】" + "，".join(perf))
    lines_en.append(f"[Market {last_day}] " + ", ".join(perf_en))

    # ── 2. 信号状态 ───────────────────────────────────────────────
    idx = sig.get("indices", {})
    base_rate = sig.get("base_rate_20d", 0.62)
    base_rate_pct = round(base_rate * 100)
    flat = sig.get("calibration_flat", False)
    sig_parts, sig_parts_en = [], []
    for k, label, label_en in [("NASDAQ", "纳指", "NASDAQ"), ("SP500", "标普", "S&P 500")]:
        s = idx.get(k, {})
        if s:
            raw_pct = round(s["prob"] * 100)
            if flat:
                # 校准曲线压平=模型无样本外区分度，原始概率只是内部分，不当"概率"展示
                sig_parts.append(f"{label}（原始打分{raw_pct}%）")
                sig_parts_en.append(f"{label_en} (raw score {raw_pct}%)")
            elif s.get("prob_cal") is not None:
                cal_pct = round(s["prob_cal"] * 100)
                sig_parts.append(f"{label} 20日上涨概率 {cal_pct}%（校准，原始{raw_pct}%）")
                sig_parts_en.append(f"{label_en} 20-day probability of a gain {cal_pct}% "
                                    f"(calibrated; raw {raw_pct}%)")
            else:
                sig_parts.append(f"{label} 20日上涨概率 {raw_pct}%（原始）")
                sig_parts_en.append(f"{label_en} 20-day probability of a gain {raw_pct}% (raw)")
    if sig_parts:
        if flat:
            # 用无条件基率 base_rate_20d（非 PAV 压平值，后者是测试窗均值会偏高）
            lines.append("【信号】" + "、".join(sig_parts) +
                         f"｜模型无样本外区分度：未来20日上涨概率≈基率 {base_rate_pct}% · 实验性信号")
            lines_en.append("[Signal] " + ", ".join(sig_parts_en) +
                            f" | the model shows no out-of-sample discrimination: the 20-day "
                            f"probability of a gain is ~the base rate of {base_rate_pct}% "
                            "· experimental signal")
        else:
            lines.append("【信号】" + "；".join(sig_parts) +
                         f"｜基率 {base_rate_pct}% · 实验性信号")
            lines_en.append("[Signal] " + "; ".join(sig_parts_en) +
                            f" | base rate {base_rate_pct}% · experimental signal")

    # ── 3. 风险状态（VIX期限结构 + 波动率） ───────────────────────
    risk, risk_en = [], []
    # 成对对齐再取最后一行：两列分别 dropna 会比较不同日期的值（缓存回退时尤甚）
    v = v3 = pd.Series(dtype=float)
    if "VIX" in prices.columns and "VIX3M" in prices.columns:
        pair = prices[["VIX", "VIX3M"]].dropna()
        if len(pair):
            v, v3 = pair["VIX"], pair["VIX3M"]
    if len(v) and len(v3):
        if v.iloc[-1] >= v3.iloc[-1]:
            risk.append(f"⚠ VIX期限结构倒挂（{v.iloc[-1]:.1f} ≥ {v3.iloc[-1]:.1f}）——恐慌状态，"
                        f"但历史上倒挂后20日胜率64.8%，往往接近底部")
            risk_en.append(f"⚠ VIX term structure inverted ({v.iloc[-1]:.1f} >= {v3.iloc[-1]:.1f}) "
                           "— a fear state, though historically the 20-day win rate after an "
                           "inversion has been 64.8%, often close to a bottom")
        else:
            risk.append(f"VIX期限结构正常（{v.iloc[-1]:.1f} < {v3.iloc[-1]:.1f}），无恐慌")
            risk_en.append(f"VIX term structure normal ({v.iloc[-1]:.1f} < {v3.iloc[-1]:.1f}), "
                           "no panic")
    ndq_ret = prices["NASDAQ"].dropna().pct_change()
    vol20 = float(ndq_ret.rolling(20).std().iloc[-1] * (252 ** 0.5) * 100)
    risk.append(f"纳指20日年化波动 {vol20:.0f}%" + ("（高波动）" if vol20 > 25 else ""))
    risk_en.append(f"NASDAQ 20-day annualised volatility {vol20:.0f}%"
                   + (" (high volatility)" if vol20 > 25 else ""))
    lines.append("【风险】" + "；".join(risk))
    lines_en.append("[Risk] " + "; ".join(risk_en))

    # ── 3.5 关键指标红绿灯（直接看的状态层，不进概率模型）─────────
    lights = []
    ndq_s = prices["NASDAQ"].dropna()
    ma200 = float(ndq_s.rolling(200).mean().iloc[-1])
    above = float(ndq_s.iloc[-1]) > ma200
    lights.append({"name": "趋势(MA200)", "name_en": "Trend (MA200)",
                   "status": "green" if above else "red",
                   "value": f"{'上方' if above else '下方'} {abs(ndq_s.iloc[-1]/ma200-1)*100:.1f}%",
                   "value_en": f"{'above' if above else 'below'} {abs(ndq_s.iloc[-1]/ma200-1)*100:.1f}%",
                   "note": "牛熊分界线，下方时一切看空信号加倍认真",
                   "note_en": "The bull/bear dividing line; below it, take every bearish signal "
                              "twice as seriously."})
    if len(v) and len(v3):
        bwd = v.iloc[-1] >= v3.iloc[-1]
        lights.append({"name": "VIX期限结构", "name_en": "VIX term structure",
                       "status": "red" if bwd else "green",
                       "value": f"{v.iloc[-1]:.1f}/{v3.iloc[-1]:.1f}",
                       "note": "倒挂=恐慌（历史上倒挂后20日胜率64.8%，常近底部）",
                       "note_en": "Inversion = fear (historically the 20-day win rate after an "
                                  "inversion has been 64.8%, often close to a bottom)."})
        lights.append({"name": "VIX水平", "name_en": "VIX level",
                       "status": "red" if v.iloc[-1] > 30 else
                       ("yellow" if v.iloc[-1] > 20 else "green"),
                       "value": f"{v.iloc[-1]:.1f}",
                       "note": "<20平静 / 20-30警惕 / >30恐慌",
                       "note_en": "<20 calm / 20-30 wary / >30 panic"})
    if "T10Y2Y" in prices.columns:
        t = prices["T10Y2Y"].dropna()
        if len(t):
            tv = float(t.iloc[-1])
            lights.append({"name": "收益率曲线(10Y-2Y)", "name_en": "Yield curve (10Y-2Y)",
                           "status": "red" if tv < 0 else
                           ("yellow" if tv < 0.3 else "green"),
                           "value": f"{tv:+.2f}%",
                           "note": "倒挂(<0)是历史上最可靠的衰退预警，领先6-18个月",
                           "note_en": "An inversion (<0) is historically the most reliable recession "
                                      "warning, leading by 6-18 months."})
    if "HY_SPREAD" in prices.columns:
        h = prices["HY_SPREAD"].dropna()
        if len(h) > 21:
            hv, hchg = float(h.iloc[-1]), float(h.iloc[-1] - h.iloc[-21])
            lights.append({"name": "信用利差(HY)", "name_en": "Credit spread (HY)",
                           "status": "red" if hv > 5 or hchg > 0.8 else
                           ("yellow" if hv > 4 or hchg > 0.4 else "green"),
                           "value": f"{hv:.2f}%（20日{hchg:+.2f}）",
                           "value_en": f"{hv:.2f}% (20d {hchg:+.2f})",
                           "note": "信用市场比股市先闻到危险；快速走阔=避险",
                           "note_en": "The credit market smells danger before equities do; a rapid "
                                      "widening means risk-off."})

    # ── 4. 未来一周窗口 ───────────────────────────────────────────
    fc = sig.get("next_opportunities", {}).get("all_forecast", [])[:5]
    if fc:
        wk = "，".join(f"{d['date'][5:]}({d['dow_cn']}){d['prob']*100:.0f}%"
                      + ("⚠" + d["macro"] if d.get("macro") else "")
                      for d in fc)
        # 星期几英文按日期现算(signals 只给了 dow_cn),宏观事件名用上游已有的 macro_en
        wk_en = ", ".join(f"{d['date'][5:]}({d.get('dow_en') or _dow_en(d['date'])}){d['prob']*100:.0f}%"
                          + ("⚠" + d.get("macro_en", d["macro"]) if d.get("macro") else "")
                          for d in fc)
        lines.append(f"【未来一周】{wk}")
        lines_en.append(f"[Week ahead] {wk_en}")
        best = max(fc, key=lambda d: d["prob"])
        if best["tier"] >= 4:
            lines.append(f"【提示】{best['date'][5:]}（{best['dow_cn']}）为本周最佳入场窗口"
                         f"（{best['prob']*100:.0f}%），建议尾盘买入")
            lines_en.append(f"[Note] {best['date'][5:]} ({best.get('dow_en') or _dow_en(best['date'])}) is this week's best "
                            f"entry window ({best['prob']*100:.0f}%); buying near the close is "
                            "suggested")

    # ── 5. 宏观事件 ───────────────────────────────────────────────
    macro = sig.get("macro_calendar", [])[:2]
    if macro:
        lines.append("【事件】" + "；".join(f"{m['date'][5:]} {m['label']}" for m in macro)
                     + " —— 当日波动放大，避免重仓操作")
        lines_en.append("[Events] "
                        + "; ".join(f"{m['date'][5:]} {m.get('label_en', m['label'])}" for m in macro)
                        + " — volatility is amplified on the day; avoid large positions")

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "model_version": sig.get("model_version"),
        "lines": lines, "lines_en": lines_en,
        "lights": lights,
    }
    with open(WEB_DIR / "brief.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n".join(lines))
    print(f"[OK] → brief.json")


if __name__ == "__main__":
    main()
