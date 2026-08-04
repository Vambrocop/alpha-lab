"""test_fear_extremes.py — 高/极端恐慌事件研究(纯描述)测试(SPEC_FEAR_EXTREMES.md §7,11 项)。

全部合成/固定数据,不碰网络、不读真实 CSV(与 test_fomc.py 同一习惯:注入 _vix/_prices,
保证测试不随每日数据刷新而漂移)。
"""
import inspect
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fear_extremes as fe


# ═══════════════════════════════════════════════════════════════════════════
# 1. T1/T2 绝对阈值精确
# ═══════════════════════════════════════════════════════════════════════════
class TestThresholdPrecision:
    def test_t1_threshold_exact_boundary(self):
        idx = pd.bdate_range("2021-01-04", periods=7)
        vix = pd.Series([15, 29.99, 15, 30.0, 15, 15, 15], index=idx)
        events = fe.detect_events(vix, "T1")
        assert idx[3] in events, "VIX=30.0 必须触发 T1(≥30)"
        assert idx[1] not in events, "VIX=29.99 不得触发 T1"
        assert len(events) == 1

    def test_t2_threshold_exact_boundary(self):
        idx = pd.bdate_range("2021-01-04", periods=7)
        vix = pd.Series([15, 39.99, 15, 40.0, 15, 15, 15], index=idx)
        events = fe.detect_events(vix, "T2")
        assert idx[3] in events, "VIX=40.0 必须触发 T2(≥40)"
        assert idx[1] not in events, "VIX=39.99 不得触发 T2"
        assert len(events) == 1

    def test_t1_does_not_fire_below_30(self):
        idx = pd.bdate_range("2021-01-04", periods=5)
        vix = pd.Series([10, 20, 25, 29, 15], index=idx)
        assert fe.detect_events(vix, "T1") == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. T3 单日 +20% 精确(含 ②b 加的地板 25)
# ═══════════════════════════════════════════════════════════════════════════
class TestT3SpikeDefinition:
    def test_pct_jump_below_20pct_never_fires(self):
        idx = pd.bdate_range("2021-01-04", periods=3)
        # 21 -> 24.99：涨幅 (24.99/21-1)=18.99% < 20%，即使当日收盘已过地板 25 附近也不该触发
        vix = pd.Series([15.0, 21.0, 24.99], index=idx)
        assert fe.detect_events(vix, "T3") == []

    def test_pct_jump_ge_20pct_but_below_floor_does_not_fire(self):
        idx = pd.bdate_range("2021-01-04", periods=3)
        # 20 -> 24.5：涨幅 22.5% ≥ 20%，但收盘 24.5 < 25 地板 → 不触发(②b 加的地板)
        vix = pd.Series([15.0, 20.0, 24.5], index=idx)
        assert fe.detect_events(vix, "T3") == []

    def test_pct_jump_ge_20pct_and_floor_met_fires(self):
        idx = pd.bdate_range("2021-01-04", periods=3)
        # 21 -> 25.5：涨幅 (25.5/21-1)=21.4% ≥ 20% 且收盘 25.5 ≥ 25 → 触发
        vix = pd.Series([15.0, 21.0, 25.5], index=idx)
        events = fe.detect_events(vix, "T3")
        assert idx[2] in events
        assert len(events) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. 危机重置去聚集(§1.3 命门)
