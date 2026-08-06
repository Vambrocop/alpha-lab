"""test_autodiscovery.py — v1.5 Phase 1b：两处性能向量化的「等价性」回归门（独立审 P1-a）。

把"提速不改结果"焊成自动门：若未来有人再优化、悄悄破坏了块索引或前向收益的等价性，
立刻失败。block_bootstrap 是 placebo/factor/walk_forward 的共享原语，错了会污染公开统计链。
纯数学等价、无数据依赖、快。

2026-07-04(#7 扩声明)：加仓位族(COT)/期权情绪族(P/C) 的 H-1 反退化(必须显式路由,不许静默落
p=1.0)、H-2 数组裁剪(裁到首个可判定状态)、H-3 防泄漏(改未来段不改过去 sel)、156份"报告"非天守门。
全部合成数据·monkeypatch 内部加载函数，不联网、不依赖真实 data/cot.csv|cboe_putcall.csv 的具体内容
（那两个文件的真实解析由 test_fetch_cot.py / test_fetch_putcall.py 单独覆盖）。
"""
import numpy as np
import pandas as pd
import pytest


def test_block_index_vectorization_equiv():
    # walk_forward.block_bootstrap_diff 的块索引向量化必须逐位 == 旧 Python 推导式
    rng = np.random.default_rng(0)
    for n, block in [(13958, 1), (6635, 5), (1000, 20), (500, 3), (300, 1)]:
        n_blocks = int(np.ceil(n / block))
        starts = rng.integers(0, n, n_blocks)
        old = np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]
        new = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        assert np.array_equal(old, new), (n, block)


def test_rebound_fwd_vectorization_equiv():
    # autodiscovery._rebound 的 cumsum 前向收益必须 == 旧 rolling().apply(np.prod)
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.012, 3000)
    for hold in (1, 5, 10):
        C = np.log1p(r).cumsum()
        fwd_vec = np.full(len(r), np.nan)
        m = len(r) - hold
        fwd_vec[:m] = np.expm1(C[hold:hold + m] - C[:m])
        s = pd.Series(r)
        fwd_old = ((1 + s).rolling(hold).apply(np.prod, raw=True).shift(-hold) - 1).values
        mask = ~np.isnan(fwd_old)
        assert np.allclose(fwd_vec[mask], fwd_old[mask], atol=1e-10), hold
        # 尾部 hold 个应为 NaN（无前向窗口）
        assert np.all(np.isnan(fwd_vec[m:]))


# ══════════════════════════════════════════════════════════════════════════
# 仓位族(COT)/期权情绪族(P/C) — #7 2026-07-04 扩声明：H-1反退化 / H-2数组裁剪 / H-3防泄漏 / 156周频守门
# ══════════════════════════════════════════════════════════════════════════
def _synthetic_reports(n=250, start="2000-01-04", seed=0):
    """合成 COT 报告级数据：n 份周频报告(report_date 每 7 天一份)，usable_from=report_date+6天。"""
    dates = pd.date_range(start, periods=n, freq="7D")
    usable = dates + pd.Timedelta(days=6)
    rng = np.random.default_rng(seed)
    values = rng.normal(0, 1, n)
    return pd.DataFrame({"report_date": dates, "usable_from": usable, "value": values})


def _synthetic_price(start="1998-01-01", end="2012-12-31", seed=1):
    idx = pd.date_range(start, end, freq="B")
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0003, 0.01, len(idx))
    px = 100 * np.cumprod(1 + rets)
    return pd.Series(px, index=idx)


# ── _rolling_pctrank：window 单位是"报告篇数"，绝非日历天(156周频守门的最底层单测)──
def test_rolling_pctrank_window_is_report_count():
    import autodiscovery as ad
    vals = np.arange(200, dtype=float)          # 严格递增，无并列 → 排名无歧义
    out = ad._rolling_pctrank(vals, window=156)
    assert np.all(np.isnan(out[:155]))          # 前 155 个暖机不足 → NaN
    assert not np.isnan(out[155])               # 第 156 个(index155)起可判
    assert out[155] == pytest.approx(100.0)     # 递增序列里，窗口内最后一个值必是窗口最大 → 100 分位


def test_positioning_window_is_156_reports_not_156_days(monkeypatch):
    """156 份"周频报告"滚动分位，绝非 156 个日历天——若误当成 156 天，暖机在两周内就结束。
    (fixture n=300：n=200 时暖机后仅 45 份可判报告→hi 状态 ~20 交易日 < 实现里正当的 30 天
    检验力守卫——那是守卫工作正常不是 bug，故造够数据而非放松守卫。)"""
    import autodiscovery as ad
    reports = _synthetic_reports(n=300)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())
    arr = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    assert arr is not None
    idx, sel, y = arr
    span_days = (idx.min() - reports["report_date"].iloc[0]).days
    assert span_days > 500          # 156 份周报≈3年(>500天)，远超"156天"误判的量级


