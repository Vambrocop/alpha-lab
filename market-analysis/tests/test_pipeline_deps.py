"""流水线可选依赖守门 — 缺了就让测试红,而不是让数据悄悄发霉。

起因(2026-08-24):CI 的 requirements-core 没装 lxml → build_ndx 的 pd.read_html 每跑必
ImportError → workflow 里 `|| echo ::warning::` 把它咽下去 → ndx.json 悄悄陈旧 24 天,
直到 staleness_watchdog 才叫(阈值 14 天)。本地有 lxml 所以怎么跑都正常——最难发现的那类。

这里守的是"**pandas 的可选后端在 CI 里真的装了**":pytest 门禁跑在与流水线同一个环境、
且在 run_all 之前,缺依赖会立刻红,不用等两周后看数据发霉。
hermetic:只用内存里的 HTML 字符串,不联网、不读 data/(CI 干净检出也能跑)。
"""
from io import StringIO

import pandas as pd
import pytest


def test_lxml_importable():
    """build_ndx 依赖 lxml 作 read_html 后端;缺失时 pandas 只报 ImportError,这里提前拦。"""
    pytest.importorskip  # noqa: B018  (显式表明这里刻意 *不* skip:缺了就该红)
    import lxml.etree  # noqa: F401


def test_read_html_parses_a_table():
    """真正跑一遍 pd.read_html(与 build_ndx._fetch_constituents 同一调用路径)。
    仅靠 `import lxml` 不够:pandas 换后端/换 API 也会在这里现形。"""
    html = """
    <table>
      <tr><th>Ticker</th><th>Company</th></tr>
      <tr><td>AAPL</td><td>Apple</td></tr>
      <tr><td>MSFT</td><td>Microsoft</td></tr>
    </table>
    """
    tables = pd.read_html(StringIO(html))
    assert len(tables) == 1
    t = tables[0]
    assert list(t.columns) == ["Ticker", "Company"]
    assert t["Ticker"].tolist() == ["AAPL", "MSFT"]


def test_build_ndx_declares_lxml_in_core_requirements():
    """防回退:有人清理依赖时把 lxml 删掉 → 这条红,提醒他先看 build_ndx。"""
    from pathlib import Path
    req = (Path(__file__).parent.parent / "requirements-core.txt").read_text(encoding="utf-8")
    assert "lxml" in req, "requirements-core.txt 缺 lxml → CI 里 build_ndx 会 ImportError 后静默烂掉"


# ── 数据层双语:标签规则翻译器的覆盖率守门(2026-08-27) ──────────────────────
def test_label_en_translates_known_factor_labels():
    """label_en 是规则式(非映射表),好处是新因子自动跟上;代价是片段表可能漏。
    这里钉住一批**线上真实出现过**的标签必须全译,防止将来改片段表时悄悄退化。"""
    from label_en import label_en, is_fully_translated
    must = ["BTC在MA200上方", "NASDAQ RSI超买>75", "BTC近20日涨>5%", "NASDAQ低波动<15%",
            "星期效应", "月份效应(月度胜率)", "九月效应", "隔夜动量为正(20d)",
            "美元走弱", "油价→标普", "地缘冲击", "银行危机"]
    bad = [m for m in must if not is_fully_translated(m)]
    assert not bad, f"这些线上标签没被 label_en 全译(片段表需补): {bad}"
    assert label_en("BTC在MA200上方") == "BTC above MA200"


def test_label_en_is_safe_on_odd_input():
    """非字符串/空/纯英文 → 原样返回,不炸(调用方可无脑套用)。"""
    from label_en import label_en
    assert label_en(None) is None and label_en("") == ""
    assert label_en("QQQ vs SPY") == "QQQ vs SPY"
