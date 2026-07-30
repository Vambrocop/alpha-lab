"""test_ebm_duel.py — SPEC_EBM.md(R3)§6 测试(≥11条·脱网/合成)

编号对应 spec §6 列表(1..11)。多数测试不需要 `interpret`(合成数据测逻辑:特征变换/无前瞻/
PIT/门逻辑/同信息公平性/新写成对块自助/fail-soft跳过/无污染)——interpret 真正需要的测试
(纯可加/位级可复现)用 `pytest.importorskip("interpret")` 守。
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ebm_duel  # noqa: E402


# ══════════════════════════════════════════════════════════════════
# 测试夹具:合成 combined_prices.csv + NASDAQ_COMP_long.csv(§6 测试1/2/3 共用)
# ══════════════════════════════════════════════════════════════════
def _write_synthetic_raw(raw_dir, n=80, seed=7):
    """构造 n 个交易日的合成原始数据,写到 raw_dir/combined_prices.csv 与 NASDAQ_COMP_long.csv。
    价格/VIX/T10Y2Y/CREDIT_SPREAD 全部用固定种子随机游走生成(正值、无零),
    列名与真实文件一致(NASDAQ_COMP / VIX / T10Y2Y / CREDIT_SPREAD)。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2000-01-03", periods=n)
    px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    vix = 15 + 10 * np.abs(rng.normal(0, 1, n)).cumsum() / n * 5 + rng.normal(0, 1, n)
    vix = np.clip(vix, 5, 80)
    t10y2y = rng.normal(0.5, 0.3, n).cumsum() * 0.05
    credit = 1.5 + np.abs(rng.normal(0, 0.3, n)).cumsum() / n * 3

    combined = pd.DataFrame({
        "Date": dates, "VIX": vix, "T10Y2Y": t10y2y, "CREDIT_SPREAD": credit,
    })
    combined.to_csv(raw_dir / "combined_prices.csv", index=False)

    long_df = pd.DataFrame({"Date": dates, "NASDAQ_COMP": px})
    long_df.to_csv(raw_dir / "NASDAQ_COMP_long.csv", index=False)
    return dates, px, vix, t10y2y, credit


@pytest.fixture
def small_constants(monkeypatch):
    """把窗口常量调小,配小样本(§6 测1/2/3 只需验证公式对齐,不需要真实的756/126等大窗口)。"""
    monkeypatch.setattr(ebm_duel, "MOM_SKIP", 2)
    monkeypatch.setattr(ebm_duel, "MOM_LOOKBACK", 5)
    monkeypatch.setattr(ebm_duel, "VOL_WINDOW", 4)
    monkeypatch.setattr(ebm_duel, "VIX_PCT_WINDOW", 6)
    monkeypatch.setattr(ebm_duel, "PIT_LAG", 1)
    monkeypatch.setattr(ebm_duel, "HORIZON", 5)