# ── H-2:数组裁到该 series 首个"可判定"状态生效的交易日(暖机/无报告段绝不当 False)──
def test_positioning_truncates_before_first_usable_state(monkeypatch):
    import autodiscovery as ad
    reports = _synthetic_reports(n=250)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())
    arr = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    assert arr is not None
    idx, sel, y = arr
    first_valid_usable = pd.Timestamp(reports["usable_from"].iloc[ad._POS_WINDOW - 1])
    assert pd.Timestamp(idx.min()) >= first_valid_usable


# ── H-3:防泄漏守门——改动"未来"那份报告/未来那段 P/C 的值，绝不能改变过去日的 sel ──
def test_positioning_future_report_change_does_not_alter_past_sel(monkeypatch):
    import autodiscovery as ad
    n = 260
    rng = np.random.default_rng(3)
    base_vals = rng.normal(0, 1, n)

    def _reports_with_last(v_last):
        reports = _synthetic_reports(n=n)
        vals = base_vals.copy()
        vals[-1] = v_last
        reports = reports.assign(value=vals)
        return reports

    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())

    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: _reports_with_last(1000.0))
    arr_a = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: _reports_with_last(-1000.0))
    arr_b = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", 20)
    assert arr_a is not None and arr_b is not None
    idx_a, sel_a, _ = arr_a
    idx_b, sel_b, _ = arr_b

    last_usable = pd.Timestamp(_reports_with_last(1000.0)["usable_from"].iloc[-1])
    mask_a, mask_b = idx_a < last_usable, idx_b < last_usable
    assert list(idx_a[mask_a]) == list(idx_b[mask_b])            # 未来段改动前，日期集合必须完全一致
    assert np.array_equal(sel_a[mask_a], sel_b[mask_b])          # 且逐日 sel 必须完全一致(零泄漏)


def _optsent_base_with_spikes(seed, n=1600, spike_val=2.5):
    """P/C 合成基础序列：噪声 + **过去段**确定性尖峰(index 300..1500 每 25 天一个 ≈ 49 个 hi 极端日)。
    尖峰必须放在过去段——否则 hi 极端日几乎全靠"未来段"贡献,一改未来段整个候选就跌破 30 天检验力
    守卫返回 None(守卫按整段样本量拒绝、不改任何过去 sel,是正当行为非泄漏,但会让本测试测不到点时间)。"""
    idx_all = pd.date_range("2006-11-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    base = rng.normal(0.9, 0.15, n)
    base[300:1500:25] = spike_val               # 过去段尖峰(全部早于末尾 50 天)
    return idx_all, base


def test_optsent_future_change_does_not_alter_past_sel(monkeypatch):
    import autodiscovery as ad
    idx_all, base = _optsent_base_with_spikes(seed=4)

    def _putcall_with_tail(tail_val):
        vals = base.copy()
        vals[-50:] = tail_val                   # 两版都是合法 P/C 值(非 NaN/负数),只测点时间不测守卫
        return pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all)

    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price(start="2006-01-01", end="2015-12-31"))

    monkeypatch.setattr(ad, "_putcall_daily", lambda: _putcall_with_tail(2.0))   # 版本A:尾段偏高
    arr_a = ad._optsent_arrays("total_pc", "hi", 10)
    monkeypatch.setattr(ad, "_putcall_daily", lambda: _putcall_with_tail(0.9))   # 版本B:尾段中性
    arr_b = ad._optsent_arrays("total_pc", "hi", 10)
    assert arr_a is not None and arr_b is not None
    idx_a, sel_a, _ = arr_a
    idx_b, sel_b, _ = arr_b

    cutoff = idx_all[-50]
    mask_a, mask_b = idx_a < cutoff, idx_b < cutoff
    assert list(idx_a[mask_a]) == list(idx_b[mask_b])
    assert np.array_equal(sel_a[mask_a], sel_b[mask_b])


# ── H-1 反退化：compute_results 必须显式路由两新族到真统计，绝不静默落 fac.get(None)→p=1.0 ──
def test_compute_results_routes_positioning_not_silent_fallback(monkeypatch):
    import autodiscovery as ad
    reports = _synthetic_reports(n=260)
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: _synthetic_price())
    cand = {"candidate_id": "pos_test", "key": "test_key", "family": "positioning",
            "params": {"market": "sp500", "series": "legacy_noncomm_pct_oi", "extreme": "hi", "hold": 20}}
    results = ad.compute_results([cand])
    r = results[0]
    # 静默落 else 分支的话会是 {"p":1.0,"recent_p":None,"recent_powered":False}（无 windows/effect 字段）
    assert "windows" in r and "effect" in r
    assert r["effect"] == "仓位极端状态下未来持有期上涨率 vs 基率"
    assert r["p"] != 1.0


