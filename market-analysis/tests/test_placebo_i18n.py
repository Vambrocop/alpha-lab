"""数据层双语守门 — placebo 面板的英文覆盖率（2026-09-01）。

背景:英文模式下 registry 视图的 #placebo-overview 曾整块是中文,因为文案是 Python 生成的
(前端只是照显示)。补 *_en 字段容易,难的是**下次加第 7 条日历效应时别忘了**。

所以这里不去断言"某几句英文长啥样"(那是把译文抄两遍),而是断言**覆盖率**:
  · 源码里每个 claim="…" 字面量都必须在 CLAIM_EN 里有条目;
  · 每个 panel="…" / scope="…" 都必须被 label_en 全译;
  · detail 的每种结构化形状都要能重建成英文,且未知形状**原样退回中文**
    (宁可露出中文,也不编一句读起来像翻好了的假英文 —— 假英文比缺英文更危险)。
加新效应时忘了配英文 → 这里立刻红,并指名道姓缺哪条。

hermetic:只读源码文本 + 调纯函数,不跑流水线、不联网、不读 data/。
"""
import re
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "scripts" / "placebo_test.py"


def _literals(kw):
    """从 placebo_test.py 源码里抽 add(... kw="…" ...) 的字面量(f-string 的跳过)。"""
    text = SRC.read_text(encoding="utf-8")
    return sorted(set(re.findall(kw + r'="([^"{]+)"', text)))


def test_every_claim_has_english():
    from placebo_test import CLAIM_EN
    claims = _literals("claim")
    assert claims, "没抽到 claim 字面量 —— 正则或调用写法变了,先修这里再说"
    missing = [c for c in claims if c not in CLAIM_EN]
    assert not missing, f"这些 claim 没配英文(补进 placebo_test.CLAIM_EN): {missing}"


def test_every_panel_and_scope_is_translatable():
    from label_en import is_fully_translated
    bad = [s for s in _literals("panel") + _literals("scope") if not is_fully_translated(s)]
    assert not bad, f"这些 panel/scope 没被 label_en 全译(补片段表): {bad}"


@pytest.mark.parametrize("zh,en", [
    ("周三最高 / 周一最低", "Wed highest / Mon lowest"),
    ("7月最高 / 9月最低", "Jul highest / Sep lowest"),
    ("每组仅约 9 年", "only ~9 years per group"),
    ("节前交易日 n=262", "pre-holiday trading days n=262"),
    ("区间交易日 n=530", "trading days in window n=530"),
])
def test_detail_shapes_round_trip(zh, en):
    """数字必须原样搬运(不重算)——译文里的 9 / 262 / 530 都来自中文串本身。"""
    from placebo_test import _detail_en
    assert _detail_en(zh) == en


def test_unknown_detail_falls_back_to_chinese():
    """未知形状不硬翻:退回中文让人看见缺口,而不是悄悄编一句英文。"""
    from placebo_test import _detail_en
    weird = "某种以后才会出现的新说法"
    assert _detail_en(weird) == weird
    assert _detail_en(None) is None and _detail_en("") == ""


def test_cpcv_verdict_bands_are_single_branch():
    """CPCV 裁决的档位表必须中英同源(同一 key 取两列),不能是两套 if/elif —— 那迟早漂移。"""
    import cpcv
    src = Path(cpcv.__file__).read_text(encoding="utf-8")
    m = re.search(r'band = "high" if p >= 0\.5 else "mid" if p >= 0\.35 else "low"', src)
    assert m, "CPCV 档位判定不再是单分支了?中英文案有各判一次、进而漂移的风险,请检查"
    for band in ("high", "mid", "low"):
        assert re.search(rf'"{band}":\s*\(', src), f"TAG 表缺 {band} 档"
