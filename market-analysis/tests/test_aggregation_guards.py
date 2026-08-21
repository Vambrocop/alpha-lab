"""test_aggregation_guards.py — run_all 级聚合产物防漂移单测。

覆盖三个高价值聚合点：
1. scorecard.run(write=False)  — 公开计分卡结构稳定性
2. overreaction_alert.run(write=False, push=False)  — 告警函数在无数据时优雅降级
3. 已提交的 web/*.json 关键产物顶层键完整性（无网络、无 LLM）

设计原则：
- 不联网、不真实写盘、不依赖真实原始数据文件（缺失则 skip）
- 本地 CI 数据齐备时全通，本地数据缺失时 skip 而非 FAIL
"""
import json
from pathlib import Path

import pytest

# ── 路径常量 ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).parent.parent.parent   # repo root
_WEB = _REPO / "market-analysis" / "web"


# ══════════════════════════════════════════════════════════════════════════════
# 1. scorecard.run(write=False) — 公开计分卡结构稳定性
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def scorecard_result():
    """跑 scorecard.run(write=False)；依赖的原始数据(data/raw/combined_prices.csv 等)缺失时
    skip 而非 FAIL——遵循本文件设计原则(缺失则 skip)。

    为什么必须 skip：CI 的 pytest 门禁在流水线之前跑(挡坏代码发布)，此时 data/raw/ 还没生成
    (且 gitignore 不入库)，scorecard.run 直接读 combined_prices.csv 会 FileNotFoundError。
    已提交的 scorecard.json 形状另有 test_scorecard_json_top_level_keys 在 CI 里守。"""
    import scorecard
    try:
        return scorecard.run(write=False)
    except FileNotFoundError as e:
        pytest.skip(f"scorecard 依赖的原始数据缺失（{getattr(e, 'filename', e)}）"
                    f"——CI 门禁在流水线前、无生成数据，跳过")


def test_scorecard_run_returns_dict_with_sources(scorecard_result):
    """scorecard.run(write=False) 必须返回含 sources(dict) 的 dict，不抛异常。"""
    result = scorecard_result
    assert isinstance(result, dict), "scorecard.run 应返回 dict"
    assert "sources" in result, "返回值须含 'sources' 键"
    assert isinstance(result["sources"], dict), "'sources' 须是 dict"


def test_scorecard_llm_row_filters_by_direction_not_bucket(tmp_path, monkeypatch):
    """防复发(2026-08 真 bug):⑤ LLM 行曾误用 `bucket`(=实际结果桶)筛"方向下注",
    等于挑"市场真动了的日子"再看一个几乎只说中性的 LLM 中没中 → 假 0%(误导公开战绩)。
    必须按 `direction`(LLM 的预测)筛。合成账本:29 条中性预测(其中 13 条实际结果落在
    偏多/偏空桶) + 1 条真·方向预测 → n_scored 必须是 1(按预测),不是 13(按实际结果)。
    hermetic:合成 CSV + monkeypatch BASE/RAW/PROC(RAW/PROC 是模块级常量,patch BASE 够不着;
    CI 干净检出无 data/raw/,若漏 patch RAW,_nasdaq() 会 FileNotFoundError → 门禁红,06-25 同坑)。"""
    import pandas as pd
    import scorecard

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # 合成纳指价格(RAW):_nasdaq() 开场就读它,必须 hermetic 提供
    raw_dir = data_dir / "raw"
    raw_dir.mkdir()
    dates = pd.bdate_range("2026-06-01", periods=60)
    pd.DataFrame({"Date": dates, "NASDAQ": 100.0 + pd.RangeIndex(len(dates))}).to_csv(
        raw_dir / "combined_prices.csv", index=False)
    rows = ["pred_date,symbol,direction,confidence,horizon_td,ret_pct,bucket,hit,settled,dropped"]
    # 29 条中性预测:前 13 条市场实际大动(bucket=偏多/偏空)——旧 bug 会把这 13 条错当"方向下注"
    for i in range(29):
        bucket = ("偏多" if i % 2 == 0 else "偏空") if i < 13 else "中性"
        hit = "False" if i < 13 else "True"
        rows.append(f"2026-07-{i % 28 + 1:02d},SPY,中性,低,5,0.5,{bucket},{hit},True,False")
    # 1 条真·方向预测(偏多,实际中性→没中)
    rows.append("2026-07-30,SPY,偏多,中,5,0.2,中性,False,True,False")
    (data_dir / "llm_prediction_log.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(scorecard, "BASE", data_dir.parent)   # 其它源找不到文件→各自 except 跳过,只剩 ⑤ 可算
    monkeypatch.setattr(scorecard, "RAW", raw_dir / "combined_prices.csv")
    monkeypatch.setattr(scorecard, "PROC", data_dir / "processed")
    try:
        result = scorecard.run(write=False)
    except FileNotFoundError:
        pytest.fail("scorecard.run 不该因其它数据缺失而抛 FileNotFoundError(各源应独立 fail-soft)")
    llm = result["sources"].get("LLM前瞻方向(出格·live)")
    assert llm is not None, "合成账本存在时 ⑤ LLM 行必须出现"
    assert llm["n_scored"] == 1, (
        f"n_scored 应=1(按 direction 筛真·方向预测);若=13 说明退回了按 bucket(实际结果)筛的旧 bug: {llm}")


def test_scorecard_model_calibration_shape(scorecard_result):
    """若 model_calibration 存在且非 None，须含数值型 base_rate_pct。

    若 walk_forward_results.json 缺失，_model_calibration() 返回 None — 这也合法，跳过。
    """
    mc = scorecard_result.get("model_calibration")
    if mc is None:
        pytest.skip("model_calibration 为 None（缺少 walk_forward_results.json），可接受")
    assert isinstance(mc, dict), "model_calibration 须是 dict"
    br = mc.get("base_rate_pct")
    assert isinstance(br, (int, float)), f"base_rate_pct 须是数值，实际: {type(br)}"
    assert 0.0 < br < 100.0, f"base_rate_pct 须在 (0,100) 范围，实际: {br}"


def test_scorecard_sources_entries_have_required_keys(scorecard_result):
    """sources 里每一条预测源必须携带 n_scored 和 n_pending（不管是否有命中率）。"""
    for name, entry in scorecard_result["sources"].items():
        assert "n_scored" in entry, f"source '{name}' 缺 n_scored"
        assert "n_pending" in entry, f"source '{name}' 缺 n_pending"
        assert isinstance(entry["n_scored"], int), f"source '{name}' n_scored 须是 int"
        assert isinstance(entry["n_pending"], int), f"source '{name}' n_pending 须是 int"


# ══════════════════════════════════════════════════════════════════════════════
# 2. overreaction_alert.run — 无数据时优雅降级到 None
# ══════════════════════════════════════════════════════════════════════════════

def test_overreaction_alert_graceful_on_missing_data(monkeypatch, tmp_path):
    """SP500_long.csv 不存在时 run() 须返回 None，不抛异常。"""
    import overreaction_alert as oa
    import util_io

    # 把 _sp_close 替换成总是返回 None（模拟无数据）
    monkeypatch.setattr(oa, "_sp_close", lambda: None)
    monkeypatch.setattr(oa, "LOG", tmp_path / "sig_log.csv")
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)

    result = oa.run(write=False, push=False)
    assert result is None, "无 SP500 数据时 run() 须返回 None"