# ══════════════════════════════════════════════════════════════════
# 1. 特征自建正确:5 因子各按 §1 变换/回看手算对齐(合成序列)
# ══════════════════════════════════════════════════════════════════
def test_feature_transforms_match_spec(tmp_path, monkeypatch, small_constants):
    monkeypatch.setattr(ebm_duel, "RAW_DIR", tmp_path)
    dates, px, vix, t10y2y, credit = _write_synthetic_raw(tmp_path, n=80)

    feat = ebm_duel.build_ebm_features()
    assert list(feat.columns) == ebm_duel.FEATURE_COLS + ["fwd_up_20d"]

    # 独立按 §1 公式重算(不复用 build_ebm_features 内部代码路径)，逐行比对交集
    px_s = pd.Series(px, index=dates)
    vix_s = pd.Series(vix, index=dates)
    t10y2y_s = pd.Series(t10y2y, index=dates)
    credit_s = pd.Series(credit, index=dates)

    exp_mom = px_s.shift(2) / px_s.shift(2 + 5) - 1                       # px[t-21]/px[t-147]-1 口径(小窗版)
    exp_vol = px_s.pct_change().rolling(4).std() * np.sqrt(252)
    exp_vix_pct = vix_s.rolling(6, min_periods=6).apply(lambda x: (x <= x[-1]).mean(), raw=True)
    exp_t10y2y = t10y2y_s.shift(1)
    exp_credit = credit_s.shift(1)

    common = feat.index
    np.testing.assert_allclose(feat.loc[common, "mom_6_1"], exp_mom.loc[common], rtol=1e-9)
    np.testing.assert_allclose(feat.loc[common, "vol_63"], exp_vol.loc[common], rtol=1e-9)
    np.testing.assert_allclose(feat.loc[common, "vix_pct_756"], exp_vix_pct.loc[common], rtol=1e-9)
    np.testing.assert_allclose(feat.loc[common, "t10y2y_lag1"], exp_t10y2y.loc[common], rtol=1e-9)
    np.testing.assert_allclose(feat.loc[common, "credit_spread_lag1"], exp_credit.loc[common], rtol=1e-9)

    # VIX 分位必须落在 [0,1](百分位定义)
    assert feat["vix_pct_756"].between(0, 1).all()
    # 公共窗:没有任何 NaN 残留(dropna 已整行剔除,不是 NaN-bin)
    assert not feat.isna().any().any()


def test_target_is_forward_20d_up_direction(tmp_path, monkeypatch, small_constants):
    """目标 fwd_up_20d 必须是"未来"HORIZON日涨跌,不是过去——用单调上涨的合成价格验证全为1。"""
    monkeypatch.setattr(ebm_duel, "RAW_DIR", tmp_path)
    dates = pd.bdate_range("2000-01-03", periods=60)
    px = np.linspace(100, 200, 60)          # 单调上涨 → 未来20日必然更高 → fwd_up_20d 全为1
    pd.DataFrame({"Date": dates, "VIX": 20.0, "T10Y2Y": 0.5, "CREDIT_SPREAD": 2.0}).to_csv(
        tmp_path / "combined_prices.csv", index=False)
    pd.DataFrame({"Date": dates, "NASDAQ_COMP": px}).to_csv(tmp_path / "NASDAQ_COMP_long.csv", index=False)

    feat = ebm_duel.build_ebm_features()
    assert (feat["fwd_up_20d"] == 1.0).all()
    assert len(feat) > 0


# ══════════════════════════════════════════════════════════════════
# 2. 无前瞻:purge + embargo 生效,train 尾部不与 test 的前向窗重叠(§3 S4)
# ══════════════════════════════════════════════════════════════════
def test_purge_embargo_removes_boundary_rows():
    # 需跨多年、边界落在内部(否则 index<{year}-01-01 会空掉 train):1000 交易日≈2010–2013
    dates = pd.bdate_range("2010-01-01", periods=1000)
    feat = pd.DataFrame({"mom_6_1": np.arange(1000, dtype=float),
                         "fwd_up_20d": np.zeros(1000)}, index=dates)
    train_end_year, test_end_year = 2012, 2013   # train=2010–2011、test=2012(内部边界)

    train_df, test_df = ebm_duel.purge_embargo_split(feat, train_end_year, test_end_year,
                                                       purge=20, embargo=5)
    train_end_ts = pd.Timestamp(f"{train_end_year}-01-01")
    # test 完整保留(purge/embargo 只动 train,不动 test)
    expected_test = feat[(feat.index >= train_end_ts) &
                         (feat.index < pd.Timestamp(f"{test_end_year}-01-01"))]
    assert len(test_df) == len(expected_test)
    assert len(train_df) > 0                       # 内部边界:train 非空

    # train 最后一行与 test 第一行之间,在原始有序序列里至少间隔 purge+embargo=25 行
    full_positions = {d: i for i, d in enumerate(feat.index)}
    last_train_pos = full_positions[train_df.index[-1]]
    first_test_pos = full_positions[test_df.index[0]]
    assert first_test_pos - last_train_pos - 1 >= 25


