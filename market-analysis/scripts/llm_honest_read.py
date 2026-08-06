"""llm_honest_read.py — 大白话读三个诚实研究(dip/vixvol/feargreed·喂真数据·死守 copy-guard)

严格实现 docs_internal/SPEC_HONEST_READ.md。把三个 **describe-only** 研究的真实结论用 Gemini 翻成新手能懂的
大白话,放各页顶部。**honesty-critical**:LLM 极易把"深跌后历史多涨""现在偏贪婪"顺嘴译成买卖建议——命门是堵死这条:
① 只喂脚本从三个 JSON 真读出来的数字(防瞎编);② 后置守门扫描肯定式操作词,越界文案绝不上线。

复用 llm_core(与 llm_daily_read 同基建);无 GEMINI_API_KEY 静默跳过、不阻断流水线(fail-soft)。
"""
import os
import re
import sys
import csv
import json
import datetime
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from llm_core import _llm, _llm_key, _active_model
from util_io import write_json

WEB = _SCRIPTS.parent / "web"
LOG = _SCRIPTS.parent / "data" / "honest_read_log.csv"

# ══════════════════════════════════════════════════════════════════
# 后置诚实守门(§3 命门):只拦【肯定式】操作词,不误伤"这不是买入信号"这类正当否定
# ══════════════════════════════════════════════════════════════════
NEG_CHARS = set("不别非勿绝没")         # 否定字:命中词前一小窗内出现任一 → 判免责否定语境,放行
CLAUSE_END = set("。，；！？\n")          # 往回只扫到句读边界(否定不跨句)
NEG_WINDOW = 8
# 【明确操作指令】短语——含对抄底页最诱人的 抄底/逢低/买进/建仓 类(审查 HIGH#2 补全)。
# 含糊者(抄底/买入类)靠否定窗放行免责句(如「这不是抄底信号」);「该买/该卖」仍不进守门
# (与 应该/不该 碰撞),交 prompt 铁律。见 [[honesty-guard-test-disclaimers]]。
FORBIDDEN = ("建议买", "建议卖", "赶紧买", "赶紧卖", "可以买入", "可以卖出", "现在买入", "现在卖出",
             "抄底", "逢低", "买进", "建仓", "加仓", "加码", "减仓", "清仓", "满仓",
             "离场", "梭哈", "止损", "止盈", "应买入", "应卖出")


def _neg_before(s, i):
    """命中位置 i 往回 NEG_WINDOW 字(不跨句读)内是否有否定字 → 是则视为免责否定语境(审查 MEDIUM#3)。"""
    j, steps = i - 1, 0
    while j >= 0 and steps < NEG_WINDOW and s[j] not in CLAUSE_END:
        if s[j] in NEG_CHARS and not (s[j] == "不" and s[j:j + 2] == "不妨"):
            return True   # 「不妨」是"其实建议"的肯定语气,不算否定(审查 HIGH#2 的「不妨买进」滑过场景)
        j -= 1
        steps += 1
    return False


def guard_ok(text):
    """返回 (ok, hit)。命中【肯定式】操作指令 → (False, 词);否定语境(免责句)放行。
    先归一化去掉可能插进词中间的空白/分隔符(防「建 议 买」「赶紧、买」绕过·审查 HIGH#2)。"""
    s = re.sub(r"[\s·、]", "", text or "")
    for ph in FORBIDDEN:
        i = s.find(ph)
        while i != -1:
            if not _neg_before(s, i):
                return False, ph
            i = s.find(ph, i + 1)
    return True, None