def test_overreaction_alert_result_shape_when_data_available(monkeypatch, tmp_path):
    """当 _sp_close 有数据时，run() 须返回含 today/threshold_pct/track_record 的 dict。

    本测试用合成数据驱动，不联网。
    """
    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        pytest.skip("numpy/pandas 不可用")

    import overreaction_alert as oa
    import util_io

    # 合成 600 条收益序列（无极端下跌，不触发告警）
    rng = np.random.default_rng(42)
    rets = list(rng.normal(0.0005, 0.01, 600)) + [0.005]   # 末日正收益
    idx = pd.bdate_range(start="2001-01-02", periods=len(rets) + 1)
    px = [100.0]
    for r in rets:
        px.append(px[-1] * (1 + r))
    series = pd.Series(px, index=idx)

    monkeypatch.setattr(oa, "_sp_close", lambda: series)
    monkeypatch.setattr(oa, "_modern_stat",
                        lambda: {"bounce_next_pct": 0.294, "other_next_pct": 0.018,
                                 "p_value": 0.001, "pct_negative": 46.3})
    monkeypatch.setattr(oa, "LOG", tmp_path / "sig_log.csv")
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: None)

    result = oa.run(write=False, push=False)
    assert result is not None, "有数据时 run() 不应返回 None"
    assert isinstance(result, dict), "run() 须返回 dict"
    assert "today" in result, "返回值须含 'today' 键"
    assert "threshold_pct" in result, "返回值须含 'threshold_pct' 键"
    assert "track_record" in result, "返回值须含 'track_record' 键"


# ══════════════════════════════════════════════════════════════════════════════
# 3. 已提交的 web/*.json 关键产物顶层键完整性
# ══════════════════════════════════════════════════════════════════════════════

def _load_web_json(filename):
    """加载 web/*.json；若文件不存在则返回 None（调用方 skip）。"""
    p = _WEB / filename
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def test_scorecard_json_top_level_keys():
    """已发布的 scorecard.json 须含 sources/horizon_days/generated。"""
    data = _load_web_json("scorecard.json")
    if data is None:
        pytest.skip("scorecard.json 不存在，跳过")
    for key in ("sources", "horizon_days", "generated"):
        assert key in data, f"scorecard.json 缺顶层键 '{key}'"
    assert isinstance(data["sources"], dict), "scorecard.json sources 须是 dict"


def test_overreaction_json_top_level_keys():
    """已发布的 overreaction.json 须含 status/verdict/full/recent。"""
    data = _load_web_json("overreaction.json")
    if data is None:
        pytest.skip("overreaction.json 不存在，跳过")
    for key in ("status", "verdict", "full", "recent"):
        assert key in data, f"overreaction.json 缺顶层键 '{key}'"


def test_fdr_crossfamily_json_claims_have_survive_flags():
    """已发布的 fdr_crossfamily.json：每条 claim 须含 p 值和至少一个 survive_* 标志。"""
    data = _load_web_json("fdr_crossfamily.json")
    if data is None:
        pytest.skip("fdr_crossfamily.json 不存在，跳过")
    claims = data.get("claims", [])
    assert len(claims) >= 1, "fdr_crossfamily.json claims 不应为空"
    for c in claims:
        assert "p" in c, f"claim '{c.get('label')}' 缺 p 值"
        has_survive = any(k.startswith("survive_") for k in c)
        assert has_survive, f"claim '{c.get('label')}' 缺 survive_* 存活标志"


def test_market_regime_json_structure():
    """已发布的 market_regime.json 须含 status/components/composite。"""
    data = _load_web_json("market_regime.json")
    if data is None:
        pytest.skip("market_regime.json 不存在，跳过")
    for key in ("status", "components", "composite"):
        assert key in data, f"market_regime.json 缺顶层键 '{key}'"
    assert isinstance(data["components"], list), "market_regime.json components 须是 list"
