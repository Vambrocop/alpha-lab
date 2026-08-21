"""
verify_output.py — 发布前自检（CI 质量门）

任何检查失败都以非零码退出 → run_all 终止 → GitHub Actions 不会把坏数据推上线。
"""
import json
import sys
import datetime
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from ledger_hash import verify_hash_chain

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WEB_DIR  = Path(__file__).parent.parent / "web"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
US_TODAY = datetime.datetime.now(ZoneInfo("America/New_York")).date()
errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)
        print(f"  ✗ {msg}")
    else:
        print(f"  ✓ {msg}")


# 0. web/ ↔ docs/ 镜像同步守卫（手动编辑 web/ 后忘记镜像时拦住发布）
#    run_all 末步会自动镜像，所以全量流水线下此检查恒过；价值在抓"手改 web/ 未同步"的情况。
#    docs/ 不存在时静默跳过（部分 CI 环境可能没 checkout docs/）。
try:
    import importlib.util as _ilu
    _mirror_spec = _ilu.spec_from_file_location(
        "check_docs_mirror",
        Path(__file__).parent / "check_docs_mirror.py",
    )
    _mirror_mod = _ilu.module_from_spec(_mirror_spec)
    _mirror_spec.loader.exec_module(_mirror_mod)
    _mirror_problems = _mirror_mod.run()
    check(not _mirror_problems,
          f"web/↔docs/ 镜像同步（漂移文件：{_mirror_problems or '无'}）")
except Exception as _e:
    print(f"  · web/↔docs/ 镜像同步检查跳过（{_e}）")


# 1. 前端要拉取的文件都必须存在且非空
for f in ["index.html", "dashboard.html", "app-1.js", "app-2.js", "app-3.js", "app-4.js",
          "app-5.js", "style.css", "signals.json", "prices.json",
          "charts_extra.json", "long_history.json", "stocks.json",
          "overnight.json", "news.json", "signals_history.json",
          "plotly-cartesian-2.35.2.min.js"]:
    p = WEB_DIR / f
    check(p.exists() and p.stat().st_size > 100, f"{f} 存在且非空")

# 首屏体积守门：signals.json 发布版只含近两年（P1-3），别让它再胖回去
check((WEB_DIR / "signals.json").stat().st_size < 800_000,
      f"signals.json < 800KB（当前 {(WEB_DIR / 'signals.json').stat().st_size//1024}KB）")

# 1b. 拆分后的前端脚本语法守门：每个 app-*.js 过 node --check
#     （app.js 拆成 5 个有序经典脚本后，一处语法错会整站白屏 → 上线前拦住）
import shutil, subprocess
_node = shutil.which("node")
if _node:
    for jf in sorted(WEB_DIR.glob("app-*.js")):
        r = subprocess.run([_node, "--check", str(jf)],
                           capture_output=True, text=True)
        check(r.returncode == 0,
              f"{jf.name} 语法合法" + ("" if r.returncode == 0
                                      else f"（{r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'parse error'}）"))
else:
    print("  · 跳过 app-*.js 语法检查（环境无 node）")

# 1c. 全部 web JSON 必须是"浏览器级"严格 JSON。
#     注意：Python json.load 默认放行 NaN/Infinity（它们是非法 JSON），
#     而浏览器 JSON.parse 会拒绝整个文件——曾导致 charts_extra.json 5 张图全空。
def _reject_const(c):
    raise ValueError(f"非法 JSON 常量 {c}（浏览器无法解析）")

for jf in sorted(WEB_DIR.glob("*.json")):
    try:
        with open(jf, encoding="utf-8") as fh:
            json.load(fh, parse_constant=_reject_const)
        check(True, f"{jf.name} 严格 JSON")
    except Exception as e:
        check(False, f"{jf.name} 严格 JSON —— {e}")

# 2. signals.json 严格合法 + 结构完整 + 无周末数据 + 不过期
try:
    with open(WEB_DIR / "signals.json", encoding="utf-8") as fh:
        sig = json.load(fh)   # 注：NaN 检查由上方 1c 节统一负责（json.load 默认放行 NaN）
    for key in ["daily_signals", "daily_signals_sp500", "indices",
                "next_opportunities", "macro_calendar", "model_version"]:
        check(key in sig, f"signals.json 含 {key}")
    weekends = [k for k in sig["daily_signals"]
                if datetime.date.fromisoformat(k).weekday() >= 5]
    check(not weekends, f"无周末污染数据（发现 {len(weekends)} 条）")
    gen = datetime.date.fromisoformat(sig["generated"])
    age = (US_TODAY - gen).days
    check(age <= 4, f"数据新鲜（generated={sig['generated']}，美东{age}天前）")
    last = max(sig["daily_signals"])
    check((US_TODAY - datetime.date.fromisoformat(last)).days <= 6,
          f"信号覆盖到近期（最新 {last}）")
    check(len(sig.get("macro_calendar", [])) > 0,
          "宏观日历非空（空了说明 MACRO_EVENTS 需要补来年日程）")
    vol = list(sig["daily_signals"].values())[-1].get("nasdaq_vol", 0)
    vol_ok = (isinstance(vol, (int, float)) and not isinstance(vol, bool)
              and math.isfinite(vol) and 0 <= vol < 1.5)
    check(vol_ok, f"波动率量纲正常（{vol}，应为有限年化小数）")