# ══════════════════════════════════════════════════════════════════
# 真事实包(§1):各研究只从自己 JSON 提炼真实数字,缺字段 → 返回 None(该段跳过,不硬编)
# ══════════════════════════════════════════════════════════════════
def facts_dip(j):
    try:
        b = j["base_rate"]["h252"]
        cells = {(c["dd_threshold_pct"], c["horizon"]): c for c in j["drawdown_curve"]}
        c5, c20, c30 = cells[(5, 252)], cells[(20, 252)], cells[(30, 252)]
        lp = next(x for x in j["low_proximity"] if x["within_pct"] == 5)
        return (
            f"- 光是「随便哪天买、持有1年」:历史上约 {b['up_pct']}% 上涨、平均 {b['mean_pct']}%。\n"
            f"- 「等跌了再买」分档(都持有1年):跌5%后 {c5['up_pct']}%涨/均值{c5['mean_pct']}%、"
            f"跌20%后 {c20['up_pct']}%/{c20['mean_pct']}%、跌30%后 {c30['up_pct']}%/{c30['mean_pct']}%。\n"
            f"- 关键(别读成「越跌越好」):浅跌(跌5%)后持有1年才 {c5['up_pct']}%,其实【低于】随便买的 {b['up_pct']}%"
            f"——浅跌到中跌(5~15%)并不比随便买强、有的还略差;只有深跌(20/30%)才明显更高。\n"
            f"- 而且深跌(20/30%)历史上只有 {c20['n_independent']}/{c30['n_independent']} 次真正独立的危机撑着"
            f"(样本极小),判定全是「仅描述·样本不够下结论」;没有一格达到「稳健」(any_robust={j['any_robust']})。\n"
            f"- 买在「52周最低点附近」反而最差:约 {lp['up_pct']}% 上涨(低于随便买的 {lp['base_up_pct']}%)。\n"
            f"- 研究给的一句话结论:{j['verdict_note']}\n"
            f"- 这是纯描述、不是买入信号、会错。"
        )
    except Exception:
        return None


def facts_vixvol(j):
    try:
        return (
            f"- 用我们2000年以来的数据:VIX(衡量市场预期波动/恐慌的指标)预测「下个月市场会晃多厉害」的相关性约 "
            f"{j['r_vix']};而单看「最近一个月晃得凶不凶」预测下个月约 {j['r_past']}。\n"
            f"- 两个数很接近,而且 VIX 测的是「波动大小」,不是「涨还是跌」。\n"
            f"- 所以「VIX低就会涨」没根据——VIX 不预测方向。这是描述、会错。"
        )
    except Exception:
        return None


def facts_feargreed(j):
    try:
        cur = j["current"]
        bands = j["contrarian"]["bands"]
        xg60 = next(c for c in bands if c["band"] == "extreme_greed" and c["horizon"] == 60)
        all_not = all(c["verdict"] == "not-contrarian" for c in bands)
        return (
            f"- 现在这个「恐慌贪婪合成表」(用我们能算的约{len(j['components_used'])}个指标拼出来的0-100情绪温度计,"
            f"是近似、不是CNN官方值)读数是 {cur['composite']},属于「{cur['band']}」档。\n"
            f"- 民间说「别人贪婪我恐惧」,但我们老实回测各情绪档之后市场怎么走:"
            f"{'全都' if all_not else '多数'}说不上有可靠的逆向规律;极度贪婪之后60天历史上平均比随便买还"
            f"{'高' if (xg60['diff_mean'] or 0) >= 0 else '低'} {abs(xg60['diff_mean'])} 个百分点"
            f"(更像顺势/动量,不是该卖)。\n"
            f"- 研究给的结论:{j['verdict_note']}\n"
            f"- 这是情绪温度计、不是买卖信号、会错。"
        )
    except Exception:
        return None


def require_dip(text):
    """HIGH#1:dip 读数【必须】点明「浅到中跌不比随便买强」,否则会被读成「越跌越好」——
    缺这一点判不合格(重试;仍缺则置空、box 隐藏,宁可不显示也不上误导读数)。"""
    t = text or ""
    shallow = any(k in t for k in ("浅跌", "浅回撤", "小跌", "跌得少", "跌5%", "跌 5%",
                                    "5~15", "5-15", "5%~15%", "5%到15%", "中跌", "浅"))
    under = any(k in t for k in ("不如", "不比", "低于", "略差", "白等", "并不", "反而",
                                  "没更", "不见得", "不一定更"))
    return shallow and under


STUDIES = [
    # (key, json, 名字, 提炼器, 该研究特别强调(进 prompt), 必点要点后置检查(缺则重试/置空))
    ("dip", "dip_hold.json", "跌了买、持有一年的诚实账", facts_dip,
     "必须明说:浅跌到中跌(比如跌 5%~15%)持有一年【并不比】「随便哪天买」强、有时反而略差;"
     "只有深跌(20/30%)才明显更高。绝不能只说「跌得越深越好」。", require_dip),
    ("vixvol", "vix_vol.json", "VIX 到底预测什么", facts_vixvol, "", None),
    ("feargreed", "fear_greed.json", "恐慌贪婪合成表 + 逆向检验", facts_feargreed, "", None),
]

