"""event_study 置换检验守门(2026-08-24 新增)。

为什么加:此前显著性只靠 `ttest_1samp`(假设 iid 正态)。事件收益厚尾、事件数常只有个位数,
这种条件下 t 检验会**高估**显著性——而我们把 p<0.10 当 "significant" 公开发布。
上线当天实测就抓到:地缘冲击 p_t=0.059(t 检验判显著) vs p_perm=0.258(置换判不显著)。

这里守三件事:① 置换 p 真被算出来且落在合法区间;② significant 是「两检验都过」的与门
(不能悄悄退回只看 t 检验);③ 置换检验本身在**已知答案**的合成数据上行为正确
(真无效应→p 大;真有强效应→p 小)。
hermetic:全部用合成价格序列,不联网、不读 data/。
"""
import numpy as np
import pandas as pd
import pytest

from event_study import event_study


def _synth_prices(n_days=4000, mu=0.0003, sigma=0.01, seed=7):
    """几何随机游走日线(无任何事件效应)。"""
    rng = np.random.default_rng(seed)
    rets = rng.normal(mu, sigma, n_days)
    idx = pd.bdate_range("2000-01-03", periods=n_days)
    return pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)


def test_permutation_fields_present_and_valid():
    px = _synth_prices()
    dates = [px.index[i].strftime("%Y-%m-%d") for i in (500, 1000, 1500, 2000, 2500)]
    r = event_study(px, dates, window_days=30, label="合成")
    assert r is not None
    assert r["n_permutations"] > 0
    p = r["p_permutation"]
    assert p is not None and 0.0 < p <= 1.0        # (1+hits)/(B+1) 永不为 0
    assert "significance_basis" in r


def test_significant_requires_both_tests():
    """与门:t 检验过、置换没过 → 整体不显著(反之亦然)。防有人把口径悄悄放松回单一 t 检验。"""
    px = _synth_prices()
    dates = [px.index[i].strftime("%Y-%m-%d") for i in (500, 1000, 1500, 2000, 2500)]
    r = event_study(px, dates, window_days=30, label="合成")
    both = (r["p_value"] < 0.10) and (r["p_permutation"] < 0.10)
    assert r["significant"] is both
    assert r["significant_ttest_only"] is (r["p_value"] < 0.10)
    # 与门只会更严、不会更松
    assert not (r["significant"] and not r["significant_ttest_only"])


def test_permutation_says_not_significant_when_no_real_effect():
    """真无效应(事件日=随便挑的日子)→ 置换 p 不该系统性地小。
    多组随机事件日,允许个别偶然偏小,但中位数必须明显大于 0.10(否则说明检验被写坏了)。"""
    px = _synth_prices(seed=11)
    ps = []
    rng = np.random.default_rng(3)
    for _ in range(12):
        pos = rng.choice(np.arange(200, len(px) - 200), size=5, replace=False)
        dates = [px.index[i].strftime("%Y-%m-%d") for i in pos]
        r = event_study(px, dates, window_days=30, label="合成")
        ps.append(r["p_permutation"])
    assert float(np.median(ps)) > 0.10, f"无效应时置换 p 中位数={np.median(ps):.3f},过小=检验有偏"


def test_permutation_detects_a_strong_real_effect():
    """真有强效应(事件后 30 天被人为拉高)→ 置换 p 必须变小,证明它不是永远说'不显著'。"""
    rng = np.random.default_rng(5)
    n = 4000
    rets = rng.normal(0.0002, 0.008, n)
    idx = pd.bdate_range("2000-01-03", periods=n)
    pos = [500, 1000, 1500, 2000, 2500, 3000]
    for p0 in pos:                       # 事件后 30 个交易日每天多 +0.4%
        rets[p0 + 1: p0 + 31] += 0.004
    px = pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)
    dates = [idx[i].strftime("%Y-%m-%d") for i in pos]
    r = event_study(px, dates, window_days=30, label="合成强效应")
    assert r["p_permutation"] < 0.05, f"强效应下置换 p={r['p_permutation']} 仍大,检验没检测力"
    assert r["significant"] is True


def test_permutation_is_deterministic():
    """固定种子 → 已发布 p 值可复现(repo 铁律:公开统计结论不许每跑一个样)。"""
    px = _synth_prices(seed=21)
    dates = [px.index[i].strftime("%Y-%m-%d") for i in (600, 1200, 1800, 2400)]
    a = event_study(px, dates, window_days=30, label="合成")
    b = event_study(px, dates, window_days=30, label="合成")
    assert a["p_permutation"] == b["p_permutation"]
