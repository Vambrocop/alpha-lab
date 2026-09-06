"""test_survivors_live.py — 存活规律观察台单测。

不碰真数据/真 autodiscovery：合成价 CSV + 合成 autodiscovery.json，把"应期判定 / 方向标注(尤其负向) /
优雅降级 / 未接入新规律 / 诚实框 / 排序"每条路径跑出来断言。命门复用生产模块 survivors_live，不复制逻辑。
"""
import json
import types
import datetime

import numpy as np
import pandas as pd

import survivors_live as sl
import autodiscovery


# ════════════════════════════════════════════════════════════════════════════
# 1. 纯逻辑：方向标注 — 负向不能按族名想当然（回撤族 up<base 必须报偏负）
# ════════════════════════════════════════════════════════════════════════════
def test_dnote_directions():
    assert sl._dnote(75, 62) == "明显偏正"
    assert sl._dnote(66, 63) == "微弱偏正"
    assert sl._dnote(51, 54) == "微弱偏负"        # 反弹族 up<base → 偏负(反直觉,不能当利好)
    assert sl._dnote(45, 62) == "明显偏负"
    assert sl._dnote(52, 52) == "≈基率(几乎无差别)"
    assert sl._dnote(None, 62) == "方向不明"


def test_pick_window_prefers_2000_then_full():
    cand = {"windows": [{"label": "完整", "up_pct": 60, "base_pct": 58},
                        {"label": "2000后", "up_pct": 66, "base_pct": 63}]}
    assert sl._pick_window(cand) == (66, 63, "2000后")
    cand2 = {"windows": [{"label": "完整", "up_pct": 60, "base_pct": 58}]}
    assert sl._pick_window(cand2) == (60, 58, "完整")
    assert sl._pick_window({"windows": []}) == (None, None, None)


# ════════════════════════════════════════════════════════════════════════════
# 2. 当前态函数：合成价打进 tmp RAW
# ════════════════════════════════════════════════════════════════════════════
def _price(path, values, start="2000-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
    pd.Series(values, index=idx, name="close").to_csv(path, header=True)


def test_golden_cross_active_when_uptrend(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "SP500_long.csv", list(np.linspace(100, 300, 400)))
    active, state = sl._golden_cross_state()
    assert active is True and "金叉成立" in state


def test_golden_cross_inactive_when_downtrend(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "SP500_long.csv", list(np.linspace(300, 100, 400)))
    active, state = sl._golden_cross_state()
    assert active is False and "未成立" in state


def test_golden_cross_missing_data_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)          # 无 CSV
    active, state = sl._golden_cross_state()
    assert active is None and "不足" in state


def test_btc_mom_pos_active_and_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    vals = [100.0] * 40
    vals[-1] = 110.0                                  # last/[-21] = 110/100 = +10% > 5%
    _price(tmp_path / "BTC.csv", vals)
    active, state = sl._btc_mom_pos_state()
    assert active is True and "高于" in state


def test_btc_mom_pos_inactive_below_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "BTC.csv", [100.0] * 40)        # 0% 动量 < +5%
    active, state = sl._btc_mom_pos_state()
    assert active is False and "未高于" in state


def test_btc_mom_neg_active_on_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    vals = [100.0] * 40
    vals[-1] = 90.0                                   # last/[-21] = 90/100 = -10% < -5%
    _price(tmp_path / "BTC.csv", vals)
    active, state = sl._btc_mom_neg_state()
    assert active is True and "低于" in state


def test_nasdaq_ma200_active_when_above(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(np.linspace(100, 300, 400)))  # 上升→收盘>200MA
    active, state = sl._nasdaq_ma200_state()
    assert active is True and "高于" in state


def test_nasdaq_ma200_inactive_when_below(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(np.linspace(300, 100, 400)))  # 下降→收盘<200MA
    active, state = sl._nasdaq_ma200_state()
    assert active is False and "不高于" in state


def test_world_cup_active_in_noncup_summer(monkeypatch):
    _freeze_month(monkeypatch, 2025, 7, 1)            # 夏季且 2025 非杯年→触发组成立·应期
    active, state = sl._world_cup_state()
    assert active is True and "应期" in state


def test_world_cup_dormant_in_cup_year_summer(monkeypatch):
    _freeze_month(monkeypatch, 2026, 7, 1)            # 夏季但 2026 是杯年→触发组不成立·休眠(修复审#Important)
    active, state = sl._world_cup_state()
    assert active is False and "世界杯年" in state


