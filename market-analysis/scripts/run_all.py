"""
run_all.py — 一键运行完整流水线并同步部署目录

═══ 阶段 DAG 地图（R5·2026-07-07：哪步产出→谁消费；接手前先读这张图）═══════════
【A 取数】fetch_data(combined_prices/vix…) · long_history(SP500_long/NASDAQ_COMP_long)
    └→ 几乎所有下游；raw/ 全目录 gitignore(再生数据)——CI 干净检出没有它们,
       测试绝不许依赖(见 tools/pre_commit_gate.py 的 CI 同构门,#100-104 教训)
【B 独立统计族】placebo(日历防伪)→seasonality(原始计数) · event_causal · overreaction
    →overreaction_alert(计分账本) · risk_dashboard · market_regime · conformal · cycles
    · overnight_analysis(隔夜因子→walk_forward 特征) · fomc_study
    └→ 各写自己的 web/*.json;market_regime+overreaction 另被 stock_checkup/日读吃
【C 信号主链】analyze/timing_analysis/event_study/horizon_stats → build_signals①(daily_signals)
    → backtest → walk_forward(walk_forward_results·MODEL_VERSION 所在)
    → factor_pruning → fdr_crossfamily(全站显著性收口)
    → candidate_registry(锚·append-only)→ autodiscovery(148候选·BY-FDR·喂④) → cpcv(PBO)
    → vol_model/market_structure → track_predictions(prediction_log·append-only) → benchmark
    → build_signals②(把回测/验证/追踪嵌回 signals.json——「两遍」是刻意的,别合并)
【D 展示/出格层】export_chart_data/fx/stocks → stock_checkup → fetch_news → paper_trading
    → daily_brief/weekly_report/daily_digest → tipjar/outlook/composite_read(计分账本)
    → survivors_live(读 autodiscovery 存活→喂日读) → llm_daily_read → llm_monthly_read
    (周读【不在】此处:weekly-review.yml 周六生成完整周,勿再接回——07-07 撤重复的教训)
    → llm_prediction → btc_nasdaq_backtest/regime_forward → fetch_insider/fetch_ipo/fetch_data_au(均fail-soft)
    → au_checkup(独立区体检) → au_pick_ledger(B3·澳股荐股独立账本,零克隆 pick_ledger 规则)
    → insider_signal/pick_ledger → scorecard → evidence_ledger → knowledge_base(kb_ledger·OOS门4)
    → flicker
【E 封存/门禁/部署】ledger_sidecar(14账本哈希链) → verify_output(不绿不发布)
    → web/ 镜像 docs/(Pages 部署目录;check_docs_mirror 守漂移)
依赖铁则:改 C 链任何统计 → 全量跑通+pytest 绿+新旧指标对比;账本(append-only)绝不改历史行。
═══════════════════════════════════════════════════════════════════════════════

加 --full 参数会额外跑重型 ML 分析（advanced_analysis / multivariate）。
加 --light 参数只刷数据和信号（盘中小时级 CI 用）：跳过长历史/回测/walk-forward/
隔夜分析等重型步骤，复用上次全量运行的 data/ 产物（CI 里靠 actions/cache 恢复；
没有缓存时 build_signals 会退化到手设 LR，信号数字会与全量运行有出入）。
"""
import subprocess, sys, shutil
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS = Path(__file__).parent
WEB_DIR = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"   # 仓库根 docs/，GitHub Pages 部署目录

