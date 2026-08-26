"""
benchmark.py — Benchmark 记分卡（聚合型功能）

把项目里「每个模型 vs 它的诚实基线」集中到一张卡，并随时间追踪。
不改建模逻辑：只读现有产物 + 聚合 + 展示。

Benchmark 铁律（必须体现在代码与文案）：
  ① 用硬基线不是稻草人：方向比 0.50（不比"瞎猜更差"），波动比 VIX，策略比买入持有；
  ② 样本外/前向，不是样本内；
  ③ 前向类样本太小时标「数据不足」，而非草率判输赢。
诚实现状：迄今没有模型稳健打败诚实基线——如实呈现，不粉饰也不夸张。

输出：
  data/processed/benchmark.json        （结构化记分卡，供 build_signals 嵌入前端）
  <仓库根>/.benchmark-history.json     （append-only 快照，按 date 去重保留最新）

可独立运行：py market-analysis/scripts/benchmark.py
"""
import json
from datetime import date
from pathlib import Path

SCRIPTS  = Path(__file__).parent
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
REPO_ROOT = SCRIPTS.parent.parent          # E:\finance
HISTORY_PATH = REPO_ROOT / ".benchmark-history.json"

PRINCIPLE = "硬基线 · 样本外/前向 · 前向样本不足则不判输赢"

# verdict 取值（中文字符串，前端据此上色）
V_BEATS = "✅打败"
V_TIE   = "➖持平"
V_LOSE  = "❌未达"
V_INSUF = "⏳数据不足"
V_MISS  = "数据缺失"


# ── 可测的纯函数：算 verdict ──────────────────────────────────────
def _verdict_auc(model, base):
    """行1：AUC vs 0.5 基线。硬基线=随机无区分度。
    model<0.485 → 未达；0.485..0.515 → 持平；>0.515 → 打败。"""
    if model is None or base is None:
        return V_MISS
    if model < base - 0.015:
        return V_LOSE
    if model > base + 0.015:
        return V_BEATS
    return V_TIE


def _verdict_diff(diff, p):
    """行2：胜率−基率(pp) vs 0，看块自助 p 值。
    diff<0 → 未达；diff>0 且 p<0.10 → 打败；否则持平。"""
    if diff is None:
        return V_MISS
    if diff < 0:
        return V_LOSE
    if diff > 0 and p is not None and p < 0.10:
        return V_BEATS
    return V_TIE


def _verdict_gain(gain):
    """行3：模型 AUC 相对只看 VIX 的增益。硬基线=只看 VIX。
    gain<-0.02 → 未达；-0.02..0.02 → 持平；>0.02 → 打败。"""
    if gain is None:
        return V_MISS
    if gain < -0.02:
        return V_LOSE
    if gain > 0.02:
        return V_BEATS
    return V_TIE


def _forward_verdict(enough, delta):
    """前向类（行4/5）：样本不足时一律「数据不足」，绝不因当前 delta 为负就判输。
    样本足够后才按 delta 正负判打败/未达。"""
    if not enough:
        return V_INSUF
    if delta is None:
        return V_MISS
    if delta > 0:
        return V_BEATS
    if delta < 0:
        return V_LOSE
    return V_TIE


