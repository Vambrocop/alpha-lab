"""test_llm_honest_read.py — SPEC_HONEST_READ §6(mock LLM·不打网络)。

覆盖:后置守门(拦肯定式操作词·不误伤否定式免责)、事实包缺字段跳过、prompt 带铁律+真数字、
_generate_one 重试后置空、无 key run() 静默跳过。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import llm_honest_read as H  # noqa: E402


# ── 1. 后置守门:肯定式拦、否定式免责放行(命门·honesty-guard-test-disclaimers 教训)──
def test_guard_blocks_affirmative():
    assert H.guard_ok("现在建议买入这只票")[0] is False
    assert H.guard_ok("该买就赶紧买")[0] is False
    assert H.guard_ok("到止损位了")[0] is False


def test_guard_allows_negation_disclaimers():
    assert H.guard_ok("这不是买入信号,过去不代表未来")[0] is True
    assert H.guard_ok("不该读成贪婪就该卖")[0] is True     # 含「该卖」但前面是「不」
    assert H.guard_ok("别赶紧买,这只是历史描述")[0] is True  # 含「赶紧买」但前面是「别」
    assert H.guard_ok("VIX 测的是波动,不是涨跌;会错")[0] is True


# ── 2. 事实包:缺字段 → None(该段跳过,不硬编);字段全 → 含真数字 ──
def test_facts_dip_missing_field_returns_none():
    assert H.facts_dip({"base_rate": {}}) is None
    assert H.facts_vixvol({}) is None
    assert H.facts_feargreed({"current": {}}) is None


def test_facts_dip_carries_real_numbers_and_nuance():
    j = {
        "base_rate": {"h252": {"up_pct": 75.2, "mean_pct": 7.8}},
        "any_robust": False,
        "drawdown_curve": [
            {"dd_threshold_pct": 5, "horizon": 252, "up_pct": 66.1, "mean_pct": 6.9, "n_independent": 2},
            {"dd_threshold_pct": 20, "horizon": 252, "up_pct": 77.1, "mean_pct": 15.0, "n_independent": 4},
            {"dd_threshold_pct": 30, "horizon": 252, "up_pct": 95.5, "mean_pct": 27.9, "n_independent": 3},
        ],
        "low_proximity": [{"within_pct": 5, "up_pct": 50.3, "base_up_pct": 75.2}],
        "verdict_note": "描述性总结……",
    }
    f = H.facts_dip(j)
    assert "75.2" in f and "95.5" in f
    assert "别读成「越跌越好」" in f          # 明确防"越跌越好"误读
    assert "低于" in f                        # 浅跌低于基率的诚实点
    assert "不是买入信号" in f


# ── 3. prompt 组装:含铁律 + 真事实(§6·1)──
def test_prompt_has_rules_and_facts():
    p = H.PROMPT_TMPL.format(name="测试研究", facts="- 真实数字 42%")
    assert "绝不给操作建议" in p and "只用给定数字" in p and "说人话" in p
    assert "42%" in p and "测试研究" in p


# ── 4. _generate_one:干净输出→ok;连两次越界→blocked 且置空(§6·2)──
def test_generate_ok_with_clean_output():
    text, guard = H._generate_one("研究", "- 数字", lambda p: "这是历史描述,不是买卖信号,会错。")
    assert guard == "ok" and text


def test_generate_blocked_after_retry():
    text, guard = H._generate_one("研究", "- 数字", lambda p: "建议买入这只票")
    assert guard == "blocked" and text is None


# ── 5. 无 key → run() 静默跳过、返回 None(§6·4)──
def test_run_skips_without_key(monkeypatch):
    monkeypatch.setattr(H, "_llm_key", lambda: None)
    assert H.run(write=False) is None