steps = [
    ("下载数据",           "fetch_data.py"),
    ("下载长历史数据",     "long_history.py"),
    ("规律置换检验placebo", "placebo_test.py"),         # P4-1：日历效应防伪（须在 long_history 后，复用其 SP500_long.csv）
    ("季节性原始计数",     "seasonality.py"),          # 补 placebo 没有的原始计数(逐月/任期年/Sell-in-May/世界杯全22届)，复用其数据不重算
    ("反事实事件影响",     "event_causal.py"),         # 方法B：回归反事实+bootstrap（SVB验证事件 + SPCX钩子）
    ("短期反转(过度反应)", "overreaction.py"),         # R3：极端下跌次日反弹检验(描述非建议,全样本vs现代)
    ("极端下跌→次日反弹告警(出格计分)", "overreaction_alert.py"),  # 敢预测敢认账:极端下跌日触发"次日偏涨"信号+Telegram推送+append公开计分+次日自动结算;须在 overreaction 后(引其现代统计);不入 light(盘后触发一次即可)
    ("风险仪表盘",         "risk_dashboard.py"),       # 方法D：VXN-VIX价差 + 条件下行(测风险不测方向)
    ("市场风险体制(R1)",   "market_regime.py"),        # R1：当前风险环境(VIX/收益率曲线/期限结构,描述非预测)
    ("收益区间(保形)",     "conformal.py"),            # 方法E：split-conformal 覆盖区间(测不确定性,非方向)
    ("周期检验(谱)",       "cycles.py"),               # 方法F：periodogram + AR1红噪声(测周期真伪,非预测周期延续)
    ("隔夜vs日内分析",     "overnight_analysis.py"),   # 产出隔夜动量因子数据
    ("基础统计分析",       "analyze.py"),
    ("买卖时机分析",       "timing_analysis.py"),
    ("历史事件研究",       "event_study.py"),
    ("持有期基率(长期视角)", "horizon_stats.py"),  # 复活:产 horizon_stats.json,由 build_signals 嵌入;须在 build_signals 前
    ("生成每日信号",       "build_signals.py"),
    ("回测验证",           "backtest.py"),
    ("滚动样本外验证",     "walk_forward.py"),
    ("因子样本外尸检",     "factor_pruning.py"),   # P2-5：因子记分卡 + 靶子探针（研究面板）
    ("跨检验族FDR收口",    "fdr_crossfamily.py"),  # P4-#5：汇池全站显著性主张做多重比较（须在 factor_pruning 后）
    ("候选注册登记(自生长P-A地基)", "candidate_registry.py"),  # append-only 锚点登记簿:每候选首次枚举即 stamp declared_date(OOS锚·不可改);须在 autodiscovery 前;扩N时给新候选盖当天锚;不入light
    ("自生长自动发现(出格)", "autodiscovery.py"),   # v1.5 Phase1b：42预声明候选(日历/反弹/因子)路由真统计→双栏BY-FDR三态裁决；须在 walk_forward+factor_pruning 后；不入 light(盘前/盘后全量才跑、同数据裁决不闪烁)；独立统计审 GO-WITH-FIXES(P1全清)
    ("大跌日诚实数据包(事实通报)", "downturn_brief.py"),  # W4a:大跌触发(纳指/标普单日≤-2.5%·VXSMH≥60+纳指≤-1.5%·VIX单日≥+15%)→合并一条Telegram(今日跌幅/VXSMH/连跌当前态+过校正数/长跨度当前态+过校正数/极端下跌次日分布/条件下行)；全部读现成json真实字段不重算；须在risk_dashboard+overreaction_alert+autodiscovery后(读三者产物)；append-only data/downturn_brief_log.csv每自然日限推一次；无token完全跳过不落账(同ipo_alerts取舍)；fail-soft;不入light(盘后触发一次即可)
    ("过拟合概率PBO",      "cpcv.py"),             # 方法G：CSCV/PBO 量化因子选择过拟合风险(升级验证、不加模型)
    ("波动率状态原型",     "vol_model.py"),        # P2-6：高信噪比靶子（研究面板）
    ("市场结构解释",       "market_structure.py"), # PCA共动 + 相关性体制（研究面板）
    ("实盘预测追踪",       "track_predictions.py"),
    ("Benchmark记分卡",    "benchmark.py"),        # 须在 track_predictions 后，读最新预测命中率；在第二遍 build_signals 前以便嵌入
    ("信号嵌入回测结果",   "build_signals.py"),   # 第二遍：嵌入最新回测/验证/追踪
    ("导出图表数据",       "export_chart_data.py"),
    ("导出货币汇率",       "export_fx.py"),       # fx_rates.json：CGT 计算器"显示货币"切换用(仅显示,不改税务计算)
    ("导出个股数据",       "export_stocks.py"),
    ("个股诚实体检",       "stock_checkup.py"),   # 个股风险画像(块0起)：复用 stocks_prices/combined_prices,非荐股非预测
    ("恐慌极值事件研究(描述)", "fear_extremes.py"),   # VIX高/极端恐慌尖峰后前向收益·纯描述非信号·事件级自助+LOCO;读combined_prices(VIX)+SP500_long/NASDAQ_COMP_long;须在long_history后;不入light
    ("跌了买持有一年诚实账(描述)", "dip_hold_study.py"),  # 52周回撤深度→持有1年前向收益vs基率·纯描述非买入信号·段级聚类自助(前向窗口去重叠);读SP500_long+stocks_prices;须在export_stocks后;不入light
    ("VIX波动预报力复现(描述)", "vix_vol_forecast.py"),  # 复现维基VIX vs实现波动散点·测波动不测方向;读combined_prices;纯描述;不入light
    ("恐慌贪婪合成表+逆向检验(描述)", "fear_greed.py"),  # ~4分量0-100情绪温度计(近似非CNN)+逆向情绪事件研究·纯描述非买卖信号;读combined_prices;须在fetch_data后;不入light
    ("大白话读三研究(LLM·描述)", "llm_honest_read.py"),  # 把dip/vixvol/feargreed真数字喂Gemini翻大白话+后置守门拦操作词·死守copy-guard;须在三研究后(读其JSON);无key静默跳;fail-soft;不入light(LLM)
    ("市场要闻RSS",        "fetch_news.py"),
    ("模拟盘执行",         "paper_trading.py"),
    ("每日盘后简报",       "daily_brief.py"),
    ("统计评估报告",       "weekly_report.py"),
    ("每日诚实摘要",       "daily_digest.py"),    # 三层(事实/留意/探索)诚实摘要;红线门禁禁方向/荐股词,须在体制/信号/模拟盘后
    ("试胆区(玩具预测+计分)", "tipjar.py"),       # 故意下方向判断但公开残酷计分(≈掷硬币),娱乐非建议;须在 fetch_data 后
    ("观点/预测(授权出格区)", "outlook.py"),      # 用户授权:直接给纳指方向+个股看好看淡,带免责;读 signals+动量,须在 build_signals 后
    ("综合读数(出格·加权倾向)", "composite_read.py"),  # 把体制/信用/羊群/季节性/信号按写死透明权重合成当下倾向,每日 append composite_log 计分(自升级地基);须在 market_regime+seasonality+build_signals 后
    ("存活规律观察台(自生长·喂日读)", "survivors_live.py"),  # 读autodiscovery存活候选(verdict==survive)+本地算"今天是否应期"(金叉/BTC动量/回撤/9月)→survivors_live.json;历史edge复用不重算(单一真相源);喂 llm_daily_read + 前端观察台;须在autodiscovery后、日读前;不入light(autodiscovery全量才刷);缺数据静默退0
    ("LLM大白话日读(出格)", "llm_daily_read.py"),   # 把 composite_read 真因子喂 Gemini→一段人话解读;须在 composite_read 后;无 GEMINI_API_KEY 则静默跳过;喂真数据防瞎编、带计分
    # 周读【不】进 run_all:由专门的 weekly-review.yml(周六 cron·收盘后·覆盖完整 Mon-Fri)生成——
    # 比这里周五盘前跑更完整(2026-07-07:一度误加此处,会用不完整周 dedup 掉周六完整周,已撤)。
    ("LLM大白话月报(出格)", "llm_monthly_read.py"),  # 本月综合倾向走势+月末体制→Gemini 翻大白话回顾;月末最后4天才生成、本月只调一次(节流);无 key 静默跳;喂真数据防瞎编、append 月级公开计分
    ("LLM前瞻预测→公开计分(出格)", "llm_prediction.py"),  # LLM 据真因子对 SPY 未来5交易日出方向(偏多/偏空/中性)+信心→append-only账本→满5日按SPY真实涨跌分桶结算记命中;按信心分桶看高信心是否真更准;须在composite_read后;无key静默跳;Opus审GO;前向计分·敢预测敢认账·非投资建议
    ("BTC动量→纳指回测(出格)", "btc_nasdaq_backtest.py"),  # 红线审计🟡#1:唯一穿过FDR的方向规律,诚实回测(条件分布/带成本overlay/多体制/计分);读 combined_prices,独立审 GO-WITH-FIXES已修
    ("体制→前向分布(出格)", "regime_forward.py"),   # 红线审计🟡#2:倒挂/VIX/信用利差→SP500前向收益分布(重标独立事件段);读 combined_prices,描述性
    ("预FOMC漂移事件研究(出格)", "fomc_study.py"),   # Lucca-Moench 先验:FOMC公告前1交易日SP500偏强?块自助 p+逐十年(2010s真→2020s反转);读SP500_long+硬编码FOMC日期;探索性未入FDR池;不入light
    ("内部人买入取数(SEC Form4)", "fetch_insider.py"),  # 抓近期开市买入P写insider.json;SEC daily-index,需 SEC_UA_CONTACT(secret);SEC失败静默退0不阻断;不入light(日更一次即可)
    ("IPO近期申报取数(SEC EDGAR)", "fetch_ipo.py"),  # 抓近30天S-1/424B申报写ipo_filings.json(IPO雷达页事实层);SEC全文搜索,复用SEC_UA_CONTACT;含大量小盘/空壳非策展;失败静默退0不阻断;不入light(日更一次即可)
    ("澳洲市场取数(独立区)", "fetch_data_au.py"),
    ("澳股诚实体检(独立区)", "au_checkup.py"),   # B2:stock_checkup 纯函数复用到 ASX100(β=^AXJO+流动性档位+FMG/COL标记透传)→au_checkup.json(au.html 🩺模态读);美股路径零触碰(回归门已验逐字节);FDR AU独立池;须在 fetch_data_au 后;不入 light  # B1:^AXJO/AUDUSD/ASX100→au_market.json+au_probe.json(au.html 独立市场概览页读);独立平行区,不碰美股任何脚本/数据/账本;fail-soft 不阻断;不入light(日更一次即可)
    ("澳股荐股→前向计分(出格·独立账本)", "au_pick_ledger.py"),  # B3:pick_ledger配置级克隆(_select_picks/_outcome/_followable零克隆import)+^AXJO本地取价结算(forward_ledger零改,从不联网);独立账本data/au_pick_ledger.csv(与美股不混);须在fetch_data_au后;宽表(raw/au/au_stocks_prices.csv)暂缺时fail-soft空跑;不入light
    ("澳股荐股回测轨迹披露(出格)", "au_pick_backtest.py"),  # B3附:同一规则(_select_picks零克隆)历史轨迹披露→au_backtest.json(au.html 📜模态读);含幸存者偏差·系统性偏乐观(页面大字);须在fetch_data_au后;顶层fail-soft(sys.exit0)不阻断;不入light
    ("澳股跌了买持有一年诚实账(描述)", "au_dip_hold_study.py"),  # 澳股版dip_hold:复用US已审统计核(去聚集/聚类自助/前向窗去重叠)换^AXJO全历史+CGT持1年口径→au_dip_hold.json(au.html 📉板块·噪音识别);读raw/au/{AXJO,au_stocks_prices}.csv;须在fetch_data_au后;顶层fail-soft不阻断;不入light
    ("IPO重大性分层富化(SEC Exhibit107)", "ipo_enrich.py"),  # A2:从ipo_filings.json机械分层🔴major/🟡notable/rest(策展名单/母市值/拟募资/SPAC);读SEC submissions+EX-FILING FEES结构化费用,复用SEC_UA_CONTACT;金额只升档·未知不升档·绝不正文刮数;fail-soft(炸掉→原始json完好·前端显未分层);须在fetch_ipo后;不入light;SEC限流退避·本地分批top-up
    ("IPO重大事件预警(出格·事实通报)", "ipo_alerts.py"),  # A3:major公司状态档(filed/priced/listed取最高)首见即append事件账ipo_alert_log+合并一条Telegram(tag=IPO雷达·事实通报·上市≠值得买非荐股);去重键(cik,stage)绝不改历史行;推送失败pushed=False留痕不重推(见其文件头取舍);须在ipo_enrich后;fail-soft不阻断;不入light
    ("IPO挂牌后事实档(出格·非计分)", "ipo_aftermath.py"),  # A5:对ipo_alert_log里stage∈(listed,priced)带ticker的major公司,yfinance抓其日线记D1/D5/D20相对首日收盘+vsQQQ同窗超额→data/ipo_aftermath_log.csv(append-only·每ticker取最后一行为准)+web/ipo_aftermath.json(含Ritter长期跑输文献caveat);事实档非计分非荐股;须在ipo_alerts后(读其账本);单票无数据fail-soft跳过;不入light

    ("内部人买入→前向计分(出格)", "insider_signal.py"),  # 跟内部人买的诚实前向公开计分:append notable买入+到期vs SPY自动结算;须在 fetch_insider 后;读yfinance(结算出错不阻断);不入light
    ("荐股→前向计分vsQQQ(出格)", "pick_ledger.py"),  # outlook看好/看淡进append-only账本+满20交易日vs QQQ自动结算(看好命中=跑赢/看淡命中=跑输);须在outlook后;读yfinance(结算出错不阻断);不入light
    ("公开计分/校准卡(吸收)", "scorecard.py"),   # 4站调研吸收:汇 prediction_log/composite/tipjar + walk_forward OOS校准成公开战绩卡(按置信分桶看实际命中=护城河);须在 track_predictions/composite_read/walk_forward 后
    ("证据库总览(吸收)", "evidence_ledger.py"),   # 把已测规律族汇成单一诚实总览(每族 scope+证据+裁决+详情链接·没证据不进库);须在 autodiscovery/placebo/btc/regime 后
    ("门4样本外→知识库晋升降级(自生长P-C)", "knowledge_base.py"),  # OOS门4(oos_gate)只认注册锚后数据:survive∧confirmed→晋升/在库∧翻盘→降级;append-only单调写kb_ledger;须在autodiscovery+candidate_registry后;不入light;Opus双审GO(B1/S1已修);今日全pending=0晋升(边跑边攒约1月出首批)
    ("防闪烁稳定度(自生长P-B)", "flicker.py"),   # 读autodiscovery_log前向史:抓在FDR边界来回横跳的脆弱候选+诚实标注"裁决稳定≠独立确认(自相关)";纯描述不引新统计;须在autodiscovery后;不入light
    ("账本sidecar哈希链封存", "ledger_sidecar.py"),  # P2-9:14个append-only公开计分账本的链哈希存独立manifest(账本本体零写入);身份字段verify-before-seal被改则拒封;须在全部账本写手后、verify前;入light(无变化=no-op,顺带小时级抓外改)
    ("发布前自检",         "verify_output.py"),   # 失败则终止，不发布坏数据
]