def test_compute_results_routes_optsent_not_silent_fallback(monkeypatch):
    """H-1:optsent 显式路由 + 真 p。fixture 造【真效应】：尖峰日(hi 极端)后 10 天注入正漂移
    → sel 日前向上涨率≈1 vs 基率≈0.5 → p 必然很小(而非指望噪声碰巧 p≠1.0)。"""
    import autodiscovery as ad
    idx_all, vals = _optsent_base_with_spikes(seed=5)
    df = pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all)

    # 价格与 P/C 同索引：默认小噪声收益；每个尖峰日后 10 天 +1%/天(真效应,非碰运气)
    rng = np.random.default_rng(6)
    rets = rng.normal(0.0, 0.004, len(idx_all))
    for i in range(300, 1500, 25):
        rets[i + 1: i + 11] += 0.01
    px = pd.Series(100 * np.cumprod(1 + rets), index=idx_all)

    monkeypatch.setattr(ad, "_putcall_daily", lambda: df)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    cand = {"candidate_id": "opt_test", "key": "test_key", "family": "options_sentiment",
            "params": {"series": "total_pc", "extreme": "hi", "hold": 10}}
    results = ad.compute_results([cand])
    r = results[0]
    assert "windows" in r and "effect" in r
    assert r["effect"] == "期权情绪极端状态下未来持有期上涨率 vs 基率"
    assert r["p"] != 1.0
    assert r["p"] < 0.10                    # 真效应必须被测出(路由+统计链端到端)


def test_compute_results_unrouted_family_raises():
    """H-1 反退化的防御端：未知 family 必须炸,不许静默落 p=1.0（防未来再漏接一族）。"""
    import autodiscovery as ad
    cand = {"candidate_id": "x", "key": "x", "family": "totally_unknown", "params": {}}
    with pytest.raises(ValueError):
        ad.compute_results([cand])


def test_arrays_exclude_days_without_realized_forward_window(monkeypatch):
    """审④阻断修回归锁(合成版·CI 恒跑):数组最后一天必须早于最后价格日至少 hold 个交易日——
    尾部"前向窗未实现"的日子绝不许以 y=0(捏造下跌)进数组(修正前正是这样,
    系统性压制'当前正处极端态'的活信号,翻转过 legacy_lo_h60_nasdaq100 公开头条)。
    价格序列刻意在最后报告后不足 hold 日就截止 → 不裁剪的话尾部必混入未实现窗。"""
    import autodiscovery as ad
    hold = 20
    # positioning:最后 usable_from≈2004-12-27,价格 2005-01-08 截止(仅 ~8 交易日 < hold)
    reports = _synthetic_reports(n=260)
    px_short = _synthetic_price(start="1998-01-01", end="2005-01-08")
    monkeypatch.setattr(ad, "_cot_reports", lambda market, series: reports)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px_short)
    arr = ad._positioning_arrays("sp500", "legacy_noncomm_pct_oi", "hi", hold)
    assert arr is not None
    idx, sel, y = arr
    pos = px_short.index.get_indexer([idx.max()])[0]
    assert pos + hold <= len(px_short.index) - 1, (
        f"positioning: idx.max()={idx.max().date()} 距最后价格日不足 {hold} 交易日——尾部未实现前向窗混入")
    assert not np.isnan(y).any()

    # optsent:P/C 与价格同索引同截止 → 最后 hold 天必须被裁掉
    idx_all, vals = _optsent_base_with_spikes(seed=7)
    df = pd.DataFrame({"total_pc": vals, "equity_pc": vals}, index=idx_all)
    rng = np.random.default_rng(8)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.008, len(idx_all))), index=idx_all)
    monkeypatch.setattr(ad, "_putcall_daily", lambda: df)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    arr = ad._optsent_arrays("total_pc", "hi", hold)
    assert arr is not None
    idx, sel, y = arr
    pos = px.index.get_indexer([idx.max()])[0]
    assert pos + hold <= len(px.index) - 1, (
        f"optsent: idx.max()={idx.max().date()} 距最后价格日不足 {hold} 交易日——尾部未实现前向窗混入")
    assert not np.isnan(y).any()


def test_regime_arrays_exclude_warmup_and_unrealized_tail(monkeypatch):
    """T1(2026-07-07):_regime_arrays 既有代码的同款双bug修回归锁(合成·CI恒跑)。
    ①暖机段(前199天,200日均线未定义)绝不当 sel=False 混进基率(H-2 纪律);
    ②尾部 hold 天(前向窗未实现)绝不以 (NaN>0)→False 捏造 y=0。
    修正前:idx 从第1个价格日排到最后价格日(n=全长);修正后精确 n=全长-199-hold。"""
    import autodiscovery as ad
    idx_all = pd.date_range("2000-01-03", "2009-12-31", freq="B")
    rng = np.random.default_rng(11)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0, 0.01, len(idx_all))), index=idx_all)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    hold = 20
    arr = ad._regime_arrays("golden_cross", "sp500", hold)
    assert arr is not None
    idx, sel, y = arr
    assert idx.min() >= px.index[199], "暖机段(均线未定义)混进了数组"
    pos = px.index.get_indexer([idx.max()])[0]
    assert pos + hold <= len(px.index) - 1, "尾部未实现前向窗混进了数组"
    assert not np.isnan(y).any()
    assert len(idx) == len(px.index) - 199 - hold   # 精确:恰好剔 199 暖机 + hold 尾窗


