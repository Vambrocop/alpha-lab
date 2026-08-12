"""test_au_checkup.py — 澳股体检(B2)单测:流动性分档边界 + beta_key 参数化守门 + 数据卫生标记守门。"""
import numpy as np
import pandas as pd

import au_checkup as ac
import stock_checkup as sc
import fetch_data_au as fau


# ── 流动性档位:机械分档边界(规则公示口径,勿漂移) ────────────────────────
def test_liquidity_tier_boundaries():
    assert ac.liquidity_tier(10e6)["tier"] == "high"          # ≥$10M 含边界
    assert ac.liquidity_tier(9.99e6)["tier"] == "mid"
    assert ac.liquidity_tier(1e6)["tier"] == "mid"            # ≥$1M 含边界
    assert ac.liquidity_tier(0.99e6)["tier"] == "low"
    low = ac.liquidity_tier(0.5e6)
    assert "note_zh" in low and "谨慎" in low["note_zh"]       # 低档必须带谨慎解读标
    unk = ac.liquidity_tier(None)
    assert unk["status"] == "unknown" and "tier" not in unk    # 缺数据如实 unknown,绝不猜档


def test_liquidity_tier_nan_is_unknown():
    assert ac.liquidity_tier(float("nan"))["status"] == "unknown"


# ── beta_key 参数化:默认=美股原键(回归门语义);AU 键独立 ─────────────────
def _toy_px(n=300, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=idx)


def test_compute_basic_risk_beta_key_default_unchanged():
    px, bench = _toy_px(), _toy_px(seed=8)
    out = sc.compute_basic_risk(px, bench)
    assert "beta_nasdaq" in out and "beta_axjo" not in out     # 默认=美股原行为


def test_compute_basic_risk_beta_key_axjo():
    px, bench = _toy_px(), _toy_px(seed=8)
    out = sc.compute_basic_risk(px, bench, beta_key="beta_axjo")
    assert "beta_axjo" in out and "beta_nasdaq" not in out
    # 键名只改名不改值:两次调用 β 数值必须一致
    assert out["beta_axjo"] == sc.compute_basic_risk(px, bench)["beta_nasdaq"]


# ── 数据卫生标记守门:B0 结论的常量别被将来误删(FMG 身份/COL 短史) ─────────
def test_data_hygiene_notes_present():
    assert "FMG" in fau.IDENTITY_NOTES, "FMG 身份连续性标记被删——B3 回测门依赖它"
    assert "COL" in fau.SHORT_HISTORY_NOTES, "COL 短史标记被删"
    assert "NCM" not in fau.STOCK_TICKERS, "NCM 已退市,不该回到池子"
    assert len(fau.STOCK_TICKERS) >= 100, "③ 已扩到 ~ASX100(100+ 只);少于此说明池被误缩"


def test_au_names_cover_pool():
    missing = [n for n in fau.STOCK_TICKERS if n not in ac.AU_NAMES]
    assert not missing, f"AU 池有票缺中文名映射: {missing}"


# ── fail-soft 冒烟(事后审计 MEDIUM:上游选择逻辑与故障路径此前零测·真实28票全high档跑不到)──
def test_run_all_fail_soft_all_data_missing(monkeypatch):
    import util_io
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: [])   # 不落盘
    monkeypatch.setattr(ac, "STOCK_TICKERS", {"BHP": "BHP.AX", "CBA": "CBA.AX"})
    monkeypatch.setattr(ac, "_load_au_close", lambda name: None)     # AXJO+票 csv 全缺
    monkeypatch.setattr(ac, "_load_dollar_volume", lambda: None)     # dv 缺
    out = ac.run_all()                                               # 不炸
    assert out["summary"]["n_ok"] == 0
    assert all(v["status"] == "unavailable" for v in out["tickers"].values())


def test_run_all_liquidity_unknown_when_few_obs(monkeypatch):
    import util_io
    monkeypatch.setattr(util_io, "write_json", lambda *a, **k: [])
    monkeypatch.setattr(ac, "STOCK_TICKERS", {"BHP": "BHP.AX"})
    idx = pd.bdate_range("2023-01-02", periods=600)
    rng = np.random.default_rng(3)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 600)), index=idx)
    monkeypatch.setattr(ac, "_load_au_close", lambda name: px)       # 票与 AXJO 同型合成序列
    dv = pd.DataFrame({"BHP.AX": np.full(20, 5e6)}, index=idx[-20:])  # 仅20个有效观测(<30门槛)
    monkeypatch.setattr(ac, "_load_dollar_volume", lambda: dv)
    out = ac.run_all()
    assert out["tickers"]["BHP.AX"]["status"] == "ok"                # 体检本体正常
    assert out["tickers"]["BHP.AX"]["liquidity"]["status"] == "unknown"   # <30 有效值→不猜档