except Exception as e:
    errors.append(f"signals.json 解析失败: {e}")
    print(f"  ✗ signals.json 解析失败: {e}")

# 3. 其余 JSON 全部严格合法
for f in ["prices.json", "charts_extra.json", "stocks.json",
          "overnight.json", "news.json", "long_history.json",
          "signals_history.json"]:
    try:
        with open(WEB_DIR / f, encoding="utf-8") as fh:
            json.load(fh)
        print(f"  ✓ {f} 合法 JSON")
    except Exception as e:
        errors.append(f"{f} 非法: {e}")
        print(f"  ✗ {f} 非法: {e}")

# 3b. 关键数据列完整性（yfinance 部分失败会静默掉列 → 残缺站点）
try:
    import pandas as pd
    cp = pd.read_csv(PROC_DIR.parent / "raw" / "combined_prices.csv",
                     index_col="Date", parse_dates=True)
    KEY_COLS = ["NASDAQ", "SP500", "VIX", "VIX3M", "BTC", "DXY", "HY_SPREAD"]
    missing_cols = [c for c in KEY_COLS if c not in cp.columns]
    check(not missing_cols, f"关键列齐全（缺失：{missing_cols or '无'}）")
    if not missing_cols:
        stale = [c for c in KEY_COLS if cp[c].dropna().empty
                 or (US_TODAY - cp[c].dropna().index[-1].date()).days > 6]
        check(not stale, f"关键列近期有值（疑似过期/全空：{stale or '无'}）")
except Exception as e:
    errors.append(f"列完整性检查失败: {e}")
    print(f"  ✗ 列完整性检查失败: {e}")

# 3c. 保形预测产物形状（方法E：每期限有区间且 lower<upper；存在才查，缺失不致命）
try:
    cf_path = WEB_DIR / "conformal.json"
    if cf_path.exists():
        with open(cf_path, encoding="utf-8") as fh:
            cf = json.load(fh)
        hs = cf.get("horizons", [])
        bad = [h.get("horizon_days") for h in hs for b in h.get("bands", [])
               if b.get("lower_pct") is None or b["lower_pct"] >= b["upper_pct"]]
        check(len(hs) > 0 and not bad, f"conformal.json 形状正常（坏区间：{bad or '无'}）")
except Exception as e:
    errors.append(f"conformal 形状检查失败: {e}")
    print(f"  ✗ conformal 形状检查失败: {e}")

# 3d. 周期检验产物形状（方法F：status ok 时 p_global 合法、具名周期齐全；存在才查，缺失不致命）
try:
    cy_path = WEB_DIR / "cycles.json"
    if cy_path.exists():
        with open(cy_path, encoding="utf-8") as fh:
            cy = json.load(fh)
        res = cy.get("result", {})
        if res.get("status") == "ok":
            p = res.get("p_global")
            ok_p = isinstance(p, (int, float)) and 0.0 <= p <= 1.0
            nnamed = len(res.get("named_cycles", []))
            check(ok_p and nnamed >= 1,
                  f"cycles.json 形状正常（p_global={p}，具名周期 {nnamed} 条）")
except Exception as e:
    errors.append(f"cycles 形状检查失败: {e}")
    print(f"  ✗ cycles 形状检查失败: {e}")

# 3e. 跨检验族 FDR 形状（#5：BY 存活 ≤ BH 存活 是头条不变式；claims 非空。存在才查，缺失不致命）
try:
    fx_path = WEB_DIR / "fdr_crossfamily.json"
    if fx_path.exists():
        with open(fx_path, encoding="utf-8") as fh:
            fx = json.load(fh)
        by10, bh10 = fx.get("n_survive_by_10"), fx.get("n_survive_bh_10")
        ok = (isinstance(by10, int) and isinstance(bh10, int) and by10 <= bh10
              and len(fx.get("claims", [])) >= 1)
        check(ok, f"fdr_crossfamily.json 形状正常（BY {by10} ≤ BH {bh10}，{len(fx.get('claims', []))} 项）")
        # 3e-2. 诚实纪律：每条 claim 必须带 p 值 + 至少一个 survive_* 标志（不得只亮结论不带统计支撑）
        claims = fx.get("claims", [])
        missing_p = [c.get("label") for c in claims if "p" not in c]
        missing_sv = [c.get("label") for c in claims
                      if not any(k.startswith("survive_") for k in c)]
        check(not missing_p, f"fdr_crossfamily claims 均带 p 值（缺失：{missing_p or '无'}）")
        check(not missing_sv, f"fdr_crossfamily claims 均带 survive_* 标志（缺失：{missing_sv or '无'}）")