# ══════════════════════════════════════════════════════════════════════════
# 连跌族 streak(2026-07-10·SPEC_STREAK_FAMILY.md) — runlen 向量化正确性 / ==N 单触发 /
# break 单触发 / 互斥 / 尾窗裁剪 / H-1 路由 / trailing_extreme stage2 桩
# ══════════════════════════════════════════════════════════════════════════
def _naive_runlen(down):
    """朴素循环版游程长度(down=bool array)：逐位累计，遇 False 清零。作向量化版对照基线。"""
    out = np.zeros(len(down), dtype=int)
    run = 0
    for i, d in enumerate(down):
        run = run + 1 if d else 0
        out[i] = run
    return out


def _vectorized_runlen(down):
    down_i = pd.Series(down).astype(int)
    return down_i.groupby((down_i == 0).cumsum()).cumsum().values


def test_streak_runlen_vectorized_matches_naive_loop():
    rng = np.random.default_rng(42)
    for trial in range(20):
        down = rng.random(500) < 0.45          # 随机布尔序列，覆盖各种游程长度分布
        assert np.array_equal(_vectorized_runlen(down), _naive_runlen(down)), trial


def _synthetic_streak_price(seed=0, n=2000, start="2000-01-03"):
    """合成一条价格序列，收益带明显的连跌/连涨段，足量覆盖 N=3/4/5 各深度事件。"""
    idx = pd.date_range(start, periods=n, freq="B")
    rng = np.random.default_rng(seed)
    rets = np.zeros(n)
    i = 0
    while i < n:
        run = rng.integers(1, 8)                # 1~7 天的连续同向段
        sign = rng.choice([-1.0, 1.0])
        mag = rng.uniform(0.003, 0.02, size=min(run, n - i))
        rets[i:i + len(mag)] = sign * mag
        i += len(mag)
    px = pd.Series(100 * np.cumprod(1 + rets), index=idx)
    return px


def test_streak_down_fires_exactly_once_per_eligible_run(monkeypatch):
    """==N 事件日:一段 7 连跌只在深度 3/4/5 各触发一次(§1)，不是 >=N 状态连续触发。"""
    import autodiscovery as ad
    px = _synthetic_streak_price(seed=1)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    ret = px.pct_change()
    down = (ret < 0).values
    runlen = _vectorized_runlen(down)
    for n in (3, 4, 5):
        # 手算:某段若连跌恰好 >=n，则该段内 runlen==n 精确出现 1 次(游程递增到 n 后若更长会变 n+1...)
        expected = int((runlen == n).sum())
        arr = ad._streak_arrays("streak_down", n, 1, "sp500")
        if arr is None:
            continue
        idx, sel, y = arr
        # dropna 会剔除首日(ret NaN)与尾部(fwd 未实现)，但 sel==True 的那些行必须原样保留
        assert int(sel.sum()) <= expected
        assert int(sel.sum()) > 0


def test_streak_break_fires_once_after_decline_episode():
    """break: sel[t]=(ret[t]>0 且到 t-1 连跌>=N)——每段连跌只触发一次(首根阳线确认)。"""
    px = _synthetic_streak_price(seed=2)
    ret = px.pct_change()
    down = (ret < 0)
    runlen = pd.Series(_vectorized_runlen(down.values), index=px.index)
    for n in (3, 5):
        brk = (ret > 0) & (runlen.shift(1) >= n)
        # 每次"游程从 >=n 回落到 0"必然对应恰好一个 break 事件（up 日本身 down=False→runlen=0）
        drop_to_zero = (runlen.shift(1) >= n) & (runlen == 0)
        assert int(brk.sum()) <= int(drop_to_zero.sum())
        assert int(brk.sum()) > 0


def test_streak_down_and_break_mutually_exclusive_same_day(monkeypatch):
    """停机条件③:streak_down(==N)与 streak_break 绝不可能同日双触发——down 日要求 ret<0(严格)，
    break 日要求 ret>0(严格)，二者互斥;若真出现重叠，说明口径被破坏，测试必须能杀。"""
    import autodiscovery as ad
    px = _synthetic_streak_price(seed=3)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    down_sel = set()
    for n in (3, 4, 5):
        arr = ad._streak_arrays("streak_down", n, 1, "sp500")
        if arr is not None:
            idx, sel, _ = arr
            down_sel |= set(idx[sel])
    break_sel = set()
    for n in (3, 5):
        arr = ad._streak_arrays("streak_break", n, 1, "sp500")
        if arr is not None:
            idx, sel, _ = arr
            break_sel |= set(idx[sel])
    assert down_sel & break_sel == set()


