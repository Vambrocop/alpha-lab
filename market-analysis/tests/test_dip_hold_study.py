"""test_dip_hold_study.py — SPEC_DIP_HOLD §6(合成/固定,不碰网络)。

覆盖:dd/prox 计算、rolling252 边界、去聚集(重置+合并)、日级手算、基率、段级聚类自助 CI、
described-only 门槛、分时代、verdict 三态且无 edge/买入态、单股只出快照+幸存者守门、honesty/primary_cell 进 json。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dip_hold_study as D  # noqa: E402


def _bidx(n, start="2000-01-03"):
    return pd.bdate_range(start, periods=n)


# ── 1. dd / prox 计算 ────────────────────────────────────────────────
def test_drawdown_value(monkeypatch):
    monkeypatch.setattr(D, "LOOKBACK", 3)
    idx = _bidx(5)
    px = pd.Series([100.0, 110, 120, 90, 60], index=idx)
    dd, prox = D._drawdown(px)
    # idx3=90: rolling3 高=max(110,120,90)=120 → 90/120-1=-0.25;低=90 → 0
    assert round(dd.iloc[3], 4) == round(90 / 120 - 1, 4)
    assert round(prox.iloc[3], 4) == 0.0


# ── 2. rolling252 边界:< LOOKBACK 日无产出 ──────────────────────────
def test_rolling_boundary_nan():
    px = pd.Series(np.linspace(100, 130, 300), index=_bidx(300))
    dd, prox = D._drawdown(px)
    assert dd.iloc[: D.LOOKBACK - 1].isna().all()
    assert not np.isnan(dd.iloc[D.LOOKBACK - 1])


# ── 3. 去聚集:重置 + 合并 ──────────────────────────────────────────
def test_declustering_reset():
    # -0.25(ep1) → -0.02(≥-0.03 解除) → -0.25(ep2) → -0.10(< thresh 但未过地板) → -0.01(解除) → -0.25(ep3)
    dd = pd.Series([-0.25, -0.02, -0.25, -0.10, -0.01, -0.25], index=_bidx(6))
    eps = D.detect_dd_episodes(dd, -0.20, recovery=-0.03)
    assert len(eps) == 3


def test_declustering_merge():
    # -0.25 → 只回到 -0.05(< -0.03,未解除)→ -0.25 = 同一段
    dd = pd.Series([-0.25, -0.05, -0.25], index=_bidx(3))
    eps = D.detect_dd_episodes(dd, -0.20, recovery=-0.03)
    assert len(eps) == 1
    assert len(eps[0]) == 2   # 两个合格日都归这一段


# ── 4. 日级手算 + 基率参照 + described-only(段<8)──────────────────
def test_daylevel_handcalc_and_small_sample():
    idx = _bidx(5)
    dd = pd.Series([-0.25, -0.05, -0.25, -0.25, -0.01], index=idx)   # 合格(≤-0.20): d0,d2,d3
    fwd = pd.Series([0.10, 0.0, -0.05, 0.20, 0.0], index=idx)
    cell = D.build_dd_cell(dd, fwd, 20, base_up=0.5, base_mean=0.05, seed=1, horizon=20)
    assert cell["n_days"] == 3
    assert cell["mean_pct"] == round((0.10 - 0.05 + 0.20) / 3 * 100, 2)   # 8.33
    assert cell["up_pct"] == round(2 / 3 * 100, 2)                        # 66.67
    assert cell["base_mean_pct"] == 5.0
    assert cell["diff_mean"] == round(cell["mean_pct"] - 5.0, 2)
    # d0,d2,d3 属同一段(中间 -0.05 未过地板)→ 段=1 < 8 → described-only 无 CI
    assert cell["n_episodes_with_fwd"] == 1
    assert cell["too_small_no_ci"] is True
    assert cell["ci95_mean"] is None
    assert cell["verdict"] == "described-only"


# ── 4b. 前向窗口去重叠:相隔 < horizon 的危机段并为一个 CI 聚类 ────────
def test_dd_cell_horizon_merges_overlapping_windows():
    idx = _bidx(60)
    # 段1 = d0,d1(≤-0.20);d2 回到 -0.01(≥-0.03 重置);段2 = d5,d6。相隔 4 交易日。
    vals = [-0.25, -0.25, -0.01, -0.01, -0.01, -0.25, -0.25] + [-0.01] * 53
    dd = pd.Series(vals, index=idx)
    fwd = pd.Series([0.05] * 60, index=idx)
    cell = D.build_dd_cell(dd, fwd, 20, base_up=0.5, base_mean=0.0, seed=1, horizon=10)
    assert cell["n_episodes_with_fwd"] == 2   # 两个原始危机段
    assert cell["n_independent"] == 1          # 相隔 4 < horizon 10 → 前向窗口重叠 → 并为 1 聚类


# ── 5. 段级聚类自助 CI 覆盖已知均值 ─────────────────────────────────
def test_cluster_bootstrap_covers_mean():
    rng = np.random.default_rng(0)
    eps = [rng.normal(0.10, 0.02, size=20) for _ in range(12)]   # 12 段,真均值 ~10%
    ci = D.cluster_bootstrap(eps, seed=1)
    assert ci[0] <= 10.0 <= ci[1]
    assert ci[0] < ci[1]


# ── 6. 分时代 same_sign 逻辑 ───────────────────────────────────────
def test_era_same_sign():
    # 全在 2000-2012(合格日)且都正 → era2 无数据 → era_same_sign None
    idx = _bidx(4, start="2005-01-03")
    dd = pd.Series([-0.25, -0.25, -0.01, -0.25], index=idx)
    fwd = pd.Series([0.1, 0.2, 0.0, 0.1], index=idx)
    cell = D.build_dd_cell(dd, fwd, 20, base_up=0.5, base_mean=0.02, seed=1, horizon=20)
    assert cell["era1_mean_pct"] is not None
    assert cell["era2_mean_pct"] is None
    assert cell["era_same_sign"] is None


# ── 7. verdict 三态可达 且 均非 edge/买入/信号 ─────────────────────
def test_verdict_states_and_no_edge():
    assert D.verdict_for(True, 5.0, True, True) == "described-only"          # 段太小
    assert D.verdict_for(False, 5.0, True, True) == "robust-across-crises"   # 跑赢+CI可靠跑赢+同向
    assert D.verdict_for(False, 5.0, True, False) == "crisis-driven-fragile" # 跑赢但 CI 不可靠
    assert D.verdict_for(False, -1.0, True, True) == "described-only"        # 不跑赢基率
    for v in D.ALLOWED_VERDICTS:
        assert all(bad not in v for bad in ("edge", "buy", "signal", "抄底"))


# ── 8. 单股:只出快照、绝不回测、幸存者守门 ────────────────────────
def test_single_stock_snapshot_only():
    df = pd.DataFrame({"AAA": np.linspace(100, 150, 300)}, index=_bidx(300))
    snap = D.single_stock_snapshot(df)
    assert set(snap["current"][0].keys()) == {"ticker", "dd_from_52wk_high_pct", "dist_from_52wk_low_pct"}
    assert snap["survivorship_note"] and "幸存者" in snap["survivorship_note"]
    assert "绝不回测" in snap["survivorship_note"]   # 守门:显式声明单股不回测
    # 单股条目只含当前快照字段,无任何前向收益/回测结果字段泄漏
    for row in snap["current"]:
        assert not any(k for k in row if "forward" in k or "fwd" in k or "verdict" in k)


# ── 9. 集成:结构 + 机器守门(honesty/primary_cell/survivorship 进 json)──
def test_run_structure_and_guards():
    n = 800
    idx = _bidx(n)
    px = pd.Series(
        np.concatenate([np.linspace(100, 200, 300),
                        np.linspace(200, 120, 100),
                        np.linspace(120, 260, 400)])[:n], index=idx)
    stocks = pd.DataFrame({"AAA": px.values, "BBB": (px.values * 0.5)}, index=idx)
    out = D.run(write=False, _price=px, _stocks=stocks)

    assert out["primary_cell"] == {"index": "SP500", "dd_threshold_pct": 20, "horizon": 252}
    assert out["base_rate"]["h252"]["n"] > 0
    assert out["honesty"] and any("幸存者" in h for h in out["honesty"])
    assert out["single_stocks"]["survivorship_note"]
    for c in out["drawdown_curve"]:
        assert c["verdict"] in D.ALLOWED_VERDICTS
        # 每格都带独立段数(重叠日不当真 N)
        assert "n_episodes_with_fwd" in c and "n_days" in c and "n_independent" in c
        assert c["n_independent"] <= c["n_episodes_with_fwd"]   # 去重叠后聚类数 ≤ 原始段数
    # verdict_note 必须带「非买入信号」免责,且不得出现肯定买入的措辞
    assert "非买入信号" in out["verdict_note"]
    assert "建议买入" not in out["verdict_note"] and "该买" not in out["verdict_note"]
