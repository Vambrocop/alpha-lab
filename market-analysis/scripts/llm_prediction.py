"""llm_prediction.py — LLM 前瞻预测 · append-only 公开计分（敢预测就敢认账·出格区）。

差异化命门 = 诚实计分,不是吹票机:每天让 LLM 据【真实算出的因子】对标普500(SPY)未来 5 个交易日
出一个方向判断(偏多/偏空/中性)+信心(低/中/高)+一句理由 → 进 append-only 账本 → 满 5 交易日用 SPY
真实涨跌**自动结算**记命中 → 公开胜率(还按信心分桶看「高信心是否真更准」)。边跑边攒。

机械件(账本I/O·取价·前向收益·结算骨架)走 forward_ledger;本文件只留「预测」专属判断:
  - 生成:_gen_prediction()(读 composite_read 真因子 → LLM 出结构化方向)
  - 命中口径:_outcome()(实际 5 日 SPY 收益落哪个桶 == 预测方向 → 命中)

口径(都进 caveat):
- 方向桶:5 交易日 SPY 收益 > +BAND=偏多桶、< −BAND=偏空桶、其间=中性桶(三桶互斥划分)。预测==实际桶则命中。
- 入场 = 预测次日(act after the call,不抢跑);持有 5 交易日;绝对方向(非相对基准)。
- LLM 只据给定因子判断、不许编;**这是会被公开计分的前瞻判断**,不确定就选中性/低信心。
- 诚实预期:LLM 前瞻很可能 ≈ 掷硬币(无 edge),公开计分就是要诚实裁决它到底准不准。
- append-only,绝不改历史行;结算靠网络出错不阻断流水线;非投资建议、会错、过去≠未来。
"""
import datetime
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import forward_ledger as fl
from llm_core import _llm, _llm_key, _active_model

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
WEB = BASE / "web"
LOG = BASE / "data" / "llm_prediction_log.csv"

SYMBOL = "SPY"          # 预测标的:标普500 ETF(绝对方向,bench 设同标的→settle 仅借其等窗口)
HOLD_TD = 5             # 持有 5 个交易日(≈1 周)
BAND = 0.01            # ±1% 定义"中性"桶(5 交易日 SPY 标准差≈1.5–2%,1% 让三桶大致均衡)
DIRECTIONS = ("偏多", "偏空", "中性")
CONFIDENCES = ("低", "中", "高")

HEADER = ["pred_date", "symbol", "direction", "confidence", "reason", "horizon_td",
          "entry_date", "entry_px", "exit_date", "exit_px", "ret_pct", "bucket",
          "hit", "settled", "dropped"]

PREDICTION_PROMPT = """你是给新手讲解的助手。下面是系统【真实算出】的当前市场因子读数（综合倾向：{stance}）：
{facts}

请只基于【上面给出的因子】，对标普500（SPY）未来 5 个交易日做一个方向判断。严格按以下三行格式输出，不要任何别的内容：
方向: 偏多 或 偏空 或 中性
信心: 低 或 中 或 高
理由: 一句话，只用上面的因子，不许编造任何未给出的数据、新闻或事件
铁律：①只能用上面的因子；②这是会被公开记录命中率的前瞻判断，不确定就选"中性"或"低"信心；③不点任何个股、不说买入/卖出。"""


# ── 生成:读真因子 → LLM 出结构化方向(可注入 _llm 旁路;解析失败→None 不污染账本)──
def _factor_summary(cr):
    return "\n".join(f"  - {f.get('name','')}: {f.get('reason','')}" for f in (cr.get("factors") or [])[:8])


def _parse(text):
    """从 LLM 文本解析 {direction, confidence, reason};方向/信心缺失或非法 → None(跳过,不记垃圾)。"""
    if not text:
        return None
    d = re.search(r"方向[:：]\s*(偏多|偏空|中性)", text)
    c = re.search(r"信心[:：]\s*(低|中|高)", text)
    if not d or not c:
        return None
    rm = re.search(r"理由[:：]\s*(.+)", text)
    reason = (rm.group(1).strip() if rm else "")[:120]
    return {"direction": d.group(1), "confidence": c.group(1), "reason": reason}