full_steps = [
    ("高级ML分析",         "advanced_analysis.py"),
    ("多元统计分析",       "multivariate_analysis.py"),
    ("导出多元分析数据",   "export_multivariate_json.py"),
]

# 盘中轻量模式：只保留"数据刷新 + 信号 + 前端产物"链路，分析类产物吃缓存
LIGHT_STEPS = {
    "fetch_data.py", "build_signals.py", "track_predictions.py",
    "export_chart_data.py", "export_fx.py", "export_stocks.py", "fetch_news.py",
    "paper_trading.py", "daily_brief.py", "weekly_report.py",
    "ledger_sidecar.py", "verify_output.py",
}

if "--full" in sys.argv:
    # 重型分析放在导出图表数据之前
    steps = steps[:-1] + full_steps + steps[-1:]
elif "--light" in sys.argv:
    steps = [(label, s) for label, s in steps if s in LIGHT_STEPS]
    print("※ light 模式：跳过长历史/回测/walk-forward/隔夜分析，复用上次全量产物")

for label, script in steps:
    print(f"\n{'='*55}")
    print(f"  ▶  {label}  ({script})")
    print(f"{'='*55}")
    r = subprocess.run([sys.executable, str(SCRIPTS / script)])
    if r.returncode != 0:
        print(f"\n✗ [{label}] 失败，已终止")
        sys.exit(1)

# ── 同步部署目录：web/ → 仓库根 docs/ ──────────────────────────
print(f"\n{'='*55}")
print(f"  ▶  同步部署目录  web/ → {DOCS_DIR}")
print(f"{'='*55}")
DOCS_DIR.mkdir(exist_ok=True)
web_names = set()
for f in WEB_DIR.iterdir():
    if f.is_file():
        shutil.copy2(f, DOCS_DIR / f.name)
        web_names.add(f.name)
        print(f"  ✓ {f.name}")
# 清理 docs/ 里 web/ 已不存在的部署文件（如拆分后残留的旧 app.js）；保留 .nojekyll 等点文件
for f in DOCS_DIR.iterdir():
    if f.is_file() and not f.name.startswith(".") and f.name not in web_names:
        f.unlink()
        print(f"  ✗ 清理残留 {f.name}")

print("\n✓ 全部完成！打开 web/index.html 查看仪表盘，git push 后部署生效")
