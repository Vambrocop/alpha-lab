"""daily_digest.py — 每日诚实摘要（三层标签；🔴 红线：绝不预测方向、不荐股）。

读 run_all 产出的 JSON，对比上次 digest 算"什么变了"，分三层输出：
  ① 事实（客观）        —— 数据/信号 tier/模拟盘/体制现值
  ② 诚实留意点（描述）  —— 已验证规律此刻状态/变化 + 历史风险框架 +「看哪里」，非预测
  ③ 探索（强标注）      —— 未验证假设，"很可能是噪声、不可交易"

输出 web/docs 的 digest.json，并 append 进 data/processed/digest_history.json（供周报 rollup）。
运行时门禁：任何层文案出现方向/操作词 → 直接 raise，绝不发布（test_daily_digest 复核）。
"""
import datetime
import json
import re
from pathlib import Path

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
DOCS = SCRIPTS.parent.parent / "docs"
PROC = SCRIPTS.parent / "data" / "processed"
HIST = PROC / "digest_history.json"

# 🔴 红线词：digest 任何层都不得出现（方向预测 / 操作建议 / 荐股）。
FORBIDDEN = ["买入", "卖出", "看涨", "看跌", "会涨", "会跌", "该买", "该卖", "目标价",
             "荐股", "必涨", "必跌", "加仓", "减仓", "抄底", "梭哈", "建议买", "建议卖", "买进", "卖出"]