def test_streak_down_counts_match_declared_registration(monkeypatch):
    """§1 命门:口径写死 down=ret<0(严格)。用真实价格数据核对触发计数 ≥ SPEC 预注册数字
    (纳指758/363/190·标普1423/646/307；见 candidate_space.py streak 族声明——那是【冻结的 OOS 锚】,不改)。
    用 ≥ 而非 ==:历史 streak 只增不减(新数据只在末尾追加新 streak、不动过去的),声明值是 floor;
    == 会随每次数据刷新漂移误红(2026-08 nasdaq/3 由 758→759 即此)。仍能抓口径漂移(公式坏了会跌破 floor/结构剧变)。
    真数据缺失(CI 干净检出无 data/raw/)则 skip。"""
    import autodiscovery as ad
    px_nq = ad._daily_price("nasdaq")
    px_sp = ad._daily_price("sp500")
    if px_nq is None or px_sp is None:
        pytest.skip("data/raw/ 价格缺失(CI 干净检出)")
    expect = {("nasdaq", 3): 758, ("nasdaq", 4): 363, ("nasdaq", 5): 190,
              ("sp500", 3): 1423, ("sp500", 4): 646, ("sp500", 5): 307}
    for (index, n), want in expect.items():
        px = ad._daily_price(index)
        ret = px.pct_change()
        down_i = (ret < 0).astype(int)
        runlen = down_i.groupby((down_i == 0).cumsum()).cumsum()
        assert int((runlen == n).sum()) >= want, f"{index} n={n}: 计数 < 声明 floor(口径漂移)"
    expect_brk = {("nasdaq", 3): 756, ("nasdaq", 5): 189, ("sp500", 3): 1402, ("sp500", 5): 304}
    for (index, n), want in expect_brk.items():
        px = ad._daily_price(index)
        ret = px.pct_change()
        down_i = (ret < 0).astype(int)
        runlen = down_i.groupby((down_i == 0).cumsum()).cumsum()
        brk = (ret > 0) & (runlen.shift(1) >= n)
        assert int(brk.sum()) >= want, f"{index} break n>={n}: 计数 < 声明 floor(口径漂移)"


def test_streak_arrays_exclude_unrealized_tail(monkeypatch):
    """T1 尾窗纪律:数组最后一天必须早于最后价格日至少 hold 个交易日——尾部"前向窗未实现"的日子
    绝不许以 y=0(捏造下跌)进数组(同 regime/positioning 侧同款修)。"""
    import autodiscovery as ad
    px = _synthetic_streak_price(seed=4, n=1500)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    hold = 20
    arr = ad._streak_arrays("streak_down", 3, hold, "sp500")
    assert arr is not None
    idx, sel, y = arr
    pos = px.index.get_indexer([idx.max()])[0]
    assert pos + hold <= len(px.index) - 1, "尾部未实现前向窗混进了数组"
    assert not np.isnan(y).any()


def test_streak_arrays_no_data_returns_none(monkeypatch):
    import autodiscovery as ad
    monkeypatch.setattr(ad, "_daily_price", lambda index: None)
    assert ad._streak_arrays("streak_down", 3, 1, "sp500") is None
    assert ad._streak_arrays("streak_break", 3, 1, "sp500") is None
    assert ad._streak_arrays("bogus_kind", 3, 1, "sp500") is None


def test_streak_arrays_invalid_kind_returns_none(monkeypatch):
    import autodiscovery as ad
    px = _synthetic_streak_price(seed=6)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    assert ad._streak_arrays("bogus_kind", 3, 1, "sp500") is None


# ── H-1 反退化:compute_results 必须显式路由 streak 到真统计 ──
def test_compute_results_routes_streak_not_silent_fallback(monkeypatch):
    import autodiscovery as ad
    px = _synthetic_streak_price(seed=5)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    for fam in ("streak_down", "streak_break"):
        cand = {"candidate_id": f"{fam}_test", "key": "test_key", "family": fam,
                "params": {"n": 3, "hold": 1, "index": "sp500"}}
        results = ad.compute_results([cand])
        r = results[0]
        assert "windows" in r and "effect" in r      # 静默落 else 分支不会有这两个字段
        assert r["p"] != 1.0                          # 真统计路径跑过(非静默 p=1.0 桩)


# ══════════════════════════════════════════════════════════════════════════
# 长跨度对称反转/延续族 trailing_extreme(2026-07-11·SPEC_STREAK_FAMILY.md §5·stage4 真统计) ——
# 命门1 PIT 反泄漏锁 / 状态族多日 sel / 命门2 block 放大生效 / 三端裁剪(尤其 2520 分位暖机边界) /
# H-1 路由反退化(真统计 + 数据不足仍 p=1.0 兜底) / 分母对账(§3 N3，见文件末尾既有测试)。
# ══════════════════════════════════════════════════════════════════════════

