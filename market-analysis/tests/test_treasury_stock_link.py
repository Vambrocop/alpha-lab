"""treasury_stock_link 对旁路数据源缺失的隔离回归测试 + 核心分档逻辑单测。

仿 test_build_signals_resilience.py 的核心断言:整表宽表若某列(尤其 YIELD_10Y)全 NaN,
不会连坐删光其它列的有效历史——这正是本项目此前修过的 bug(build_signals.py 的教训,
CLAUDE.md 里"对宽表整表 .dropna() 会因某列全 NaN 连坐删光")。本脚本按列取数(_series),
从不对整表 dropna,且干脆不用 YIELD_10Y(改用日频 TNX 代理,见模块 docstring),
故 YIELD_10Y 整列 NaN、甚至整列缺失,都不该影响 NASDAQ/SP500 的有效计算。
"""
import numpy as np
import pandas as pd

from treasury_stock_link import (
    run,
    level_buckets,
    change_buckets,
    _bucket_episodes,
    _monotonic,
)


def _synthetic_df(n=900, seed=7, yield10y_all_nan=True):
    idx = pd.bdate_range("2015-01-01", periods=n)
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 6 * np.pi, n)
    tnx = 3.0 + 1.5 * np.sin(t) + np.cumsum(rng.normal(0, 0.01, n))
    tnx = np.clip(tnx, 0.3, None)                        # 收益率不为负
    trend = np.linspace(100.0, 220.0, n)
    nasdaq = trend * 3.0 + 5 * np.sin(t / 2) + np.cumsum(rng.normal(0, 0.2, n))
    sp500 = trend * 1.2 + 3 * np.cos(t / 2) + np.cumsum(rng.normal(0, 0.1, n))
    data = {
        "TNX": tnx,
        "NASDAQ": nasdaq,
        "SP500": sp500,
        "GOLD": rng.normal(1500, 50, n),                 # 无关列,正常有数据
    }
    if yield10y_all_nan:
        data["YIELD_10Y"] = np.nan
    else:
        data["YIELD_10Y"] = tnx + rng.normal(0, 0.05, n)
    return pd.DataFrame(data, index=idx)


def test_yield10y_all_nan_does_not_cascade_delete_other_columns():
    """核心回归:YIELD_10Y 整列 NaN 不该连坐删空 TNX/NASDAQ/SP500 的有效行。"""
    df = _synthetic_df(yield10y_all_nan=True)
    assert df["YIELD_10Y"].isna().all()

    out = run(write=False, _df=df)

    for asset in ("NASDAQ", "SP500"):
        base20 = out["assets"][asset]["base"]["20"]
        assert base20 is not None
        assert base20["n_days"] > 400            # 远大于 0,证明没被连坐删空


def test_missing_yield10y_column_entirely_still_works():
    """更严格版本:YIELD_10Y 列压根不存在(不只是 NaN)——证明脚本真的不依赖它(用 TNX 代理)。"""
    df = _synthetic_df(yield10y_all_nan=True).drop(columns=["YIELD_10Y"])
    assert "YIELD_10Y" not in df.columns
    out = run(write=False, _df=df)
    assert out["yield_proxy"] == "TNX"
    assert out["assets"]["SP500"]["base"]["252"]["n_days"] > 0


def test_run_output_structure_and_cell_count():
    df = _synthetic_df()
    out = run(write=False, _df=df)
    assert set(out["assets"].keys()) == {"NASDAQ", "SP500"}
    for asset in out["assets"]:
        assert len(out["assets"][asset]["level"]) == 3 * 3        # 3档 x 3窗口
        assert len(out["assets"][asset]["direction"]) == 3 * 3
    assert len(out["diagnostics"]["monotonic"]) == 2 * 2 * 3       # 2资产 x 2变量 x 3窗口
    assert "honesty" in out and len(out["honesty"]) > 0
    # 诚实红线:免责句本身会合法引用被否定的禁词(如"不产出买卖信号"),裸词匹配会误伤——
    # 只守"肯定式操作短语"是否混入(与项目 honesty-guard 测试惯例一致,见 memory)。
    forbidden_affirmative = ("建议买入", "现在买入", "应该买", "抄底吧", "赶紧卖", "值得买")
    for h in out["honesty"]:
        assert not any(p in h for p in forbidden_affirmative)


def test_level_buckets_roughly_thirds():
    idx = pd.bdate_range("2020-01-01", periods=900)
    level = pd.Series(np.linspace(0, 100, 900), index=idx)         # 均匀分布,三分位应各占约 1/3
    bucket, (q1, q2) = level_buckets(level)
    counts = bucket.value_counts()
    for k in ("low", "mid", "high"):
        assert 280 <= counts[k] <= 320
    assert q1 < q2


def test_bucket_episodes_contiguous_runs():
    idx = pd.bdate_range("2021-01-01", periods=10)
    vals = ["low", "low", "mid", "low", "low", "low", "high", "high", "low", "mid"]
    s = pd.Series(vals, index=idx)
    eps = _bucket_episodes(s, "low")
    assert len(eps) == 3                                            # 三段独立"low"游程
    assert [len(e) for e in eps] == [2, 3, 1]
    assert eps[0][0] == idx[0] and eps[0][-1] == idx[1]


def test_monotonic_flag():
    order = ["low", "mid", "high"]
    inc = {"low": {"mean_pct": 1.0}, "mid": {"mean_pct": 2.0}, "high": {"mean_pct": 3.0}}
    dec = {"low": {"mean_pct": 3.0}, "mid": {"mean_pct": 2.0}, "high": {"mean_pct": 1.0}}
    humped = {"low": {"mean_pct": 1.0}, "mid": {"mean_pct": 3.0}, "high": {"mean_pct": 2.0}}
    missing = {"low": {"mean_pct": 1.0}, "mid": {"mean_pct": None}, "high": {"mean_pct": 2.0}}
    assert _monotonic(order, inc) is True
    assert _monotonic(order, dec) is True
    assert _monotonic(order, humped) is False
    assert _monotonic(order, missing) is None


def test_change_buckets_direction_cutoffs_bracket_zero_on_real_like_series():
    """20日变化的三分位切点应大致跨零(升/降真实反映涨跌方向,不是把"最小的正数变化"误标成"降")——
    用真正双向波动的合成序列验证(而非单调序列那种退化场景)。"""
    idx = pd.bdate_range("2015-01-01", periods=900)
    t = np.linspace(0, 8 * np.pi, 900)
    level = pd.Series(3.0 + 1.0 * np.sin(t), index=idx)             # 纯正弦,涨跌各半
    _bucket, _chg, (q1, q2) = change_buckets(level)
    assert q1 < 0 < q2                                               # 切点跨零 → falling 真是"跌"