def test_purge_embargo_empty_train_when_too_few_rows():
    """train 行数 <= purge+embargo → 整段清空(而非负索引裁出乱七八糟的东西)。"""
    dates = pd.bdate_range("2020-01-01", periods=15)
    feat = pd.DataFrame({"x": np.arange(15, dtype=float), "fwd_up_20d": np.zeros(15)}, index=dates)
    train_df, test_df = ebm_duel.purge_embargo_split(feat, dates[10].year, dates[10].year + 1,
                                                       purge=20, embargo=5)
    assert len(train_df) == 0


# ══════════════════════════════════════════════════════════════════
# 3. PIT:T10Y2Y/CREDIT_SPREAD 只取滞后值,不取未来发布值(§1.4/§1.5)
#    (CREDIT_SPREAD 实测为日频·非月频,见 ebm_duel.py 常量区注释 —— 测的是实际实现的日频滞后路径)
# ══════════════════════════════════════════════════════════════════
def test_pit_lag_never_uses_future_value(tmp_path, monkeypatch, small_constants):
    monkeypatch.setattr(ebm_duel, "RAW_DIR", tmp_path)
    dates = pd.bdate_range("2000-01-03", periods=60)
    px = 100 * np.exp(np.cumsum(np.full(60, 0.0005)))
    # T10Y2Y/CREDIT_SPREAD 编码成"日序号"——若特征取到当日或未来值，立刻能从数值差异测出来
    day_index = np.arange(60, dtype=float)
    pd.DataFrame({"Date": dates, "VIX": 20.0, "T10Y2Y": day_index, "CREDIT_SPREAD": day_index}).to_csv(
        tmp_path / "combined_prices.csv", index=False)
    pd.DataFrame({"Date": dates, "NASDAQ_COMP": px}).to_csv(tmp_path / "NASDAQ_COMP_long.csv", index=False)

    feat = ebm_duel.build_ebm_features()
    day_pos = {d: i for i, d in enumerate(dates)}
    for ts, row in feat.iterrows():
        i = day_pos[ts]
        assert row["t10y2y_lag1"] == i - 1          # 恰好滞后1日,不是当日(i)也不是未来(>i)
        assert row["credit_spread_lag1"] == i - 1
        assert row["t10y2y_lag1"] < i
        assert row["credit_spread_lag1"] < i


# ══════════════════════════════════════════════════════════════════
# 4. interactions=0 纯可加(需要 interpret)
# ══════════════════════════════════════════════════════════════════
def test_ebm_interactions_zero_purely_additive():
    pytest.importorskip("interpret")
    from interpret.glassbox import ExplainableBoostingClassifier

    rng = np.random.default_rng(11)
    X = rng.normal(size=(250, 5))
    y = (X[:, 0] + 0.3 * X[:, 1] + rng.normal(scale=0.5, size=250) > 0).astype(int)

    probs = ebm_duel.fit_ebm(ExplainableBoostingClassifier, X, y, X)
    assert len(probs) == len(X)
    assert np.all((probs >= 0) & (probs <= 1))

    ebm = ExplainableBoostingClassifier(interactions=0, random_state=42, n_jobs=1)
    ebm.fit(X, y)
    assert all(len(t) == 1 for t in ebm.term_features_)   # 只有单因子项,没有任何交叉项(pair)


# ══════════════════════════════════════════════════════════════════
# 5. 门逻辑:合成"不过基线"→not-promote(不写产物);合成"稳赢"→promote
# ══════════════════════════════════════════════════════════════════
def test_gate_not_promote_when_ebm_has_no_edge():
    boot20 = {"auc_ci95": [-0.03, 0.02], "auc_diff_obs": -0.005}
    boot40 = {"auc_ci95": [-0.04, 0.03], "auc_diff_obs": -0.004}
    gate = ebm_duel.promotion_gate(boot20, boot40, brier_ebm=0.24, brier_lr=0.23)
    assert gate["verdict"] == "not_promote"