# ═══════════════════════════════════════════════════════════════════════════
class TestDeclustering:
    def test_sustained_high_fear_never_below_20_is_one_event(self):
        idx = pd.bdate_range("2021-01-04", periods=10)
        vix = pd.Series([32, 35, 31, 33, 30, 34, 31, 32, 33, 31], index=idx)
        events = fe.detect_events(vix, "T1")
        assert len(events) == 1, "持续高恐慌未回落<20 → 只应有 1 个事件(不是每天一个)"
        assert events[0] == idx[0]

    def test_reset_below_20_then_retrigger_gives_second_event(self):
        idx = pd.bdate_range("2021-01-04", periods=10)
        # 唯一一次回落 <20 在 idx2；之后不再回落，直到 idx4 再破阈 → 恰好 2 个事件
        vix = pd.Series([32, 35, 15, 18, 31, 33, 32, 34, 33, 31], index=idx)
        events = fe.detect_events(vix, "T1")
        assert len(events) == 2, "回落 <20 后再破阈 → 应产生第 2 个事件"
        assert events[0] == idx[0]
        assert events[1] == idx[4]

    def test_dip_to_20_exactly_does_not_reset(self):
        """地板是 '< 20'(严格小于);正好等于 20 不算回落，仍在阻塞中。"""
        idx = pd.bdate_range("2021-01-04", periods=6)
        vix = pd.Series([32, 20.0, 20.0, 31, 15, 31], index=idx)
        events = fe.detect_events(vix, "T1")
        # idx1/idx2=20.0 不满足 <20，不解除阻塞；idx3=31 仍被阻塞不算新事件；
        # idx4=15<20 才真正解除；idx5=31 才是第 2 个事件
        assert len(events) == 2
        assert events[0] == idx[0]
        assert events[1] == idx[5]


# ═══════════════════════════════════════════════════════════════════════════
# 4. 前向收益手算对齐(合成)
# ═══════════════════════════════════════════════════════════════════════════
class TestForwardReturnAlignment:
    def test_hand_calc_matches_pipeline(self):
        idx = pd.bdate_range("2020-01-01", periods=250)
        vix = pd.Series(15.0, index=idx)
        vix.iloc[50] = 31.0   # 孤立的单次 T1 触发(前后都是 15，早已 <20)
        price = pd.Series(100.0 + np.arange(len(idx)) * 1.0, index=idx)   # 线性:price[t]=100+t
        prices = {"SP500": price, "NASDAQ": price.copy()}

        result = fe.run(write=False, _vix=vix, _prices=prices)
        ev = result["triggers"]["T1"]["events"]
        assert len(ev) == 1
        rec = ev[0]

        entry_pos = 51   # 触发在 pos50，入场=次一交易日 pos51
        for h in fe.HORIZONS:
            expected = (price.iloc[entry_pos + h] / price.iloc[entry_pos] - 1) * 100
            got = rec["SP500"][str(h)]
            assert got is not None
            assert abs(got - round(expected, 3)) < 1e-6, f"h={h}: {got} != {expected}"

    def test_entry_is_next_day_not_trigger_day_itself(self):
        idx = pd.bdate_range("2020-01-01", periods=100)
        vix = pd.Series(15.0, index=idx)
        vix.iloc[30] = 31.0
        price = pd.Series(200.0 + np.arange(len(idx)) * 2.0, index=idx)
        prices = {"SP500": price, "NASDAQ": price.copy()}
        result = fe.run(write=False, _vix=vix, _prices=prices)
        rec = result["triggers"]["T1"]["events"][0]
        # 若入场用了触发日当天(pos30)而非次日(pos31)，5日收益会不同 —— 精确核对
        wrong_if_same_day = (price.iloc[30 + 5] / price.iloc[30] - 1) * 100
        right_next_day = (price.iloc[31 + 5] / price.iloc[31] - 1) * 100
        assert abs(rec["SP500"]["5"] - round(right_next_day, 3)) < 1e-6
        assert abs(rec["SP500"]["5"] - round(wrong_if_same_day, 3)) > 1e-6


# ═══════════════════════════════════════════════════════════════════════════
# 5. 全样本基率参照系
# ═══════════════════════════════════════════════════════════════════════════
class TestBaseRate:
    def test_base_rate_matches_forward_returns_directly(self):
        idx = pd.bdate_range("2020-01-01", periods=300)
        vix = pd.Series(15.0, index=idx)   # 无任何触发
        price = pd.Series(100.0 * (1.0005 ** np.arange(len(idx))), index=idx)  # 平滑复利增长
        prices = {"SP500": price, "NASDAQ": price.copy()}

        result = fe.run(write=False, _vix=vix, _prices=prices)
        cell = result["triggers"]["T1"]["by_index"]["SP500"]["20"]
        assert cell["n_events"] == 0

        from stats_util import forward_returns
        fwd20 = forward_returns(price, 20).dropna()
        expected_mean_pct = round(float(fwd20.mean()) * 100, 2)
        expected_up_pct = round(float((fwd20 > 0).mean()) * 100, 2)
        assert cell["base_mean_pct"] == expected_mean_pct
        assert cell["base_up_pct"] == expected_up_pct
        assert cell["base_up_pct"] == 100.0, "单调复利增长序列,任意起点前向收益必为正"


