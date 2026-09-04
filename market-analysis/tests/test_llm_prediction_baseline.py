"""AI 前瞻计分牌的诚实性守门(2026-09-03)。

## 起因(别删,这是这些测试存在的理由)

计分牌上写着"三桶随机基线约 1/3",于是 59.0% 的命中率读起来像"远高于随机、AI 有点本事"。
**那个基线是错的**:三个结果桶根本不等概(实测 中性 61.5% / 偏多 20.5% / 偏空 17.9%)。
真正的门槛是**多数类基线**——每天闭眼说最常出现的那一桶。按这个比,59.0% 其实
**低于 61.5%**,也就是不如什么都不想。一个诚实计分的项目,把"不如常数策略"展示成"有本事",
是最不能犯的错。

所以这里钉三件事:
  1. 基线**从数据现算**,不是写死的常数(数据会漂,写死的基线迟早骗人);
  2. 二项检验的方向和量级正确;
  3. "1/3 随机基线"那种措辞**不许回潮**。

hermetic:纯函数 + 构造样本,不联网、不调 LLM、不读真账本。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import llm_prediction as lp  # noqa: E402


def _row(bucket, hit, direction="中性", settled=True, dropped=False, conf="低"):
    return {"bucket": bucket, "hit": str(hit), "direction": direction,
            "settled": str(settled), "dropped": str(dropped), "confidence": conf}


def test_baseline_picks_the_majority_class_not_uniform_random():
    """基线 = 多数类,不是 1/3。这条是整个修复的核心。"""
    rows = [_row("中性", True)] * 6 + [_row("偏多", False)] * 2 + [_row("偏空", False)] * 2
    b = lp._baseline(rows)
    assert b["class"] == "中性"
    assert b["pct"] == 60.0, "基线应为多数类占比 6/10,不是 33%"
    assert b["n"] == 10


def test_baseline_exposes_llm_underperforming_the_trivial_strategy():
    """真实形状复刻:命中率**低于**多数类基线时,数字必须如实出来。"""
    # 10 条:结果 7 中性 / 3 偏多;LLM 只中了 5 条 → 50% < 基线 70%
    rows = ([_row("中性", True)] * 5 + [_row("中性", False)] * 2 + [_row("偏多", False)] * 3)
    b = lp._baseline(rows)
    assert b["pct"] == 70.0
    hit_pct = 50.0
    assert hit_pct < b["pct"], "构造样本本身就该是「不如基线」"
    assert b["p_value_vs_llm"] > 0.5, "低于基线时,单边检验 p 值必须很大(远非显著)"


def test_binomial_p_is_small_when_llm_clearly_beats_baseline():
    """反向:全中且基线不高 → p 值应该很小(证明检验方向没写反)。"""
    rows = [_row("中性", True)] * 5 + [_row("偏多", True)] * 5
    b = lp._baseline(rows)
    assert b["pct"] == 50.0
    assert b["p_value_vs_llm"] < 0.01, f"10/10 命中 vs 50% 基线,p 应极小,实得 {b['p_value_vs_llm']}"


def test_baseline_is_none_without_usable_samples():
    assert lp._baseline([]) is None
    assert lp._baseline([_row("", True)]) is None, "bucket 全空 → 无法定基线,应返回 None"


def test_directional_bets_exclude_neutral_and_dropped():
    """「中性」不是方向赌注 —— scorecard.py 2026-08 已为此修过一次 bug,这里锁死。"""
    rows = [
        _row("偏多", True, direction="偏多"),
        _row("偏空", False, direction="偏空"),
        _row("中性", True, direction="中性"),          # 不算
        _row("偏多", True, direction="偏多", dropped=True),  # 作废,不算
        _row("偏空", False, direction="偏空", settled=False),  # 未结算
    ]
    d = lp._directional_bets(rows)
    assert d["n_total"] == 3, "应只数 偏多/偏空 且未作废的"
    assert d["n_settled"] == 2
    assert d["n_hit"] == 1


def test_verdict_leads_with_the_baseline_comparison():
    """裁决句必须**先**给对照,再给命中率 —— 不给对照,59% 会被读成本事。"""
    rows = ([_row("中性", True)] * 5 + [_row("中性", False)] * 2 + [_row("偏多", False)] * 3)
    v = lp._verdict(lp._scorecard(rows))
    assert "闭眼说" in v and "中性" in v, "裁决里必须出现多数类对照"
    assert "二项检验" in v, "必须给出显著性依据,不能只摆两个百分比"


def test_verdict_warns_when_almost_no_directional_bets():
    """几乎全是中性时,必须说清这页在量什么(否则读者以为在量方向判断力)。"""
    rows = [_row("中性", True)] * 30 + [_row("偏多", False)] * 9
    v = lp._verdict(lp._scorecard(rows))
    assert "押方向" in v and "不足以谈" in v


def test_uniform_random_baseline_wording_never_returns():
    """防回潮:'三桶随机基线 1/3' 这类措辞不许再出现在脚本或页面里。"""
    # 只查**用户真正看得到的文案**(裁决句 + caveat + 页面),不查源码注释/docstring ——
    # 注释里讲"当年为什么错"是有价值的,不该被守门测试逼着删掉。
    rows = [_row("中性", True)] * 30 + [_row("偏多", False)] * 9
    sc = lp._scorecard(rows)
    shipped = [lp._verdict(sc),
               (ROOT / "web" / "prediction.html").read_text(encoding="utf-8")]
    # caveat 是模块里的用户文案:取出来一并查
    src = (ROOT / "scripts" / "llm_prediction.py").read_text(encoding="utf-8")
    i = src.find('"caveat"')
    shipped.append(src[i:i + 1200] if i >= 0 else "")

    bad = [t[:60] for t in shipped
           if "随机基线" in t and ("1/3" in t or "33" in t) and "2026-09-03 修" not in t]
    assert not bad, (
        f"'三桶随机基线约 1/3' 的错误参照回到用户可见文案里了: {bad} —— "
        "正确门槛是多数类基线(见本文件开头)")