def test_world_cup_dormant_in_winter(monkeypatch):
    _freeze_month(monkeypatch, 2025, 1, 15)           # 非夏季→休眠
    active, state = sl._world_cup_state()
    assert active is False and "非夏季" in state


def test_diff_family_rest_is_base_rate_not_complement(tmp_path, monkeypatch):
    """诚实守门(Opus 审#Critical)：factor/regime/rebound 走 _diff_windows，base=全样本基率(非补集)。
    rest 必须写「全样本基率」，绝不能写补集名(如"200线下方"/"未成立")——否则把全样本数字安到补集头上。"""
    web = tmp_path / "web"; web.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _price(tmp_path / "SP500_long.csv", list(np.linspace(100, 300, 400)))
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(np.linspace(100, 300, 400)))
    _autodisc(web, [
        {"family": "regime", "key": "golden_cross_sp500", "verdict": "survive",
         "windows": [{"label": "2000后", "up_pct": 66, "base_pct": 63}]},
        {"family": "factor", "key": "NASDAQ_above_ma200", "verdict": "survive",
         "windows": [{"label": "2000后", "up_pct": 66, "base_pct": 62}]},
    ])
    out = sl.build()
    for s in out["survivors"]:
        assert "全样本基率" in s["edge_plain"]          # base 挂到"全样本基率"
        assert "200 日线下方" not in s["edge_plain"]     # 绝不把全样本数字标成补集
        assert "未成立 63%" not in s["edge_plain"]


def test_rebound_active_on_crash_day(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    rets = np.tile([0.01, -0.01, 0.005, -0.005, 0.0], 220)   # 1100 天,5%分位≈-0.01
    px = 100 * np.cumprod(1 + rets)
    px = np.append(px, px[-1] * 0.90)                 # 末日 -10% → 必 ≤ 5%分位
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(px))
    active, state = sl._rebound_state()
    assert active is True and "跌进" in state


def test_rebound_inactive_on_calm_day(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "RAW", tmp_path)
    rets = np.tile([0.01, -0.01, 0.005, -0.005, 0.0], 220)
    px = 100 * np.cumprod(1 + rets)
    px = np.append(px, px[-1] * 1.02)                 # 末日 +2% → 高于 5%分位
    _price(tmp_path / "NASDAQ_COMP_long.csv", list(px))
    active, state = sl._rebound_state()
    assert active is False and "未跌进" in state


def _freeze_month(monkeypatch, y, m, d):
    class _D(datetime.date):
        @classmethod
        def today(cls):
            return datetime.date(y, m, d)
    monkeypatch.setattr(sl, "datetime",
                        types.SimpleNamespace(date=_D, datetime=datetime.datetime, timezone=datetime.timezone))


def test_september_active_only_in_september(monkeypatch):
    _freeze_month(monkeypatch, 2024, 9, 15)
    active, state = sl._september_state()
    assert active is True and "应期" in state


def test_september_dormant_other_months(monkeypatch):
    _freeze_month(monkeypatch, 2024, 7, 1)
    active, state = sl._september_state()
    assert active is False and "非 9 月" in state


# ── _cot_nq_extreme_short_state：COT 纳指仓位极空(2026-07-08 新增，全合成、不碰真 data/cot.csv)──
#   monkeypatch 打在 autodiscovery 模块本身(函数内部是 `import autodiscovery as ad` 后调 `ad._cot_reports`，
#   两个引用名指向 sys.modules 里同一个模块对象，打哪个名字都生效)。_POS_WINDOW/_rolling_pctrank 用真的。
def _cot_reports_df(n, start="2015-01-06", values=None, usable_overrides=None):
    """合成 COT 报告级数据：report_date 每 7 天一份(远早于真实"今天"→天然可用，除非显式覆盖)。"""
    dates = pd.date_range(start, periods=n, freq="7D")
    usable = list(dates + pd.Timedelta(days=6))
    if usable_overrides:
        for i, v in usable_overrides.items():
            usable[i] = v
    if values is None:
        values = np.random.default_rng(0).normal(0, 1, n)
    return pd.DataFrame({"report_date": dates, "usable_from": pd.to_datetime(usable), "value": values})


