"""test_vix_vol_forecast.py — 合成/固定,不碰网络。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vix_vol_forecast as V  # noqa: E402


def test_nonoverlapping_and_corr_structure():
    # 合成:VIX 与「未来波动」强相关但不完美,过去波动弱一点 —— 只验结构/字段/无前视
    n = 800
    idx = pd.bdate_range("2000-01-03", periods=n)
    rng = np.random.default_rng(0)
    ret = rng.normal(0, 0.01, n)
    sp = pd.Series(100 * np.cumprod(1 + ret), index=idx)
    vix = pd.Series(15 + 5 * rng.random(n), index=idx)
    out = V.compute(pd.DataFrame({"SP500": sp, "VIX": vix}))
    # 字段齐全
    for k in ("r_vix", "r_past", "fit_vix", "fit_past", "points", "wiki", "honesty", "n"):
        assert k in out
    assert -1.0 <= out["r_vix"] <= 1.0 and -1.0 <= out["r_past"] <= 1.0
    # 三个平行数组等长(散点对齐)
    p = out["points"]
    assert len(p["vix"]) == len(p["past_rv"]) == len(p["fwd_rv"]) == out["n"]
    # 诚实说明含「方向」命门
    assert any("方向" in h for h in out["honesty"])


def test_forward_window_is_shifted_not_leaking():
    # 目标 fwd_rv 必须来自「未来」窗:构造一段末尾波动骤增,fwd_rv 应在骤增【之前】就升高
    n = 400
    idx = pd.bdate_range("2000-01-03", periods=n)
    ret = np.concatenate([np.full(300, 0.001), np.random.default_rng(1).normal(0, 0.05, 100)])
    sp = pd.Series(100 * np.cumprod(1 + ret), index=idx)
    vix = pd.Series(np.full(n, 18.0), index=idx)
    out = V.compute(pd.DataFrame({"SP500": sp, "VIX": vix}))
    fwd = out["points"]["fwd_rv"]
    past = out["points"]["past_rv"]
    # fwd_rv 的最大值应出现在 past_rv 达到最大值【之前】(前瞻窗把未来高波动提前反映)
    assert np.argmax(fwd) < np.argmax(past)