def _load(name):
    p = WEB / name
    try:
        return json.load(open(p, encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def _prev():
    p = WEB / "digest.json"
    try:
        return json.load(open(p, encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def build_digest():
    sig = _load("signals.json") or {}
    regime = _load("market_regime.json") or {}
    paper = _load("paper.json") or {}
    over = _load("overreaction.json") or {}
    health = _load("data_health.json") or {}
    prev = _prev()
    prev_labels = prev.get("_regime_labels") or {}
    prev_labels_en = prev.get("_regime_labels_en") or {}

    facts, watch, explore = [], [], []
    # 数据层双语(2026-09-01)：中英**同一处构建**(同一批取值渲染两次),
    # 不是事后再翻一遍——事后翻译会漏掉这里的条件分支(有变化/无变化、有 prob/无 prob)。
    facts_en, watch_en, explore_en = [], [], []

    # ── ① 事实 ────────────────────────────────────────────────
    hs = health.get("summary") or {}
    if hs:
        _src = f"{hs.get('ok', 0)}/{hs.get('total', 0)} live"
        facts.append(f"数据源 {_src}"
                     + (f" · 缓存 {hs.get('cache')}" if hs.get("cache") else "")
                     + (f" · 过期 {hs.get('stale')}" if hs.get("stale") else ""))
        facts_en.append(f"Data sources {_src}"
                        + (f" · cached {hs.get('cache')}" if hs.get("cache") else "")
                        + (f" · stale {hs.get('stale')}" if hs.get("stale") else ""))
    tier = sig.get("latest_tier")
    if tier is not None:
        chg = ""
        if prev.get("_tier") is not None and prev["_tier"] != tier:
            chg = f"（{prev['_tier']} → {tier}）"
        _prob = (f" · prob {sig.get('latest_prob')}" if sig.get("latest_prob") is not None else "")
        facts.append(f"纳指信号 tier {tier}{chg}" + _prob)
        facts_en.append(f"NASDAQ signal tier {tier}"
                        + (f" ({prev['_tier']} -> {tier})" if chg else "") + _prob)
    strats = paper.get("strategies") or {}
    if strats:
        rank = sorted(strats.items(), key=lambda kv: -(kv[1].get("ret_pct") if kv[1].get("ret_pct") is not None else -1e9))
        lead = rank[0][1]
        facts.append(f"模拟盘领先：{lead.get('label', '?')} {lead.get('ret_pct')}%（前向竞技，无法事后美化）")
        facts_en.append(f"Paper-portfolio leader: {lead.get('label_en', lead.get('label', '?'))} "
                        f"{lead.get('ret_pct')}% (a forward competition — it cannot be prettied up "
                        "after the fact)")

    # ── ② 诚实留意点（已验证规律此刻状态 / 变化 + 历史框架） ──────
    cur_labels, cur_labels_en = {}, {}
    for c in (regime.get("components") or []):
        nm, lbl = c.get("name"), c.get("label")
        if not nm:
            continue
        cur_labels[nm] = lbl
        cur_labels_en[nm] = c.get("label_en", lbl)
        old = prev_labels.get(nm)
        pct = c.get("percentile")
        notable = (isinstance(pct, (int, float)) and (pct >= 75 or pct <= 25)) or c.get("inverted") or c.get("backwardation")
        note = c.get("note", "")
        cav = "" if ("非预测" in note or "描述" in note) else "（描述，非预测）"
        # 英文取 market_regime 已有的 *_en(单一真相源在那边);缺就回落中文,不另译一版
        nm_e, lbl_e = c.get("name_en", nm), c.get("label_en", lbl)
        old_e = prev_labels_en.get(nm) or old
        note_e = c.get("note_en", note)
        # 与中文同一条规则:note 里已含免责语就不再追加,免得重复啰嗦
        cav_e = ("" if ("not a forecast" in note_e or "descriptive" in note_e.lower())
                 else " (descriptive, not a forecast)")
        if old and old != lbl:
            watch.append(f"**{nm}** {old} → {lbl}。{note}{cav}")
            watch_en.append(f"**{nm_e}** {old_e} -> {lbl_e}. {note_e}{cav_e}")
        elif notable:
            watch.append(f"**{nm}** 当前 {lbl}。{note}{cav}")
            watch_en.append(f"**{nm_e}** currently {lbl_e}. {note_e}{cav_e}")
    if over.get("verdict") == "real":
        watch.append("短期反转（过度反应）统计可见、但经济不可用——历史上极端下跌日次日有反弹倾向，"
                     "这是【描述】不是抄底信号，且扣成本后未必站得住。")
        watch_en.append("Short-term reversal (overreaction) is statistically visible but not "
                        "economically usable: historically, the day after an extreme decline has "
                        "tended to bounce. This is a [description], not a buy-the-dip signal, and it "
                        "may not survive once costs are deducted.")

    # ── ③ 探索（未验证，强标注） ────────────────────────────────
    explore.append("🔭 探索区里的民间周期 / 裸显著但未过 FDR 的项 = 未验证假设，"
                   "**很可能是噪声、不可交易**，仅留作逐次重验：过了升登记簿、被否进坟场。")
    explore_en.append("🔭 Folk cycles in the exploration zone, and items that are naively significant "
                      "but fail FDR, are **unvalidated hypotheses** — most likely noise and not "
                      "tradeable. They are kept only for repeated re-testing: pass and they are "
                      "promoted to the registry, fail and they go to the graveyard.")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": (sig.get("generated") or datetime.date.today().isoformat())[:10],
        "tier1_facts": facts, "tier1_facts_en": facts_en,
        "tier2_watch": watch, "tier2_watch_en": watch_en,
        "tier3_explore": explore, "tier3_explore_en": explore_en,
        "caveat": "本摘要只描述【当前状态 + 历史风险分布】，🔴 绝不预测方向、不荐股。"
                  "规律均来自已验证项；未验证猜测仅在③探索层、强标注。",
        "caveat_en": "This digest only describes [the current state + the historical distribution of "
                     "risk]. 🔴 It never forecasts direction and never recommends a stock. Every "
                     "regularity cited comes from a validated item; unvalidated guesses live only in "
                     "layer ③ (exploration) and are labelled as such.",
        "_tier": tier,                 # 内部：供下次算变化
        "_regime_labels": cur_labels,  # 内部：供下次算变化
        "_regime_labels_en": cur_labels_en,  # 内部：英文版"上次标签",供下次算变化时出英文
    }
    _assert_no_forbidden(out)
    return out


_NEG = "不非别未"   # 否定/免责语境放行（"不荐股""不是抄底""非预测"），断言才算违规


def _violations(out):
    texts = [out.get("caveat", "")]
    for k in ("tier1_facts", "tier2_watch", "tier3_explore"):
        texts += [str(x) for x in (out.get(k) or [])]
    hits = []
    for t in texts:
        for w in FORBIDDEN:
            for m in re.finditer(re.escape(w), t):
                pre = t[max(0, m.start() - 3):m.start()]
                if not re.search(f"[{_NEG}]", pre):   # 前 3 字无否定词 = 断言 → 违规
                    hits.append(w)
    return sorted(set(hits))


def _assert_no_forbidden(out):
    hit = _violations(out)
    if hit:
        raise ValueError(f"🔴 红线违规：digest 含【未否定的】方向/操作词 {hit}，拒绝发布。")


def run():
    out = build_digest()
    from util_io import write_json
    write_json("digest.json", out, allow_nan=False)
    # append-only 历史（保留近 90 条，供周报 rollup）
    hist = []
    if HIST.exists():
        try:
            hist = json.load(open(HIST, encoding="utf-8"))
        except Exception:
            hist = []
    slim = {k: v for k, v in out.items() if not k.startswith("_")}
    if not hist or hist[-1].get("date") != slim["date"]:
        hist.append(slim)
    else:
        hist[-1] = slim   # 同日重跑覆盖
    HIST.write_text(json.dumps(hist[-90:], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] digest.json — ①{len(out['tier1_facts'])}事实 ②{len(out['tier2_watch'])}留意 ③{len(out['tier3_explore'])}探索")
    return out


if __name__ == "__main__":
    run()