except Exception as e:
    errors.append(f"fdr_crossfamily 形状检查失败: {e}")
    print(f"  ✗ fdr_crossfamily 形状检查失败: {e}")

# 3f. 新闻 curated 条目须遵守自动下架（防"停在旧日期"回归 → CI 自动抓，不靠人工发现）
try:
    nj = WEB_DIR / "news.json"
    if nj.exists():
        with open(nj, encoding="utf-8") as fh:
            nd = json.load(fh)
        stale_cur = []
        for it in nd.get("items", []):
            if it.get("kind", "curated") == "curated":
                ds = (it.get("time") or "")[:10]
                try:
                    if (US_TODAY - datetime.date.fromisoformat(ds)).days > 3:
                        stale_cur.append(ds)
                except Exception:
                    pass
        check(not stale_cur, f"新闻无滞留的旧 curated 条目（发现 {stale_cur or '无'}）")
except Exception as e:
    errors.append(f"新闻 curated 新鲜度检查失败: {e}")
    print(f"  ✗ 新闻 curated 新鲜度检查失败: {e}")

# 3g. CPCV 过拟合概率 PBO 形状（方法G：pbo∈[0,1]、n_combos>0。存在才查，缺失不致命）
try:
    cv_path = WEB_DIR / "cpcv.json"
    if cv_path.exists():
        with open(cv_path, encoding="utf-8") as fh:
            cv = json.load(fh)
        r = cv.get("result", {})
        pbo_v = r.get("pbo")
        ok = (isinstance(pbo_v, (int, float)) and 0.0 <= pbo_v <= 1.0
              and int(r.get("n_combos", 0)) > 0)
        check(ok, f"cpcv.json 形状正常（PBO={pbo_v}，n_combos={r.get('n_combos')}）")
except Exception as e:
    errors.append(f"cpcv 形状检查失败: {e}")
    print(f"  ✗ cpcv 形状检查失败: {e}")

# 3h. 校准漂移形状（#3：嵌在 signals.json；verdict 合法、每折 gap 有界。存在才查，缺失不致命）
try:
    with open(WEB_DIR / "signals.json", encoding="utf-8") as fh:
        _sig = json.load(fh)
    cd = _sig.get("calibration_drift")
    if cd and cd.get("status") == "ok":
        ok = (cd.get("verdict") in {"stable", "drifting", "inconclusive"}
              and isinstance(cd.get("folds"), list) and len(cd["folds"]) >= 2
              and all(abs(f.get("gap", 9)) <= 1.0 for f in cd["folds"]))
        check(ok, f"signals.json calibration_drift 形状正常（{cd.get('verdict')}，{cd.get('n_folds')} 折）")
except Exception as e:
    errors.append(f"calibration_drift 形状检查失败: {e}")
    print(f"  ✗ calibration_drift 形状检查失败: {e}")

# 3i. 个股诚实体检形状（块0：tickers 非空、ok 票 vol 有界且回撤≤0。存在才查、缺失不致命）
try:
    sc_path = WEB_DIR / "stock_checkup.json"
    if sc_path.exists():
        with open(sc_path, encoding="utf-8") as fh:
            sc = json.load(fh)
        tks = sc.get("tickers", {})
        oks = [v for v in tks.values() if v.get("status") == "ok"]
        ok = (len(tks) > 0 and all(
            0 < v.get("ann_vol_pct", 0) < 500 and v.get("max_drawdown_pct", 1) <= 0 for v in oks))
        check(ok, f"stock_checkup.json 形状正常（{len(tks)} 票，{len(oks)} 个 ok）")
except Exception as e:
    errors.append(f"stock_checkup 形状检查失败: {e}")
    print(f"  ✗ stock_checkup 形状检查失败: {e}")

# 3i-2. 数据源健康形状（实时/缓存/过期透明度；存在才查，缺失不致命）
try:
    dh_path = WEB_DIR / "data_health.json"
    if dh_path.exists():
        with open(dh_path, encoding="utf-8") as fh:
            dh = json.load(fh)
        sm = dh.get("summary", {})
        src = dh.get("sources", {})
        ok = (isinstance(src, dict) and len(src) >= 20
              and sm.get("total") == len(src)
              and sm.get("freshness") in {"ok", "degraded", "incomplete"})
        check(ok, f"data_health.json 形状正常（{len(src)} 源，freshness={sm.get('freshness')}）")
