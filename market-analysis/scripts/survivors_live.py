"""survivors_live.py — 存活规律观察台（把扛过多重检验的 FDR 存活规律，标出"今天是否应期"）。

autodiscovery 里 verdict=='survive' 的候选 = 在预声明候选池(命门)里扛过 BY-FDR + 现代子样本仍显著的
"存活规律"。它们大多不是每天成立：金叉看当前趋势、九月只在 9 月、回撤看当日大跌。本脚本：
  1. 读 autodiscovery.json 取 verdict=='survive'（历史 edge 数字直接复用、**不重算** → 单一真相源、不漂移）；
  2. 本地按各族**原定义**算"今天是否应期"（金叉 50>200 / BTC 20日动量±5% / 纳指跌进最低5% / 纳指>200日线 / 月份等）；
  3. 写 survivors_live.json（web+docs）：常驻清单 + 应期/休眠标记 → 喂 llm_daily_read 做诚实解读、给前端观察台展示。

**方向诚实命门**：autodiscovery 的窗口口径是 `up_pct = label==1(触发组) 上涨率`、`base_pct = label==0(对照组)`。
对"先验说某期偏弱"的日历效应(九月/世界杯年/sell-in-may)，`label==1` 是**相反的强组**(非九月/非杯年/冬季)——
所以每条描述符显式记 `触发组/对照组`，edge 永远把 up 挂到真实触发组，**绝不**想当然按族名把 up 当成"该条件本身"。

诚实红线：仅描述性、非预测非荐股；「应期」=今天该条件成立、「休眠」=今天不成立(勿当当前信号)、「未接入」=当前态未监测(仅历史)；
前向 OOS(门4)仍在累积、未确认；"扛过检验"≠"下次一定灵"；过去≠未来。数据/autodiscovery 缺失 → 优雅跳过(不阻断)。
"""
import json
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
RAW = SCRIPTS.parent / "data" / "raw"

try:                                     # 单一真相源：BTC 动量阈值与生产对齐(改上游自动传导)
    from signal_model import BTC_MOM_THRESH
except Exception:
    BTC_MOM_THRESH = 0.05
REBOUND_PCTL = 5         # p5_h1_nasdaq：跌破全样本第 5 百分位(与 candidate_space 一致)
GOLDEN_MA = (50, 200)    # 金叉：50 日均线上穿 200 日均线


def _load_px(fname, floor):
    """读一列价 CSV → 升序正价 Series；行数不足 floor 返回 None。"""
    p = RAW / fname
    if not p.exists():
        return None
    try:
        s = pd.read_csv(p, index_col=0, parse_dates=True)
    except Exception:
        return None
    s = pd.to_numeric(s.iloc[:, 0], errors="coerce").dropna()
    s = s[s > 0].sort_index()
    return s if len(s) >= floor else None


# ── 各族"今天是否应期"（active, 当前态大白话）；无数据 → (None, 说明) ──────────────
def _golden_cross_state():
    px = _load_px("SP500_long.csv", GOLDEN_MA[1])
    if px is None:
        return None, "标普数据不足"
    ma_s = px.rolling(GOLDEN_MA[0]).mean().iloc[-1]
    ma_l = px.rolling(GOLDEN_MA[1]).mean().iloc[-1]
    if pd.isna(ma_s) or pd.isna(ma_l):
        return None, "均线未算出"
    active = bool(ma_s > ma_l)
    return active, ("标普 50 日均线高于 200 日均线（金叉成立·趋势向上）" if active
                    else "标普 50 日均线未高于 200 日均线（金叉未成立）")


def _btc_r20():
    """BTC 20 日动量 pct_change(20)；无数据 None。"""
    px = _load_px("BTC.csv", 21)
    if px is None:
        return None
    return float(px.iloc[-1] / px.iloc[-21] - 1)


def _btc_mom_pos_state():
    r = _btc_r20()
    if r is None:
        return None, "BTC 数据不足"
    return bool(r > BTC_MOM_THRESH), f"BTC 近 20 日动量 {r * 100:+.1f}%（{'高于' if r > BTC_MOM_THRESH else '未高于'} +5% 阈值）"


def _btc_mom_neg_state():
    r = _btc_r20()
    if r is None:
        return None, "BTC 数据不足"
    return bool(r < -BTC_MOM_THRESH), f"BTC 近 20 日动量 {r * 100:+.1f}%（{'低于' if r < -BTC_MOM_THRESH else '未低于'} -5% 阈值）"