def test_cot_future_report_excluded_from_active_and_text(monkeypatch):
    """点时间命门(最重要)：最后一份报告 usable_from=明天(未来)且 value=全序列最小值
    (若被计入，末份窗口分位≈1/156*100<10 必判极空)——正确实现必须排除它：
    active 不受污染、state 文本里的"最新可用"报告日=倒数第二份，未来那份完全不出现在文案里。"""
    n = 200
    values = np.full(n, 50.0)                     # 常数序列：一旦正确排除未来份，末份分位=100(不极端)
    values[-1] = 0.0                               # 未来那份人为设成全序列最小(若计入必成极空)
    today = pd.Timestamp(datetime.date.today())
    tomorrow = today + pd.Timedelta(days=1)
    reports = _cot_reports_df(n, values=values, usable_overrides={n - 1: tomorrow})
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: reports)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is False                                          # 未被未来极空值污染
    assert str(reports["report_date"].iloc[-2].date()) in state     # 报告日=倒数第二份
    assert str(reports["report_date"].iloc[-1].date()) not in state  # 未来那份不出现在文案里


def test_cot_report_included_once_usable_from_is_yesterday(monkeypatch):
    """对照组：同一份报告(全序列最小值) usable_from 改成昨天(已公布)后必须被计入——
    证明上一条测试排除的是"点时间"而非其他原因(如巧合排序)。"""
    n = 200
    values = np.full(n, 50.0)
    values[-1] = 0.0
    today = pd.Timestamp(datetime.date.today())
    yesterday = today - pd.Timedelta(days=1)
    reports = _cot_reports_df(n, values=values, usable_overrides={n - 1: yesterday})
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: reports)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is True
    assert str(reports["report_date"].iloc[-1].date()) in state     # 报告日=最后一份(已计入)
    assert "极空档·应期" in state


def test_cot_extreme_short_active_when_at_3yr_low(monkeypatch):
    """极空判定：157 份可用报告，末份 value 为 156 窗口内最小 → 分位 ≤10 → active True + "应期"文案。"""
    n = 157
    rng = np.random.default_rng(0)
    values = rng.normal(0, 1, n)
    values[-1] = values.min() - 10.0               # 强制末份严格小于窗口(index1..156)内其余所有值
    reports = _cot_reports_df(n, values=values)
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: reports)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is True
    assert "极空档·应期" in state


def test_cot_extreme_short_inactive_at_median_level(monkeypatch):
    """极空判定对照：末份 value 落在窗口中位水平 → 分位≈50，远高于 10 → active False，文案不含"应期"。"""
    n = 157
    rng = np.random.default_rng(0)
    values = rng.normal(0, 1, n)
    values[-1] = np.median(values[1:156])           # 与 _rolling_pctrank 实际窗口(index1..156)对齐取中位
    reports = _cot_reports_df(n, values=values)
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: reports)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is False
    assert "未到 ≤10 极空档" in state
    assert "应期" not in state


def test_cot_insufficient_reports_returns_none(monkeypatch):
    """可用报告 <156 份(暖机中)→ (None, 含"不足"的说明)，不装极端判定。"""
    n = 100
    reports = _cot_reports_df(n)
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: reports)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is None
    assert "不足" in state


def test_cot_reports_none_returns_none_gracefully(monkeypatch):
    """`_cot_reports` 返回 None(如 data/cot.csv 缺失)→ 优雅降级，不崩。"""
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: None)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is None and "缺失" in state


def test_cot_reports_empty_returns_none_gracefully(monkeypatch):
    """`_cot_reports` 返回空 DataFrame → 优雅降级，不崩(len==0 与 None 同路径)。"""
    empty = pd.DataFrame({"report_date": pd.to_datetime([]), "usable_from": pd.to_datetime([]), "value": []})
    monkeypatch.setattr(autodiscovery, "_cot_reports", lambda market, series: empty)
    active, state = sl._cot_nq_extreme_short_state()
    assert active is None and "缺失" in state


# ════════════════════════════════════════════════════════════════════════════
# 3. build()：只取 verdict==survive、算应期、排序、未接入新规律、诚实框、优雅降级
# ════════════════════════════════════════════════════════════════════════════
def _autodisc(tmp_path, candidates):
    (tmp_path / "autodiscovery.json").write_text(
        json.dumps({"candidates": candidates}, ensure_ascii=False), encoding="utf-8")