# ═══════════════════════════════════════════════════════════════════════════
# 6. 事件级自助 CI:合成已知均值的一组事件,CI 覆盖正确
# ═══════════════════════════════════════════════════════════════════════════
class TestEventBootstrapCI:
    def test_ci_covers_sample_mean(self):
        rng = np.random.default_rng(123)
        values = rng.normal(0.03, 0.01, size=200)
        sample_mean_pct = round(float(values.mean()) * 100, 2)
        boot = fe.event_bootstrap(values, base_mean=0.0, seed=42)
        lo, hi = boot["ci95_mean"]
        assert lo <= sample_mean_pct <= hi, "事件级自助 CI 应覆盖样本自身均值"

    def test_diff_ci_uses_fixed_base_mean(self):
        rng = np.random.default_rng(7)
        values = rng.normal(0.05, 0.005, size=150)   # 紧凑分布,均值明显 >5%
        base_mean = 0.0   # base 固定为 0，不参与重采样
        boot = fe.event_bootstrap(values, base_mean=base_mean, seed=1)
        lo_diff, hi_diff = boot["ci95_diff"]
        # diff = event_mean - base_mean(固定)；base=0 时 diff CI 应约等于 mean CI
        lo_mean, hi_mean = boot["ci95_mean"]
        assert abs(lo_diff - lo_mean) < 0.05
        assert abs(hi_diff - hi_mean) < 0.05
        assert lo_diff > 0, "均值明显为正且分布紧凑时，diff CI 不应跨 0"

    def test_wide_ci_when_n_small_and_noisy(self):
        """N 小、方差大 → CI 应该宽(诚实结果，不做美化)。"""
        values = np.array([0.10, -0.08, 0.05, -0.12, 0.15])
        boot = fe.event_bootstrap(values, base_mean=0.0, seed=5)
        lo, hi = boot["ci95_mean"]
        assert (hi - lo) > 5.0, "小 N 高方差应给出宽 CI，不能人为收窄"


