"""
au_checkup.py — 澳股诚实体检（B2·独立 🇦🇺 区）

stock_checkup.py 的 AU 配置级复用：**统计纯函数全部 import、一行不改**（EVT/依赖度/规律真伪/
保形区间/大跌分布/异动——全通用，β 基准换 ^AXJO）。美股路径零触碰（stock_checkup.py 仅
compute_basic_risk 加了带默认值的 beta_key 参数，回归门已验逐字节不变）。

诚实定位与美股版完全一致：描述这只票**是什么样**（风险/规律真伪），**绝不预测涨跌、绝不荐股**。

AU 特有（相对美股版的增量）：
  · 流动性档位：60 日中位日成交额 AUD（Close×Volume，源 raw/au/dollar_volume.csv）
    ≥$10M 高 / $1M–10M 中 / <$1M 低（低档=点差/滑点风险,谨慎解读）/ 数据缺失=unknown。
    ASX 前 100 之外流动性迅速变薄——这是 AU 体检对框架的增值项（美股精选池无此问题）。
  · FMG 身份连续性 / COL 短史标记透传（import fetch_data_au 的常量=单一真相源；
    FMG 1988-2002 为壳公司数据 → 长窗口统计结论解读须打折,B3 回测门另行处理）。
  · franking（红利抵免）**不含**：无可靠免费数据源,宁缺勿猜（B4 或做人工策展字段）。

FDR：跨【AU 全部票×效应】独立统一校正（_fdr_annotate_patterns 复用）——**绝不与美股池混**
（不同市场分别校正,与"独立平行区"设计一致）。

数据：raw/au/{name}.csv（fetch_data_au.py 产,单列 Close）+ AXJO.csv（β 基准）。
输出 au_checkup.json（PROC+WEB+DOCS,allow_nan=False）。fail-soft:缺数据的票如实标注,绝不编造。
"""
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

# 统计纯函数全部复用 stock_checkup（一行不改;见其文件头与回归门记录）
from stock_checkup import (MIN_DAYS, compute_basic_risk, compute_evt,
                           compute_market_dependence, compute_patterns,
                           compute_conformal, compute_dip_distribution,
                           compute_anomaly, _fdr_annotate_patterns)
# 池子/数据卫生标记的单一真相源 = fetch_data_au（B0/B1 定的:剔 NCM、COL 短史、FMG 身份留痕）
from fetch_data_au import STOCK_TICKERS, SHORT_HISTORY_NOTES, IDENTITY_NOTES

SCRIPTS = Path(__file__).parent
AU_RAW = SCRIPTS.parent / "data" / "raw" / "au"