PROMPT_TMPL = """你是给股票新手讲人话的助手。下面是一个「诚实统计研究」真实算出的结论,请用 2-4 句大白话中文讲清它在说什么。

研究:{name}
真实数据 / 结论(你只能用这些,不许编任何别的数字或断言):
{facts}

铁律(必须全部遵守):
1.【绝不给操作建议】不许出现「该买/该卖/建议买入/建议卖出/赶紧买/抄底吧/加仓/清仓/止损」这类话——这是历史描述,不是买卖信号。可以明说「这不是买入/卖出信号」。
2.【只用给定数字】不许引入上面没给的任何数字或断言。
3.【说人话】用到专业词(如 VIX、实现波动、回撤、基率、前向收益)必须紧跟一个小括号、用最朴素一句解释它是什么。
4.【保留诚实结论】照上面结论的方向讲,不许改写成更"能操作"的口气;结尾带一句"会错、过去不代表未来"。{emphasis}
只输出这 2-4 句本身,不要标题、不要列表、不要 markdown 符号。"""


def _generate_one(name, facts, llm_fn, emphasis="", require_fn=None):
    """出一段大白话 + 双向守门(负向:拦操作词;正向:require_fn 必点要点)。重试一次,仍不合格则置空。
    返回 (text_or_None, guard, last_raw)。guard ∈ ok/blocked/error;last_raw 供审计日志(含被拦的原文)。"""
    emph = ("\n特别要求(必须做到):" + emphasis) if emphasis else ""
    prompt = PROMPT_TMPL.format(name=name, facts=facts, emphasis=emph)
    last = None
    for _ in range(2):
        try:
            text = (llm_fn(prompt) or "").strip()
        except Exception as e:
            print(f"[诚实日读] LLM 调用失败(非致命): {e}")
            return None, "error", last
        if not text:
            continue
        last = text
        ok, hit = guard_ok(text)
        if not ok:
            print(f"[诚实日读] 守门拦下越界文案(命中「{hit}」),重试")
            continue
        if require_fn and not require_fn(text):
            print("[诚实日读] 缺必点诚实要点(如'浅跌不跑赢基率'),重试")
            continue
        return text, "ok", text
    return None, "blocked", last


def _append_log(today, rows):
    """append-only;按 (date,study) 去重(同日重跑不重复追行·绝不改历史行)。"""
    seen = set()
    if LOG.exists():
        with open(LOG, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                seen.add((r.get("date"), r.get("study")))
    new = [r for r in rows if (today, r[1]) not in seen]
    if not new:
        return 0
    write_header = not LOG.exists()
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if write_header:
            w.writerow(["date", "study", "model", "guard", "text"])
        for study, guard, text in [(r[1], r[2], r[3]) for r in new]:
            w.writerow([today, study, _active_model(), guard, (text or "").replace("\n", " ")])
    return len(new)


def run(write=True, _llm_fn=None):
    if not _llm_key():
        print("[诚实日读] 未配置 LLM key(GEMINI_API_KEY / LLM_API_KEY),跳过")
        return None
    llm_fn = _llm_fn or _llm
    reads = {}
    log_rows = []
    for key, fname, name, extractor, emphasis, require_fn in STUDIES:
        try:
            j = json.loads((WEB / fname).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[诚实日读] 读 {fname} 失败,跳过 {key}: {e}")
            continue
        facts = extractor(j)
        if not facts:
            print(f"[诚实日读] {key} 事实包缺字段,跳过")
            continue
        text, guard, raw = _generate_one(name, facts, llm_fn, emphasis, require_fn)
        reads[key] = {"text": text if guard == "ok" else None, "guard": guard}
        log_rows.append([key, key, guard, raw])   # 记原始文本(含被拦/缺要点的)供审计(审查 LOW)
        print(f"  {key}: guard={guard}" + (f"  {len(text)}字" if text else ""))

    today = datetime.date.today().isoformat()
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": today,
        "model": _active_model(),
        "reads": reads,
        "caveat": "AI 据三个研究的真实数字生成的大白话解读;喂真数据防瞎编、后置守门拦操作词,"
                  "但仍可能误读。纯描述、非买卖信号、会错,过去≠未来。",
    }
    if write:
        try:   # 写出/记账失败绝不阻断流水线(run_all 一步非零即终止·SPEC §5 fail-soft·审查 MEDIUM#4)
            for d in write_json("honest_reads.json", out):
                print(f"  Written: {d}/honest_reads.json")
            n = _append_log(today, log_rows)
            print(f"[OK] honest_reads.json — {len(reads)} 段(新记 {n} 行日志)")
        except Exception as e:
            print(f"[诚实日读] 写出/记账失败(非致命,不阻断流水线): {e}")
    return out


if __name__ == "__main__":
    run(write=True)
