"""数据层双语守门 — 模拟盘 / 体制分项（2026-09-01）。

同 test_placebo_i18n 的思路:不断言译文长什么样(那是把译文抄两遍),只断言**覆盖率**和
**回落行为**,让"下次加一个策略/加一个体制分项时忘了配英文"当场变红。

特别守两件事:
  1. **账本 note 的英文是读时重建**——paper_ledger.csv 是 append-only,历史行绝不回改。
     所以 note_en 必须能把已写死的中文 note 还原成英文;认不出的形状必须**退回中文**,
     不许编一句读着像翻好了的假英文(假英文比缺英文危险:缺英文你看得见)。
  2. **档位表中英同源**——体制标签先定档、再从同一张表取两列。两套 if/elif 迟早漂移,
     而"英文读者看到的体制判断和中文不一致"在诚实计分的项目里是硬伤。

hermetic:只 import 模块常量 + 调纯函数,不跑流水线、不联网、不读 data/。
"""
import re

import pytest

CJK = re.compile(r"[一-龥]")


# ── 模拟盘：策略元数据 ──────────────────────────────────────────────
def test_every_strategy_has_english_label_and_desc():
    """加第 6 个策略时忘配英文 → 这条红,并指名道姓缺哪个。"""
    from paper_trading import STRATS
    missing = [k for k, v in STRATS.items() if not v.get("label_en") or not v.get("desc_en")]
    assert not missing, f"这些策略缺 label_en/desc_en: {missing}"
    bad = [k for k, v in STRATS.items() if CJK.search(v["desc_en"])]
    assert not bad, f"这些策略的 desc_en 里还有中文(没翻完就别标成英文): {bad}"


@pytest.mark.parametrize("zh,en", [
    ("全仓纳指@25170", "All-in NASDAQ @25170"),
    ("站上MA200，买入@25170", "Crossed above MA200, bought @25170"),
    ("跌破MA200，清仓@24800", "Broke below MA200, went to cash @24800"),
    ("tier4，买入@26376", "tier4, bought @26376"),
    ("tier2，清仓@26100", "tier2, went to cash @26100"),
    ("调仓→SNDK(124%)+AMD(105%)", "Rebalanced -> SNDK(124%)+AMD(105%)"),
])
def test_note_en_rebuilds_ledger_notes(zh, en):
    """价格/代码/百分比必须**原样搬运**——译文里的数字都来自中文串本身,不重算。"""
    from paper_trading import note_en
    assert note_en(zh) == en


def test_note_en_falls_back_on_unknown_shape():
    """认不出的形状退回中文;None/空不炸(调用方可无脑套用)。"""
    from paper_trading import note_en
    weird = "以后才会有的新动作@123"
    assert note_en(weird) == weird
    assert note_en(None) is None and note_en("") == ""


def test_note_en_covers_every_note_template_in_source():
    """源码里每个 note 模板都要有对应的还原规则 —— 新增一种成交动作就会红。
    做法:把 f-string 模板里的 {…} 占位换成样例数字,再要求 note_en 能翻动它。"""
    from pathlib import Path
    from paper_trading import note_en
    import paper_trading as pt
    src = Path(pt.__file__).read_text(encoding="utf-8")
    templates = set(re.findall(r'note = "[A-Z]+", f"([^"]+)"', src))
    assert templates, "没抽到 note 模板 —— 写法变了,先修这里"
    unhandled = []
    for t in templates:
        sample = re.sub(r"\{[^}]+\}", "123", t)
        if CJK.search(note_en(sample) or ""):
            unhandled.append(t)
    assert not unhandled, (
        f"这些 note 模板没有英文还原规则(补进 paper_trading._NOTE_PATTERNS): {unhandled}")


# ── 体制分项：档位表 ────────────────────────────────────────────────
@pytest.mark.parametrize("table_name", [
    "_VIX_BANDS", "_CURVE_BANDS", "_CREDIT_BANDS", "_TERM_BANDS", "_HERD_BANDS",
])
def test_regime_band_tables_are_bilingual_pairs(table_name):
    """每档必须是 (中文, 英文) 两列,且英文列里不能残留中文。"""
    import market_regime as mr
    table = getattr(mr, table_name)
    assert table, f"{table_name} 是空表"
    for key, pair in table.items():
        assert isinstance(pair, tuple) and len(pair) == 2, f"{table_name}[{key}] 不是(中,英)二元组"
        zh, en = pair
        assert zh and en, f"{table_name}[{key}] 有空值"
        assert not CJK.search(en), f"{table_name}[{key}] 的英文列里还有中文: {en!r}"


def test_regime_component_names_all_have_english():
    """comps.append 里出现的每个中文 name 都要在 _NAME_EN 里有英文 —— 加新分项就会红。"""
    from pathlib import Path
    import market_regime as mr
    src = Path(mr.__file__).read_text(encoding="utf-8")
    names = set(re.findall(r'comps\.append\(\{"name": "([^"]+)"', src))
    assert names, "没抽到 comps 的 name 字面量 —— 写法变了,先修这里"
    missing = [n for n in names if n not in mr._NAME_EN]
    assert not missing, f"这些体制分项缺英文名(补进 market_regime._NAME_EN): {missing}"
    bad = [n for n, v in mr._NAME_EN.items() if CJK.search(v)]
    assert not bad, f"这些 _NAME_EN 的值里还有中文: {bad}"


# ── 结论层：档位表中英同源（2026-09-01 尾扫补） ──────────────────────
@pytest.mark.parametrize("mod,table", [
    ("composite_read", "_STANCE"), ("composite_read", "_ACTION"), ("composite_read", "_TILT"),
])
def test_composite_band_tables_are_bilingual_pairs(mod, table):
    """立场/行动/倾斜三张表必须同键同档 —— 它们共用一个 _band(),
    阈值只写一处,所以中英不可能只改一边。"""
    import importlib
    m = importlib.import_module(mod)
    t = getattr(m, table)
    for key, pair in t.items():
        assert isinstance(pair, tuple) and len(pair) == 2, f"{table}[{key}] 不是(中,英)二元组"
        assert pair[0] and pair[1], f"{table}[{key}] 有空值"
        assert not CJK.search(pair[1]), f"{table}[{key}] 的英文列里还有中文: {pair[1]!r}"


def test_composite_tables_share_the_same_bands():
    """三张表的档位键必须完全一致 —— 少一档就会在某个分数区间取到 KeyError/回落中文。"""
    import composite_read as cr
    keys = {frozenset(cr._STANCE), frozenset(cr._ACTION), frozenset(cr._TILT)}
    assert len(keys) == 1, f"_STANCE/_ACTION/_TILT 的档位键不一致: {[sorted(k) for k in keys]}"


@pytest.mark.parametrize("score,expect", [
    (-0.9, "strong_def"), (-0.2, "def"), (0.0, "neutral"), (0.2, "pos"), (0.9, "strong_pos"),
    (None, "na"),
])
def test_composite_band_boundaries(score, expect):
    """定档函数的边界钉死 —— 以后调阈值必须同时改这条测试,不能悄悄挪。"""
    import composite_read as cr
    assert cr._band(score) == expect