except Exception as e:
    errors.append(f"data_health 形状检查失败: {e}")
    print(f"  ✗ data_health 形状检查失败: {e}")

# 3i-3. IPO 近期申报形状（SEC EDGAR：两档均为列表、行带 company/cik、日期倒序。存在才查、缺失不致命）
try:
    ipo_path = WEB_DIR / "ipo_filings.json"
    if ipo_path.exists():
        with open(ipo_path, encoding="utf-8") as fh:
            ipo = json.load(fh)
        filed = ipo.get("filed", [])
        priced = ipo.get("priced", [])
        rows = filed + priced
        shape_ok = (
            isinstance(filed, list) and isinstance(priced, list)
            and ipo.get("n_filed") == len(filed) and ipo.get("n_priced") == len(priced)
            and len(rows) > 0
            and all(r.get("company") and r.get("cik") for r in rows)
        )
        # 每档内部按 filed 日期倒序（新→旧）——防脚本改动打乱排序
        def _desc(lst):
            ds = [r.get("filed") or "" for r in lst]
            return ds == sorted(ds, reverse=True)
        order_ok = _desc(filed) and _desc(priced)
        check(shape_ok and order_ok,
              f"ipo_filings.json 形状正常（S-1 {len(filed)} / 424B {len(priced)}，倒序={order_ok}）")
except Exception as e:
    errors.append(f"ipo_filings 形状检查失败: {e}")
    print(f"  ✗ ipo_filings 形状检查失败: {e}")

# 3l. R3 短期反转形状(full 有 p_value/diff_pct、verdict 合法。存在才查、缺失不致命)
try:
    ov_path = WEB_DIR / "overreaction.json"
    if ov_path.exists():
        with open(ov_path, encoding="utf-8") as fh:
            ov = json.load(fh)
        if ov.get("status") == "ok":
            f = ov.get("full", {})
            ok = ("p_value" in f and "diff_pct" in f
                  and ov.get("verdict") in {"real", "faded", "real_recent_untested", "rejected", "inconclusive"})
            check(ok, f"overreaction.json 形状正常（verdict={ov.get('verdict')}）")
            # 3l-2. 诚实纪律：方向性结论须带现代段 p 值（recent.p_value）——判断不能只看全样本
            rec = ov.get("recent", {})
            rp = rec.get("p_value")
            check(isinstance(rp, (int, float)) and 0.0 <= rp <= 1.0,
                  f"overreaction.json recent.p_value 存在且合法（值={rp}）")
except Exception as e:
    errors.append(f"overreaction 形状检查失败: {e}")
    print(f"  ✗ overreaction 形状检查失败: {e}")