def _nasdaq_ma200_state():
    px = _load_px("NASDAQ_COMP_long.csv", 200)
    if px is None:
        return None, "纳指数据不足"
    ma200 = px.rolling(200).mean().iloc[-1]
    if pd.isna(ma200):
        return None, "均线未算出"
    active = bool(px.iloc[-1] > ma200)
    return active, f"纳指最新收盘{'高于' if active else '不高于'} 200 日均线"


def _rebound_state():
    px = _load_px("NASDAQ_COMP_long.csv", 1000)
    if px is None:
        return None, "纳指数据不足"
    ret = px.pct_change().dropna()
    thr = float(np.percentile(ret.values, REBOUND_PCTL))   # hold=1 → 与 autodiscovery 阈值仅差末 1 行(§审#3·可忽略)
    last = float(ret.iloc[-1])
    active = bool(last <= thr)
    return active, (f"纳指最新日收益 {last * 100:+.1f}%"
                    f"（{'跌进' if active else '未跌进'}历史最低 5% 档 {thr * 100:.1f}%）")


def _september_state():
    m = datetime.date.today().month
    active = (m == 9)
    return active, f"当前 {m} 月（{'正是 9 月·应期' if active else '非 9 月'}）"


def _cot_nq_extreme_short_state():
    """COT 纳指投机净仓位是否处 3 年(156 份周报)最低 10% 档(极空)。
    点时间命门(T2·2026-07-08)：只用 usable_from <= 今天 的报告——CFTC 周二快照周五才发布
    (usable_from≈report_date+4 交易日)，绝不偷看"已统计但还没公布"的报告。
    窗口(156)/阈值(≤10)/分位函数 全部复用 autodiscovery 原定义(单一真相源,改上游自动传导)。"""
    try:
        import autodiscovery as ad
        rep = ad._cot_reports("nasdaq100", "legacy_noncomm_pct_oi")
    except Exception as e:
        return None, f"COT 数据不可用({type(e).__name__})"
    if rep is None or len(rep) == 0:
        return None, "COT 数据缺失"
    today = pd.Timestamp(datetime.date.today())
    usable = rep[rep["usable_from"] <= today]
    if len(usable) < ad._POS_WINDOW:
        return None, f"可用 COT 报告不足 {ad._POS_WINDOW} 份(暖机中)"
    pct = float(ad._rolling_pctrank(usable["value"].values)[-1])
    if np.isnan(pct):
        return None, "COT 分位未算出"
    active = bool(pct <= 10)
    last = usable.iloc[-1]
    return active, (f"最新可用 COT 报告(报告日 {pd.Timestamp(last['report_date']).date()}·"
                    f"{pd.Timestamp(last['usable_from']).date()} 起可用)：纳指投机净仓位处 3 年第 {pct:.0f} 分位"
                    f"（{'≤10 极空档·应期' if active else '未到 ≤10 极空档'}）")


def _world_cup_state():
    """触发组=非杯年夏季(label==1)。应期 = 夏季(6-8月) 且 今年非世界杯年——杯年夏季触发组不成立。"""
    today = datetime.date.today()
    summer = today.month in (6, 7, 8)                      # 效应只作用于夏季(6-8月)
    try:
        from seasonality import WORLD_CUP_YEARS            # 单一来源,与 autodiscovery 同表不漂移
        wc = today.year in WORLD_CUP_YEARS
    except Exception:
        wc = None
    active = bool(summer and wc is False)                 # 非杯年夏季才是触发组成立
    if not summer:
        state = f"当前 {today.month} 月（非夏季·休眠）"
    elif wc:
        state = f"当前 {today.month} 月夏季，但 {today.year} 是世界杯年 → 触发组「非杯年夏季」不成立·休眠"
    elif wc is False:
        state = f"当前 {today.month} 月夏季且 {today.year} 非世界杯年 → 触发组成立·应期"
    else:
        state = f"当前 {today.month} 月夏季（{today.year} 杯年状态未知）"
    return active, state


