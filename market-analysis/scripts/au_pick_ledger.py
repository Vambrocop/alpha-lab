"""au_pick_ledger.py — 澳股荐股「看好/看淡」的 append-only 公开计分（独立账本·出格区·B3）。

pick_ledger.py 的 AU 配置级克隆（SPEC_AU_PICKS.md §1）：规则/命中口径**零克隆**——直接
`from pick_ledger import _select_picks, _outcome, _followable, MOM_WIN, VOL_WIN, N_PICKS`，
绝不复制函数体（S-1：_outcome/_followable 皆 bench-agnostic，复制=埋漂移；两市场规则/
命中口径 = 同一份代码）。本文件只自带 AU 专属的薄壳：读本地宽表选票 → 拼本地 px 字典 →
喂现成 `fl.settle`（forward_ledger 一个字节不动，美股回归风险归零）。

**独立账本**：`data/au_pick_ledger.csv`，绝不与美股 `pick_ledger.csv` 混（基准不同不可比）。
挂 ledger_sidecar 哈希链（见该文件 SPECS 列表）。

配置差异（全部差异仅此，SPEC §1.2）：
| 项 | 美股 pick_ledger | AU |
|---|---|---|
| UNIVERSE | raw/stocks_prices.csv | raw/au/au_stocks_prices.csv（fetch_data_au 顺手拼，暂缺时 fail-soft） |
| BENCH | QQQ（yfinance 实时取） | ^AXJO（本地取价，从不调 yfinance） |
| HOLD_TD | 20 | 20（同） |
| LOG | data/pick_ledger.csv | data/au_pick_ledger.csv |
| 币种 | USD | AUD 本币（两腿同币，零汇率调整） |
| 输出 | picks.json | au_picks.json（web+docs） |

**N-1 键一致性**（防静默丢票）：宽表列名 = `.AX` ticker = `_select_picks` 输出 symbol =
settle 的 px 字典键；bench 键锁死 `"^AXJO"`（raw/au/AXJO.csv 的 series 列名就是 "^AXJO"，
**文件名 AXJO.csv ≠ 键名**，读列名/Series.name，不把文件名当键）。

AU 专属 caveat 全套（§1.5，美股全套之上追加）：
  - **股息口径不对称声明（B-2·必披露）**：个股序列 = 含息复权总回报（yfinance auto_adjust），
    ^AXJO = 除息价格指数 → 存在 ≈ 股息率（AU ~4%/年 ≈ 0.3%/20个交易日）的**持续性口径顺风**，
    对「看好」系统性有利——这不是我们的 edge，是两条腿口径不对称的产物。
  - franking（红利抵免）不含：无可靠免费源，宁缺勿猜。
  - 池 = ASX100 大中盘（③ 扩池 ~108 只；流动性档位见体检，不再全高档）；ASX 本地日 = 交易日。
  - FMG 在池，但 1988–2002 为壳公司稀疏数据（真正 Fortescue 连续交易史 2003 起）——本账本
    126 日动量/63 日低波动窗口只回看近期数据，不会跨越那段历史；au_pick_backtest.py（长窗口
    回测）另有独立截断逻辑处理，live 与回测各自处理但同一份"截断日前 NaN"单一真相源。
  - 池（28 巨头）≈ ^AXJO 主导权重 → 超额天然被压制（"打赢你自己"），AU 集中度比美股更极端。
  - 非投资建议、不可交易（成本/滑点/税）、会错、过去≠未来——同美股全套。

fail-soft：raw/au/au_stocks_prices.csv 暂缺（宽表由另一条线在 fetch_data_au.py 里建）→
`_load_picks` 空跑不炸（不新增荐股，但已有挂账行仍可正常结算）。
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import forward_ledger as fl
from pick_ledger import MOM_WIN, N_PICKS, VOL_WIN, _followable, _outcome, _select_picks

SCRIPTS = Path(__file__).parent
BASE = SCRIPTS.parent
RAW_AU = BASE / "data" / "raw" / "au"
LOG = BASE / "data" / "au_pick_ledger.csv"

HOLD_TD = 20              # 持有交易日数——与美股 pick_ledger 同（§1.2 表：唯二"同"项）
BENCH = "^AXJO"           # 基准：ASX200（33.6 年史，覆盖完整周期；本地取价，从不调 yfinance）
UNIVERSE = RAW_AU / "au_stocks_prices.csv"   # ASX100 大中盘宽表（date×ticker，fetch_data_au 顺手拼，③ ~108 票）
# 与美股同一规则、同一代码（_select_picks 零克隆 import）——AU 池 = ASX100 大中盘（③ 扩池 ~108 只）
PICK_RULE = ("动量+低波动 等权排名（126日动量 + 63日低波动，ASX100 大中盘池取头/尾各3）"
             "——与美股 pick_ledger 同一规则、同一代码（零克隆）")
PICK_RULE_EN = ("Momentum + low-volatility equal-weight ranking (126-day momentum + 63-day low volatility; "
                "top/bottom 3 from the ASX100 mid/large-cap pool) — same rule and same code as the US "
                "pick_ledger (zero cloning)")

HEADER = ["pick_date", "symbol", "view", "mom_pct", "entry_date", "entry_px",
          "exit_date", "exit_px", "ret_pct", "bench_pct", "excess_pct",
          "call_excess_pct", "hit", "settled", "dropped"]

# 宽表/辅助文件不是单票价格序列，_local_px 拼字典时跳过
_NON_TICKER_FILES = {"au_stocks_prices.csv", "dollar_volume.csv"}


# ── 身份去重键(照美股 pick_ledger 同构) ──────────────────────────────────
def _key(r):
    return (r.get("symbol"), str(r.get("pick_date")), r.get("view"))


def _load_picks():
    """读 AU 宽表 → _select_picks(零克隆) → 标今日为出榜日。宽表暂缺/损坏 → 空列表,不阻断。"""
    try:
        prices = pd.read_csv(UNIVERSE, index_col=0, parse_dates=True)
    except Exception:
        return []
    today = datetime.date.today().isoformat()
    return [{**p, "pick_date": today} for p in _select_picks(prices)]


def _settle(rows, px):
    return fl.settle(rows, px, bench=BENCH, hold=HOLD_TD, trading_days=True,
                     symbol_key="symbol", followable_of=_followable, outcome_of=_outcome)


def _local_px():
    """从 raw/au/*.csv（单票 Close 序列，fetch_data_au.py 产）拼本地 px 字典（S-1：
    forward_ledger 零改——settle 只认 px 字典键，从不调 yfinance；AU 结算永不联网）。
    键 = 各 csv 唯一列名（.AX ticker / "^AXJO"），不是文件名（N-1：AXJO.csv 的列名是 "^AXJO"）。
    某票 csv 缺失/损坏 → 该票静默缺席（fail-soft，同 fetch_prices 网络失败的兜底哲学）。"""
    px = {}
    if not RAW_AU.exists():
        return px
    for f in RAW_AU.glob("*.csv"):
        if f.name in _NON_TICKER_FILES:
            continue
        try:
            s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        except Exception:
            continue
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) > 5 and s.name:
            px[str(s.name)] = s
    return px


# ── 聚合/展示（非"规则/命中口径"，故自写而非 import；文案换 ^AXJO） ─────────
def _side_stats(rows, view):
    s = [r for r in rows if fl.is_true(r.get("settled")) and r.get("view") == view]
    if not s:
        return {"n": 0, "hit_pct": None, "mean_call_excess_pct": None}
    hit = sum(1 for r in s if fl.is_true(r.get("hit")))
    ce = np.array([float(r["call_excess_pct"]) for r in s], float)
    return {"n": len(s), "hit_pct": round(hit / len(s) * 100, 1),
            "mean_call_excess_pct": round(float(ce.mean()), 3)}


def _scorecard(rows):
    settled = [r for r in rows if fl.is_true(r.get("settled"))]
    n = len(settled)
    n_hit = sum(1 for r in settled if fl.is_true(r.get("hit")))
    n_pending, n_dropped = fl.count_pending_dropped(rows)
    return {
        "n_settled": n, "n_hit": n_hit,
        "call_hit_pct": round(n_hit / n * 100, 1) if n else None,
        "bullish": _side_stats(rows, "看好"),
        "bearish": _side_stats(rows, "看淡"),
        "n_pending": n_pending, "n_dropped": n_dropped,
        "dropped_pct": round(n_dropped / max(1, n + n_dropped) * 100, 1),
    }


def _verdict(sc, lang="zh"):
    """数据层双语(2026-08-26):**分支只判一次**,中英从同一模板渲染——写两套 if 必然各自漂移
    (btc_nasdaq 那次的教训)。lang="en" 出英文版,au.html 在 EN 模式优先取 verdict_en。"""
    n = sc["n_settled"]
    if n == 0:
        key = "empty"
    elif n < 30:
        key = "small"
    elif 45 <= sc["call_hit_pct"] <= 55:
        key = "coinflip"
    else:
        key = "caveat"
    ch = sc.get("call_hit_pct")
    head_zh = f"已结算 {n} 条荐股：判断对(看好跑赢/看淡跑输 ^AXJO)的比例 {ch}%"
    head_en = (f"{n} settled picks: the share judged right (bullish beats / bearish lags ^AXJO) is {ch}%")
    V = {
        "empty": ("刚上线·0 结算——约 1 个月后才有第一批 AU 荐股战绩，攒数据中。",
                  "Just launched, 0 settled — the first AU pick results arrive in about a month; still accumulating."),
        "small": (head_zh + f"（n={n} 太小，纯描述、不是结论）。",
                  head_en + f" (n={n} is too small — descriptive only, not a conclusion)."),
        "coinflip": (head_zh + "——≈掷硬币，追因子没看出对 ^AXJO 的 edge（诚实）。",
                     head_en + " — about a coin flip; the momentum factor shows no edge over ^AXJO (honest)."),
        "caveat": (head_zh + "。重叠窗口/幸存者偏差/股息口径顺风未除，别当 edge。",
                   head_en + ". Overlapping windows, survivorship bias and the dividend-convention tailwind are "
                             "not removed — do not read it as an edge."),
    }
    return V[key][1] if lang == "en" else V[key][0]


def run(write=True, prices=None):
    rows = fl.read_log(LOG)
    seen = {_key(r) for r in rows}

    n_new = 0
    for p in _load_picks():
        if _key(p) in seen:
            continue
        seen.add(_key(p))
        rows.append({**p, "entry_date": "", "entry_px": "", "exit_date": "", "exit_px": "",
                     "ret_pct": "", "bench_pct": "", "excess_pct": "", "call_excess_pct": "",
                     "hit": "", "settled": False, "dropped": False})
        n_new += 1

    settled_now = 0
    unsettled = [r for r in rows if not fl.is_true(r.get("settled")) and not fl.is_true(r.get("dropped"))]
    if unsettled:
        try:                                   # 本地价格拼字典——AU 结算绝不联网(S-1)
            px = prices if prices is not None else _local_px()
            settled_now = _settle(rows, px)
        except Exception as e:
            print(f"[AU荐股计分] 结算阶段出错(非致命,跳过本次结算): {e}")

    sc = _scorecard(rows)
    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "澳股(ASX100大中盘池) 动量+低波动 选股 → 前向公开计分(独立账本)",
        "source_en": "AU stocks (ASX100 mid/large-cap pool) · momentum + low-volatility selection "
                     "-> forward public scoring (independent ledger)",
        "pick_rule": PICK_RULE, "pick_rule_en": PICK_RULE_EN,
        "hold_td": HOLD_TD, "benchmark": BENCH,
        "track_record": sc,
        "recent": sorted(
            [{"symbol": r["symbol"], "view": r.get("view"), "pick_date": r.get("pick_date"),
              "mom_pct": _num(r.get("mom_pct")), "settled": fl.is_true(r.get("settled")),
              "dropped": fl.is_true(r.get("dropped")), "excess_pct": _num(r.get("excess_pct")),
              "call_excess_pct": _num(r.get("call_excess_pct")), "hit": fl.is_true(r.get("hit"))}
             for r in rows],
            key=lambda x: (x["pick_date"] or ""), reverse=True)[:40],
        "verdict": _verdict(sc), "verdict_en": _verdict(sc, lang="en"),
        "caveat": ("出格区·澳股荐股前向公开计分,与美股 pick_ledger 完全独立的账本(基准不同不可比)。"
                   "挑票规则=%s,进 append-only 账本:出榜次日入场、持有 %d 交易日、相对 %s 结算。"
                   "看好命中=跑赢%s、看淡命中=跑输%s。**前向计分**:刚上线样本极小(约1月后首批),别当结论。"
                   "**股息口径不对称**:个股=含息复权总回报,%s=除息价格指数,存在≈股息率(AU~4%%/年"
                   "≈0.3%%/20交易日)的持续性口径顺风,对「看好」系统性有利——这不是edge。"
                   "franking(红利抵免)不含(无可靠免费源,宁缺勿猜)。池=ASX100大中盘(③扩池~108只·流动性档位见体检,不再全高档),"
                   "ASX本地日=交易日。FMG在池,1988-2002壳公司数据(2003起才是真Fortescue连续史),"
                   "本账本窗口只回看近期不跨越该段;长窗口回测(au_pick_backtest.py)另有截断逻辑。"
                   "池(ASX100大中盘)≈%s主要成分,超额天然被压(「打赢你自己」),AU集中度比美股更极端。"
                   "幸存者偏差%s%%因退市/无价被丢;重叠窗口只看描述;相关≠因果;"
                   "非投资建议、不可交易(成本/滑点/税)、会错、过去≠未来。每跑 append 认账。"
                   % (PICK_RULE, HOLD_TD, BENCH, BENCH, BENCH, BENCH, BENCH, sc["dropped_pct"])),
    }

    if write:
        from util_io import write_json
        write_json("au_picks.json", out)
        fl.write_log(LOG, HEADER, rows)
        print(f"[OK] au_picks.json — {out['verdict']}")
        print(f"  新增 {n_new} 条 · 本次新结算 {settled_now} · 已结算 {sc['n_settled']} "
              f"(判断对 {sc['call_hit_pct']}%) · 挂账 {sc['n_pending']} · 丢弃 {sc['n_dropped']}")
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    run()