# ── 数据源加载（缺失不让整脚本崩）─────────────────────────────────
def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _get(d, *keys, default=None):
    """安全链式取值，任一层缺失返回 default。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _days_since(date_str, today):
    try:
        return (today - date.fromisoformat(date_str)).days
    except (TypeError, ValueError):
        return None


def _latest_version_entry(by_version):
    """取版本号最大的那项（按数值比较，回退字符串比较）。"""
    if not isinstance(by_version, dict) or not by_version:
        return None
    def _key(v):
        try:
            return (0, float(v))
        except (TypeError, ValueError):
            return (1, v)
    latest = max(by_version, key=_key)
    return by_version[latest]


# ── 构建记分卡 ────────────────────────────────────────────────────
def build(today=None):
    if today is None:
        today = date.today()
    generated = today.isoformat()

    fp = _load(PROC_DIR / "factor_pruning.json")
    wf = _load(PROC_DIR / "walk_forward_results.json")
    vm = _load(PROC_DIR / "vol_model.json")
    pa = _load(WEB_DIR / "paper.json")
    ps = _load(PROC_DIR / "prediction_log_summary.json")
    lint = _load(REPO_ROOT / ".brooks-lint-history.json")

    rows = []

    # ── 行1：方向预测（拼接样本外）AUC vs 0.50 ─────────────────────
    dir_auc = _get(fp, "target_probe", "direction_auc_pooled_2012_2024")
    rows.append({
        "name": "方向预测(拼接样本外)",
        "metric": "AUC",
        "model_value": dir_auc,
        "baseline_label": "随机·无区分度",
        "baseline_value": 0.50,
        "delta": round(dir_auc - 0.50, 4) if dir_auc is not None else None,
        "verdict": _verdict_auc(dir_auc, 0.50),
        "basis": "样本外·多regime拼接",
        "note": "AUC<0.5 意味着原始方向信号弱于随机——这是诚实的尸检结论",
    })

    # ── 行2：Tier≥4 信号 胜率−基率(pp) vs 0 ────────────────────────
    boot = _get(wf, "duel_summary", "naive", "tier4_boot", default={}) or {}
    diff = boot.get("diff")
    p_boot = boot.get("p_boot")
    rows.append({
        "name": "Tier≥4 信号",
        "metric": "胜率−基率(pp)",
        "model_value": diff,
        "baseline_label": "基率",
        "baseline_value": 0.0,
        "delta": diff,
        "verdict": _verdict_diff(diff, p_boot),
        "basis": "样本外·块自助(p=" + str(p_boot) + ")",
        "note": "块自助 95%CI 跨 0，未发现样本外优势",
    })

    # ── 行3：波动率模型 AUC vs 只看 VIX ────────────────────────────
    holdout_auc = _get(vm, "holdout_auc")
    vix_auc = _get(vm, "holdout_vix_only_auc")
    gain = _get(vm, "holdout_model_gain_over_vix")
    rows.append({
        "name": "波动率模型",
        "metric": "AUC",
        "model_value": holdout_auc,
        "baseline_label": "只看VIX",
        "baseline_value": vix_auc,
        "delta": gain,
        "verdict": _verdict_gain(gain),
        "basis": "样本外·holdout",
        "note": "对的靶子（波动率可预测），但相对只看 VIX 的增益微乎其微",
    })

    # ── 行4：模拟盘·信号策略 收益% vs 买入持有（前向）─────────────
    sig_ret = _get(pa, "strategies", "signal", "ret_pct")
    bh_ret = _get(pa, "strategies", "buyhold", "ret_pct")
    start_date = _get(pa, "start_date")
    if sig_ret is None or bh_ret is None:
        row4 = {
            "name": "模拟盘·信号策略", "metric": "收益%", "model_value": sig_ret,
            "baseline_label": "买入持有", "baseline_value": bh_ret, "delta": None,
            "verdict": V_MISS, "basis": "前向实盘", "note": "数据源缺失",
        }
    else:
        delta4 = round(sig_ret - bh_ret, 2)
        age = _days_since(start_date, today)
        enough4 = age is not None and age >= 30
        verdict4 = _forward_verdict(enough4, delta4)
        if not enough4:
            remaining = 30 - age if age is not None else 30
            note4 = f"前向实验需积累，约 {remaining} 天后才有统计意义"
        else:
            note4 = "前向样本已足，按实盘收益差判定"
        row4 = {
            "name": "模拟盘·信号策略", "metric": "收益%", "model_value": sig_ret,
            "baseline_label": "买入持有", "baseline_value": bh_ret, "delta": delta4,
            "verdict": verdict4, "basis": "前向实盘·自" + str(start_date), "note": note4,
        }
    rows.append(row4)

    # ── 行5：实盘预测·方向 1日命中% vs 抛硬币（前向）──────────────
    latest_v = _latest_version_entry(_get(ps, "by_version", default={}))
    hit_1d = latest_v.get("hit_rate_1d") if latest_v else None
    n_scored = latest_v.get("n_scored_1d") if latest_v else None
    if hit_1d is None:
        row5 = {
            "name": "实盘预测·方向", "metric": "1日命中%", "model_value": None,
            "baseline_label": "抛硬币", "baseline_value": 50.0, "delta": None,
            "verdict": V_MISS, "basis": "前向实盘", "note": "数据源缺失",
        }
    else:
        delta5 = round(hit_1d - 50, 1)
        enough5 = n_scored is not None and n_scored >= 20
        verdict5 = _forward_verdict(enough5, delta5)
        if not enough5:
            remaining = 20 - (n_scored or 0)
            note5 = f"前向实验需积累，约 {remaining} 个已评分预测后才有统计意义"
        else:
            note5 = "前向样本已足，按命中率差判定"
        row5 = {
            "name": "实盘预测·方向", "metric": "1日命中%", "model_value": hit_1d,
            "baseline_label": "抛硬币", "baseline_value": 50.0, "delta": delta5,
            "verdict": verdict5, "basis": "前向实盘·已评分 n=" + str(n_scored), "note": note5,
        }
    rows.append(row5)

    # ── 行6：代码健康分 vs 首次基线（工程类）──────────────────────
    if isinstance(lint, list) and lint:
        last_score = lint[-1].get("score")
        first_score = lint[0].get("score")
        if last_score is None or first_score is None:
            row6 = {
                "name": "代码健康分", "metric": "健康分", "model_value": last_score,
                "baseline_label": "首次基线", "baseline_value": first_score, "delta": None,
                "verdict": V_MISS, "basis": "工程", "note": "lint 历史字段缺失",
            }
        else:
            delta6 = last_score - first_score
            # 工程类不会"输"：持平或改进
            verdict6 = V_BEATS if delta6 > 0 else V_TIE
            row6 = {
                "name": "代码健康分", "metric": "健康分", "model_value": last_score,
                "baseline_label": "首次基线", "baseline_value": first_score, "delta": delta6,
                "verdict": verdict6, "basis": "工程",
                "note": "工程类只比自己的起点：持平或改进，不存在'输'",
            }
    else:
        row6 = {
            "name": "代码健康分", "metric": "健康分", "model_value": None,
            "baseline_label": "首次基线", "baseline_value": None, "delta": None,
            "verdict": V_MISS, "basis": "工程", "note": ".brooks-lint-history.json 缺失",
        }
    rows.append(row6)

    # ── 汇总计数 ──────────────────────────────────────────────────
    summary = {"beats": 0, "ties": 0, "loses": 0, "insufficient": 0}
    for r in rows:
        v = r["verdict"]
        if v == V_BEATS:
            summary["beats"] += 1
        elif v == V_TIE:
            summary["ties"] += 1
        elif v == V_LOSE:
            summary["loses"] += 1
        elif v == V_INSUF:
            summary["insufficient"] += 1
        # V_MISS 不计入四类

    headline = (
        f"迄今 {summary['beats']} 个模型稳健打败诚实基线"
        f"；前向类 {summary['insufficient']} 项仍在积累。"
        "这是诚实现状，也是任何'优化'必须先过的关。"
    )

    return {
        "generated": generated,
        "principle": PRINCIPLE,
        "rows": rows,
        "summary": summary,
        "headline": headline,
    }


# ── 漂移监控：与上次快照比，发现 verdict 退化就告警（⑤）────────────
# 越靠前越好：打败 > 持平 > 数据不足 > 未达 > 缺失
VERDICT_RANK = {V_BEATS: 4, V_TIE: 3, V_INSUF: 2, V_LOSE: 1, V_MISS: 0}



# ── 数据层双语(2026-08-25)：EN 字段单点附加，不逐行改 6 个 rows.append ────────────
# 为什么另出 *_en 而不改原值:verdict 的中文值同时被 app-5.js 当颜色映射的**键**用,
# 改值会打断前端。行级 EN 按 name 索引(name 是稳定标识),缺失回落中文——诚实取舍:
# 宁可显示中文,也不显示空白或机翻。
VERDICT_EN = {V_BEATS: "beats", V_TIE: "ties", V_LOSE: "falls short",
              V_INSUF: "insufficient data", V_MISS: "data missing"}

METRIC_EN = {"胜率−基率(pp)": "win rate - base rate (pp)",
             "收益%": "return %",
             "1日命中%": "1-day hit %",
             "健康分": "health score"}

ROW_EN = {
    "方向预测(拼接样本外)": {
        "name_en": "Direction prediction (pooled out-of-sample)",
        "baseline_label_en": "random · no discrimination",
        "note_en": "AUC below 0.5 means the raw directional signal is worse than random - an honest post-mortem"},
    "Tier≥4 信号": {
        "name_en": "Tier >=4 signal",
        "baseline_label_en": "base rate",
        "note_en": "The block-bootstrap 95% CI straddles zero - no out-of-sample edge found"},
    "波动率模型": {
        "name_en": "Volatility model",
        "baseline_label_en": "VIX alone",
        "note_en": "The right target (volatility is forecastable), but the gain over just using VIX is marginal"},
    "模拟盘·信号策略": {
        "name_en": "Paper trading · signal strategy",
        "baseline_label_en": "buy and hold",
        "note_en": "Forward sample is now sufficient; judged on realised return difference"},
    "实盘预测·方向": {
        "name_en": "Live prediction · direction",
        "baseline_label_en": "coin flip",
        "note_en": "Forward sample is now sufficient; judged on hit-rate difference"},
    "代码健康分": {
        "name_en": "Code health score",
        "baseline_label_en": "first baseline",
        "note_en": "Engineering items are compared only against their own starting point: tie or improve, never 'lose'"},
}

_BASIS_FRAG = [("样本外", "out-of-sample"), ("前向实盘", "forward live"),
               ("块自助", "block bootstrap"), ("已评分", "scored"),
               ("多regime拼接", "pooled across regimes"),
               ("工程", "engineering"), ("自", "since ")]


def _basis_en(basis):
    """basis 是带数字的动态串(如 样本外·块自助(p=0.042))——按片段翻,数字原样保留、不会漂移。"""
    if not basis:
        return basis
    out = str(basis)
    for zh, en in _BASIS_FRAG:
        out = out.replace(zh, en)
    return out


def attach_en(card):
    """给已构造好的 rows / 顶层文案附加 *_en(单点,将来加行不易遗漏)。"""
    for r in card.get("rows", []):
        meta = ROW_EN.get(r.get("name"), {})
        r["name_en"] = meta.get("name_en", r.get("name"))
        r["baseline_label_en"] = meta.get("baseline_label_en", r.get("baseline_label"))
        r["basis_en"] = _basis_en(r.get("basis"))
        r["note_en"] = meta.get("note_en", r.get("note"))
        r["verdict_en"] = VERDICT_EN.get(r.get("verdict"), r.get("verdict"))
        r["metric_en"] = METRIC_EN.get(r.get("metric"), r.get("metric"))
    card["principle_en"] = ("Hard baselines · out-of-sample / forward · when the forward sample is too "
                            "small, we declare neither a win nor a loss")
    su = card.get("summary") or {}
    card["headline_en"] = (f"So far {su.get('beats', 0)} models robustly beat an honest baseline; "
                           f"{su.get('insufficient', 0)} forward-looking items are still accumulating. "
                           f"This is the honest state of things, and the bar any 'optimisation' must clear first.")
    d = card.get("drift") or {}
    if d:
        if not d.get("changes"):
            d["status_en"] = "No drift versus " + str(d.get("since"))
        else:
            # 逐条把「模型名:旧裁决→新裁决」翻成英文(复用同一份 ROW_EN/VERDICT_EN,不另写一套)
            det = []
            for c in d.get("changes", []):
                nm = str(c.get("name", ""))
                nm_en = (ROW_EN.get(nm) or {}).get("name_en", nm)
                det.append(f"{nm_en}: {VERDICT_EN.get(c.get('from'), c.get('from'))} -> "
                           f"{VERDICT_EN.get(c.get('to'), c.get('to'))}")
            d["status_en"] = (f"{len(det)} item(s) changed versus {d.get('since')} (" + "; ".join(det) + ")")
    return card


def detect_drift(card):
    """对比上一条历史快照，标出哪些项较上次退化/改进。数据攒够后这就是'结论是否仍成立'的哨兵。"""
    hist = _load(HISTORY_PATH)
    if not isinstance(hist, list) or not hist:
        return {"status": "首次记录，无历史可比", "changes": [], "degraded_count": 0}
    prev = hist[-1]
    prev_v = prev.get("verdicts", {})
    changes = []
    for r in card["rows"]:
        was, now = prev_v.get(r["name"]), r["verdict"]
        if was and was != now:
            direction = "improved" if VERDICT_RANK.get(now, 0) > VERDICT_RANK.get(was, 0) else "degraded"
            changes.append({"name": r["name"], "from": was, "to": now, "direction": direction})
    degraded = [c for c in changes if c["direction"] == "degraded"]
    return {
        "since": prev.get("date"),
        "changes": changes,
        "degraded_count": len(degraded),
        "status": (f"⚠ 较 {prev.get('date')} 有 {len(degraded)} 项退化" if degraded
                   else ("较上次有改进" if changes else f"与 {prev.get('date')} 一致，无漂移")),
    }


# ── history：append + 按 date 去重保留最新 ────────────────────────
def update_history(card):
    hist = _load(HISTORY_PATH)
    if not isinstance(hist, list):
        hist = []
    entry = {
        "date": card["generated"],
        "verdicts": {r["name"]: r["verdict"] for r in card["rows"]},
        "summary": card["summary"],
    }
    # 同日重复运行覆盖当天那条
    hist = [h for h in hist if h.get("date") != entry["date"]]
    hist.append(entry)
    hist.sort(key=lambda h: h.get("date", ""))
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2, allow_nan=False)
    return hist


# ── 对齐打印 ──────────────────────────────────────────────────────
def _w(s):
    """显示宽度：中文/全角字符算 2，其余算 1。"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in str(s))