# ── ① 命门1:PIT 反泄漏锁——构造"全样本分位 vs expanding 分位在某点判定相反"的合成序列，
#   断言代码走 expanding(那点不被全样本式误判"触发") ──
def test_trailing_pit_quantile_no_lookahead_flip():
    import autodiscovery as ad
    warmup = 500          # 只为测试可控收敛速度，不改动生产 _TRAILING_WARMUP=2520
    rng = np.random.default_rng(7)
    n1, n2 = 600, 3000
    regime1 = rng.normal(0, 0.02, n1)     # 前段:中等波动(t0 所在区间，PIT 只能看到这段)
    regime2 = rng.normal(0, 0.001, n2)    # 后段:低波动(未来才出现，PIT 不可见；全样本会被这段拉窄)
    trailing_ret = pd.Series(np.concatenate([regime1, regime2]))
    t0 = 550                              # 暖机(500)已过、仍在前段(600)内
    trailing_ret.iloc[t0] = -0.005        # 相对前段(std=0.02)温和，不算极端

    expanding_p10 = ad._trailing_pit_quantile(trailing_ret, 0.10, warmup=warmup)
    full_p10 = np.percentile(trailing_ret.values, 10)     # 反面对照:被禁用的全样本口径

    # 测试前提自检:两口径在 t0 必须给出相反判定，否则这条构造没有测到命门
    triggered_expanding = bool(trailing_ret.iloc[t0] <= expanding_p10.iloc[t0])
    triggered_naive_full = bool(trailing_ret.iloc[t0] <= full_p10)
    assert triggered_naive_full is True, "构造前提:全样本分位(被未来低波动段拉窄)应误判 t0 触发"
    assert triggered_expanding is False, "构造前提:expanding 分位(只用 t0 及之前)不应判 t0 触发"
    assert triggered_expanding != triggered_naive_full     # 命门1:两口径在该点判定相反

    # 生产 helper 必须给出与 expanding 一致的结果(即不触发)，不是全样本的结果
    assert bool(trailing_ret.iloc[t0] <= expanding_p10.iloc[t0]) is False


def test_trailing_pit_quantile_never_uses_future_observations():
    """PIT helper 在任一点 t 的分位值必须与"截到 t 为止"手算 np.percentile 逐点一致——
    直接证伪"用了未来数据"（若用了未来数据，数值会漂移，逐点比对会不等）。"""
    import autodiscovery as ad
    rng = np.random.default_rng(11)
    vals = pd.Series(rng.normal(0, 0.015, 4000))
    warmup = 300
    p10 = ad._trailing_pit_quantile(vals, 0.10, warmup=warmup)
    for t in (299, 300, 301, 1000, 3999):
        manual = np.percentile(vals.values[: t + 1], 10)   # 只用 0..t(含 t)
        assert abs(p10.iloc[t] - manual) < 1e-9, f"t={t} 与手算 expanding 分位不符"
    assert p10.iloc[:warmup - 1].isna().all(), "暖机前必须 NaN(不可提前给出分位)"


# ── ② 状态族多日 sel 正确(连续尾部段，非单日事件) ──
def _synth_trailing_price(seed=1, n_days=2900, decline_start=2820, decline_len=50, decline_mag=-0.006):
    """合成一条价格序列:前段常规噪声，末段插入一段持续下跌(制造 trailing 低分位多日连续状态)。"""
    idx = pd.date_range("2000-01-03", periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.01, n_days)
    rets[decline_start:decline_start + decline_len] = decline_mag + rng.normal(0, 0.002, decline_len)
    return pd.Series(100 * np.cumprod(1 + rets), index=idx)


def _true_run_lengths(bool_arr):
    arr = np.asarray(bool_arr, dtype=bool)
    if arr.sum() == 0:
        return np.array([], dtype=int)
    change = np.diff(np.concatenate(([0], arr.astype(int), [0])))
    starts, ends = np.where(change == 1)[0], np.where(change == -1)[0]
    return ends - starts


def test_trailing_extreme_state_persists_multiple_consecutive_days(monkeypatch):
    """命门2:状态族——sel 落进尾部会连续多天为真，不是 streak 那种 ==N 单日事件。"""
    import autodiscovery as ad
    px = _synth_trailing_price()
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    arr = ad._trailing_extreme_arrays(63, 5, "sp500", "low")
    assert arr is not None
    idx, sel, y = arr
    assert int(sel.sum()) > 0
    runs = _true_run_lengths(sel)
    assert runs.max() >= 10, "构造的持续下跌段应产生 >=10 天连续 sel=True(状态而非单日事件)"


# ── ③ 命门2:block 放大生效——断言用的是 hold+TRAILING_BLOCK_EXTRA 非 hold；
#   附"人造长聚簇段使 block=hold 虚假存活、放大后被杀"的统计对照(seed=3 建造期实测锁定) ──
def test_trailing_extreme_passes_extended_block_to_bootstrap(monkeypatch):
    """直接窥探 block_bootstrap_diff 收到的 block 实参，必须是 hold+TRAILING_BLOCK_EXTRA。"""
    import autodiscovery as ad
    px = _synth_trailing_price()
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    seen_blocks = []
    orig = ad.block_bootstrap_diff

    def spy(sel, y, block=20, **kw):
        seen_blocks.append(block)
        return orig(sel, y, block=block, **kw)

    monkeypatch.setattr(ad, "block_bootstrap_diff", spy)
    hold = 5
    r = ad._trailing_extreme(63, hold, "low", "sp500", "cid")
    assert r is not None
    expect = hold + ad.TRAILING_BLOCK_EXTRA
    assert seen_blocks, "block_bootstrap_diff 未被调用"
    assert all(b == expect for b in seen_blocks), f"block 必须恒为 hold+EXTRA={expect}，实收 {seen_blocks}"
    assert expect != hold, "放大必须真实存在(EXTRA>0)，否则这条断言测不出命门2"


