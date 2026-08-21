"""
event_causal.py — 方法 B：反事实事件影响（counterfactual event impact）

给定 (处理资产, 一组对照资产, 事件日, 前/后窗口)：
  1. 事件前窗口用 OLS 拟合 处理 ~ 对照（建立"反事实关系"）；
  2. 把对照在事件后窗口的走势映射成处理资产的**反事实**路径；
  3. 实际 − 反事实 = 异常累计影响(CAR)；
  4. block-bootstrap 前窗残差 → "无效应"零分布，看实际累计影响是否超出 95% 区间。
     （= CausalImpact / 合成控制 的精神：用对照构造反事实，再做诚实显著性检验。）

诚实红线：
  - 前窗拟合 R² 太低（对照解释不了处理）→ 判"对照不充分,不下结论"；
  - 后窗太短（如 SPCX 仅上市 1–2 天）→ 返回 pending，**绝不对极短样本硬估反事实**。

依赖仅 numpy/pandas/yfinance（OLS 用 numpy.linalg.lstsq，无需 statsmodels）。
输出 event_causal.json（processed + web + docs）。
"""
import datetime
import json
import numpy as np
import pandas as pd
from pathlib import Path

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

SEED       = 20260613
N_BOOT     = 2000
MIN_R2     = 0.30      # 前窗拟合解释力下限：低于此判"对照不充分"
MIN_POST_N = 15        # 后窗最少交易日：不足则不估（SPCX 早期即属此）
SPCX_LIST  = "2026-06-12"


def _fetch(tickers, start, end):
    """独立拉日收盘（与 long_history 同口径，自带缓存兜底）。"""
    import yfinance as yf
    out = {}
    for t in tickers:
        cache = RAW_DIR / f"evt_{t.replace('^','').replace('-','')}.csv"
        s = None
        try:
            df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
            if not df.empty:
                c = df["Close"]
                s = (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna()
                s.index = pd.to_datetime(s.index)
                s.to_csv(cache)
        except Exception as e:
            print(f"  ⚠ {t} 下载失败：{e}")
        if s is None and cache.exists():
            s = pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0].dropna()
        if s is not None:
            out[t] = s
    return pd.DataFrame(out).dropna() if out else None


def counterfactual_impact(treated, controls, event_date,
                          pre_n=120, post_n=20, n_boot=N_BOOT, seed=SEED):
    """treated: 收益 Series；controls: 收益 DataFrame（同 index）。返回结果 dict。"""
    treated = treated.dropna()
    controls = controls.reindex(treated.index).dropna()
    treated = treated.reindex(controls.index)
    idx = treated.index
    # side='left'：事件当日算作后窗第 1 天；事件日若非交易日则顺延到下一交易日。
    ev = int(idx.searchsorted(pd.Timestamp(event_date)))
    avail_post = len(idx) - ev
    if ev < pre_n:
        return {"status": "insufficient_pre", "have_pre": ev, "need_pre": pre_n}
    if avail_post < MIN_POST_N:
        return {"status": "pending", "have_post": int(avail_post), "need_post": MIN_POST_N}
    post_n = int(min(post_n, avail_post))
    if pre_n - post_n < 10:           # 残差块起点太少 → 零分布退化，诚实地不估
        return {"status": "insufficient_pre_for_bootstrap", "pre_n": pre_n, "post_n": post_n}

    Xpre = np.column_stack([np.ones(pre_n), controls.values[ev - pre_n:ev]])
    ypre = treated.values[ev - pre_n:ev]
    coef, *_ = np.linalg.lstsq(Xpre, ypre, rcond=None)
    resid = ypre - Xpre @ coef
    sst = ((ypre - ypre.mean()) ** 2).sum()
    r2 = float(1 - (resid ** 2).sum() / sst) if sst > 0 else 0.0

    Xpost = np.column_stack([np.ones(post_n), controls.values[ev:ev + post_n]])
    daily_ab = treated.values[ev:ev + post_n] - Xpost @ coef
    cum = float(daily_ab.sum())

    # ── 零分布(无效应)：block-bootstrap 残差 + 系数估计不确定性 ──
    # 独立审查 BLOCKER#1：旧版只抽前窗残差求和，漏了"反事实 Xpost@coef 本身是估计量、
    # 有抽样方差"这一项——事件期对照偏离前窗均值时该方差最大，导致 p 偏小(反保守)。
    # 这里把系数不确定性经后窗设计行传播进零分布，使推断诚实/偏保守。
    rng = np.random.default_rng([seed, post_n])
    starts = rng.integers(0, pre_n - post_n + 1, n_boot)
    resid_sum = np.array([resid[s:s + post_n].sum() for s in starts])   # 残差噪声(保留厚尾/自相关)
    dof = max(pre_n - Xpre.shape[1], 1)
    cov = ((resid ** 2).sum() / dof) * np.linalg.pinv(Xpre.T @ Xpre)
    cov = (cov + cov.T) / 2                                              # 对称化(数值稳)
    c = Xpost.sum(axis=0)                                               # 累计反事实对各系数的灵敏度
    coef_term = rng.multivariate_normal(np.zeros(len(c)), cov, size=n_boot) @ c
    null = resid_sum + coef_term                                        # 残差噪声 + 系数不确定性
    p = float((np.sum(np.abs(null) >= abs(cum)) + 1) / (n_boot + 1))    # 双边
    lo, hi = np.percentile(null, [2.5, 97.5])

    if r2 < MIN_R2:
        status, verdict = "inadequate_controls", f"对照不充分(前窗R²={r2:.2f})，不下结论"
    elif p < 0.05:
        sign = "下跌" if cum < 0 else "上涨"
        status, verdict = "significant", f"✓ 显著异常{sign} {cum*100:+.1f}% (p={p:.3f})"
    else:
        status, verdict = "not_significant", f"✗ 未见显著异常 (p={p:.3f})"

    return {"status": status, "verdict": verdict,
            "cum_abnormal_pct": round(cum * 100, 2),
            "p_value": round(p, 4), "pre_r2": round(r2, 3),
            "null_ci95_pct": [round(lo * 100, 2), round(hi * 100, 2)],
            "pre_n": pre_n, "post_n": post_n,
            "daily_abnormal_pct": [round(x * 100, 3) for x in daily_ab]}