def test_gate_not_promote_when_ebm_significantly_worse():
    boot20 = {"auc_ci95": [-0.08, -0.02], "auc_diff_obs": -0.05}
    boot40 = {"auc_ci95": [-0.09, -0.01], "auc_diff_obs": -0.05}
    gate = ebm_duel.promotion_gate(boot20, boot40, brier_ebm=0.26, brier_lr=0.23)
    assert gate["verdict"] == "not_promote"


def test_gate_promote_when_ebm_robustly_wins():
    boot20 = {"auc_ci95": [0.02, 0.09], "auc_diff_obs": 0.05}
    boot40 = {"auc_ci95": [0.01, 0.10], "auc_diff_obs": 0.05}
    gate = ebm_duel.promotion_gate(boot20, boot40, brier_ebm=0.20, brier_lr=0.23)
    assert gate["verdict"] == "promote"


def test_gate_borderline_stop_on_mixed_or_marginal_signal():
    """§4 停机点:CI贴0/跨block方向不稳 → 不自我说服上站,判 borderline_stop 交人判断。"""
    boot20 = {"auc_ci95": [0.001, 0.05], "auc_diff_obs": 0.02}    # block20 显著为正
    boot40 = {"auc_ci95": [-0.02, 0.04], "auc_diff_obs": 0.01}    # block40 却含0——跨block不稳
    gate = ebm_duel.promotion_gate(boot20, boot40, brier_ebm=0.21, brier_lr=0.23)
    assert gate["verdict"] == "borderline_stop"


def test_gate_promote_requires_brier_not_worse():
    """ΔAUC CI 双 block 都显著为正,但 Brier 更差 → 不满足"且Brier不更差",不能干净promote。"""
    boot20 = {"auc_ci95": [0.02, 0.09], "auc_diff_obs": 0.05}
    boot40 = {"auc_ci95": [0.01, 0.10], "auc_diff_obs": 0.05}
    gate = ebm_duel.promotion_gate(boot20, boot40, brier_ebm=0.30, brier_lr=0.23)   # EBM Brier 更差
    assert gate["verdict"] != "promote"


# ══════════════════════════════════════════════════════════════════
# 6. 同信息公平性:EBM 与 LR 的源特征/行逐列相同(标准化是LR内部的唯一单调变换)
# ══════════════════════════════════════════════════════════════════
def test_same_info_source_matrix_untouched_by_either_fit():
    pytest.importorskip("interpret")
    from interpret.glassbox import ExplainableBoostingClassifier

    rng = np.random.default_rng(21)
    X_train = rng.normal(size=(150, 5))
    X_test = rng.normal(size=(50, 5))
    y_train = rng.integers(0, 2, 150)
    X_train_copy, X_test_copy = X_train.copy(), X_test.copy()

    ebm_duel.fit_same_info_lr(X_train, y_train, X_test)
    ebm_duel.fit_ebm(ExplainableBoostingClassifier, X_train, y_train, X_test)

    # 两个 fit 函数都不应就地改写调用方传入的源矩阵——EBM 和 LR 吃的是同一份未被污染的连续矩阵
    np.testing.assert_array_equal(X_train, X_train_copy)
    np.testing.assert_array_equal(X_test, X_test_copy)


def test_scaler_fit_on_train_fold_only(monkeypatch):
    """②b 新增红线:StandardScaler 只在训练折 fit,不含 test(全样本fit=前瞻=bug)。"""
    calls = {}
    from sklearn.preprocessing import StandardScaler as RealScaler

    class RecordingScaler(RealScaler):
        def fit(self, X, y=None):
            calls["n_rows_fit"] = np.asarray(X).shape[0]
            calls["mean_fit_on"] = np.asarray(X).mean(axis=0).copy()
            return super().fit(X, y)

    monkeypatch.setattr(ebm_duel, "StandardScaler", RecordingScaler)

    rng = np.random.default_rng(22)
    X_train = rng.normal(loc=0.0, scale=1.0, size=(120, 5))
    X_test = rng.normal(loc=10.0, scale=1.0, size=(40, 5))   # 分布刻意与train不同,误全样本fit会被测出
    y_train = rng.integers(0, 2, 120)

    ebm_duel.fit_same_info_lr(X_train, y_train, X_test)

    assert calls["n_rows_fit"] == 120
    np.testing.assert_allclose(calls["mean_fit_on"], X_train.mean(axis=0))