def test_trailing_extreme_block_formula_matches_discovery_constant():
    import autodiscovery as ad
    for hold in (21, 63, 126):
        assert ad._trailing_extreme_block(hold) == hold + ad.TRAILING_BLOCK_EXTRA
    assert ad.TRAILING_BLOCK_EXTRA == 77          # 实测值锁定(建造期 measure_block.py，见声明注释)


def test_trailing_extreme_block_extra_kills_false_survival_from_clustering():
    """对照(§5.3"可用"建议)：人造长聚簇段(episode 内 y 恒定=极端序列相关)造成的"看似有边际"其实是
    仅 K=8 个独立聚簇的小样本噪声。block=hold(远小于聚簇长度)低估方差→误判显著；
    block=hold+TRAILING_BLOCK_EXTRA(更贴近聚簇长度)正确放大方差→回到不显著。种子/参数为建造期
    实测锁定(seed=3 在此配置下稳定复现，非挑选到能通过的随机种子撞大运)。"""
    import autodiscovery as ad
    from walk_forward import block_bootstrap_diff
    hold = 21

    def build(seed, n_days=4000, n_episodes=8, length=140, base=0.50):
        rng = np.random.default_rng(seed)
        sel = np.zeros(n_days, dtype=bool)
        y = (rng.random(n_days) < base).astype(float)
        gap = n_days // n_episodes
        for k in range(n_episodes):
            start, end = k * gap + 10, k * gap + 10 + length
            if end > n_days:
                break
            sel[start:end] = True
            y[start:end] = rng.choice([0.0, 1.0])   # 段内恒定(极端序列相关，真实总体无差异)
        return sel, y

    sel, y = build(seed=3)
    bb_small = block_bootstrap_diff(sel, y, block=hold, seed=42)
    bb_big = block_bootstrap_diff(sel, y, block=hold + ad.TRAILING_BLOCK_EXTRA, seed=42)
    assert bb_small is not None and bb_big is not None
    assert bb_small["p_boot"] < 0.05, "构造前提:block=hold 应虚假显著(低估聚簇内相关性)"
    assert bb_big["p_boot"] > 0.10, "block 放大后应回落到不显著(正确反映仅 8 个独立聚簇的高不确定性)"


# ── ④ 三端未成熟 dropna:formation(n天)/分位暖机(2520，最长边界)/forward-hold(hold天)，
#   验基率未被未成熟日污染(H-2 同款纪律) ──
def test_trailing_extreme_arrays_three_end_trim_exact_2520_boundary(monkeypatch):
    import autodiscovery as ad
    idx = pd.date_range("2000-01-03", periods=3000, freq="B")
    rng = np.random.default_rng(9)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 3000)), index=idx)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    n, hold = 63, 5
    arr = ad._trailing_extreme_arrays(n, hold, "sp500", "low")
    assert arr is not None
    idx2, sel, y = arr
    # 分位暖机(2520)远长于 formation(63)，是决定"首个可信号日"的那道边界(S3 命门:最长边界)
    expect_first_pos = n + ad._TRAILING_WARMUP - 1          # 0-indexed:前面全部未成熟
    pos_min = px.index.get_indexer([idx2.min()])[0]
    pos_max = px.index.get_indexer([idx2.max()])[0]
    assert pos_min == expect_first_pos, "首日必须恰好卡在'formation+分位暖机2520'边界，早一天都是未成熟日污染"
    assert pos_max == len(px) - 1 - hold, "末日必须恰好卡在 forward-hold 边界，晚一天是前向未实现的伪造"
    assert len(idx2) == len(px) - expect_first_pos - hold, "长度必须精确 == 剔除两道边界后的天数(基率未被未成熟日污染)"
    assert not np.isnan(y).any()


def test_trailing_extreme_arrays_immature_days_are_nan_not_false(monkeypatch):
    """S3 核心:未成熟日在中间计算阶段必须是 NaN，不是被悄悄转成 False 混进基率——
    用一条比暖机短的价格序列断言直接返回 None(暖机吃不满，不能硬凑基率)。"""
    import autodiscovery as ad
    idx = pd.date_range("2000-01-03", periods=1000, freq="B")     # 远小于 63+2520+hold
    rng = np.random.default_rng(3)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 1000)), index=idx)
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    assert ad._trailing_extreme_arrays(63, 21, "sp500", "low") is None
    assert ad._trailing_extreme_arrays(63, 21, "sp500", "high") is None


