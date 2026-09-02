"""
weekly_report.py — 统计评估报告（滚动生成，模型的"体检报告"）

不是新闻层，是数学层：实盘命中率（按模型版本）、样本外验证、校准质量、
当前市场状态在历史分布中的位置、模拟盘表现。→ web/report.json
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
WEB_DIR  = Path(__file__).parent.parent / "web"


def main():
    with open(WEB_DIR / "signals.json", encoding="utf-8") as f:
        sig = json.load(f)
    sections = []

    # ── 1. 实盘成绩单（按模型版本）────────────────────────────────
    lt = sig.get("live_tracking", {})
    if lt.get("n_logged"):
        rows, rows_en = [], []
        for v, s in (lt.get("by_version") or {}).items():
            # 中英两份行**由同一批取值构建**(h1/h5 只算一次) —— 不是各写一遍,免得日后改了一边
            h1 = f"{s['hit_rate_1d']}%" if s.get("hit_rate_1d") is not None else None
            h5 = f"{s['hit_rate_5d']}%" if s.get("hit_rate_5d") is not None else None
            rows.append({"版本": f"v{v}", "已记录": s.get("n"),
                         "1日命中": h1 or "待回填", "5日命中": h5 or "待回填"})
            rows_en.append({"Version": f"v{v}", "Logged": s.get("n"),
                            "1d hit": h1 or "pending", "5d hit": h5 or "pending"})
        sections.append({
            "title": "实盘成绩单（append-only日志，按模型版本）",
            "title_en": "Live scorecard (append-only log, by model version)",
            "table": rows, "table_en": rows_en,
            "note": f"自 {lt.get('since')} 起共 {lt['n_logged']} 条。命中=方向判断正确"
                    "（prob>50% 且实际上涨，或反之）。样本少时波动大，4周后才有统计意义。",
            "note_en": f"{lt['n_logged']} entries since {lt.get('since')}. A 'hit' means the direction "
                       "call was right (prob>50% and the market rose, or the reverse). Small samples "
                       "swing a lot; this only becomes statistically meaningful after about 4 weeks.",
        })

    # ── 2. 样本外验证（模型的真实能力）────────────────────────────
    wf = sig.get("walk_forward", {})
    if wf.get("summary"):
        s = wf["summary"]
        adv = f"{s.get('mean_tier4_advantage_pp', '?')}pp"
        sigf = f"{s.get('n_significant_folds')}/{s.get('n_folds')}"
        sections.append({
            "title": "Walk-Forward 样本外验证（纳指）",
            "title_en": "Walk-forward out-of-sample validation (NASDAQ)",
            "table": [{"折数": s.get("n_folds"), "Tier≥4样本外优势": adv,
                       "显著折数": sigf, "验证窗口": f"{s.get('horizon_days')}日"}],
            "table_en": [{"Folds": s.get("n_folds"), "Tier>=4 OOS edge": adv,
                          "Significant folds": sigf,
                          "Validation window": f"{s.get('horizon_days')}d"}],
            "note": "负值=高档位信号在没见过的数据上没有跑赢基准。这是模型最诚实的成绩，"
                    "也是为什么显示概率要经过校准、决策要参考校准后概率。",
            "note_en": "A negative number means the high-tier signal did not beat the benchmark on data "
                       "it had never seen. This is the model's most honest scoreline, and it is exactly "
                       "why the displayed probability goes through calibration and why decisions should "
                       "use the calibrated probability.",
        })

    # ── 3. 校准质量 ───────────────────────────────────────────────
    cal = sig.get("calibration_points", [])
    if cal:
        _pairs = [(f"{c['prob']*100:.0f}%", f"{c['actual_wr']*100:.1f}%") for c in cal]
        sections.append({
            "title": "概率校准映射（原始概率 → 历史实际20日胜率）",
            "title_en": "Probability calibration map (raw probability -> actual historical 20-day win rate)",
            "table":    [{"模型概率": a, "实际胜率": b} for a, b in _pairs],
            "table_en": [{"Model probability": a, "Actual win rate": b} for a, b in _pairs],
            "note": "模型原始概率系统性偏低（55%档实际约60-64%），因为基准日上涨概率本身就≈63%。",
            "note_en": "The model's raw probabilities are systematically too low (the 55% bucket actually "
                       "runs about 60-64%), because the base rate of an up day is itself around 63%.",
        })

    # ── 4. 当前状态在历史分布中的位置 ─────────────────────────────
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv",
                         index_col="Date", parse_dates=True)
    ndq = prices["NASDAQ"].dropna()
    ret = ndq.pct_change()
    vol20 = ret.rolling(20).std() * np.sqrt(252) * 100
    vol_pct = float((vol20 < vol20.iloc[-1]).mean() * 100)
    dd = float((ndq.iloc[-1] / ndq.tail(252).max() - 1) * 100)
    rsi_r = ret.clip(lower=0).rolling(14).mean() / ((-ret.clip(upper=0)).rolling(14).mean() + 1e-10)
    rsi = float(100 - 100 / (1 + rsi_r.iloc[-1]))
    # 体制只判一次,中英各取一列(两套 if 迟早漂移 —— 同 cpcv 的做法)
    inverted = prices["VIX"].dropna().iloc[-1] >= prices["VIX3M"].dropna().iloc[-1]
    ts_zh, ts_en = ("倒挂(恐慌)", "Inverted (fear)") if inverted else ("正常", "Normal")
    sections.append({
        "title": "当前市场状态（历史分位）",
        "title_en": "Current market state (historical percentile)",
        "table": [{
            "20日波动率": f"{vol20.iloc[-1]:.0f}%（高于{vol_pct:.0f}%的历史日）",
            "距52周高点": f"{dd:.1f}%", "RSI14": f"{rsi:.0f}", "VIX期限结构": ts_zh,
        }],
        "table_en": [{
            "20d volatility": f"{vol20.iloc[-1]:.0f}% (above {vol_pct:.0f}% of historical days)",
            "From 52w high": f"{dd:.1f}%", "RSI14": f"{rsi:.0f}", "VIX term structure": ts_en,
        }],
        "note": "波动率分位>80%时历史上未来20日胜率下降；倒挂期反而常接近底部（胜率64.8%）。",
        "note_en": "Historically, when the volatility percentile is above 80% the next-20-day win rate "
                   "falls; periods of inversion, by contrast, have often been close to a bottom "
                   "(64.8% win rate).",
    })

    # ── 5. 模拟盘（五策略竞技）────────────────────────────────────
    try:
        with open(WEB_DIR / "paper.json", encoding="utf-8") as f:
            pp = json.load(f)
        _ss = sorted(pp.get("strategies", {}).values(), key=lambda x: -x["ret_pct"])
        rows = [{"策略": s["label"], "净值": f"${s['equity']:,.0f}",
                 "收益": f"{s['ret_pct']:+.2f}%", "仓位": s["position"],
                 "交易": s["n_trades"]} for s in _ss]
        # 策略名/仓位的英文直接取 paper.json 已有的 *_en(单一真相源在 paper_trading,这里不另译)
        rows_en = [{"Strategy": s.get("label_en", s["label"]), "Equity": f"${s['equity']:,.0f}",
                    "Return": f"{s['ret_pct']:+.2f}%",
                    "Position": s.get("position_en", s["position"]),
                    "Trades": s["n_trades"]} for s in _ss]
        if rows:
            sections.append({
                "title": f"模拟盘五策略竞技（自 {pp['start_date']} 各 $10,000）",
                "title_en": f"Five-strategy paper competition (since {pp['start_date']}, $10,000 each)",
                "table": rows, "table_en": rows_en,
                "note": pp.get("note", ""), "note_en": pp.get("note_en", ""),
            })
    except Exception:
        pass

    out = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "model_version": sig.get("model_version"),
        "sections": sections,
    }
    with open(WEB_DIR / "report.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[OK] 统计评估报告：{len(sections)} 个板块 → report.json")


if __name__ == "__main__":
    main()