def test_build_extracts_survivors_flags_sorts(tmp_path, monkeypatch):
    web = tmp_path / "web"; raw = tmp_path / "raw"
    web.mkdir(); raw.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", raw)
    _price(raw / "SP500_long.csv", list(np.linspace(100, 300, 400)))   # 金叉应期
    _freeze_month(monkeypatch, 2024, 7, 1)                             # 九月休眠
    _autodisc(web, [
        {"family": "regime", "key": "golden_cross_sp500", "verdict": "survive",
         "recent_p": 0.026, "modern_status": "现代仍有效",
         "windows": [{"label": "2000后", "up_pct": 66, "base_pct": 63}]},
        {"family": "calendar", "key": "september_sp500", "verdict": "survive",
         "recent_p": 0.03, "modern_status": "现代仍有效",
         "windows": [{"label": "2000后", "up_pct": 54, "base_pct": 51}]},
        {"family": "factor", "key": "some_dead_thing", "verdict": "dead",
         "windows": [{"label": "2000后", "up_pct": 50, "base_pct": 50}]},   # 非 survive → 排除
        {"family": "newfam", "key": "brand_new", "verdict": "survive",       # 未接入描述符
         "windows": [{"label": "完整", "up_pct": 70, "base_pct": 60}]},
    ])
    out = sl.build()
    assert out["n_survivors"] == 3                     # dead 被排除
    keys = [s["key"] for s in out["survivors"]]
    assert "some_dead_thing" not in keys
    # 金叉应期 True 排最前；未接入(None)排最后
    assert out["survivors"][0]["key"] == "golden_cross_sp500"
    assert out["survivors"][0]["active"] is True
    assert out["survivors"][-1]["key"] == "brand_new"
    assert out["survivors"][-1]["active"] is None
    assert "未接入" in out["survivors"][-1]["state"]
    assert out["n_active"] == 1
    # 九月休眠但仍在清单(常驻)
    sep = next(s for s in out["survivors"] if s["key"] == "september_sp500")
    assert sep["active"] is False
    # 未接入(brand_new)用中性口径,不猜组名
    bn = out["survivors"][-1]
    assert "触发组 70% vs 基率 60%" in bn["edge_plain"] and "组别待接入" in bn["edge_plain"]


def test_september_direction_not_backwards(tmp_path, monkeypatch):
    """诚实守门(审#1修复)：september label==1=非九月 → up(54)必挂到'非九月'、base(51)挂到'九月'，
    绝不能写成'九月 54%'(那是把非九月的数字安到九月头上·九月实为最弱月)。"""
    web = tmp_path / "web"; web.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _freeze_month(monkeypatch, 2024, 7, 1)
    _autodisc(web, [
        {"family": "calendar", "key": "september_sp500", "verdict": "survive",
         "windows": [{"label": "2000后", "up_pct": 54, "base_pct": 51}]},          # up=非九月, base=九月
        {"family": "calendar", "key": "monthof_9_sp500", "verdict": "survive",
         "windows": [{"label": "2000后", "up_pct": 51, "base_pct": 54}]},          # up=九月, base=其余
    ])
    out = sl.build()
    sep = next(s for s in out["survivors"] if s["key"] == "september_sp500")
    m9 = next(s for s in out["survivors"] if s["key"] == "monthof_9_sp500")
    # september: 触发组=非九月(54)、对照=九月(51)——54 挂"非九月"、51 挂"九月"(正向断言即锁死方向)
    assert "非九月 54%" in sep["edge_plain"] and "九月 51%" in sep["edge_plain"]
    assert "九月 54% vs 非九月 51%" not in sep["edge_plain"]  # 反向 bug 的整段红旗
    # monthof_9: 触发组=九月(51)、对照=其余月份(54)——两口径都指向"九月≈51% 偏弱"
    assert "九月 51%" in m9["edge_plain"] and "其余月份 54%" in m9["edge_plain"]
    assert m9["dnote"] == "微弱偏负"                         # 九月组 vs 其余 → 偏负


def test_build_caveat_has_honest_frame(tmp_path, monkeypatch):
    web = tmp_path / "web"; web.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", tmp_path)
    _autodisc(web, [])
    out = sl.build()
    cav = out["caveat"]
    assert "非预测" in cav and ("OOS" in cav or "未确认" in cav) and "过去≠未来" in cav


def test_build_missing_autodiscovery_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "WEB", tmp_path)           # 空目录,无 autodiscovery.json
    assert sl.build() is None


# ════════════════════════════════════════════════════════════════════════════
# 4. 裁决横跳标注（2026-09-06 补）
#    观察台此前只按 recent_p 贴近 q=0.10 判"不稳",不看**跨族 FDR 边界横跳**。
#    实证:golden_cross_sp500 一周内 survive→dead(08-31~09-02)→survive(09-03),
#    p 只在 0.001↔0.002 之间动,却因卡在 BY-FDR 边界上反复改判——而它在观察台上
#    显示为干净稳定的存活者。6 条存活者里有 4 条这样(世界杯年翻转 18 次)。
# ════════════════════════════════════════════════════════════════════════════
def _flicker(web, rows):
    (web / "flicker.json").write_text(
        json.dumps({"candidates": rows}, ensure_ascii=False), encoding="utf-8")