def test_trailing_extreme_arrays_invalid_side_returns_none(monkeypatch):
    import autodiscovery as ad
    px = _synth_trailing_price()
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    assert ad._trailing_extreme_arrays(63, 21, "sp500", "bogus_side") is None


def test_trailing_extreme_arrays_no_data_returns_none(monkeypatch):
    import autodiscovery as ad
    monkeypatch.setattr(ad, "_daily_price", lambda index: None)
    assert ad._trailing_extreme_arrays(63, 21, "sp500", "low") is None


# ── ⑤ H-1 路由反退化:真统计路径 + 数据不足仍 p=1.0 兜底(不是永久桩，是"数据不足→p=1.0"的
#   既有既有模式，本函数不再恒返回 None) ──
def test_compute_results_routes_trailing_extreme_real_stats_not_stub(monkeypatch):
    import autodiscovery as ad
    px = _synth_trailing_price()
    monkeypatch.setattr(ad, "_daily_price", lambda index: px)
    cand = {"candidate_id": "tr_real", "key": "test_key", "family": "trailing_extreme",
            "params": {"n": 63, "hold": 5, "side": "low", "index": "sp500"}}
    results = ad.compute_results([cand])
    r = results[0]
    assert "windows" in r and "effect" in r          # 桩阶段(纯 p=1.0 兜底)不会有这两个字段
    assert isinstance(r["p"], float) and 0.0 <= r["p"] <= 1.0


def test_compute_results_trailing_extreme_insufficient_data_still_p1_not_fabricated(monkeypatch):
    """H-1 兜底仍在:数据不足(暖机吃不满/无价格)时必须走既有'数据不足→p=1.0'，绝不能编造假统计——
    这是"数据不足→p=1.0"的既有模式，不是本族专属的永久桩(与旧 stage2 桩测试语义不同，见上方②号
    命门2 测试已证真实数据下会给真统计)。"""
    import autodiscovery as ad
    monkeypatch.setattr(ad, "_daily_price", lambda index: None)
    assert ad._trailing_extreme(63, 21, "low", "sp500", "cid") is None
    cand = {"candidate_id": "tr_short", "key": "test_key", "family": "trailing_extreme",
            "params": {"n": 63, "hold": 21, "side": "low", "index": "sp500"}}
    results = ad.compute_results([cand])
    r = results[0]
    assert r["p"] == 1.0 and r["recent_p"] is None and r["recent_powered"] is False
    assert "windows" not in r                        # 数据不足兜底分支不带 windows(与真统计路径区分)


def test_compute_results_unrouted_family_still_raises_with_streak_present():
    """H-1 反退化防御端回归锁:即便新增了 streak/trailing_extreme 路由，未知 family 仍必须炸。"""
    import autodiscovery as ad
    cand = {"candidate_id": "x", "key": "x", "family": "totally_unknown_2", "params": {}}
    with pytest.raises(ValueError):
        ad.compute_results([cand])


# ── 分母对账(N3)：len(enumerate)==148 且分族计数 == N_STREAK/N_TRAILING ──
def test_candidate_denominator_locked_at_148():
    import candidate_space as cs
    cands = list(cs.enumerate_candidates())
    assert len(cands) == cs.N_DECLARED == 148
    n_streak = sum(1 for c in cands if c["family"] in ("streak_down", "streak_break"))
    n_trailing = sum(1 for c in cands if c["family"] == "trailing_extreme")
    assert n_streak == cs.N_STREAK == 30
    assert n_trailing == cs.N_TRAILING == 14


def test_arrays_exclude_days_without_realized_forward_window_real_data():
    """同一锁的真数据集成版。CI 干净检出无 data/raw/ 价格(gitignore 生成数据) → skip——
    门禁测试不依赖 gitignore 数据是铁律(2026-07-07 CI #100-104 连挂教训),合成版已恒跑同一性质。"""
    import autodiscovery as ad
    if ad._daily_price("sp500") is None or ad._daily_price("nasdaq") is None:
        pytest.skip("data/raw/ 价格缺失(CI 干净检出)——合成版已覆盖本锁")
    for maker, args, hold in [
        (ad._positioning_arrays, ("sp500", "legacy_noncomm_pct_oi", "lo", 60), 60),
        (ad._positioning_arrays, ("nasdaq100", "legacy_noncomm_pct_oi", "lo", 20), 20),
        (ad._optsent_arrays, ("total_pc", "hi", 20), 20),
    ]:
        arr = maker(*args)
        assert arr is not None, f"{args} 真数据下不应返回 None"
        idx, sel, y = arr
        px = ad._daily_price("sp500" if args[0] == "sp500" or maker is ad._optsent_arrays else "nasdaq")
        last_price_day = px.index.max()
        # idx 最后一天 + hold 个交易日必须 <= 最后价格日(即该日的前向窗已完整实现)
        pos = px.index.get_indexer([idx.max()])[0]
        assert pos + hold <= len(px.index) - 1, (
            f"{args}: idx.max()={idx.max().date()} 距最后价格日不足 {hold} 交易日——尾部未实现前向窗混入")
        assert not np.isnan(y).any()
