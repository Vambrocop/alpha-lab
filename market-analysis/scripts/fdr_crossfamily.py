"""
fdr_crossfamily.py — #5 跨检验族 FDR 收口（诚实统计的"总账"）

诚实问题：把全站各方法做过的"显著性主张"放进**同一个**多重比较框架后，还剩几条经得起？
单看每族(日历/事件/路径/因子)各自校正还不够——跨族汇池才反映"我们试过的所有东西"的
forking-paths 风险（Benjamini & Yekutieli 2001；Bailey & López de Prado 反过拟合精神）。

方法：收集各 JSON 已发布的 p 值 → 池化
  · Benjamini-Yekutieli(任意相关稳健，**诚实头条**；BH 阈值再除以调和数 c(m))
  · Benjamini-Hochberg(PRDS 假定，偏乐观，作对照)
  · Bonferroni(FWER，最严，看最强主张)

口径(写在 caveat)：这是**保守的探索性**跨族 meta 校正，不是统一模型；只要每个 p 在各自零假设
下有效即可用 BY 池化。部分"主张"是机械/同期关系(如恐慌↔标普同期负相关)，存活≠真发现，
逐条由各自方法的脚注负责；本表只回答"多重比较后还剩几条"。仅 numpy/stdlib。
"""
import datetime
import json
from pathlib import Path

SCRIPTS  = Path(__file__).parent
WEB_DIR  = SCRIPTS.parent / "web"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
DOCS_DIR = SCRIPTS.parent.parent / "docs"


# 数据层双语(2026-08-27):族名/标签的英文由共享规则翻译器生成——上游一加新因子
# 就自动跟上,不用手抄映射表(同 build_signals._macro_en 的思路)。
from label_en import label_en  # noqa: E402

FAMILY_EN = {"日历效应": "Calendar effects", "事件因果": "Event causality",
             "路径/Granger": "Path / Granger", "因子AUC": "Factor AUC"}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# BH/BY step-up 已统一到 stats_util(审计 S5);沿用 _bh_reject/_by_reject 名
from stats_util import bh_reject as _bh_reject, by_reject as _by_reject


def collect():
    """从各方法已发布的产物里收集 (family, label, p)。缺哪族就跳哪族（诚实标注）。"""
    claims, sources = [], []
    pl = _load(WEB_DIR / "placebo_tests.json")
    if pl:
        sources.append("日历效应")
        for t in pl.get("tests", []):
            if t.get("p_value") is not None:
                claims.append({"family": "日历效应", "label": t.get("panel"), "p": float(t["p_value"])})
    ev = _load(WEB_DIR / "event_causal.json")
    if ev:
        sources.append("事件因果")
        for e in ev.get("events", []):
            if e.get("p_value") is not None and e.get("status") != "pending":
                claims.append({"family": "事件因果", "label": e.get("name"), "p": float(e["p_value"])})
    mv = _load(WEB_DIR / "multivariate.json")
    if mv and mv.get("path"):
        sources.append("路径/Granger")
        for p in mv["path"]:
            if p.get("pvalue") is not None:
                claims.append({"family": "路径/Granger", "label": p.get("path"), "p": float(p["pvalue"])})
    fp = _load(PROC_DIR / "factor_pruning.json")
    if fp:
        sources.append("因子AUC")
        for fr in fp.get("factors", []):
            if fr.get("dev_p_boot") is not None:
                claims.append({"family": "因子AUC", "label": fr.get("name"), "p": float(fr["dev_p_boot"])})
    return claims, sources


def run_all(write=True):
    print("=== #5 跨检验族 FDR 收口 ===")
    claims, sources = collect()
    m = len(claims)
    if m < 2:
        print(f"⚠ 仅收集到 {m} 项主张，跳过")
        return None

    pvals = [c["p"] for c in claims]
    rej_by10, c_m = _by_reject(pvals, 0.10)
    rej_by05, _   = _by_reject(pvals, 0.05)
    rej_bh10      = _bh_reject(pvals, 0.10)
    bonf = 0.05 / m

    for i, c in enumerate(claims):
        c["survive_by_10"]          = i in rej_by10
        c["survive_by_05"]          = i in rej_by05
        c["survive_bh_10"]          = i in rej_bh10
        c["survive_bonferroni_05"]  = c["p"] < bonf
        c["p"] = round(c["p"], 4)
    claims.sort(key=lambda c: c["p"])

    fams = {}
    for c in claims:
        f = fams.setdefault(c["family"], {"family": c["family"], "n": 0, "n_survive_by_10": 0})
        f["n"] += 1
        f["n_survive_by_10"] += int(c["survive_by_10"])

    survivors = [c["label"] for c in claims if c["survive_by_10"]]
    survivors_en = [label_en(c["label"]) for c in claims if c["survive_by_10"]]
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "跨检验族汇池多重比较：Benjamini-Yekutieli(任意相关稳健，头条) + "
                  "Benjamini-Hochberg(PRDS，乐观对照) + Bonferroni(FWER)。",
        "caveat": "保守的**探索性**跨族 meta 校正，非统一模型。汇集各方法已发布的 p 值，"
                  "回答'把试过的所有东西算进去后还剩几条'。部分主张是机械/同期关系(如恐慌↔标普同期负相关)，"
                  "存活≠真发现，需看各自方法脚注；step-up 程序下，足够多的极小 p 会抬高同批其它主张的阈值，"
                  "故个别中等 p 可能跨族存活而族内不存活，属正常。",
        "families_pooled": sources,
        "m_total": m,
        "by_c_m": round(c_m, 3),
        "bonferroni_alpha": round(bonf, 5),
        "n_survive_by_10": len(rej_by10),
        "n_survive_by_05": len(rej_by05),
        "n_survive_bh_10": len(rej_bh10),
        "n_survive_bonferroni_05": int(sum(c["survive_bonferroni_05"] for c in claims)),
        "by_family": list(fams.values()),
        "claims": [dict(c, label_en=label_en(c.get("label")),
                        family_en=FAMILY_EN.get(c.get("family"), c.get("family")))
                   for c in claims],
        "verdict": f"全站 {m} 项显著性主张，跨族 BY(任意相关稳健, q=0.10)仅 {len(rej_by10)} 项经得起"
                   f"（BH 乐观留 {len(rej_bh10)}）。存活：{('、'.join(survivors)) or '无'}。",
    }
    if write:                                  # 测试传 write=False:不写生产 JSON(防 pytest 污染工作树→时间戳churn)
        from util_io import write_json
        write_json("fdr_crossfamily.json", out, proc=True, allow_nan=False)
        print(f"  {out['verdict']}")
        print("[OK] fdr_crossfamily.json")
    return out


if __name__ == "__main__":
    run_all()
