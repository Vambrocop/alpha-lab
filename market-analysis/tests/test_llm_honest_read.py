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
    assert H.guard_ok("该买就赶紧买")[0] is False           # 赶紧买
    assert H.guard_ok("到止损位了")[0] is False


def test_guard_blocks_gap_directives():
    # 审查 HIGH#2:抄底页最诱人的词都得拦
    assert H.guard_ok("现在正是逢低抄底的好时机")[0] is False   # 逢低/抄底
    assert H.guard_ok("可以考虑分批建仓")[0] is False          # 建仓
    assert H.guard_ok("深跌后不妨买进一些")[0] is False        # 买进,且「不妨」不算否定
    assert H.guard_ok("建 议 买 入")[0] is False              # 归一化去空白后仍拦


def test_guard_allows_negation_disclaimers():
    assert H.guard_ok("这不是买入信号,过去不代表未来")[0] is True
    assert H.guard_ok("这不是建议买入的信号")[0] is True       # 否定窗:不 离「建议买」2字(旧单字版会误拦)
    assert H.guard_ok("这不是抄底信号")[0] is True             # 否定窗放行 bare 抄底 的免责句
    assert H.guard_ok("不该读成贪婪就该卖")[0] is True         # 「该卖」不在守门(交 prompt)
    assert H.guard_ok("别赶紧买,这只是历史描述")[0] is True
    assert H.guard_ok("浅跌其实不如随便买,只有深跌才更高")[0] is True  # dip 正常读数不被误拦
    # 整句扫描:否定远在句首也接得住(fear 真读数「绝不能理解成恐慌后就能抄底」·8字窗会误拦)
    assert H.guard_ok("这只是历史描述,绝不能理解成恐慌后就能抄底")[0] is True


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
    p = H.PROMPT_TMPL.format(name="测试研究", facts="- 真实数字 42%", emphasis="")
    assert "绝不给操作建议" in p and "只用给定数字" in p and "说人话" in p
    assert "42%" in p and "测试研究" in p


# ── 4. _generate_one:干净输出→ok;越界/缺必点→blocked 且置空(§6·2)──
def test_generate_ok_with_clean_output():
    text, guard, raw = H._generate_one("研究", "- 数字", lambda p: "这是历史描述,不是买卖信号,会错。")
    assert guard == "ok" and text and raw == text


def test_generate_blocked_after_retry():
    text, guard, raw = H._generate_one("研究", "- 数字", lambda p: "现在建议买入这只票")
    assert guard == "blocked" and text is None
    assert raw == "现在建议买入这只票"   # 审计:原始被拦文本仍留痕


def test_generate_blocked_when_required_point_missing():
    # HIGH#1:dip 必点「浅跌不跑赢基率」缺失 → 判 blocked、置空(宁可不显示也不上误导读数)
    text, guard, raw = H._generate_one(
        "dip", "- 数字", lambda p: "跌得越深越好,会错、过去不代表未来。",
        require_fn=H.require_dip)
    assert guard == "blocked" and text is None


def test_require_dip_semantics():
    assert H.require_dip("跌得越深越好") is False                       # 无浅跌caveat → 不合格
    assert H.require_dip("浅跌其实不如随便买,只有深跌才明显更高") is True


def test_require_fear_semantics():
    assert H.require_fear("恐慌后市场就能反弹上涨") is False              # 无样本小/脆caveat → 不合格
    assert H.require_fear("历史上只出现过几次,样本很少,剔掉危机就不稳") is True


def test_require_treasury_semantics():
    assert H.require_treasury("利率低的时候买股票收益更好") is False        # 无限制caveat → 不合格
    assert H.require_treasury("36格里只有低利率档1个月那格分得开,方向档几乎没有可靠信号") is True


def test_facts_treasury_missing_returns_none():
    assert H.facts_treasury({}) is None
    assert H.facts_treasury({"assets": {"NASDAQ": {"level": [], "direction": []}}}) is None


def test_facts_treasury_carries_real_numbers_and_limits():
    """喂真字段 → 必须带真实数字 + 「唯一分得开」「方向没信号」的限制(防被读成利率低就该买)。"""
    j = {"assets": {"NASDAQ": {
        "level": [
            {"bucket": "low", "horizon": 20, "mean_pct": 1.5, "base_mean_pct": 0.76,
             "diff_mean": 0.74, "ci95_mean": [1.24, 1.98], "ci_vs_base": "above_base"},
            {"bucket": "high", "horizon": 20, "mean_pct": -0.11, "base_mean_pct": 0.76,
             "diff_mean": -0.87, "ci95_mean": [-1.74, 1.82], "ci_vs_base": "overlaps_base"},
        ],
        "direction": [
            {"bucket": b, "horizon": 20, "mean_pct": 0.7, "base_mean_pct": 0.76,
             "diff_mean": -0.06, "ci95_mean": [-0.1, 1.5], "ci_vs_base": "overlaps_base"}
            for b in ("falling", "flat", "rising")
        ]}}}
    f = H.facts_treasury(j)
    assert f and "1.5" in f and "[1.24, 1.98]" in f      # 真数字来自 JSON,不是编的
    assert "唯一" in f                                    # 点明只有那一格分得开
    assert "有 0 格" in f                                 # 方向档可分格数=0(真算出来的)
    assert H.require_treasury(f) is True                  # 自家 facts 必须过自家正向门


def test_facts_fear_missing_returns_none():
    assert H.facts_fear({}) is None
    assert H.facts_fear({"primary_cell": {"trigger": "T1", "index": "SP500", "horizon": 20}, "triggers": {}}) is None


# ── 5. 无 key → run() 静默跳过、返回 None(§6·4)──
def test_run_skips_without_key(monkeypatch):
    monkeypatch.setattr(H, "_llm_key", lambda: None)
    assert H.run(write=False) is None
