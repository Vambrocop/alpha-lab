"""llm_honest_read.py — 大白话读三个诚实研究(dip/vixvol/feargreed·喂真数据·死守 copy-guard)

严格实现 docs_internal/SPEC_HONEST_READ.md。把三个 **describe-only** 研究的真实结论用 Gemini 翻成新手能懂的
大白话,放各页顶部。**honesty-critical**:LLM 极易把"深跌后历史多涨""现在偏贪婪"顺嘴译成买卖建议——命门是堵死这条:
① 只喂脚本从三个 JSON 真读出来的数字(防瞎编);② 后置守门扫描肯定式操作词,越界文案绝不上线。

复用 llm_core(与 llm_daily_read 同基建);无 GEMINI_API_KEY 静默跳过、不阻断流水线(fail-soft)。
"""
import os
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
NEG_PREFIX = ("不", "别", "非", "勿", "绝")   # 紧邻在前=否定语境,放行
# 只列【明确的操作指令】短语。故意不含「该买/该卖」——它们太含糊(出现在 应该/不该/就该 里),
# 且否定常远离禁词(如「不该读成贪婪就该卖」),裸词匹配必误伤免责句(见 [[honesty-guard-test-disclaimers]])。
FORBIDDEN = ("建议买", "建议卖", "赶紧买", "赶紧卖", "可以买入", "可以卖出",
             "现在买入", "现在卖出", "抄底吧", "加仓", "清仓", "满仓", "止损", "应买入", "应卖出")


def guard_ok(text):
    """返回 (ok, hit)。命中肯定式操作词 → (False, 词);否则 (True, None)。"""
    s = text or ""
    for ph in FORBIDDEN:
        i = s.find(ph)
        while i != -1:
            prev = s[i - 1] if i > 0 else ""
            if prev not in NEG_PREFIX:          # 前面不是否定字 → 肯定式,拦
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


STUDIES = [
    ("dip", "dip_hold.json", "跌了买、持有一年的诚实账", facts_dip),
    ("vixvol", "vix_vol.json", "VIX 到底预测什么", facts_vixvol),
    ("feargreed", "fear_greed.json", "恐慌贪婪合成表 + 逆向检验", facts_feargreed),
]

PROMPT_TMPL = """你是给股票新手讲人话的助手。下面是一个「诚实统计研究」真实算出的结论,请用 2-4 句大白话中文讲清它在说什么。

研究:{name}
真实数据 / 结论(你只能用这些,不许编任何别的数字或断言):
{facts}

铁律(必须全部遵守):
1.【绝不给操作建议】不许出现「该买/该卖/建议买入/建议卖出/赶紧买/抄底吧/加仓/清仓/止损」这类话——这是历史描述,不是买卖信号。可以明说「这不是买入/卖出信号」。
2.【只用给定数字】不许引入上面没给的任何数字或断言。
3.【说人话】用到专业词(如 VIX、实现波动、回撤、基率、前向收益)必须紧跟一个小括号、用最朴素一句解释它是什么。
4.【保留诚实结论】照上面结论的方向讲,不许改写成更"能操作"的口气;结尾带一句"会错、过去不代表未来"。
只输出这 2-4 句本身,不要标题、不要列表、不要 markdown 符号。"""


def _generate_one(name, facts, llm_fn):
    """出一段大白话 + 后置守门(命中肯定式操作词 → 重试一次 → 仍命中则置空)。返回 (text_or_None, guard)。"""
    prompt = PROMPT_TMPL.format(name=name, facts=facts)
    for _ in range(2):
        try:
            text = (llm_fn(prompt) or "").strip()
        except Exception as e:
            print(f"[诚实日读] LLM 调用失败(非致命): {e}")
            return None, "error"
        if not text:
            continue
        ok, hit = guard_ok(text)
        if ok:
            return text, "ok"
        print(f"[诚实日读] 守门拦下越界文案(命中「{hit}」),重试")
    return None, "blocked"


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
    for key, fname, name, extractor in STUDIES:
        try:
            j = json.loads((WEB / fname).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[诚实日读] 读 {fname} 失败,跳过 {key}: {e}")
            continue
        facts = extractor(j)
        if not facts:
            print(f"[诚实日读] {key} 事实包缺字段,跳过")
            continue
        text, guard = _generate_one(name, facts, llm_fn)
        reads[key] = {"text": text if guard == "ok" else None, "guard": guard}
        log_rows.append([key, key, guard, text])   # [placeholder, study, guard, text]
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
        for d in write_json("honest_reads.json", out):
            print(f"  Written: {d}/honest_reads.json")
        n = _append_log(today, log_rows)
        print(f"[OK] honest_reads.json — {len(reads)} 段(新记 {n} 行日志)")
    return out


if __name__ == "__main__":
    run(write=True)