def _gen_prediction():
    """无 key / 读不到因子 / LLM 失败 / 解析失败 → None(静默跳过生成,不阻断结算)。"""
    if not _llm_key():
        return None
    try:
        cr = json.loads((WEB / "composite_read.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    facts = _factor_summary(cr)
    if not facts:
        return None
    try:
        text = _llm(PREDICTION_PROMPT.format(stance=cr.get("stance", "未知"), facts=facts))
    except Exception as e:
        print(f"[LLM预测] LLM 调用失败(非致命): {e}")
        return None
    return _parse(text)


# ── 「预测」专属:去重键 + 可跟单日 + 命中口径(实际桶 == 预测方向)──────────
def _key(r):
    # 规范化 pred_date(去空格、截 YYYY-MM-DD)→ 防异常格式让"一天一条"去重失效而双记(S1)
    return (str(r.get("pred_date") or "").strip()[:10], r.get("symbol"))


def _followable(r):
    return pd.Timestamp(r["pred_date"]) + pd.Timedelta(days=1)   # 预测次日入场(不抢跑)


def _bucket(ret):
    return "偏多" if ret > BAND else ("偏空" if ret < -BAND else "中性")


def _outcome(sret, bret, r):
    """实际 5 日 SPY 收益落哪个桶;预测方向 == 实际桶 → 命中。bench==symbol 故 bret 不用。"""
    bk = _bucket(sret)
    return {"ret_pct": round(sret * 100, 3), "bucket": bk,
            "hit": bool(r.get("direction") == bk)}


def _settle(rows, px):
    return fl.settle(rows, px, bench=SYMBOL, hold=HOLD_TD, trading_days=True,
                     symbol_key="symbol", followable_of=_followable, outcome_of=_outcome)


# ── 计分:总命中 + 按信心分桶(高信心是否真更准?) ───────────────────────
def _conf_stats(rows, conf):
    s = [r for r in rows if fl.is_true(r.get("settled")) and r.get("confidence") == conf]
    if not s:
        return {"n": 0, "hit_pct": None}
    return {"n": len(s), "hit_pct": round(sum(1 for r in s if fl.is_true(r.get("hit"))) / len(s) * 100, 1)}


def _baseline(settled):
    """**最该问的那个问题**:这个 LLM 有没有赢过"什么都不想"?(2026-09-03 修)

    此前拿"三桶随机基线约 1/3"当参照——那是错的。三个结果桶根本不等概(实测
    中性 ~62% / 偏多 ~20% / 偏空 ~18%),所以真正的门槛是**多数类基线**:
    每天闭着眼睛说出现最多的那一桶,能对多少。59% 相对 33% 像有本事,
    相对 62% 则是**不如什么都不想**。基线写死会随数据漂,故从已结算样本现算。

    返回 {class, pct, n} + LLM 是否显著优于它的单边二项检验 p 值。
    """
    if not settled:
        return None
    from collections import Counter
    from math import comb
    oc = Counter(str(r.get("bucket") or "") for r in settled)
    oc.pop("", None)
    if not oc:
        return None
    cls, cnt = oc.most_common(1)[0]
    n = len(settled)
    p0 = cnt / n
    k = sum(1 for r in settled if fl.is_true(r.get("hit")))
    # 单边精确二项检验 H0:命中率 = 多数类基线。n 只有几十,精确算不用上 scipy。
    pval = sum(comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1))
    return {"class": cls, "pct": round(p0 * 100, 1), "n": n,
            "p_value_vs_llm": round(min(pval, 1.0), 3)}


def _directional_bets(rows):
    """真·方向下注(偏多/偏空)计数。

    "中性"不是赌注 —— scorecard.py 2026-08 已为此修过一次 bug。这里透传出来,
    是因为它决定了这张计分牌**能不能**谈方向能力:若几乎全是中性,那这页衡量的
    其实是"SPY 五天有没有走出 ±1%",不是 AI 的方向判断力。
    """
    d = [r for r in rows if r.get("direction") in ("偏多", "偏空")
         and not fl.is_true(r.get("dropped"))]
    st = [r for r in d if fl.is_true(r.get("settled"))]
    return {"n_total": len(d), "n_settled": len(st),
            "n_hit": sum(1 for r in st if fl.is_true(r.get("hit")))}


def _scorecard(rows):
    settled = [r for r in rows if fl.is_true(r.get("settled"))]
    n = len(settled)
    n_hit = sum(1 for r in settled if fl.is_true(r.get("hit")))
    n_pending, n_dropped = fl.count_pending_dropped(rows)
    return {
        "n_settled": n, "n_hit": n_hit,
        "hit_pct": round(n_hit / n * 100, 1) if n else None,
        "by_confidence": {c: _conf_stats(rows, c) for c in CONFIDENCES},
        "baseline": _baseline(settled),
        "directional": _directional_bets(rows),
        "n_pending": n_pending, "n_dropped": n_dropped,
    }


def _verdict(sc):
    n = sc["n_settled"]
    if n == 0:
        return "刚上线·0 结算——约 1–2 周后才有第一批 AI 前瞻战绩，攒数据中。"
    h = sc["hit_pct"]
    b = sc.get("baseline")
    d = sc.get("directional") or {}
    head = f"已结算 {n} 条 AI 前瞻：命中(预测方向==实际 5 日方向)率 {h}%"

    # 先把最该说的说了:跟"什么都不想"比谁强。不给这个对照,59% 会被读成本事。
    if b:
        gap = round(h - b["pct"], 1)
        cmp_ = (f"作为对照，**每天闭眼说「{b['class']}」**(样本里最常出现的结果)能拿 {b['pct']}%"
                f"——AI {'高' if gap > 0 else '低'} {abs(gap)}pp"
                f"（单边二项检验 p={b['p_value_vs_llm']}）")
        head += f"。{cmp_}"

    # 这页到底在量什么:方向下注太少的话,量的其实是"SPY 五天动没动"
    if d.get("n_settled", 0) < 20:
        head += (f"。**注意口径**:{n} 条里真正押方向(偏多/偏空)的只有 {d.get('n_total', 0)} 条、"
                 f"已结算 {d.get('n_settled', 0)} 条,其余都是「中性」——所以这个命中率主要衡量的是"
                 "「SPY 五天有没有走出 ±1%」,**还不足以谈 AI 的方向判断力**")
    if n < 30:
        return head + f"（n={n} 太小，纯描述、不是结论）。"
    return head + "。样本仍小、重叠窗口未除，别当 edge。"


def run(write=True, prices=None, _gen=None):
    """_gen 可注入(测试旁路 LLM)。今日未记 → 生成 1 条;结算到期行;写 prediction.json + 账本。"""
    rows = fl.read_log(LOG)
    seen = {_key(r) for r in rows}
    today = datetime.date.today().isoformat()

    n_new = 0
    if (today, SYMBOL) not in seen:                          # 一天一条;LLM 只在需要时调(省 token)
        p = (_gen if _gen is not None else _gen_prediction)()
        if p:
            rows.append({"pred_date": today, "symbol": SYMBOL, "direction": p["direction"],
                         "confidence": p["confidence"], "reason": p.get("reason", ""),
                         "horizon_td": HOLD_TD, "entry_date": "", "entry_px": "", "exit_date": "",
                         "exit_px": "", "ret_pct": "", "bucket": "", "hit": "",
                         "settled": False, "dropped": False})
            n_new = 1

    settled_now = 0
    unsettled = [r for r in rows if not fl.is_true(r.get("settled")) and not fl.is_true(r.get("dropped"))]
    if unsettled:
        try:                                                 # 结算靠 yfinance 网络——出错不许拖垮流水线
            if prices is None:
                start = (datetime.date.today() - datetime.timedelta(days=HOLD_TD * 4 + 60)).isoformat()
                prices = fl.fetch_prices([SYMBOL], start, SYMBOL)
            settled_now = _settle(rows, prices)
        except Exception as e:
            print(f"[LLM预测] 结算阶段出错(非致命,跳过本次结算): {e}")

    sc = _scorecard(rows)
    latest = max(rows, key=lambda r: str(r.get("pred_date") or ""), default=None)   # N2:按日期取最新,不靠插入序
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "LLM 据真实算出的因子对 SPY 未来 5 交易日方向出判断 → 前向公开计分",
        "model": _active_model(), "symbol": SYMBOL, "hold_td": HOLD_TD, "band_pct": BAND * 100,
        "track_record": sc,
        "latest": ({"pred_date": latest.get("pred_date"), "direction": latest.get("direction"),
                    "confidence": latest.get("confidence"), "reason": latest.get("reason"),
                    "settled": fl.is_true(latest.get("settled")), "hit": fl.is_true(latest.get("hit")),
                    "ret_pct": _num(latest.get("ret_pct"))} if latest else None),
        "recent": sorted(
            [{"pred_date": r.get("pred_date"), "direction": r.get("direction"),
              "confidence": r.get("confidence"), "reason": r.get("reason"),
              "settled": fl.is_true(r.get("settled")), "dropped": fl.is_true(r.get("dropped")),
              "bucket": r.get("bucket"), "ret_pct": _num(r.get("ret_pct")), "hit": fl.is_true(r.get("hit"))}
             for r in rows], key=lambda x: (x["pred_date"] or ""), reverse=True)[:40],
        "verdict": _verdict(sc),
        "caveat": ("出格区·AI 前瞻预测前向公开计分。LLM 据真实算出的因子对 SPY 未来 %d 交易日出方向"
                   "(偏多/偏空/中性,±%.0f%% 定义中性桶);预测次日入场、绝对方向、append-only 账本。"
                   "**喂真因子防瞎编,但仍是猜**。计分的门槛不是「比瞎猜强」而是「比**什么都不想**强」:"
                   "三个桶不等概(中性占多数),所以对照的是**每天闭眼说多数类**能拿多少——"
                   "这条基线由已结算样本现算、随数据更新,不写死。(2026-09-03 修:此前拿"
                   "『三桶随机基线 1/3』作参照,那个门槛偏松、会把不如常数策略的结果显示成有本事。"
                   "当时的注里其实已经写出该比『总选中性』,只是没实现,现已补上。)"
                   "刚上线样本极小(约 1–2 周首批),别当结论。"
                   "非投资建议、不可交易、会错、过去≠未来。每跑 append 认账,绝不改历史行。"
                   % (HOLD_TD, BAND * 100)),
    }

    if write:
        from util_io import write_json
        write_json("prediction.json", out)
        fl.write_log(LOG, HEADER, rows)
        print(f"[OK] prediction.json — {out['verdict']}")
        print(f"  新增 {n_new} · 本次新结算 {settled_now} · 已结算 {sc['n_settled']} "
              f"(命中 {sc['hit_pct']}%) · 挂账 {sc['n_pending']}")
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    run()
