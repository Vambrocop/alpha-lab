"""backtest 块自助守门(2026-08-24 建，2026-08-27 随口径修正一并重写)。

为什么要有:backtest 的 up_{h}d 是**逐日**算的 h 日前向结果,相邻两天窗口共享 h-1 天。
此前 ttest_1samp 把每天当独立观测 → 有效样本约 n/h、p 被低估一到两个数量级。

**2026-08-27 口径修正(用户质疑「是不是矫枉过正」→ 实测证实)**:初版在「某档的观测子集」
自身数组上取连续块,但该档的日子在日历上是散落的,那些元素本就近乎独立却被当整块搬走 →
过度保守 1.8–2.8 倍,误判掉本该显著的格。改为块取在**日历序列**上、mask 随之重采样
(与 walk_forward.block_bootstrap_diff 同语义)。签名随之变为 (mask, y_all)。

守四件事:① 无效应不误报 ② 真有效应能检出 ③ **比朴素 t 检验更保守**(证明它真在惩罚
自相关,而不是走过场)④ 确定性与退化输入。hermetic:纯合成数组,不读 data/、不联网。
"""
import numpy as np
from scipy import stats

from backtest import block_bootstrap_p


def _series_with_overlap(n=3000, base=0.62, block=20, seed=3):
    """构造有重叠自相关结构的 0/1 日序列:每 block 天共享同一次抽样(模拟前向窗口重叠)。"""
    rng = np.random.default_rng(seed)
    draws = (rng.random(int(np.ceil(n / block))) < base).astype(float)
    return np.repeat(draws, block)[:n]


def test_no_effect_not_flagged():
    """随机挑的一半日子(与整体无差别)→ p 应该大,不该误报显著。"""
    y = _series_with_overlap()
    rng = np.random.default_rng(7)
    mask = rng.random(len(y)) < 0.5
    p = block_bootstrap_p(mask, y, block=20)
    assert p is not None and p > 0.10, f"无差别时 p={p} 过小 = 误报"


def test_real_effect_detected():
    """某个 mask 圈住的日子明显好于整体 → p 必须小(证明有检定力,不是永远说不显著)。"""
    y = np.concatenate([np.ones(1200), np.zeros(1800)])   # 前 1200 天全涨
    mask = np.zeros(3000, bool); mask[:1200] = True
    p = block_bootstrap_p(mask, y, block=20)
    assert p < 0.05, f"强效应下 p={p} 仍大 = 没有检定力"


def test_catches_what_naive_ttest_would_overstate():
    """核心性质:在**朴素 t 检验判显著**的情形下,块自助必须给出明显更大的 p。

    这正是它存在的理由——重叠窗口下 t 检验把每天当独立观测,会把"整块行情碰巧被圈中"
    误读成强证据。构造:y 每 20 天一个整块(模拟 20 日前向窗口重叠),mask 按**整块**
    选取 → 有效样本只有块数、远小于天数。朴素 t 检验会因 n 大而给出很小的 p;块自助
    尊重块结构后应该显著更保守。若哪天实现写反/退回逐日口径,这条会红。
    """
    rng = np.random.default_rng(11)
    n_blocks, block = 150, 20
    vals = (rng.random(n_blocks) < 0.62).astype(float)
    y = np.repeat(vals, block)                       # 每块内部完全相同 = 极端重叠
    chosen = rng.random(n_blocks) < 0.4
    mask = np.repeat(chosen, block)
    _, p_t = stats.ttest_1samp(y[mask], y.mean())
    p_blk = block_bootstrap_p(mask, y, block=block)
    assert p_t < 0.10, f"构造失败:朴素 p={p_t} 本应显著(换种子)"
    assert p_blk > p_t * 3, f"块自助 p({p_blk}) 未显著大于朴素 p({p_t}) = 没在惩罚自相关"


def test_deterministic():
    """固定种子 → 已发布 p 可复现(repo 铁律:公开统计结论不许每跑一个样)。"""
    y = _series_with_overlap(base=0.80, seed=5)
    mask = np.zeros(len(y), bool); mask[: len(y) // 3] = True
    assert block_bootstrap_p(mask, y, block=20) == block_bootstrap_p(mask, y, block=20)


def test_degenerate_inputs_return_none():
    """mask 太小/空序列 → None(调用方据此不判显著,而不是崩)。"""
    y = _series_with_overlap()
    tiny = np.zeros(len(y), bool); tiny[:3] = True
    assert block_bootstrap_p(tiny, y, block=20) is None        # mask < 10
    assert block_bootstrap_p(np.array([], bool), np.array([]), block=20) is None


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
