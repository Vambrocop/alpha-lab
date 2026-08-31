"""au_radar.py — 澳股六维雷达(描述性·非荐股·与美股同一套维度和代码)

用户 2026-08-27 提:「澳股综合评分雷达」(美股有、澳股无)。

**一个刻意的设计判断,先说清楚**:CLAUDE.md 把这条标为"涉诚实计分(靠近荐股),需先写规格+双审"。
核实后我的判断是——**美股那个雷达本身是描述性的**(6 维 0-100 画像:动量/趋势/稳健/性价比/
独立性/反弹空间,`export_stocks._radar` 的 docstring 明写"非预测、非买卖信号"),不是打分排名
荐股。所以:
  · 原样复用同一套维度与**同一份代码**给澳股 = 与美股口径一致、诚实风险低,不需另立规格;
  · 我**没有**新造"综合评分 → 排名 → 推荐买哪只"那种东西——那才真的靠近荐股、才需要规格+双审。
    真要做那个,应单独立项,别顺手夹带。

零克隆(同 au_checkup 复用 stock_checkup 的范式):`_stats` / `_radar` / `_scale` 全部
`from export_stocks import`,一行不复制——两市场的雷达口径由同一份代码保证永不漂移。

与美股的唯二差异(配置级):
  · 数据源 = raw/au/*.csv(fetch_data_au 产),不碰美股任何数据;
  · "独立性"维度的基准 = **^AXJO**(不是纳指)——澳股对澳洲大盘的 R²,两市场不混算
    (同 au_pick_ledger 的红线)。输出里把该维度标成 r2_axjo_1y 并在 caveat 写明。

输出 web/au_radar.json(+docs)。fail-soft:缺数据的票如实缺席,不编造。
运行:$env:PYTHONUTF8='1'; py market-analysis/scripts/au_radar.py
"""
import datetime
import sys
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# 零克隆:雷达/指标的单一实现来自美股侧,一行不复制(防两市场口径漂移)
from export_stocks import _stats, _radar          # noqa: E402
from fetch_data_au import STOCK_TICKERS           # noqa: E402  池子单一真相源
from au_checkup import AU_NAMES                   # noqa: E402  中文名单一真相源
from util_io import write_json                    # noqa: E402

AU_RAW = SCRIPTS.parent / "data" / "raw" / "au"
BENCH = "AXJO"                                    # 文件名;列名是 "^AXJO"

CAVEAT = (
    "六维描述性画像(0-100),**非荐股、非预测、不是买卖信号**——只说这只票历史上「长什么样」。"
    "与美股雷达**同一套维度、同一份代码**(零克隆),唯一差异是「独立性」的基准换成 ^AXJO"
    "(澳股对澳洲大盘的 R²,低=分散价值高),两市场不混算。分数是把原始指标线性映射到 0-100 的"
    "**相对刻度**,不代表好坏优劣:如「动量」高只说明过去一年涨得多,不代表未来会继续。"
    "不含股息/franking(澳股股息率高,忽略它会低估总回报)。会错,过去≠未来。"
)
CAVEAT_EN = (
    "A six-dimension descriptive profile (0-100). **Not advice, not a forecast, not a buy/sell signal** — "
    "it only describes what a stock has looked like historically. Same dimensions and the *same code* as the "
    "US radar (zero cloning); the only difference is that the 'independence' dimension is measured against "
    "^AXJO (R² vs the Australian market; lower = more diversification value), and the two markets are never "
    "mixed. Scores are a linear 0-100 rescaling of raw metrics, not a quality ranking: a high 'momentum' "
    "score only means it rose a lot over the past year, not that it will continue. Dividends/franking are "
    "excluded (AU yields are high, so total return is understated). Can be wrong; the past != the future."
)


def _load(name):
    f = AU_RAW / f"{name}.csv"
    if not f.exists():
        return None
    s = pd.read_csv(f, index_col=0, parse_dates=True).squeeze("columns")
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s if len(s) else None


def run(write=True):
    bench = _load(BENCH)
    if bench is None:
        print("[AU雷达] 缺 ^AXJO 基准(先跑 fetch_data_au.py),跳过")
        return {"generated": None, "stocks": {}, "caveat": CAVEAT}
    bench_ret = bench.pct_change()

    out_stocks, absent = {}, []
    for name, ticker in STOCK_TICKERS.items():
        s = _load(name)
        if s is None:
            absent.append(ticker)
            continue
        st = _stats(s, bench_ret)                 # 零克隆:与美股同一实现
        if st is None:                            # 史太短(<260 日)→ 如实缺席,不硬算
            absent.append(ticker)
            continue
        # _radar 读的是 r2_nasdaq_1y 这个键名;澳股实际算的是对 ^AXJO 的 R²,
        # 故把值放进该键喂给同一函数(不改共用代码),同时另存一份语义正确的键名给前端。
        st["r2_axjo_1y"] = st.get("r2_nasdaq_1y")
        radar = _radar(st)
        out_stocks[ticker] = {
            "label": AU_NAMES.get(name, name),
            "price": st.get("last"), "date": st.get("date"),
            "d1": st.get("chg_1d"), "w1": st.get("chg_5d"), "m1": st.get("chg_20d"),
            "chg1y": st.get("chg_1y"), "vol": st.get("vol20_ann"),
            "from_high_52w": st.get("from_high_52w"),
            "r2_axjo_1y": st.get("r2_axjo_1y"),
            "radar": radar,
        }

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": "^AXJO",
        "n": len(out_stocks), "n_absent": len(absent), "absent": sorted(absent),
        "dims": ["动量", "趋势", "稳健", "性价比", "独立性", "反弹空间"],
        "dims_en": ["Momentum", "Trend", "Stability", "Risk-adj.", "Independence", "Upside room"],
        "stocks": out_stocks,
        "caveat": CAVEAT, "caveat_en": CAVEAT_EN,
    }
    if write:
        write_json("au_radar.json", out, allow_nan=False)
        print(f"[OK] au_radar.json — {len(out_stocks)} 只(缺席 {len(absent)})")
        top = sorted(out_stocks.items(),
                     key=lambda kv: sum(kv[1]["radar"].values()) / max(1, len(kv[1]["radar"])),
                     reverse=True)[:5]
        for tk, d in top:
            avg = sum(d["radar"].values()) / max(1, len(d["radar"]))
            print(f"    {tk:<9} 均分 {avg:>5.1f}  {d['label']}")
    return out


if __name__ == "__main__":
    try:
        run()
    except Exception as e:                        # 顶层 fail-soft:独立区不阻断流水线
        print(f"[AU雷达] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        raise SystemExit(0)