# 中文名（编辑性内容·Fable 定;拿不准的用公司通用英文名,绝不硬造译名）
AU_NAMES = {
    "BHP": "必和必拓", "CBA": "澳联邦银行", "CSL": "CSL(血液制品)", "NAB": "澳国民银行",
    "WBC": "西太平洋银行", "ANZ": "澳新银行", "WES": "Wesfarmers", "MQG": "麦格理",
    "GMG": "Goodman(工业地产)", "WOW": "Woolworths(超市)", "TLS": "Telstra(电信)",
    "RIO": "力拓", "FMG": "Fortescue(铁矿)", "TCL": "Transurban(收费公路)",
    "COL": "Coles(超市)", "WDS": "Woodside(能源)", "QBE": "QBE保险", "STO": "Santos(能源)",
    "REA": "REA(地产网)", "ALL": "Aristocrat(游戏机)", "PME": "Pro Medicus(医疗影像)",
    "XRO": "Xero(财务软件)", "WTC": "WiseTech(物流软件)", "JHX": "James Hardie(建材)",
    "SHL": "Sonic(医学检验)", "COH": "Cochlear(人工耳蜗)", "AMC": "Amcor(包装)",
    "SUN": "Suncorp(保险)",
    # ── ③ ASX100 扩池新增(2026-08) ──
    # 银行/金融
    "ASX": "ASX交易所", "IAG": "IAG保险", "MPL": "Medibank(医保)", "NHF": "nib(健康险)",
    "CGF": "Challenger(年金)", "PPT": "Perpetual(资管)", "MFG": "Magellan(资管)",
    "GQG": "GQG Partners(资管)", "PNI": "Pinnacle(资管)", "NWL": "Netwealth(理财平台)",
    "HUB": "Hub24(理财平台)", "BEN": "本迪戈银行", "BOQ": "昆士兰银行", "AMP": "AMP(金融)",
    "IFL": "Insignia(资管/退休金)",
    # 材料/矿业
    "NST": "Northern Star(金矿)", "S32": "South32(矿业)", "MIN": "Mineral Resources(矿业)",
    "PLS": "Pilbara(锂矿)", "IGO": "IGO(锂/镍)", "LYC": "Lynas(稀土)", "WHC": "Whitehaven(煤炭)",
    "YAL": "兖煤澳洲(煤炭)", "ILU": "Iluka(矿砂)", "EVN": "Evolution(金矿)", "SFR": "Sandfire(铜矿)",
    "BSL": "BlueScope(钢铁)", "ORI": "Orica(炸药)", "NEM": "Newmont(金矿)", "CIA": "Champion Iron(铁矿)",
    "MND": "Monadelphous(矿业工程)", "ORA": "Orora(包装)",
    # 医疗
    "RMD": "ResMed(呼吸机)", "FPH": "Fisher&Paykel(医械)", "RHC": "Ramsay(私立医院)",
    "TLX": "Telix(放射药)", "SIG": "Sigma(医药分销)", "ANN": "Ansell(手套/防护)",
    # 消费
    "EDV": "Endeavour(酒类零售)", "JBH": "JB Hi-Fi(电器)", "HVN": "Harvey Norman(家居)",
    "TWE": "Treasury Wine(葡萄酒)", "A2M": "a2牛奶", "DMP": "Domino's(披萨)", "MTS": "Metcash(批发)",
    "LOV": "Lovisa(饰品)", "PMV": "Premier(服装零售)", "SUL": "Super Retail(运动/汽配)",
    "BRG": "Breville(小家电)", "FLT": "Flight Centre(旅行社)", "TPW": "Temple&Webster(家居电商)",
    "ARB": "ARB(越野配件)", "CKF": "Collins Foods(快餐KFC)",
    # 工业/物流
    "BXB": "Brambles(托盘物流)", "APA": "APA(天然气管道)", "QAN": "澳航", "ALX": "Atlas Arteria(收费公路)",
    "REH": "Reece(水暖分销)", "CPU": "Computershare(股权登记)", "DOW": "Downer(工程服务)",
    "CWY": "Cleanaway(废物处理)", "QUB": "Qube(物流)", "SVW": "Seven Group(工业/传媒控股)",
    # 能源/公用
    "ORG": "Origin(能源)", "AGL": "AGL(电力)", "BPT": "Beach Energy(油气)",
    # 地产 REIT
    "SGP": "Stockland(地产)", "GPT": "GPT(地产)", "MGR": "Mirvac(地产)", "DXS": "Dexus(写字楼)",
    "SCG": "Scentre(Westfield商场)", "VCX": "Vicinity(商场)", "CHC": "Charter Hall(地产资管)",
    # 科技/传媒/电信
    "NXT": "NextDC(数据中心)", "CAR": "CAR Group(汽车网)", "SEK": "Seek(招聘网)",
    "TNE": "Technology One(企业软件)", "NEC": "Nine(传媒)", "NWS": "News Corp(新闻集团)",
    "TPG": "TPG Telecom(电信)",
}

# 流动性档位阈值（60 日中位日成交额 AUD;机械规则,页面公示口径）
LIQ_HIGH_AUD = 10e6   # ≥$10M/日 = 高
LIQ_MID_AUD = 1e6     # $1M–10M = 中;<$1M = 低(点差/滑点风险)


def _load_au_close(name):
    """raw/au/{name}.csv（单列 Close,列名=ticker）→ pd.Series | None。"""
    f = AU_RAW / f"{name}.csv"
    if not f.exists():
        return None
    s = pd.read_csv(f, index_col=0, parse_dates=True).squeeze("columns")
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s if len(s) else None


def liquidity_tier(med_aud):
    """60日中位日成交额 → 档位。None=数据缺失(如实 unknown,绝不猜档)。"""
    if med_aud is None or not np.isfinite(med_aud):
        return {"status": "unknown",
                "note_zh": "成交额数据缺失，无法判定流动性档位。",
                "note_en": "Dollar-volume data unavailable — liquidity tier unknown."}
    tier = "high" if med_aud >= LIQ_HIGH_AUD else ("mid" if med_aud >= LIQ_MID_AUD else "low")
    out = {"status": "ok", "median_daily_aud_m": round(med_aud / 1e6, 1), "tier": tier,
           "window_days": 60}
    if tier == "low":
        out["note_zh"] = "低流动性：点差/滑点风险高，本页统计结论解读须更谨慎。"
        out["note_en"] = "Low liquidity: wide spreads/slippage risk — read the stats here with extra caution."
    return out


def _load_dollar_volume():
    f = AU_RAW / "dollar_volume.csv"
    if not f.exists():
        return None
    return pd.read_csv(f, index_col=0, parse_dates=True)


