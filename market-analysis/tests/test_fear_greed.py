"""test_fear_greed.py — SPEC_FEAR_GREED §6(合成/固定,不碰网络)。

覆盖:各子分映射边界、档位分类(含边界值归属)、composite=可得子分均值(<2→无)、
去聚集(同档连续日并段/变档断段)、段级聚类自助 CI 覆盖已知均值、ci_differs_base 逻辑、
verdict 三态可达且无 signal/buy/sell/edge 词根、段<8→described-only 无 CI、
集成 run() 结构 + honesty 含「近似」「非 CNN」+ components_used 进 json + verdict_note 不含「该买/该卖」。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fear_greed as fg  # noqa: E402


def _bidx(n, start="2000-01-03"):
    return pd.bdate_range(start, periods=n)


def _approx(v):
    return pytest.approx(v, abs=1e-6)


# ── 1. 各子分映射边界(§6·1)────────────────────────────────────────
def test_subscore_boundaries():
    assert fg.sub_momentum(0.10) == _approx(100)
    assert fg.sub_momentum(-0.10) == _approx(0)
    assert fg.sub_momentum(0.0) == _approx(50)

    assert fg.sub_volatility(0.0) == _approx(100)   # 分位0(最低VIX)→最贪婪
    assert fg.sub_volatility(1.0) == _approx(0)     # 分位1(最高VIX)→最恐慌
    assert fg.sub_volatility(0.5) == _approx(50)

    assert fg.sub_term_structure(0.0) == _approx(50)
    assert fg.sub_term_structure(5.0) == _approx(100)   # clip 上限
    assert fg.sub_term_structure(-5.0) == _approx(0)    # clip 下限

    assert fg.sub_risk_appetite(0.0) == _approx(50)
    assert fg.sub_risk_appetite(0.10) == _approx(100)
    assert fg.sub_risk_appetite(-0.10) == _approx(0)


# ── 2. 档位分类(§6·2,边界值归属明确)──────────────────────────────
def test_band_classification():
    assert fg.band_for(24.9) == "extreme_fear"
    assert fg.band_for(50) == "neutral"
    assert fg.band_for(80) == "extreme_greed"
    # 边界值归属(本实现的显式选择,已在 band_for 文档字符串写明):
    assert fg.band_for(25) == "extreme_fear"
    assert fg.band_for(25.01) == "fear"
    assert fg.band_for(45) == "fear"
    assert fg.band_for(45.01) == "neutral"
    assert fg.band_for(55) == "neutral"
    assert fg.band_for(55.01) == "greed"
    assert fg.band_for(74.99) == "greed"
    assert fg.band_for(75) == "extreme_greed"
    assert fg.band_for(None) is None
    assert fg.band_for(float("nan")) is None


# ── 3. composite = 可得子分均值;<2 个 → 无 composite(§6·3)────────
def test_composite_series_available_count():
    idx = _bidx(3)
    subs = pd.DataFrame({
        "momentum": [60.0, 60.0, np.nan],
        "volatility": [40.0, np.nan, np.nan],
        "term_structure": [np.nan, 80.0, np.nan],
        "risk_appetite": [50.0, np.nan, 90.0],
    }, index=idx)
    comp = fg.composite_series(subs)
    assert comp.iloc[0] == round((60 + 40 + 50) / 3, 1)   # 3 个可得
    assert comp.iloc[1] == round((60 + 80) / 2, 1)         # 2 个可得
    assert pd.isna(comp.iloc[2])                            # 只 1 个可得 → 无 composite


# ── 4. 去聚集:同档连续日并段、变档断段(§6·4)────────────────────
def test_detect_band_stretches():
    idx = _bidx(8)
    bands = pd.Series(
        ["fear", "fear", "neutral", "neutral", "neutral", "fear", "greed", "greed"], index=idx
    )
    out = fg.detect_band_stretches(bands)
    assert len(out["fear"]) == 2
    assert len(out["fear"][0]) == 2
    assert len(out["fear"][1]) == 1
    assert len(out["neutral"]) == 1 and len(out["neutral"][0]) == 3
    assert len(out["greed"]) == 1 and len(out["greed"][0]) == 2


def test_detect_band_stretches_hysteresis():
    # 迟滞重置命门:extreme_greed 抖回同侧的 greed 再抖回来 = 同一段(不因穿过 75 就多算);
    # 只有回到 neutral(离开贪婪侧)才重置、下次进入才算新段。
    idx = _bidx(9)
    #        xg    greed  xg    xg    neutral xg    xg    fear  xg
    bands = pd.Series(
        ["extreme_greed", "greed", "extreme_greed", "extreme_greed",
         "neutral", "extreme_greed", "extreme_greed", "fear", "extreme_greed"], index=idx
    )
    out = fg.detect_band_stretches(bands)
    xg = out["extreme_greed"]
    # 段1 = d0 + d2 + d3(中间 d1=greed 同侧,不断段、但 greed 日不收进 xg 段);
    # d4=neutral 离开贪婪侧 → 重置;段2 = d5 + d6;d7=fear 离开 → 重置;段3 = d8
    assert len(xg) == 3
    assert [d.day for d in xg[0]] == [idx[0].day, idx[2].day, idx[3].day]   # greed 日(d1)不在内
    assert len(xg[1]) == 2
    assert len(xg[2]) == 1


def test_detect_band_stretches_skips_none():
    idx = _bidx(5)
    bands = pd.Series(["fear", None, "fear", "fear", None], index=idx)
    out = fg.detect_band_stretches(bands)
    # None(无 composite 当日)断段,不进任何段;两段各自独立
    assert len(out["fear"]) == 2
    assert len(out["fear"][0]) == 1
    assert len(out["fear"][1]) == 2


# ── 5. 段级聚类自助 CI 覆盖已知均值(直接测 import 来的 cluster_bootstrap,§6·5)──
def test_cluster_bootstrap_covers_mean():
    rng = np.random.default_rng(0)
    segs = [rng.normal(0.05, 0.01, size=15) for _ in range(10)]   # 10 段,真均值 ~5%
    ci = fg.cluster_bootstrap(segs, seed=1)
    assert ci[0] <= 5.0 <= ci[1]
    assert ci[0] < ci[1]


# ── 6. ci_differs_base 逻辑:CI 整段在基率一侧才 True(§6·6)────────
def test_ci_differs_base_logic():
    idx = _bidx(2200)
    rng = np.random.default_rng(5)
    fwd = pd.Series(rng.normal(0.06, 0.003, size=2200), index=idx)   # 紧凑分布,真均值 ~6%
    stretches = [[idx[i]] for i in range(0, 2200, 25)]               # 88 段·间隔 25 交易日(> horizon,不会被并)

    # base=0%:CI 应整段落在 base(0) 上方 → ci_differs_base True
    cell_far = fg.build_band_cell("fear", stretches, fwd, base_up=0.5, base_mean=0.0, seed=3, horizon=20)
    assert cell_far["too_small_no_ci"] is False
    assert cell_far["ci_differs_base"] is True

    # base=6%(=样本均值附近):CI 应跨过 base → ci_differs_base False
    cell_cross = fg.build_band_cell("fear", stretches, fwd, base_up=0.5, base_mean=0.06, seed=3, horizon=20)
    assert cell_cross["ci_differs_base"] is False


# ── 7. verdict 三态可达 且 无 signal/buy/sell/edge 词根(§6·7)─────
def test_verdict_states_and_no_forbidden_words():
    assert fg.verdict_for("fear", True, 5.0, True, True) == "described-only"
    # 极度贪婪:diff<0 + CI 整段落在基率下方(ci_below_base=True,第4参)→ contrarian-holds
    assert fg.verdict_for("extreme_greed", False, -2.0, True, False) == "contrarian-holds"
    # 极度恐慌:diff>0 + CI 整段落在基率上方(ci_above_base=True,第5参)→ contrarian-holds
    assert fg.verdict_for("extreme_fear", False, 2.0, False, True) == "contrarian-holds"
    # 非极度档:无论如何都不触发 contrarian-holds
    assert fg.verdict_for("greed", False, -2.0, True, False) == "not-contrarian"
    assert fg.verdict_for("fear", False, 2.0, False, True) == "not-contrarian"
    # 极度档但方向不对/CI 不可靠
    assert fg.verdict_for("extreme_greed", False, 2.0, True, False) == "not-contrarian"
    assert fg.verdict_for("extreme_fear", False, 2.0, False, False) == "not-contrarian"

    assert len(fg.ALLOWED_VERDICTS) == 3
    # verdict 名不得含任何禁词根(spec 初稿曾用含"edge"的 "no-contrarian-edge",已改名 "not-contrarian"·§3)
    for v in fg.ALLOWED_VERDICTS:
        low = v.lower()
        for bad in ("buy", "sell", "signal", "edge"):
            assert bad not in low, f"{v} 含禁词根 {bad}"


# ── 8. 段 < MIN_STRETCHES_CI(=8)→ described-only 无 CI(§6·8)────
def test_small_sample_described_only():
    idx = _bidx(30)
    fwd = pd.Series(0.02, index=idx)
    stretches = [[idx[i]] for i in range(5)]   # 5 段(原始)< 8;且相邻会并 → 独立聚类更少
    cell = fg.build_band_cell("neutral", stretches, fwd, base_up=0.5, base_mean=0.01, seed=1, horizon=20)
    assert cell["n_stretches"] == 5
    assert cell["n_independent"] <= 5
    assert cell["too_small_no_ci"] is True
    assert cell["ci95_mean"] is None
    assert cell["verdict"] == "described-only"
    # 不静默——描述性数字仍照实给出
    assert cell["mean_pct"] is not None
    assert cell["up_pct"] is not None


def test_merge_within_horizon():
    # 前向窗口去重叠(审查 Finding-1):相隔 < horizon 的段并为一个 CI 聚类,>= horizon 的保持独立。
    idx = _bidx(100)
    pos_of = {d: i for i, d in enumerate(idx)}
    # 三段:pos 0-1、pos 5(与前段间隔 4)、pos 40(间隔 35)。horizon=10:前两段并、第三段独立 → 2 聚类。
    stretches = [[idx[0], idx[1]], [idx[5]], [idx[40]]]
    clusters = fg._merge_within_horizon(stretches, pos_of, horizon=10)
    assert len(clusters) == 2
    assert clusters[0] == [idx[0], idx[1], idx[5]]   # 前两段合并(含各自的日)
    assert clusters[1] == [idx[40]]
    # horizon=100:全部间隔都 < 100 → 并成 1 个聚类
    assert len(fg._merge_within_horizon(stretches, pos_of, horizon=100)) == 1


def test_page_no_forbidden_phrases():
    # 审查 Finding-2 守门:防「edge」词根再次泄漏进用户可见文案(初稿 EN copyGuard 曾写
    # "whether there's any contrarian edge…",已改为 "reliably deviates from the base rate")。
    # 只查这个【肯定式】短语——它不会出现在任何诚实免责句里(免责句说的是"是否可靠偏离基率"),
    # 故不会误伤 "not a buy/sell signal"、"不该读成「贪婪就该卖」" 这类正当否定式措辞。
    html = (Path(__file__).resolve().parents[1] / "web" / "feargreed.html").read_text(encoding="utf-8").lower()
    assert "contrarian edge" not in html, "feargreed.html 用户文案再次出现 'contrarian edge'(edge 词根泄漏)"


def test_at_min_stretches_gets_ci():
    idx = _bidx(200)
    rng = np.random.default_rng(2)
    fwd = pd.Series(rng.normal(0.02, 0.01, size=200), index=idx)
    stretches = [[idx[i]] for i in range(0, 160, 20)]   # 8 段·间隔 20(= horizon,不并)→ 8 独立聚类
    cell = fg.build_band_cell("fear", stretches, fwd, base_up=0.5, base_mean=0.0, seed=1, horizon=20)
    assert cell["n_stretches"] == 8
    assert cell["n_independent"] == 8
    assert cell["too_small_no_ci"] is False
    assert cell["ci95_mean"] is not None


# ── 9. 集成 run():结构齐全 + honesty/verdict_note 机器守门(§6·9)──
def test_run_structure_and_guards():
    n = 2000
    idx = _bidx(n)
    t = np.arange(n, dtype=float)
    rng = np.random.default_rng(11)
    sp500 = 100.0 * (1.0002 ** t) * (1 + 0.05 * np.sin(t / 50))
    vix = np.clip(20 + 12 * np.sin(t / 30) + rng.normal(0, 2, n), 9, 60)
    vix3m = vix + 2.0 + rng.normal(0, 0.5, n)
    gold = 300.0 * (1.0001 ** t) * (1 + 0.03 * np.sin(t / 70 + 1))
    df = pd.DataFrame({"SP500": sp500, "VIX": vix, "VIX3M": vix3m, "GOLD": gold}, index=idx)

    out = fg.run(write=False, _df=df)

    # 结构齐全
    for k in ("generated", "as_of", "composite_start", "components_used", "current",
              "contrarian", "honesty", "verdict_note"):
        assert k in out, f"缺少字段: {k}"
    assert out["components_used"] == fg.COMPONENT_NAMES
    assert set(out["current"].keys()) >= {"composite", "band", "components"}
    assert len(out["current"]["components"]) == 4
    for c in out["current"]["components"]:
        assert c["name"] in fg.COMPONENT_NAMES
        assert "raw_value" in c and "subscore" in c and "available" in c
    assert out["current"]["band"] in fg.BANDS

    assert isinstance(out["contrarian"]["bands"], list) and len(out["contrarian"]["bands"]) == 10
    for c in out["contrarian"]["bands"]:
        assert c["verdict"] in fg.ALLOWED_VERDICTS
        assert c["band"] in fg.BANDS
        assert c["horizon"] in fg.HORIZONS
        assert "n_days" in c and "n_stretches" in c and "n_independent" in c
        assert c["n_independent"] <= c["n_stretches"]   # 去重叠后聚类数不会超过原始段数
    assert set(out["contrarian"]["stretches_by_band"].keys()) <= set(fg.BANDS)

    # honesty 必含「近似」与「非 CNN」(§0/§4 显眼标注要求的机器守门)
    blob = " ".join(out["honesty"])
    assert "近似" in blob
    assert "非 CNN" in blob

    # verdict_note 不得出现「该买/该卖」等择时措辞,且不得把内部状态字面量("not-contrarian"
    # 含"edge"词根)泄漏进给用户看的文案(§3 命门:纯描述用语,见 _build_verdict_note 注释)
    assert "该买" not in out["verdict_note"]
    assert "该卖" not in out["verdict_note"]
    for bad in ("buy", "sell", "signal", "edge"):
        assert bad not in out["verdict_note"].lower()