# (family, key) → dict(name 大白话名, trigger label==1 触发组, rest 对照组基准, horizon 视野, state 当前态函数)
#   ⚠️ 两种窗口口径(命门·Opus 审 2026-07-01)：
#     · 日历族(_cal_windows): up=label==1 组、base=label==0 **补集** → rest 写真实补集名(如"九月")。
#     · 反弹/因子/体制族(_diff_windows): up=触发组、base=`yy.mean()` **全样本基率**(含触发日,非补集!)
#        → rest 必须写"全样本基率",**绝不能**写补集名(如"200线下方"),否则把全样本数字安到补集头上。
_DESCRIPTORS = {
    ("regime", "golden_cross_sp500"): dict(     # _diff_windows → base=全样本基率
        name="标普金叉（50 日线上穿 200 日线）", trigger="标普金叉成立时", rest="全样本基率",
        horizon="标普未来 20 日", state=_golden_cross_state),
    ("factor", "BTC_mom20_pos"): dict(          # _diff_windows → base=全样本基率
        name="BTC 20 日动量为正（风险偏好代理）", trigger="BTC 动量 >+5% 时", rest="全样本基率",
        horizon="纳指未来 20 日", state=_btc_mom_pos_state),
    ("factor", "BTC_mom20_neg"): dict(          # _diff_windows → base=全样本基率
        name="BTC 20 日动量为负（风险偏好走弱）", trigger="BTC 动量 <-5% 时", rest="全样本基率",
        horizon="纳指未来 20 日", state=_btc_mom_neg_state),
    ("factor", "NASDAQ_above_ma200"): dict(     # _diff_windows → base=全样本基率
        name="纳指在 200 日线上方（趋势）", trigger="纳指收盘 >200 日线时", rest="全样本基率",
        horizon="纳指未来 20 日", state=_nasdaq_ma200_state),
    ("rebound", "p5_h1_nasdaq"): dict(          # _diff_windows → base=全样本基率
        name="纳指大跌后的次日走向", trigger="纳指跌进历史最低 5% 的大跌日", rest="全样本基率",
        horizon="次日", state=_rebound_state),
    ("calendar", "september_sp500"): dict(      # _cal_windows·先验:九月最弱 → label==1=非九月(强组);base=补集九月
        name="标普九月效应（九月历史最弱月）", trigger="非九月", rest="九月",
        horizon="当日", state=_september_state),
    ("calendar", "monthof_9_sp500"): dict(      # _cal_windows·机器枚举:label==1=九月;base=补集其余月份
        name="标普 9 月（机器枚举·另一口径）", trigger="九月", rest="其余月份",
        horizon="当日", state=_september_state),
    ("calendar", "world_cup_year_nasdaq"): dict(  # _cal_windows·先验:杯年夏季偏弱 → label==1=非杯年夏季;base=补集杯年夏季
        name="纳指世界杯年夏季效应（分心先验）", trigger="非世界杯年的夏季", rest="世界杯年夏季",
        horizon="当日", state=_world_cup_state),
    ("positioning", "legacy_noncomm_pct_oi_lo_h60_nasdaq100"): dict(  # _diff_windows → base=全样本基率(#7 新存活·T2 接入)
        name="COT 纳指投机仓位极空（逆向拥挤指标）", trigger="投机净仓位处 3 年最低 10% 档时", rest="全样本基率",
        horizon="纳指未来 60 日", state=_cot_nq_extreme_short_state),
}


def _pick_window(cand):
    """取历史 edge 窗口：优先'2000后'(现代代表)，回退'完整'。返回 (up, base, label)。"""
    wins = {w.get("label"): w for w in cand.get("windows", [])}
    for lab in ("2000后", "完整"):
        w = wins.get(lab)
        if w and w.get("up_pct") is not None and w.get("base_pct") is not None:
            return w["up_pct"], w["base_pct"], lab
    return None, None, None


def _dnote(up, base):
    """方向标注(诚实：按 up-base 符号，绝不按族名想当然)。up=触发组(label==1) 上涨率。"""
    if up is None or base is None:
        return "方向不明"
    d = up - base
    if d >= 5:
        return "明显偏正"
    if d >= 1:
        return "微弱偏正"
    if d <= -5:
        return "明显偏负"
    if d <= -1:
        return "微弱偏负"
    return "≈基率(几乎无差别)"


def _edge_plain(desc, up, base, window, dnote):
    """历史 edge 大白话。desc 缺失(未接入新存活规律)→ 用 autodiscovery 中性口径'触发组 vs 基率'，绝不猜组名。"""
    if up is None or base is None:
        return "历史 edge 数据缺失"
    if desc is None:
        return f"触发组 {up}% vs 基率 {base}%（{window}·{dnote}·组别待接入）"
    return f"{desc['trigger']} {up}% vs {desc['rest']} {base}%（{desc['horizon']}上涨率·{window}·{dnote}）"