def run_all():
    print("=== 澳股诚实体检（B2·独立区·β 基准 ^AXJO·非荐股非预测）===")
    axjo = _load_au_close("AXJO")
    if axjo is None:
        print("⚠ 无 ^AXJO 基准（先跑 fetch_data_au.py），β/依赖度/异动将不完整")
        axjo = pd.Series(dtype=float)
    dv = _load_dollar_volume()

    out_tickers = {}
    for name, ticker in STOCK_TICKERS.items():
        px = _load_au_close(name)
        zh = AU_NAMES.get(name, name)
        if px is None:
            out_tickers[ticker] = {"name": zh, "status": "unavailable"}
            print(f"  {ticker:<8} 数据不可得（raw/au/{name}.csv 缺失）")
            continue
        risk = compute_basic_risk(px, axjo, beta_key="beta_axjo")
        risk["name"] = zh
        if risk["status"] == "ok":
            risk["evt"] = compute_evt(px)                              # 块1:EVT 尾部
            risk["market_dep"] = compute_market_dependence(px, axjo)   # 块2:对 ASX200 依赖度
            risk["patterns"] = compute_patterns(px, ticker)            # 块3:规律真伪(独立种子)
            risk["conformal"] = compute_conformal(px)                  # 块4:保形区间
            risk["dip_distribution"] = compute_dip_distribution(px)    # 大跌后完整分布(非抄底)
            risk["anomaly"] = compute_anomaly(px, axjo)                # 块6:当前风险状态(描述)
        # AU 特有:流动性档位(缺数据如实 unknown)
        med = None
        if dv is not None and ticker in dv.columns:
            m = dv[ticker].dropna().tail(60)
            med = float(m.median()) if len(m) >= 30 else None
        risk["liquidity"] = liquidity_tier(med)
        # 数据卫生标记透传(单一真相源=fetch_data_au 常量)
        if name in SHORT_HISTORY_NOTES:
            sh = SHORT_HISTORY_NOTES[name]
            risk["short_history_note"] = {"zh": sh["note_zh"], "en": sh["note_en"]}
        if name in IDENTITY_NOTES:
            idn = IDENTITY_NOTES[name]
            risk["identity_note"] = {"zh": idn["note_zh"], "en": idn["note_en"]}
        out_tickers[ticker] = risk
        if risk["status"] == "ok":
            liq = risk["liquidity"]
            ltxt = (f" · 流动性{ {'high':'高','mid':'中','low':'低'}[liq['tier']] }"
                    f"(${liq['median_daily_aud_m']}M/日)" if liq.get("status") == "ok" else "")
        else:
            ltxt = ""
        if risk["status"] == "ok":
            print(f"  {ticker:<8} 波动 {risk['ann_vol_pct']}% · 最深回撤 {risk['max_drawdown_pct']}%"
                  f" · β(AXJO)={risk['beta_axjo']}{ltxt}")
        else:
            print(f"  {ticker:<8} {risk['status']}（n={risk.get('n_days')}）")

    # FDR:AU 独立池统一校正(绝不与美股混)
    pattern_real = _fdr_annotate_patterns(out_tickers)
    cnt_v = lambda x: sum(1 for v in out_tickers.values() if v.get("patterns", {}).get("overall") == x)
    print(f"  规律真伪(三关后)：真规律 {cnt_v('has_real')} / faded {cnt_v('faded')} / "
          f"数据窥探 {cnt_v('data_snoop')} / 其余无规律或无定论"
          + ("  ⚠️ 触发停下(持续真规律候选需人工审视)" if pattern_real else ""))

    liq_cnt = lambda t: sum(1 for v in out_tickers.values()
                            if v.get("liquidity", {}).get("tier") == t)
    summary = {
        "n_tickers": len(out_tickers),
        "n_ok": sum(1 for v in out_tickers.values() if v.get("status") == "ok"),
        "pattern_real": cnt_v("has_real"), "pattern_faded": cnt_v("faded"),
        "pattern_hist_robust": cnt_v("hist_robust"), "pattern_data_snoop": cnt_v("data_snoop"),
        "liq_high": liq_cnt("high"), "liq_mid": liq_cnt("mid"), "liq_low": liq_cnt("low"),
    }

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "这是澳股的**风险画像**，描述它历史上是什么样——**不预测涨跌、不荐股、不给买卖点**。"
                  "β=对 ASX200(^AXJO) 的敏感度（风险特征非收益承诺）；流动性档位=60日中位日成交额的"
                  "机械分档（低档票点差/滑点风险高）。**不含 franking（红利抵免）**——无可靠免费数据源，"
                  "宁缺勿猜；税务影响请咨询专业人士。数据不足的票如实标注。ASX 本地日=交易日。",
        "benchmark": "ASX200 (^AXJO)", "min_days": MIN_DAYS,
        "liquidity_rule": {"window_days": 60, "high_aud_m": LIQ_HIGH_AUD / 1e6,
                           "mid_aud_m": LIQ_MID_AUD / 1e6,
                           "note": "60日中位日成交额(Close×Volume)机械分档,规则公示"},
        "patterns_fdr_real": bool(pattern_real),
        "summary": summary,
        "tickers": out_tickers,
    }
    from util_io import write_json
    write_json("au_checkup.json", out, proc=True, allow_nan=False)
    print(f"[OK] au_checkup.json（{len(out_tickers)} 票）")
    return out


if __name__ == "__main__":
    run_all()
