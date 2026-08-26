"""backtest 块自助守门(2026-08-24 新增)。

为什么加:backtest 的 up_{h}d 是**逐日**算的 h 日前向结果,相邻两天窗口共享 h-1 天。
此前 ttest_1samp 把每天当独立观测 → 有效样本约 n/h、p 被低估一到两个数量级。
上线当天实测(SP500):校准桶 p_t=0.0006→块自助 0.181、p_t=0.0079→0.341;
Tier>=4 策略 p_t=0.0033→0.209——三条"显著"被撤销。

守四件事:① 无效应时不误报(校准)② 真有效应时能检出(检定力)③ 块长越大 p 越保守
(证明它真的在惩罚自相关,而不是摆设)④ 固定种子可复现。
hermetic:纯合成数组,不读 data/、不联网。
"""
import numpy as np
import pytest

from backtest import block_bootstrap_p


def _ar1_binary(n=3000, base=0.62, block=20, seed=3):
    """构造有重叠自相关结构的 0/1 序列:每 block 天共享同一次抽样(模拟前向窗口重叠)。"""
    rng = np.random.default_rng(seed)
    n_blk = int(np.ceil(n / block))
    draws = (rng.random(n_blk) < base).astype(float)
    return np.repeat(draws, block)[:n]


def test_no_effect_not_flagged():
    """序列均值≈基率 → p 应该大,不该误报显著。"""
    x = _ar1_binary(base=0.62)
    p = block_bootstrap_p(x, base_rate=float(x.mean()), block=20)
    assert p is not None and p > 0.10, f"无偏离时 p={p} 过小 = 误报"


def test_real_effect_detected():
    """构造明显偏离基率的序列 → p 必须小,证明检验有检定力(不是永远说不显著)。"""
    x = np.concatenate([np.ones(1500), np.zeros(500)])   # 均值 0.75
    p = block_bootstrap_p(x, base_rate=0.50, block=20)
    assert p < 0.05, f"强偏离下 p={p} 仍大 = 没有检定力"


def test_larger_block_is_more_conservative():
    """核心性质:块越长(自相关越被尊重),p 越大(越保守)。
    若写反/写坏,这条会红——它证明检验真的在惩罚重叠,而不是走过场。"""
    x = _ar1_binary(base=0.70, block=20, seed=11)
    base = 0.62
    p_small = block_bootstrap_p(x, base, block=1)     # 当每天独立(相当于朴素做法)
    p_large = block_bootstrap_p(x, base, block=20)    # 尊重 20 日重叠
    assert p_large >= p_small, f"块长 20 的 p({p_large}) 不该小于块长 1 的 p({p_small})"


def test_deterministic_and_never_zero():
    """固定种子 → 已发布 p 可复现;(1+hits)/(B+1) → 永不为 0(有限模拟不该声称绝无可能)。"""
    x = _ar1_binary(base=0.80, seed=5)
    a = block_bootstrap_p(x, 0.50, block=20)
    b = block_bootstrap_p(x, 0.50, block=20)
    assert a == b
    assert a > 0.0


def test_degenerate_inputs_return_none():
    """样本 <2 → None(调用方据此不判显著,而不是崩)。"""
    assert block_bootstrap_p(np.array([1.0]), 0.5, block=20) is None
    assert block_bootstrap_p(np.array([]), 0.5, block=20) is None


# ── walk_forward 分档显著性也收紧为「t 检验 + 块自助」(2026-08-25) ─────────────
def test_walk_forward_tier_significance_uses_block_bootstrap():
    """walk_forward 是项目宣称的"真样本外权威",其分档显著性此前只用 t 检验
    (fwd_up_20d 逐日采样、相邻共享 19 天 → 乐观约一个数量级;本文件 P2-4 早在
    Tier>=4 汇总处用了块自助,分档是漏网)。这里守:不同 mask 必须给出不同的块自助 p
    ——防"看似接上、实则每格算的是同一个东西"(上线时 fold0 两档 p 恰好相同,
    经此法核实为真巧合而非 bug)。"""
    import numpy as np
    from walk_forward import block_bootstrap_diff
    rng = np.random.default_rng(0)
    y = (rng.random(500) < 0.62).astype(float)
    m1 = np.zeros(500, bool); m1[:150] = True; rng.shuffle(m1)
    m2 = np.zeros(500, bool); m2[:300] = True; rng.shuffle(m2)
    a = block_bootstrap_diff(m1, y, seed=42)
    b = block_bootstrap_diff(m2, y, seed=42)
    assert a is not None and b is not None
    assert a["ci95"] != b["ci95"], "不同 mask 却得到同一 CI = mask 没真正传进去"
    assert 0.0 <= a["p_boot"] <= 1.0 and 0.0 <= b["p_boot"] <= 1.0
