"""llm_monthly_read.py — LLM「本月回顾」月报（grounded · 诚实 · 带计分）。

把本月【真实算出】的数据聚合成紧凑事实摘要，喂给 LLM 翻成初学者大白话回顾。
铁律（CLAUDE.md「LLM 必须喂真数据、防瞎编」）：
  - 只解释给定数字、不许编、不点具体买卖、带免责
  - LLM 只负责"翻译成人话"，不负责"算出数字"
  - 数据不足（本月 < 5 个交易日读数）→ 强制降置信，加不足警告

DRY：window-independent 的聚合(体制/校准基准)直接 import 自 llm_weekly_read，不复制。
月级 append-only 账本 data/llm_monthly_log.csv（YYYY-MM 去重）。写 web/llm_monthly.json。

本地自测（无 key → 静默跳过）：
    $env:GEMINI_API_KEY='AIza...'; py market-analysis/scripts/llm_monthly_read.py
"""
import calendar
import csv
import datetime
import json
from pathlib import Path

from llm_core import _llm, _llm_key, _active_model
from llm_weekly_read import _load_regime, _load_scorecard_summary   # 复用·不漂移

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
WEB = BASE / "web"
DATA = BASE / "data"
LOG = DATA / "llm_monthly_log.csv"

MONTHLY_PROMPT = """你是给【完全不懂金融的新手】讲解的助手。下面是本月系统【真实算出】的市场读数摘要：

本月：{month_label}（共 {n_days} 个交易日有读数）
本月综合倾向走势（每日真实加权读数·从月初到月末）：
{stance_lines}
月末市场环境（客观描述，非预测）：
{regime_lines}
追踪记录参考（历史回测，非 live 预测）：模型基准胜率 {base_rate_pct}%（样本 {n_total} 个）

请用 5-7 句【大白话中文】，向一个新手回顾「这个月市场大环境整体怎么走、倾向是变积极还是变防御、月末处于什么状态」。
铁律：
1. 只用上面给出的数字/事实，绝不编造任何未给出的数据、新闻、事件或具体原因；
2. 【说人话】凡用到专业词（如 VIX、收益率曲线、信用利差、相关性），必须紧跟一个小括号、用最朴素一句话解释；
3. 不要出现内部打分数字（如 0.13、0.52）；用"偏积极／偏防御／中性、略有收紧／略有放松"这类词；
4. 不点任何具体股票名、不说"买入/卖出某某"；
5. 结尾加一句"（这是数据回顾不是预测，会错，过去不代表未来）"；
6. 若上面交易日数 < 5：你【只能】给"弱/不确定"倾向，必须先加一句"⚠️ 本月数据不充分（{n_days}天），本回顾可信度低"。
只输出回顾文字本身，不要标题、不要列表、不要重复上面的数字清单。"""


def _month_key(d):
    return f"{d.year}-{d.month:02d}"


def _month_label(d):
    return f"{d.year}年{d.month}月"


def _month_label_en(d):
    """英文月份名(月读标题用);中文那份是喂给 LLM 的提示词,不动。"""
    return d.strftime("%B %Y")


_DEGREES = ((0.4, "（偏积极·较强）"), (0.13, "（偏积极·偏弱）"),
            (-0.13, "（中性）"), (-0.4, "（偏防御·偏弱）"))


def _degree(score):
    try:
        sc = float(score)
    except (ValueError, TypeError):
        return ""
    for thr, word in _DEGREES:
        if sc >= thr:
            return word
    return "（偏防御·较强）"


def _load_composite_month(today):
    """composite_log.csv 取本日历月(YYYY-MM)所有行。文件缺失 → []（防御降级）。"""
    path = DATA / "composite_log.csv"
    if not path.exists():
        return []
    key = _month_key(today)
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    d = datetime.date.fromisoformat(row["date"])
                except (KeyError, ValueError):
                    continue
                if _month_key(d) == key:
                    rows.append({"date": row["date"], "stance": row.get("stance", ""),
                                 "score": row.get("score", "")})
    except Exception:
        return []
    return rows


def _format_stance_lines(rows):
    """月内各日 stance → 喂 prompt 的字符串 + stance 列表(存 JSON)。score 转程度词、不暴露原始浮点。
    超过 ~12 天则抽样(月初/月中/月末代表)，避免 prompt 过长。"""
    if not rows:
        return "（本月暂无综合读数数据）", []
    stances = [r["stance"] or "未知" for r in rows]
    show = rows if len(rows) <= 12 else (rows[:4] + rows[len(rows) // 2 - 1: len(rows) // 2 + 1] + rows[-4:])
    lines = [f"  {r['date']}: {r['stance'] or '未知'}{_degree(r['score'])}" for r in show]
    return "\n".join(lines), stances


def _append_log(today, n_days, text):
    from util_io import append_daily_log
    return append_daily_log(LOG, ["month", "n_days", "text"],
                            [[_month_key(today), str(n_days), text]], date=_month_key(today))


def _already_logged_this_month(today):
    if not LOG.exists():
        return False
    key = _month_key(today)
    try:
        with open(LOG, encoding="utf-8") as f:
            return any(r and r[0] == key for r in csv.reader(f))
    except Exception:
        return False


def run(write=True, force=False):
    if not _llm_key():
        print("[LLM月报] 未配置 LLM key（GEMINI_API_KEY 或 LLM_API_KEY），跳过")
        return None
    today = datetime.date.today()
    # 节流(run_all 每小时跑)：只在月末最后 4 天生成(攒满整月)，且本月只调一次 LLM(已记则跳)。
    last_day = calendar.monthrange(today.year, today.month)[1]
    if not force:
        if today.day < last_day - 3:
            print(f"[LLM月报] 未到月末(攒整月数据,{today.day}/{last_day})，跳过")
            return None
        if _already_logged_this_month(today):
            print("[LLM月报] 本月已生成，跳过")
            return None
    comp = _load_composite_month(today)
    stance_lines, stances = _format_stance_lines(comp)
    regime = _load_regime()
    base_rate, n_total = _load_scorecard_summary()
    n_days = len(comp)
    prompt = MONTHLY_PROMPT.format(
        month_label=_month_label(today), n_days=n_days, stance_lines=stance_lines,
        regime_lines="\n".join(regime) if regime else "（暂无体制数据）",
        base_rate_pct=base_rate, n_total=n_total)
    try:
        text = _llm(prompt)
    except Exception as e:
        print(f"[LLM月报] LLM 调用失败（非致命，不阻断流水线）: {e}")
        return None
    if not text:
        print("[LLM月报] 空返回，跳过")
        return None
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "month": _month_key(today), "month_label": _month_label(today),
        "month_label_en": _month_label_en(today), "n_days": n_days,
        "model": _active_model(), "text": text, "stances": stances,
        "caveat": ("LLM 据本月真实因子走势生成的大白话回顾；喂真数据防瞎编，但仍可能误读。"
                   "非预测、非荐股、会错，过去≠未来。每月 append 到 llm_monthly_log 公开计分。"),
    }
    if write:
        from util_io import write_json
        write_json("llm_monthly.json", out)
        wrote = _append_log(today, n_days, text)
        print(f"[OK] llm_monthly.json — {_month_label(today)} · {n_days}天 · {len(text)} 字"
              + ("" if wrote else "（本月已记，不重复）"))
    return out


if __name__ == "__main__":
    run()