# ══════════════════════════════════════════════════════════════════
# 7. 新写的成对块自助 ΔAUC/ΔBrier CI 计算正确(合成两组已知差·非 block_bootstrap_diff)
# ══════════════════════════════════════════════════════════════════
def test_paired_block_bootstrap_known_difference():
    rng = np.random.default_rng(31)
    n = 1500
    y = rng.integers(0, 2, n).astype(float)
    p_a = np.clip(0.15 + 0.7 * y + rng.normal(0, 0.08, n), 0.001, 0.999)   # EBM:强区分度
    p_b = np.clip(0.45 + 0.1 * y + rng.normal(0, 0.15, n), 0.001, 0.999)   # LR:弱区分度

    res = ebm_duel.paired_block_bootstrap(y, p_a, p_b, block=20, B=500, seed=1)

    assert res["auc_diff_obs"] > 0
    assert res["auc_ci95"][0] > 0                 # CI 不含0,方向正确(a显著占优)
    assert res["brier_diff_obs"] < 0               # a 的 Brier 更低(更好)
    assert res["brier_ci95"][1] < 0
    # schema 是新函数的(ΔAUC+ΔBrier 两条CI),不是 block_bootstrap_diff 的("diff"/"ci95"/"p_boot" 单条)
    assert set(["auc_ci95", "brier_ci95", "auc_diff_obs", "brier_diff_obs"]).issubset(res.keys())
    assert "p_boot" not in res


def test_paired_block_bootstrap_no_difference_ci_includes_zero():
    rng = np.random.default_rng(32)
    n = 1200
    y = rng.integers(0, 2, n).astype(float)
    p_a = np.clip(0.3 + 0.4 * y + rng.normal(0, 0.15, n), 0.001, 0.999)
    p_b = p_a.copy()                                # 完全相同的模型 → Δ应稳稳落在0附近
    res = ebm_duel.paired_block_bootstrap(y, p_a, p_b, block=20, B=300, seed=2)
    assert res["auc_diff_obs"] == pytest.approx(0.0, abs=1e-9)
    assert res["auc_ci95"][0] <= 0 <= res["auc_ci95"][1]


def test_paired_block_bootstrap_not_block_bootstrap_diff_function():
    """②b 的 blocker 修正:确认门用的是新函数,不是 block_bootstrap_diff(那个函数签名/语义都不同——
    只吃一个布尔选择掩码+结局,喂不了两条概率向量)。"""
    import inspect
    sig = inspect.signature(ebm_duel.paired_block_bootstrap)
    assert "p_a" in sig.parameters and "p_b" in sig.parameters
    assert ebm_duel.paired_block_bootstrap is not getattr(
        __import__("walk_forward"), "block_bootstrap_diff", None)


# ══════════════════════════════════════════════════════════════════
# 8. 缺 interpret → fail-soft 跳过、exit 0、不写产物(B4 硬红线)
# ══════════════════════════════════════════════════════════════════
def test_import_ebm_cls_returns_none_when_interpret_missing(monkeypatch):
    # 父 interpret 置 None 还不够:interpret 已装+glassbox 已缓存时,`from interpret.glassbox import`
    # 会走缓存成功。须把子模块也 null 掉,才真复现"缺 interpret"→ImportError。
    monkeypatch.setitem(sys.modules, "interpret", None)
    monkeypatch.setitem(sys.modules, "interpret.glassbox", None)
    assert ebm_duel._import_ebm_cls() is None


