"""build_signals 对旁路数据源缺失的隔离回归测试。"""

import numpy as np
import pandas as pd

from build_signals import (
    compute_daily_signals,
    compute_log_returns,
    compute_technical_signals,
)


def test_missing_vix3m_does_not_null_nasdaq_volatility():
    """VIX3M 整列失败时，NASDAQ 的有效收益/波动率不能被连带删除。"""
    idx = pd.bdate_range("2026-01-02", periods=80)
    trend = np.linspace(100.0, 125.0, len(idx))
    prices = pd.DataFrame(
        {
            "NASDAQ": trend + np.sin(np.arange(len(idx))),
            "SP500": trend * 0.8 + np.cos(np.arange(len(idx))),
            "BTC": trend * 2.0 + np.sin(np.arange(len(idx)) / 2),
            "DXY": 100.0 + np.cos(np.arange(len(idx)) / 3),
            "VIX": 18.0 + np.sin(np.arange(len(idx)) / 4),
            "VIX3M": np.nan,
        },
        index=idx,
    )

    returns = compute_log_returns(prices.ffill())
    assert returns["NASDAQ"].notna().sum() == len(idx) - 1
    assert returns["VIX3M"].isna().all()

    tech = compute_technical_signals(prices.ffill(), returns).shift(1)
    records = compute_daily_signals(
        prices.ffill(), returns, tech, idx,
        index="NASDAQ", priors={month: 0.6 for month in range(1, 13)},
    )
    latest_vol = records[idx[-1].strftime("%Y-%m-%d")]["nasdaq_vol"]
    assert np.isfinite(latest_vol)
    assert latest_vol > 0