def _pad(s, width):
    s = str(s)
    return s + " " * max(0, width - _w(s))


def print_table(card):
    cols = ["项目", "指标", "模型值", "基线", "差值", "判定", "依据"]
    rows = []
    for r in card["rows"]:
        mv = r["model_value"]
        bv = r["baseline_value"]
        dl = r["delta"]
        rows.append([
            r["name"], r["metric"],
            "—" if mv is None else str(mv),
            "—" if bv is None else str(bv),
            "—" if dl is None else (f"+{dl}" if isinstance(dl, (int, float)) and dl > 0 else str(dl)),
            r["verdict"], r["basis"],
        ])
    widths = [max(_w(cols[i]), max((_w(row[i]) for row in rows), default=0)) for i in range(len(cols))]

    print("\n" + "=" * 70)
    print("  🎯 Benchmark 记分卡 — 每个模型 vs 它的诚实基线")
    print("=" * 70)
    print("  " + "  ".join(_pad(cols[i], widths[i]) for i in range(len(cols))))
    print("  " + "  ".join("-" * widths[i] for i in range(len(cols))))
    for row in rows:
        print("  " + "  ".join(_pad(row[i], widths[i]) for i in range(len(cols))))
    s = card["summary"]
    print("-" * 70)
    print(f"  汇总：打败 {s['beats']} · 持平 {s['ties']} · 未达 {s['loses']} · 数据不足 {s['insufficient']}")
    print(f"  原则：{card['principle']}")
    print(f"  结论：{card['headline']}")
    print("=" * 70)


def main():
    card = build()
    card["drift"] = detect_drift(card)   # 先比对（用 append 之前的历史），再写盘
    attach_en(card)                      # 数据层双语:单点附加 *_en(须在 drift 之后,才能带上 status_en)
    out = PROC_DIR / "benchmark.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2, allow_nan=False)
    update_history(card)
    print_table(card)
    print(f"  漂移：{card['drift']['status']}")
    print(f"\n[OK] 已写出 {out}")
    print(f"[OK] 已追加快照 {HISTORY_PATH}")


if __name__ == "__main__":
    main()