def test_run_fail_soft_skips_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "interpret", None)
    monkeypatch.setitem(sys.modules, "interpret.glassbox", None)
    monkeypatch.setattr(ebm_duel, "PROC_DIR", tmp_path)
    out = ebm_duel.run(write=True)
    assert out is None
    assert list(tmp_path.iterdir()) == []   # 绝不写任何产物


def test_script_never_calls_pip_install():
    """静态守门:脚本源码里不许出现任何真·pip install 调用(B4 硬红线,防脆步复发)。
    先剥掉三引号 docstring 与 # 注释再查——否则文档里写"绝不 pip install"会误报(②b/④ 修)。"""
    src = (Path(__file__).resolve().parent.parent / "scripts" / "ebm_duel.py").read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", src)   # 去 docstring/三引号文本
    code = re.sub(r'#.*', "", code)                                   # 去行注释
    assert "pip install" not in code
    assert "pip.main" not in code
    assert "subprocess" not in code
    assert "os.system" not in code


# ══════════════════════════════════════════════════════════════════
# 9. build_feature_df / cpcv / factor_pruning 输出逐字节不变(证 ebm_duel 未污染·S5)
# ══════════════════════════════════════════════════════════════════
def test_no_pollution_of_shared_modules():
    import cpcv
    import factor_pruning
    import walk_forward

    # ebm_duel 已在本测试文件顶部 import 过——若它曾 monkeypatch 别的模块属性,这里就会露馅
    R = np.zeros((cpcv.S_SLICES, 2))
    R[: cpcv.S_SLICES // 2, 0], R[cpcv.S_SLICES // 2:, 0] = 1.0, -1.0
    R[: cpcv.S_SLICES // 2, 1], R[cpcv.S_SLICES // 2:, 1] = -1.0, 1.0
    res1 = cpcv.pbo(R)
    res2 = cpcv.pbo(R)
    assert res1 == res2                      # 确定性不受 ebm_duel 已导入影响
    assert res1["pbo"] > 0.9                  # 与 test_cpcv.py 已知结果一致(交叉验证未被污染)

    assert walk_forward.HORIZON == 20         # 常量未被 ebm_duel 悄悄改写
    assert factor_pruning.HORIZON == 20
    # ebm_duel 是独立命名空间:不共享/不覆盖 walk_forward 的二值特征列表
    assert not set(ebm_duel.FEATURE_COLS) & {c for c, _ in walk_forward.BINARY_FEATURES}


# ══════════════════════════════════════════════════════════════════
# 10. honesty 声明进 json(机器守门)
# ══════════════════════════════════════════════════════════════════
def test_honesty_field_present_and_content():
    h = ebm_duel.build_honesty_field("promote")
    assert h["verdict"] == "promote"
    assert "SPEC_EBM" in h["section"]
    for phrase in ["同信息", "ΔAUC", "不含 0", "Brier 不更差", "绝不", "append-only"]:
        assert phrase in h["text"], f"honesty text 缺少关键短语: {phrase}"


def test_requirements_ebm_pins_interpret_version():
    path = Path(__file__).resolve().parent.parent / "requirements-ebm.txt"
    text = path.read_text(encoding="utf-8")
    assert "interpret==" in text
    assert "requirements-core" in text        # 引用核心依赖,不重复罗列


# ══════════════════════════════════════════════════════════════════
# 11. 固定种子/版本 → 两次拟合位级一致(S1,需要 interpret)
# ══════════════════════════════════════════════════════════════════
def test_reproducible_bit_identical_refit():
    pytest.importorskip("interpret")
    from interpret.glassbox import ExplainableBoostingClassifier

    rng = np.random.default_rng(41)
    X = rng.normal(size=(200, 5))
    y = (X[:, 0] > 0).astype(int)

    p1 = ebm_duel.fit_ebm(ExplainableBoostingClassifier, X, y, X)
    p2 = ebm_duel.fit_ebm(ExplainableBoostingClassifier, X, y, X)
    assert np.array_equal(p1, p2)     # random_state=42 + n_jobs=1(S1)→ 位级可复现
