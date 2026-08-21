"""scorecard.py — 公开计分/校准卡（吸收·做实「敢预测敢认账」护城河）。

四站调研发现：大家都「AI 叫你买」却不亮自己的战绩/校准——亮战绩+校准就是差异化。
把散落的预测追踪汇成一张公开卡，核心=**校准**：按置信分桶看实际命中率（高置信真更准吗？）。

两块：
1) 模型 OOS 校准（walk_forward_results.json 的 oos_calibration·2012-2024 真历史）→ 当下就有料，
   且诚实呈现「纳指方向 walk-forward 无 OOS edge」=高置信≠更准。
2) Live 预测追踪：prediction_log（纳指方向·已有前向）、composite_log（倾向→对纳指前向）、
   tipjar（玩具·已 hit）——刚起步、样本少，随时间填充；不可验证(前向未走完)标 pending。

非荐股·描述性·会错·过去≠未来。每跑刷新 scorecard.json（web+docs）。
"""
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent.parent
PROC = BASE / "data" / "processed"
RAW = BASE / "data" / "raw" / "combined_prices.csv"
H = 20                                              # 前向交易日


def _nasdaq():
    df = pd.read_csv(RAW, index_col="Date", parse_dates=True).sort_index()
    return df["NASDAQ"].dropna()


def _fwd_hit(nq, d, bullish, h=H):
    """从 d 起 h 交易日纳指方向是否匹配 bullish；前向不足→None(pending)。"""
    i = int(nq.index.searchsorted(pd.Timestamp(d)))
    if i >= len(nq) or i + h >= len(nq):
        return None
    up = bool(nq.iloc[i + h] / nq.iloc[i] - 1 > 0)
    return up == bullish


def _stance_dir(s):
    s = str(s)
    if "积极" in s:
        return True
    if "防御" in s:
        return False
    return None                                     # 中性/其他 → 不计方向