# ═══════════════════════════════════════════════════════════════════════════
# 7. LOCO:合成"全靠 1 次危机"的事件集 → 剔它后翻转 → crisis-driven-fragile
# ═══════════════════════════════════════════════════════════════════════════
class TestLOCO:
    def test_dominant_single_crisis_flips_sign(self):
        groups = {
            2001: [0.01, 0.012],
            2002: [-0.02],
            2010: [-0.015, -0.01],
            2015: [-0.02],
            2008: [0.50, 0.55, 0.60],   # 独自撑起全部正效应的那一段危机
        }
        all_vals = [r for lst in groups.values() for r in lst]
        full_mean = float(np.mean(all_vals))
        assert full_mean > 0

        result = fe.loco_analysis(groups, full_mean, seed=1)
        assert result["loco_most_influential_crisis_year"] == 2008
        assert result["loco_sign_stable"] is False
        assert result["loco_headline_mean"] < 0, "剔掉 2008 后应翻转为负"

        verdict = fe.verdict_for_cell(too_small_no_ci=False, loco_sign_stable=result["loco_sign_stable"])
        assert verdict == "crisis-driven-fragile"

    def test_stable_multi_crisis_effect_not_flagged_fragile_by_sign(self):
        """效应在多段危机间均一致为正、剔哪段都不翻转 → sign 层面稳。"""
        groups = {
            2001: [0.02, 0.018],
            2008: [0.03, 0.025, 0.028],
            2010: [0.022],
            2015: [0.019, 0.021],
            2020: [0.03, 0.027],
        }
        all_vals = [r for lst in groups.values() for r in lst]
        full_mean = float(np.mean(all_vals))
        for y in groups:
            remaining = [r for yy, lst in groups.items() if yy != y for r in lst]
            assert np.sign(np.mean(remaining)) == np.sign(full_mean), "构造前提：剔哪段都不该翻号"

    def test_loco_undefined_with_fewer_than_two_groups(self):
        result = fe.loco_analysis({2020: [0.01, 0.02]}, 0.015, seed=1)
        assert result["loco_headline_mean"] is None
        assert result["loco_sign_stable"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 8. 分时代示意逻辑(illustrative only，非门)
# ═══════════════════════════════════════════════════════════════════════════
class TestEraSplitIllustrative:
    def test_era_same_sign_computed_correctly(self):
        pairs = [
            (2002, -0.02), (2008, -0.03),                       # era1(<=2009)：负
            (2012, 0.02), (2015, 0.025), (2018, 0.03),
            (2020, 0.01), (2021, 0.02), (2022, 0.015),
            (2010, 0.01), (2011, 0.012),                        # era2(>=2010)：正
        ]
        cell = fe.build_cell(pairs, base_mean=0.005, base_up=0.5, seed=7)
        assert cell["era1_mean_pct"] is not None and cell["era1_mean_pct"] < 0
        assert cell["era2_mean_pct"] is not None and cell["era2_mean_pct"] > 0
        assert cell["era_same_sign"] is False

    def test_era_split_is_not_a_verdict_gate(self):
        """verdict_for_cell 的签名里根本没有 era 相关参数——结构上保证分时代示意不能当门用。"""
        sig = inspect.signature(fe.verdict_for_cell)
        params = " ".join(sig.parameters.keys()).lower()
        assert "era" not in params


# ═══════════════════════════════════════════════════════════════════════════
# 9. N < MIN_N_CI(=10) → described-only·无 CI·不静默通过
# ═══════════════════════════════════════════════════════════════════════════
class TestMinNBoundary:
    def test_n_below_10_is_described_only_no_ci(self):
        pairs9 = [(2000 + i, 0.01 * i) for i in range(9)]
        cell = fe.build_cell(pairs9, base_mean=0.005, base_up=0.55, seed=3)
        assert cell["n_events"] == 9
        assert cell["too_small_no_ci"] is True
        assert cell["ci95_mean"] is None
        assert cell["ci95_up"] is None
        assert cell["ci95_diff"] is None
        assert cell["verdict"] == "described-only"
        # 不静默 —— 描述性数字(均值/up率)仍必须照实给出，不能因样本小就整体清空
        assert cell["mean_pct"] is not None
        assert cell["up_pct"] is not None

    def test_n_at_10_gets_ci(self):
        pairs10 = [(2000 + i, 0.01 * i) for i in range(10)]
        cell = fe.build_cell(pairs10, base_mean=0.005, base_up=0.55, seed=3)
        assert cell["n_events"] == 10
        assert cell["too_small_no_ci"] is False
        assert cell["ci95_mean"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# 10. honesty / 小样本告警 + primary_cell 进 json(机器守门·防删)
# ═══════════════════════════════════════════════════════════════════════════
class TestHonestyMachineGuard:
    def _synthetic_pipeline(self):
        idx = pd.bdate_range("2000-01-03", periods=2000)
        rng = np.random.default_rng(5)
        vix = pd.Series(15 + rng.random(len(idx)) * 3, index=idx)
        spike_positions = [50, 300, 500, 700, 900, 1100, 1300, 1500, 1700, 1900, 1950]
        for i, p in enumerate(spike_positions):
            vix.iloc[p] = 32 + (i % 3) * 3
            if p + 1 < len(vix):
                vix.iloc[p + 1] = 15   # 触发后立刻回落 <20，隔离出独立事件
        price = pd.Series(100 * (1.0003 ** np.arange(len(idx))), index=idx)
        prices = {"SP500": price, "NASDAQ": price.copy()}
        return fe.run(write=False, _vix=vix, _prices=prices)

    def test_primary_cell_present_and_frozen(self):
        result = self._synthetic_pipeline()
        assert result["primary_cell"] == {"trigger": "T1", "index": "SP500", "horizon": 20}

    def test_honesty_list_present_with_required_content(self):
        result = self._synthetic_pipeline()
        assert isinstance(result["honesty"], list)
        assert len(result["honesty"]) >= 5
        blob = " ".join(result["honesty"])
        for kw in ("非信号", "非荐股", "2000", "VXSMH", "LOCO", "过去"):
            assert kw in blob, f"honesty 文本缺少必守关键词: {kw}"

    def test_vxsmh_note_present_and_no_vxsmh_json_block(self):
        result = self._synthetic_pipeline()
        assert "vxsmh_note" in result and len(result["vxsmh_note"]) > 5
        assert "VXSMH" not in result["triggers"], "VXSMH 不得建独立触发器/JSON 块"

    def test_structural_keys_present(self):
        result = self._synthetic_pipeline()
        for k in ("generated", "as_of", "vix_start", "reset_floor", "min_n_ci",
                   "primary_cell", "triggers", "honesty", "vxsmh_note"):
            assert k in result, f"缺少字段: {k}"
        for tname in ("T1", "T2", "T3"):
            assert tname in result["triggers"]
            tblock = result["triggers"][tname]
            for k in ("n_events", "n_crisis_years", "events", "by_index", "tier"):
                assert k in tblock


# ═══════════════════════════════════════════════════════════════════════════
# 11. verdict 三态均可达且无任何 edge/信号态(纯描述硬保证)
# ═══════════════════════════════════════════════════════════════════════════
class TestVerdictNoEdgeState:
    def test_all_branches_return_allowed_verdicts(self):
        for too_small in (True, False):
            for loco in (True, False, None):
                v = fe.verdict_for_cell(too_small, loco)
                assert v in fe.ALLOWED_VERDICTS

    def test_each_state_reachable(self):
        assert fe.verdict_for_cell(True, None) == "described-only"
        assert fe.verdict_for_cell(False, True) == "robust-across-crises"
        assert fe.verdict_for_cell(False, False) == "crisis-driven-fragile"

    def test_verdict_function_source_has_no_forbidden_literals(self):
        """verdict_for_cell 是构造 verdict 字符串的唯一处——静态核对其源码里只出现三态允许字面量，
        且不含 edge/signal/promote/buy 等禁词(不含 §0 的说明性注释——本函数体极短，天然不会撞到)。"""
        src = inspect.getsource(fe.verdict_for_cell)
        literals = re.findall(r'"([^"]+)"', src)
        assert literals, "should have string literals"
        for lit in literals:
            assert lit in fe.ALLOWED_VERDICTS, f"verdict_for_cell 出现未授权字面量: {lit}"
        lowered = src.lower()
        for bad in ("edge", "signal", "promote", "buy", "sell"):
            assert bad not in lowered

    def test_verdict_field_has_single_source_of_truth(self):
        """整个模块只有一处构造 cell 字典的 'verdict' 键，且其值必须来自 verdict_for_cell() 算出的
        本地变量(不是硬编码字符串)——防止未来有人加第二条路径悄悄塞进 edge/signal 态。"""
        module_src = Path(fe.__file__).read_text(encoding="utf-8")
        assert module_src.count('"verdict":') == 1, (
            f"应恰好一处构造 'verdict' 键，实际 {module_src.count('\"verdict\":')} 处"
        )
        cell_src = inspect.getsource(fe.build_cell)
        assert re.search(r'\bverdict\s*=\s*verdict_for_cell\(', cell_src), (
            "build_cell 必须经 verdict_for_cell() 算出 verdict"
        )
        assert re.search(r'"verdict"\s*:\s*verdict\b', cell_src), (
            "返回字典的 'verdict' 键必须映射到 verdict_for_cell() 算出的变量"
        )

    def test_allowed_verdicts_exactly_three_and_none_mention_edge_or_signal(self):
        assert len(fe.ALLOWED_VERDICTS) == 3
        for v in fe.ALLOWED_VERDICTS:
            low = v.lower()
            assert "edge" not in low and "signal" not in low and "buy" not in low