def build():
    try:
        ad = json.loads((WEB / "autodiscovery.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[survivors_live] 读 autodiscovery.json 失败，跳过: {e}")
        return None
    # 裁决横跳记录(flicker.py 已产,这里只消费不重算——单一真相源)
    try:
        fl_rows = json.loads((WEB / "flicker.json").read_text(encoding="utf-8")).get("candidates", [])
        flick = {c.get("key"): c for c in fl_rows}
    except Exception as e:
        print(f"[survivors_live] 读 flicker.json 失败(不阻断,横跳标注将缺失): {e}")
        flick = {}

    survivors = [c for c in ad.get("candidates", []) if c.get("verdict") == "survive"]
    rows = []
    for c in survivors:
        fam, key = c.get("family"), c.get("key")
        up, base, wlabel = _pick_window(c)
        dnote = _dnote(up, base)
        desc = _DESCRIPTORS.get((fam, key))
        if desc:
            active, state = desc["state"]()
            name = desc["name"]
        else:                                        # 未来新存活规律：不落下、不谎报应期、不猜方向组名
            active, state, name = None, "当前态未接入监测（仅历史·今日不判应期）", f"{fam}/{key}"
        rp = c.get("recent_p")
        # ── 不稳定的**两种**来源,缺一不可 ─────────────────────────────
        # (a) 现代显著性临界(Opus 审 2026-07-01):recent_p 贴近 q=0.10 存活线,下次刷新可能退出。
        near_line = isinstance(rp, (int, float)) and 0.08 < rp <= 0.10
        # (b) **跨族 FDR 边界横跳**(2026-09-04 补):裁决在 survive/dead 之间来回翻。
        #     实证:golden_cross_sp500 一周内 survive→dead(08-31~09-02)→survive(09-03),
        #     p 只在 0.001↔0.002 之间动,却因为卡在 BY-FDR 边界上而反复改判。
        #     此前 unstable 只看 (a),于是它在观察台上显示为**干净稳定的存活者**——
        #     一条 stable_days=1、翻转 2 次的规律,长得跟从没动摇过一样。这是诚实缺口。
        fc = flick.get(key) or {}
        flips = fc.get("flips")
        stable_days = fc.get("stable_days")
        flicker = bool(fc.get("boundary_flicker"))
        unstable = bool(near_line or flicker)

        notes = []
        if near_line:
            notes.append(f"⚠ 现代显著性临界（recent_p≈{rp:.2f}·近 q=0.10 存活线，下次刷新可能退出，别过度当真）")
        if flicker:
            bits = "".join([f"近期翻转 {flips} 次" if flips else "",
                            f"·当前裁决仅稳定 {stable_days} 天" if stable_days is not None else ""])
            notes.append(f"⚠ 裁决在跨族 FDR 存活线上**来回横跳**（{bits}）——"
                         "今天算存活不代表明天还在，别当成稳定结论")
        rows.append({
            "family": fam, "key": key, "name": name,
            "active": active, "state": state,
            "up_pct": up, "base_pct": base, "window": wlabel, "dnote": dnote,
            "edge_plain": _edge_plain(desc, up, base, wlabel, dnote),
            "recent_p": rp, "modern": c.get("modern_status"),
            "unstable": unstable,
            "flips": flips, "stable_days": stable_days, "boundary_flicker": flicker,
            "stability_note": "；".join(notes),
        })

    def _sortkey(x):                                 # 应期在前→休眠→未接入；同类按历史 |edge| 大的在前
        act = 0 if x["active"] is True else (1 if x["active"] is False else 2)
        mag = -abs((x["up_pct"] or 0) - (x["base_pct"] or 0))
        return (act, mag)

    rows.sort(key=_sortkey)
    n_active = sum(1 for x in rows if x["active"] is True)
    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": datetime.date.today().isoformat(),
        "n_survivors": len(rows), "n_active": n_active, "survivors": rows,
        "caveat": "存活规律 = 在预声明候选池里扛过多重检验(BY-FDR)且现代子样本仍显著的历史规律。"
                  "仅描述性、非预测非荐股；「应期」=今天该条件成立、「休眠」=今天不成立(休眠的别当当前信号)、"
                  "「未接入」=当前态未监测(仅历史)；前向 OOS(门4)仍在累积、未确认；扛过检验≠下次一定灵；过去≠未来。",
    }


def run(write=True):
    out = build()
    if out is None:
        return None
    if write:
        from util_io import write_json
        write_json("survivors_live.json", out)
        print(f"[OK] survivors_live.json — {out['n_survivors']} 条存活规律 · 今日应期 {out['n_active']} 条")
        for s in out["survivors"]:
            flag = "应期" if s["active"] is True else ("休眠" if s["active"] is False else "未接入")
            print(f"    [{flag}] {s['name']} · {s['state']}")
            print(f"           {s['edge_plain']}")
    return out


if __name__ == "__main__":
    run()