def _model_calibration():
    """模型 OOS 校准曲线（prob 分桶→实际胜率）——有无随置信单调上升=有无 edge。"""
    try:
        wf = json.loads((PROC / "walk_forward_results.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    rows = (wf.get("oos_calibration") or {}).get("naive") or []
    out = [{"prob_mean_pct": round(r["prob_mean"] * 100, 1), "real_wr_pct": round(r["actual_wr"] * 100, 1), "n": r["n"]}
           for r in rows if "prob_mean" in r and "actual_wr" in r]
    if len(out) < 2:
        return None
    monotone = all(out[i]["real_wr_pct"] <= out[i + 1]["real_wr_pct"] + 3 for i in range(len(out) - 1))
    n_total = int(sum(r["n"] for r in out))
    # 市场 H 日窗口的【无条件上涨基率】≈ naive 各桶按样本加权的实际胜率均值（数据算出、不写死，
    # 供前端诚实横幅引用：高胜率多半来自这个自然漂移，不是择时本事）。
    base_rate_pct = round(sum(r["real_wr_pct"] * r["n"] for r in out) / n_total, 1) if n_total else None
    return {"curve": out, "n_total": n_total, "base_rate_pct": base_rate_pct,
            "reads": ("基本单调=略有区分力" if monotone else "不单调=高置信≠更准（无 OOS edge·诚实）")}


def run(write=True):
    nq = _nasdaq()
    sources = {}

    # ① 纳指方向信号（prediction_log·已有前向 ret_20d）
    try:
        pl = pd.read_csv(PROC / "prediction_log.csv")
        pl = pl[pl["index"] == "NASDAQ"].copy()
        pl["ret_20d"] = pd.to_numeric(pl["ret_20d"], errors="coerce")
        pl["prob"] = pd.to_numeric(pl["prob"], errors="coerce")
        sc = pl.dropna(subset=["ret_20d", "prob"])
        hit = float(((sc["ret_20d"] > 0) == (sc["prob"] > 0.5)).mean()) * 100 if len(sc) else None
        sources["纳指方向信号(live)"] = {"n_scored": int(len(sc)), "n_pending": int(len(pl) - len(sc)),
                                   "hit_pct": (None if hit is None else round(hit, 1))}
    except Exception:
        pass

    # ② 综合读数倾向（composite_log → 对纳指前向）
    try:
        cl = pd.read_csv(BASE / "data" / "composite_log.csv")
        hits, pend = [], 0
        for _, r in cl.iterrows():
            bd = _stance_dir(r.get("stance"))
            if bd is None:
                continue
            h = _fwd_hit(nq, r["date"], bd)
            if h is None:
                pend += 1
            else:
                hits.append(h)
        sources["综合读数倾向(live)"] = {"n_scored": len(hits), "n_pending": pend,
                                   "hit_pct": (round(float(np.mean(hits)) * 100, 1) if hits else None)}
    except Exception:
        pass

    # ③ 试胆玩具（tipjar·已 hit）
    try:
        tj = pd.read_csv(PROC / "tipjar_log.csv")
        tj["hit"] = pd.to_numeric(tj["hit"], errors="coerce")
        sc = tj.dropna(subset=["hit"])
        sources["试胆玩具(≈掷硬币基准)"] = {"n_scored": int(len(sc)), "n_pending": 0,
                                     "hit_pct": (round(float(sc["hit"].mean()) * 100, 1) if len(sc) else None)}
    except Exception:
        pass

    # ④ 极端下跌→次日反弹告警（overreaction_alert·敢预测敢认账·append 公开计分）
    try:
        oas = pd.read_csv(PROC / "overreaction_signal_log.csv")
        sett = oas["settled"].astype(str).str.lower().isin(["true", "1"])
        hit = oas.loc[sett, "hit"].astype(str).str.lower().isin(["true", "1"])
        n = int(sett.sum())
        sources["极端下跌→次日反弹(出格)"] = {"n_scored": n, "n_pending": int((~sett).sum()),
                                      "hit_pct": (round(float(hit.mean()) * 100, 1) if n else None)}
    except Exception:
        pass

    # ⑤ LLM 前瞻预测（llm_prediction_log·仅方向档 偏多/偏空·出格·敢预测敢认账）
    # 只计方向下注(偏多/偏空)——「中性」不是方向赌注,计进去会虚高;诚实只看方向命中。
    # BUG 修复(2026-08):此前误用 `bucket`(=实际结果桶)筛选,等于挑"市场真动了的日子"再看
    # 一个几乎只说中性的 LLM 中没中→必然0%(误导)。应按 `direction`(LLM 的预测)筛真·方向下注。
    try:
        lp = pd.read_csv(BASE / "data" / "llm_prediction_log.csv")
        dropped = lp["dropped"].astype(str).str.lower().isin(["true", "1"]) if "dropped" in lp else False
        dirp = lp[lp["direction"].isin(["偏多", "偏空"]) & ~dropped]
        sett = dirp["settled"].astype(str).str.lower().isin(["true", "1"])
        hit = dirp.loc[sett, "hit"].astype(str).str.lower().isin(["true", "1"])
        n = int(sett.sum())
        sources["LLM前瞻方向(出格·live)"] = {"n_scored": n, "n_pending": int((~sett).sum()),
                                        "hit_pct": (round(float(hit.mean()) * 100, 1) if n else None)}
    except Exception:
        pass

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_days": H,
        "model_calibration": _model_calibration(),
        "sources": sources,
        "honest_note": "把散落的预测追踪汇成公开战绩卡。模型 OOS 校准是 2012-2024 真历史；live 各源(综合读数/纳指信号/"
                       "LLM 前瞻方向)刚起步、样本少→随时间填充，不可验证的标 pending。校准=按置信分桶看实际命中——"
                       "高置信≠更准就是诚实负结果(纳指方向 walk-forward 本就无 OOS edge)。非荐股·会错·过去≠未来。",
    }
    if write:
        from util_io import write_json
        write_json("scorecard.json", out)
        mc = out["model_calibration"] or {}
        print(f"[OK] scorecard.json — 模型OOS校准 {len(mc.get('curve', []))} 桶({mc.get('reads', '—')})")
        for k, v in sources.items():
            print(f"  {k}: 命中 {v['hit_pct']}% (已记 {v['n_scored']}/待验 {v['n_pending']})")
    return out


if __name__ == "__main__":
    run()