# 3l2. 自生长 autodiscovery 形状(候选数==FDR分母、每条带 p/verdict、summary 全。存在才查、缺失不致命)
#       核心不变量=分母完整(len==n_declared)，与 quality_gate 自身断言一致，防"偷删候选/漏算分母"流到发布。
try:
    ad_path = WEB_DIR / "autodiscovery.json"
    if ad_path.exists():
        with open(ad_path, encoding="utf-8") as fh:
            adj = json.load(fh)
        cands = adj.get("candidates", [])
        ok = (len(cands) == adj.get("n_declared") and len(cands) >= 37
              and isinstance(adj.get("summary"), dict)
              and all(("p" in c and "verdict" in c) for c in cands))
        check(ok, f"autodiscovery.json 形状正常（{len(cands)} 候选=分母）")
        # 新鲜度软提示(非致命:周末/盘中 light 本就可能旧;仅异常陈旧时提醒盘后步骤是否在跑)
        try:
            import datetime as _dt
            _gen = _dt.datetime.strptime(adj["generated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
            _age = (_dt.datetime.now(_dt.timezone.utc) - _gen).days
            if _age > 5:
                print(f"  ⚠ autodiscovery.json 已 {_age} 天未刷新（盘后全量步骤是否在跑？非致命）")
        except Exception:
            pass
except Exception as e:
    errors.append(f"autodiscovery 形状检查失败: {e}")
    print(f"  ✗ autodiscovery 形状检查失败: {e}")

# 3l3b. 自生长 P-A 地基:候选注册登记簿必须覆盖全部候选(每候选都有 OOS 锚)。存在才查、缺失不致命。
#        诚实纪律:门4 OOS 要求每候选都有不可改的 declared_date 锚;漏锚=有候选能逃 OOS 检验。
try:
    import csv as _csv
    reg_path = WEB_DIR.parent / "data" / "candidate_registry.csv"
    if reg_path.exists():
        import candidate_space as _cs
        with open(reg_path, encoding="utf-8") as fh:
            reg_rows = list(_csv.DictReader(fh))
        reg_ids = {r["candidate_id"] for r in reg_rows}
        space_ids = {c["candidate_id"] for c in _cs.enumerate_candidates()}
        missing = space_ids - reg_ids
        check(not missing, f"candidate_registry 覆盖全部候选（未登记：{sorted(missing) or '无'}）")
        check(all(r.get("declared_date") for r in reg_rows),
              "candidate_registry 每行都有 declared_date（OOS 锚不空）")
except Exception as e:
    errors.append(f"candidate_registry 检查失败: {e}")
    print(f"  ✗ candidate_registry 检查失败: {e}")

# 3l3c. 自生长 P-C:知识库账本 kb_ledger 完整性(append-only·动作合法·每行候选都已注册)。存在才查、缺失不致命。
#        诚实纪律:晋升/降级是公开知识库的"进出库"账本,只能 promote/demote、只认注册过的候选(锚=declared_date)。
try:
    import csv as _csv
    kb_path = WEB_DIR.parent / "data" / "kb_ledger.csv"
    if kb_path.exists():
        import candidate_space as _cs
        with open(kb_path, encoding="utf-8") as fh:
            kb_rows = list(_csv.DictReader(fh))
        space_ids = {c["candidate_id"] for c in _cs.enumerate_candidates()}
        bad_action = [r for r in kb_rows if r.get("action") not in ("promote", "demote")]
        unreg = {r["candidate_id"] for r in kb_rows} - space_ids
        check(not bad_action, f"kb_ledger 动作仅 promote/demote（异常 {len(bad_action)} 行）")
        check(not unreg, f"kb_ledger 每行候选都在候选空间（未知：{sorted(unreg) or '无'}）")
        check(all(r.get("anchor_date") and r.get("date") for r in kb_rows),
              "kb_ledger 每行都有 date + anchor_date（可审计 OOS 锚）")
except Exception as e:
    errors.append(f"kb_ledger 检查失败: {e}")
    print(f"  ✗ kb_ledger 检查失败: {e}")

# 3l3d. 自生长 P-D:知识库前端数据 knowledge_base.json 形状(顶层键全·summary 全·caveat 诚实框)。存在才查、缺失不致命。
#        诚实纪律:展示"样本外确认/晋升"的页面必须带"未到可判=数据不够、非荐股"的认账口径(同 insider/picks)。
try:
    kbj_path = WEB_DIR / "knowledge_base.json"
    if kbj_path.exists():
        with open(kbj_path, encoding="utf-8") as fh:
            kbj = json.load(fh)
        s = kbj.get("summary", {})
        ok = (isinstance(s, dict)
              and all(k in s for k in ("in_kb", "queue", "confirmed", "overturned", "pending"))
              and all(k in kbj for k in ("members", "queue", "history", "anchor_common"))
              and isinstance(kbj.get("queue"), list))
        check(ok, f"knowledge_base.json 形状正常（在库 {s.get('in_kb')}·排队 {s.get('queue')}·已盯 {kbj.get('days_since_anchor')} 天）")
        cav = kbj.get("caveat", "")
        check("未到可判" in cav and "非荐股" in cav,
              "knowledge_base.json caveat 含未到可判+非荐股诚实框")
except Exception as e:
    errors.append(f"knowledge_base.json 形状检查失败: {e}")
    print(f"  ✗ knowledge_base.json 形状检查失败: {e}")

# 3l3e. 自生长 P-B:防闪烁 flicker.json(顶层键全·诚实框=自相关≠独立确认)。存在才查、缺失不致命。
#        诚实纪律:稳定度页绝不能让"裁决稳定 N 天"被当成 N 次独立确认——必须明写自相关、指向门4 OOS。
try:
    fk_path = WEB_DIR / "flicker.json"
    if fk_path.exists():
        with open(fk_path, encoding="utf-8") as fh:
            fk = json.load(fh)
        ok = (all(k in fk for k in ("n_snapshots", "summary", "candidates", "caveat"))
              and isinstance(fk.get("candidates"), list))
        check(ok, f"flicker.json 形状正常（快照 {fk.get('n_snapshots')}·边界闪烁 {fk.get('summary', {}).get('n_boundary_flicker')}）")
        cav = fk.get("caveat", "")
        check(("自相关" in cav or "独立确认" in cav) and "非荐股" in cav,
              "flicker.json caveat 含'自相关≠独立确认'+非荐股诚实框")
except Exception as e:
    errors.append(f"flicker.json 形状检查失败: {e}")
    print(f"  ✗ flicker.json 形状检查失败: {e}")

# 3l3f. 预FOMC漂移研究 fomc_study.json(顶层键全·诚实框=探索性+未经FDR+非荐股)。存在才查、缺失不致命。
#        诚实纪律:出格事件研究必须标"探索性·未入FDR池·非荐股"，且 verdict 不许把不显著说成显著。
try:
    fm_path = WEB_DIR / "fomc_study.json"
    if fm_path.exists():
        with open(fm_path, encoding="utf-8") as fh:
            fm = json.load(fh)
        ok = (all(k in fm for k in ("overall", "decades", "verdict", "caveat"))
              and isinstance(fm.get("decades"), list)
              and isinstance(fm.get("overall"), dict))
        check(ok, f"fomc_study.json 形状正常（n={fm.get('n_fomc_days')}·{len(fm.get('decades', []))} 个十年）")
        cav = fm.get("caveat", "")
        check("非荐股" in cav and "FDR" in cav,
              "fomc_study.json caveat 含探索性+未经FDR+非荐股诚实框")
except Exception as e:
    errors.append(f"fomc_study.json 形状检查失败: {e}")
    print(f"  ✗ fomc_study.json 形状检查失败: {e}")

# 3l3g. 存活规律观察台 survivors_live.json(顶层键全·每条 active 三态·诚实框=描述性+前向OOS未确认+非预测)。存在才查、缺失不致命。
#        诚实纪律:「休眠」的存活规律绝不能被当成当前信号；面板/日读只有「应期」才算今天成立；扛过检验≠下次必灵。
try:
    sl_path = WEB_DIR / "survivors_live.json"
    if sl_path.exists():
        with open(sl_path, encoding="utf-8") as fh:
            sl = json.load(fh)
        rows = sl.get("survivors")
        ok = (all(k in sl for k in ("n_survivors", "n_active", "survivors", "caveat"))
              and isinstance(rows, list)
              and all(("active" in r and "name" in r and "edge_plain" in r) for r in rows)
              and all(r.get("active") in (True, False, None) for r in rows))
        check(ok, f"survivors_live.json 形状正常（存活 {sl.get('n_survivors')}·今日应期 {sl.get('n_active')}）")
        cav = sl.get("caveat", "")
        check("非预测" in cav and ("OOS" in cav or "未确认" in cav) and "过去≠未来" in cav,
              "survivors_live.json caveat 含描述性+前向OOS未确认+过去≠未来诚实框")
except Exception as e:
    errors.append(f"survivors_live.json 形状检查失败: {e}")
    print(f"  ✗ survivors_live.json 形状检查失败: {e}")

# 3l4. 内部人买入前向计分形状(track_record 全/recent 是表/benchmark=SPY。存在才查、缺失不致命)
#       诚实纪律：聪明钱前向计分页必须带"非荐股 + 前向计分"免责框（敢预测就敢认账=护城河，
#       同 overreaction 强制 recent.p_value 的逻辑：方向性/跟单性产物不许丢掉认账口径）。
try:
    ins_path = WEB_DIR / "insider_signal.json"
    if ins_path.exists():
        with open(ins_path, encoding="utf-8") as fh:
            ins = json.load(fh)
        tr = ins.get("track_record", {})
        ok = (isinstance(tr, dict)
              and all(k in tr for k in ("n_settled", "n_pending", "n_dropped", "beat_spy_pct"))
              and isinstance(ins.get("recent"), list)
              and ins.get("benchmark") == "SPY")
        check(ok, f"insider_signal.json 形状正常（已结算 {tr.get('n_settled')}·挂账 {tr.get('n_pending')}）")
        cav = ins.get("caveat", "")
        check("非荐股" in cav and "前向计分" in cav,
              "insider_signal.json caveat 含非荐股+前向计分诚实框")
except Exception as e:
    errors.append(f"insider_signal 形状检查失败: {e}")
    print(f"  ✗ insider_signal 形状检查失败: {e}")

# 3l5. 荐股前向计分形状(track_record 全/recent 是表/benchmark=QQQ。存在才查、缺失不致命)
#       诚实纪律:直接荐股的产物必须带"非投资建议 + 前向计分"认账框(敢荐就敢认账=护城河)。
try:
    pk_path = WEB_DIR / "picks.json"
    if pk_path.exists():
        with open(pk_path, encoding="utf-8") as fh:
            pk = json.load(fh)
        tr = pk.get("track_record", {})
        ok = (isinstance(tr, dict)
              and all(k in tr for k in ("n_settled", "n_pending", "call_hit_pct", "bullish", "bearish"))
              and isinstance(pk.get("recent"), list)
              and pk.get("benchmark") == "QQQ")
        check(ok, f"picks.json 形状正常（已结算 {tr.get('n_settled')}·挂账 {tr.get('n_pending')}）")
        cav = pk.get("caveat", "")
        check("非投资建议" in cav and "前向计分" in cav,
              "picks.json caveat 含非投资建议+前向计分认账框")
except Exception as e:
    errors.append(f"picks 形状检查失败: {e}")
    print(f"  ✗ picks 形状检查失败: {e}")

# 3l5b. 观点/预测 outlook.json 免责门(P1-7:disclaimer 非空且含"非投资建议"关键词。
#        存在才查、缺失不致命)
#        诚实纪律:outlook 是用户明确授权的"出格"荐方向区,越出全站"不预测方向"红线的
#        唯一豁免条件是"带免责"——免责字段绝不能悄悄丢空,同 picks/insider_signal 的认账口径。
try:
    ol_path = WEB_DIR / "outlook.json"
    if ol_path.exists():
        with open(ol_path, encoding="utf-8") as fh:
            ol = json.load(fh)
        dc = ol.get("disclaimer", "")
        check(bool(dc) and "非投资建议" in dc,
              f"outlook.json disclaimer 非空且含非投资建议免责框（当前：{dc[:20] + '…' if dc else '空'}）")
except Exception as e:
    errors.append(f"outlook 免责门检查失败: {e}")
    print(f"  ✗ outlook 免责门检查失败: {e}")

# 3l6. AI 前瞻预测前向计分形状(track_record 全含 by_confidence/latest/recent。存在才查、缺失不致命)
#       诚实纪律:LLM 预测产物必须带"非投资建议 + 会错 + append 认账"框,且 track_record 含分信心命中(高信心是否真更准)。
try:
    pr_path = WEB_DIR / "prediction.json"
    if pr_path.exists():
        with open(pr_path, encoding="utf-8") as fh:
            pr = json.load(fh)
        tr = pr.get("track_record", {})
        ok = (isinstance(tr, dict)
              and all(k in tr for k in ("n_settled", "n_pending", "hit_pct", "by_confidence"))
              and isinstance(pr.get("recent"), list) and pr.get("symbol") == "SPY")
        check(ok, f"prediction.json 形状正常（已结算 {tr.get('n_settled')}·挂账 {tr.get('n_pending')}·命中 {tr.get('hit_pct')}%）")
        cav = pr.get("caveat", "")
        check("非投资建议" in cav and "会错" in cav and "认账" in cav,
              "prediction.json caveat 含非投资建议+会错+认账框")
except Exception as e:
    errors.append(f"prediction 形状检查失败: {e}")
    print(f"  ✗ prediction 形状检查失败: {e}")

# 3j. 方法论完整性护栏(automation-first):个股"真规律"(三关全过)必须先经人工审视,
#     不得自动发布——若 patterns_fdr_real=True 进了已发布 JSON,说明人工停下被绕过 → 拦住发布。
try:
    sc_path = WEB_DIR / "stock_checkup.json"
    if sc_path.exists():
        with open(sc_path, encoding="utf-8") as fh:
            _sc = json.load(fh)
        check(_sc.get("patterns_fdr_real") is not True,
              "方法论护栏:无未经人工审视的个股'真规律'(patterns_fdr_real≠True)")
except Exception as e:
    errors.append(f"方法论完整性护栏失败: {e}")
    print(f"  ✗ 方法论完整性护栏失败: {e}")

# 3k. R1 市场风险体制形状（components 非空、有 composite。存在才查、缺失不致命）
try:
    mr_path = WEB_DIR / "market_regime.json"
    if mr_path.exists():
        with open(mr_path, encoding="utf-8") as fh:
            mr = json.load(fh)
        ok = (mr.get("status") == "ok" and isinstance(mr.get("components"), list)
              and len(mr["components"]) >= 2 and bool(mr.get("composite")))
        check(ok, f"market_regime.json 形状正常（{len(mr.get('components', []))} 指标）")
except Exception as e:
    errors.append(f"market_regime 形状检查失败: {e}")
    print(f"  ✗ market_regime 形状检查失败: {e}")

# 3m. 因子现代段透镜形状（#5：segment_lens 计数非负 int、每因子 segment.status 合法。
#     嵌在 signals.json.factor_audit，存在才查、缺失不致命）
try:
    with open(WEB_DIR / "signals.json", encoding="utf-8") as fh:
        _sig2 = json.load(fh)
    _fa = _sig2.get("factor_audit") or {}
    _sl = _fa.get("segment_lens")
    if _sl:
        VALID_SEG = {"现代仍有效", "现代已淡", "现代检验力不足", "两段均无显著边际"}
        counts_ok = all(isinstance(_sl.get(k), int) and _sl[k] >= 0
                        for k in ("n_alive", "n_faded", "n_underpowered"))
        statuses = [(r.get("segment") or {}).get("status")
                    for r in _fa.get("factors", []) if r.get("segment")]
        status_ok = all(s in VALID_SEG for s in statuses)
        check(counts_ok and status_ok and isinstance(_sl.get("window_years"), int),
              f"factor_audit 现代段透镜形状正常（仍有效{_sl.get('n_alive')}/已淡{_sl.get('n_faded')}/不足{_sl.get('n_underpowered')}）")
except Exception as e:
    errors.append(f"factor_audit segment 形状检查失败: {e}")
    print(f"  ✗ factor_audit segment 形状检查失败: {e}")

# 4. 账本完整性（append-only 数据的硬约束）
try:
    import csv
    ledger_specs = [
        ("paper_ledger.csv", ("date", "strategy"),
         ["date", "strategy", "action", "holdings", "cash", "equity", "note", "logged_at"]),
        ("prediction_log.csv", ("signal_date", "index", "model_version"),
         ["logged_at", "signal_date", "index", "model_version", "prob", "tier", "ret_1d", "ret_5d", "ret_20d"]),
    ]
    for fname, keys, hash_fields in ledger_specs:
        p = PROC_DIR / fname
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            seen = [tuple(str(r[k]) for k in keys) for r in rows]
            dup = len(seen) - len(set(seen))
            check(dup == 0, f"{fname} 无重复键（发现 {dup} 条重复）")
            import pandas as pd
            h_errors = verify_hash_chain(pd.DataFrame(rows), hash_fields)
            check(not h_errors, f"{fname} hash chain 完整（{h_errors or 'ok'}）")
except Exception as e:
    errors.append(f"账本检查失败: {e}")

# 4b. Sidecar 哈希链（P2-9）：其余 append-only 公开账本（data/*.csv 计分账本——账本本体
#     无 hash 列，链存 data/ledger_hashchain.csv manifest）。相对上次封存抓「外改历史行/
#     删行截尾」；账本或封存记录缺失 → 跳过（bootstrap 友好）。诚实边界同 ledger_hash
#     docstring：独立审计（重封前跑本脚本）才抓得到外改；流水线重封会祝福当前内容。
try:
    import ledger_sidecar
    for _fname, _s_errors in ledger_sidecar.verify_all():
        check(not _s_errors, f"{_fname} sidecar hash 链完整（{_s_errors or 'ok'}）")
except Exception as e:
    errors.append(f"sidecar 账本检查失败: {e}")
    print(f"  ✗ sidecar 账本检查失败: {e}")

# 4c. Registry 不可变门（P2-10）：candidate_registry.csv 相对上次 git 提交(HEAD)必须只 append，
#     不许改历史行/删行/倒填锚点(declared_date)——git 历史本身当"外部真相"，不依赖自维护 manifest
#     (补 4b sidecar 的盲区：manifest 与账本被同一次提交一起伪造)。缺 git/非仓库/HEAD 无此文件
#     (bootstrap/git archive 检出) → 跳过+警告，不拦发布。
try:
    import shutil as _shutil
    import subprocess as _sp
    import candidate_registry as _creg
    _repo_root = Path(__file__).parent.parent.parent
    _reg_path = WEB_DIR.parent / "data" / "candidate_registry.csv"
    _git = _shutil.which("git")
    if not _git or not (_repo_root / ".git").exists() or not _reg_path.exists():
        print("  · candidate_registry 不可变门跳过（无 git/非仓库/文件不存在 —— bootstrap 友好）")
    else:
        _r = _sp.run([_git, "show", "HEAD:market-analysis/data/candidate_registry.csv"],
                      capture_output=True, text=True, encoding="utf-8", cwd=_repo_root)  # reason 含中文;不显式 utf-8 在 cp936 会解码歪→误报(Opus 审)
        if _r.returncode != 0:
            print(f"  · candidate_registry 不可变门跳过（HEAD 无此文件：{_r.stderr.strip()[:100]}）")
        else:
            _new_text = _reg_path.read_text(encoding="utf-8")
            _immut_problems = _creg.check_registry_immutable(_r.stdout, _new_text)
            check(not _immut_problems,
                  f"candidate_registry 相对 HEAD 只 append（问题：{_immut_problems or '无'}）")
except Exception as e:
    errors.append(f"candidate_registry 不可变门检查失败: {e}")
    print(f"  ✗ candidate_registry 不可变门检查失败: {e}")

if errors:
    print(f"\n[FAIL] {len(errors)} 项检查未通过，拒绝发布")
    sys.exit(1)
print("\n[OK] 全部自检通过，可以发布")