def _log_ret(px):
    return np.log(px / px.shift(1)).dropna()


def run_all():
    print("=== 方法 B：反事实事件影响 ===")
    events = []

    # ── 验证用历史事件：SVB 倒闭(2023-03) → 地区银行 KRE，对照 SPY/QQQ ──
    px = _fetch(["KRE", "SPY", "QQQ"], "2022-06-01", "2023-05-01")
    if px is not None and {"KRE", "SPY", "QQQ"} <= set(px.columns):
        ret = _log_ret(px)
        r = counterfactual_impact(ret["KRE"], ret[["SPY", "QQQ"]], "2023-03-09")
        r.update({"key": "svb_kre", "name": "SVB 倒闭 → 地区银行(KRE)",
                  "treated": "KRE", "controls": ["SPY", "QQQ"], "event_date": "2023-03-09",
                  "note": "验证用：硅谷银行挤兑。识别假设=对照(大盘/科技)未受地区银行挤兑直接冲击。"
                          "注：SPY 含约13%金融,本身被传染下跌,会把反事实拖低 → 实测异常幅度偏保守(下界)。"})
        events.append(r)
        print(f"  SVB→KRE: {r.get('verdict', r['status'])}")

    # ── SPCX 钩子：上市后交易日不足则诚实 pending ──
    spx = _fetch(["SPCX"], SPCX_LIST, (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    spcx = {"key": "spcx_listing", "name": "SPCX 上市影响（待数据）",
            "status": "pending", "days_listed": int(len(spx)) if spx is not None else 0,
            "need_post": MIN_POST_N,
            "note": f"上市后交易日不足 {MIN_POST_N}，反事实窗口太短,暂不估计——"
                    f"诚实地不对极短样本硬估。攒够后此处自动出现解禁/事件的反事实影响。"}
    print(f"  SPCX: pending（已上市 {spcx['days_listed']} 个交易日，需 ≥{MIN_POST_N}）")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "反事实事件影响：前窗 OLS(处理~对照)建反事实，后窗实际−反事实=异常累计，"
                  "block-bootstrap 前窗残差做显著性。对照不充分/窗口太短均诚实不下结论。",
        "seed": SEED, "n_boot": N_BOOT, "min_r2": MIN_R2, "min_post_n": MIN_POST_N,
        "caveat": "准实验反事实估计(非随机对照实验)：度量的是相对对照的异常收益，"
                  "因果归因依赖'对照未受同一冲击'这一识别假设——这是假设,不是已证事实。"
                  "零分布已含系数估计不确定性(偏保守)。",
        "events": events, "spcx": spcx,
    }
    from util_io import write_json
    write_json("event_causal.json", out, proc=True, allow_nan=False)
    print(f"[OK] event_causal.json：{len(events)} 个事件 + SPCX 钩子")
    return out


if __name__ == "__main__":
    # 顶层 fail-soft:在常规 CI 流水线里 + 联网抓控制资产(yfinance 会 flake)+ 反事实统计
    # (OLS/block-bootstrap 有奇异矩阵等边缘) → 任一意外异常都不该杀掉整条 refresh。
    # 内部已有 px is None/缺列的守卫,这里再兜一层顶层未预期异常(独立事件研究·非质量门)。
    try:
        run_all()
    except Exception as e:
        print(f"[反事实事件影响] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        raise SystemExit(0)