def _one_survivor_web(tmp_path, monkeypatch, recent_p=0.01):
    web = tmp_path / "web"; raw = tmp_path / "raw"
    web.mkdir(); raw.mkdir()
    monkeypatch.setattr(sl, "WEB", web)
    monkeypatch.setattr(sl, "RAW", raw)
    _price(raw / "SP500_long.csv", list(np.linspace(100, 300, 400)))
    _autodisc(web, [{"family": "regime", "key": "golden_cross_sp500", "verdict": "survive",
                     "recent_p": recent_p, "modern_status": "现代仍有效",
                     "windows": [{"label": "2000后", "up_pct": 66, "base_pct": 63}]}])
    return web


def test_boundary_flicker_marks_unstable_even_when_recent_p_is_comfortable(tmp_path, monkeypatch):
    """核心:recent_p 离存活线很远(0.01)、但裁决在横跳 → 仍必须标不稳。

    这正是金叉的形状:现代显著性看着很稳,可跨族 FDR 边界一动它就改判。
    只看 recent_p 会把它显示成"干净的存活者"。
    """
    web = _one_survivor_web(tmp_path, monkeypatch, recent_p=0.01)
    _flicker(web, [{"key": "golden_cross_sp500", "boundary_flicker": True,
                    "flips": 2, "stable_days": 1}])
    row = sl.build()["survivors"][0]
    assert row["unstable"] is True, "横跳未被标成不稳"
    assert "横跳" in row["stability_note"]
    assert "2 次" in row["stability_note"] and "1 天" in row["stability_note"], \
        "翻转次数/稳定天数必须如实写进提示,不能只说'不稳'"
    assert row["flips"] == 2 and row["stable_days"] == 1 and row["boundary_flicker"] is True


def test_stable_survivor_gets_no_warning(tmp_path, monkeypatch):
    """真稳的(0 翻转、稳 42 天)不许被误标 —— 警告滥发等于没有警告。"""
    web = _one_survivor_web(tmp_path, monkeypatch, recent_p=0.01)
    _flicker(web, [{"key": "golden_cross_sp500", "boundary_flicker": False,
                    "flips": 0, "stable_days": 42}])
    row = sl.build()["survivors"][0]
    assert row["unstable"] is False and row["stability_note"] == ""


def test_both_instability_reasons_are_reported_together(tmp_path, monkeypatch):
    """两种不稳可以同时成立,提示不能只出一条(世界杯年就是两条都占)。"""
    web = _one_survivor_web(tmp_path, monkeypatch, recent_p=0.095)
    _flicker(web, [{"key": "golden_cross_sp500", "boundary_flicker": True,
                    "flips": 18, "stable_days": 1}])
    note = sl.build()["survivors"][0]["stability_note"]
    assert "现代显著性临界" in note and "横跳" in note, f"两条理由应并列,实得: {note}"


def test_missing_flicker_json_degrades_gracefully(tmp_path, monkeypatch):
    """flicker.json 缺失(首次运行/上游失败)→ 不崩、不谎报稳定,只是没有横跳标注。"""
    web = _one_survivor_web(tmp_path, monkeypatch, recent_p=0.01)   # 不写 flicker.json
    out = sl.build()
    assert out is not None and out["survivors"], "缺 flicker.json 不该让整个观察台挂掉"
    row = out["survivors"][0]
    assert row["boundary_flicker"] is False and row["flips"] is None


def test_flicker_runs_before_survivors_live_in_pipeline():
    """顺序守门:flicker.py 必须排在 survivors_live.py **之前**。

    survivors_live 要读 flicker.json 才能给存活者标"裁决横跳"。若 flicker 排在后面,
    读到的是**上一轮**的陈旧数据 —— 今天刚发生的改判要等到明天才会显示为不稳,
    而"今天算存活明天就不算"恰恰是这条警告要防的事。2026-09-06 前移并加此守门。
    """
    from pathlib import Path
    import re
    src = (Path(__file__).resolve().parents[1] / "scripts" / "run_all.py").read_text(encoding="utf-8")
    fi = src.find('"flicker.py"')
    si = src.find('"survivors_live.py"')
    assert fi > 0 and si > 0, "run_all.py 里找不到这两步,写法变了先修这里"
    assert fi < si, (
        "flicker.py 跑在 survivors_live.py 之后了 → 观察台会读到上一轮的陈旧横跳数据")
