# HANDOVER.md — Fable 缺席时的接力手册

更新:2026-07-07(Fable 5 起草)。**触发条件:本会话主脑模型不是 Fable 5 → 先读完本文件再动手。**
(哪怕是 Fable 自己回来,也从 §3 任务队列对表开工;做完任何一项就更新队列。)

## 0. 任何模型开工前必读(顺序)

1. `CLAUDE.md`(约定+方向定调+铁律)
2. 本文件(角色分配+任务队列+CI 手册)
3. `DAILY_LOG.md` 最近几天 + `OPTIMIZATION_LOG.md` §2(计划记档)·§4c(试过但否决)·🪦坟场·📋登记簿
4. **先查后动铁律**:收到"做 X"→ 先报"之前做过没/做成啥样/有无结果"→ 再动手

## 1. 角色分配(按当天可用的最高模型)

| 场景 | 主脑(编排/判断/终审) | 建造 | 审查 |
|---|---|---|---|
| Fable 5 可用(作主循环) | Fable 5 | Sonnet(机械)/Fable(判断密集) | Opus(全新上下文) |
| Opus 作主循环 | **Opus 主公在场决断+调度+终审;Fable 5 作军师子代理出谋略/规格/设计** | Sonnet | 全新上下文 Opus |
| 只有 Sonnet | 不设主脑 | 只做队列里标 **[机械]** 的任务 | 单审(另一个 Sonnet 全新上下文) |

> **班子结构(用户 2026-07-10 定)**:Opus 主循环=主公(在场对话/最终决断/调度/终审),
> Fable 5=军师(判断密集的谋略/规格/设计方向,作被咨询子代理),Sonnet=执行。
> Opus 遇判断重的决策咨询 Fable,琐碎机械活直接执行(别每步往返烧 token)。详见 memory
> `org-fable-strategist-opus-executes`。
> **任务类型映射(用户 2026-07-10 精化)**:Fable=规划/拆任务/评审/综合;Opus=架构设计/复杂调试/
> 算法推理;Sonnet=样板代码/测试/格式化/小改动。→ 测试/样板/小改一律下沉 Sonnet,Opus 守架构/算法/难调试。

**📌 陈旧数据处置(件3·2026-07-10 军师定案·已落地)**:三源三治——
- **senate**:文档明写"结论已定·改方法论才手动重跑"=按设计静止,非故障。只补前端标注。
- **insider + ipo**:SEC 封 GitHub Actions 数据中心 IP(本地住宅IP能抓·CI 不能)。**定案 accept+诚实标注+
  本地兜底,不花钱不绕封锁**(proxy 对诚实站是规避 SEC 公平访问的气味问题)。**关键操作:本地跑
  `run_all` 时这俩 SEC 步(fetch_insider/fetch_ipo)自动补齐**——所以隔段时间本地跑一次流水线即 top-up。
  CI 那步保留(fail-soft 无害),别指望 CI 修好它。前端标注读真时间戳、不承诺固定周期。
- **ndx**:成分源页面改版→解析器坏(本地也炸)。可修 bug,排末位(B3·带停机护栏:源页若需 JS/登录/付费墙则停报)。
- watchdog 已扩栏(42dc8ee):insider/ipo=known-limited 21天松阈值兜底,ndx=live 14天该催。前端标注(B1)扛日常披露。

- 铁律不变:**审查者 ≠ 建造者 ≠ 同一上下文**;公开统计结论/模型链 = 双审,常规聚合展示 = 单审
- 六步协议不变:①写规格 → ②独立审规格 → ③建造 → ④独立审实现 → ⑤修复 → ⑥验证提交
- 只有 Sonnet 时,凡标 **[判断]** 的任务一律不碰,留言给用户等高层模型
- 与用户协作风格(用户明确偏好):**考虑+平衡最优解,不顺着点头**;诚实技术异议 > 虚假认同;
  遇判断点(口径选择/结果反直觉/规格有洞)**停下报告,不要自行决定**

## 2. 铁律速查(细则见 CLAUDE.md)

- append-only 账本**绝不改历史行**:prediction_log / paper_ledger / autodiscovery_log /
  candidate_registry / kb_ledger / ledger_hashchain(sidecar 哈希链 + git-HEAD 门 4c 双锁在守,别绕)
- 不绕 verify_output / pytest 门禁;`--no-verify` 禁用;门禁 deny 了修根因,不是找路绕
- 秘钥只走环境变量 / GitHub Secrets,绝不进仓库/日志/记忆
- Windows:用 `py` 不用 `python`;先 `$env:PYTHONUTF8='1'`
- web/ 改动镜像到 docs/(Edit 后手动 Copy-Item;提交前 `git status` 核对 docs/ 同步)
- 前端不引境外 CDN(中国访客);资源同源自托管
- 改公开统计口径 = [判断] + 双审 + commit message 附新旧指标对比 + bump MODEL_VERSION(若动模型)
- push 前先 fetch(CI 每 2 小时自动提交数据)

## 3. 任务队列(2026-07-07 快照;做完一项更新一项)

**T1 [判断·双审] `_regime_arrays` 尾窗 y=0 同款 bug** — ✅ 完成(2026-07-07·Fable 建·Opus 审·Opus 主脑收尾)
- 修:`_regime_arrays` 暖机段(前199天200日均线未定义)`.where(ma200.notna())`→NaN 被 dropna;
  fwd 以 float 先进 df 再 dropna 后派生 y。factor_model.build_features 尾月同款一并修。
- 结果:真数据裁剪精确 −219(199暖机+20尾窗);全104池新旧复算**零 verdict 翻转·新旧同存活集**
  (golden_cross_sp500 p 0.001→0.000 更显著仍 survive);新增合成回归锁(突变测试证可杀旧码)。
- R2 全库清扫连带做完:其余前向窗构造点已合规;fomc_study 同日 up-rate(非前向·池外)非同类。
- 提交:995a051(代码)+1cb6734(数据);全新 Opus 独立审 APPROVE 零 blocker。
**T2 [中·单审] 新存活者 survivors_live 描述符**
- `legacy_noncomm_pct_oi_lo_h60_nasdaq100`(COT 纳指仓位极空)现在观察台是"未接入"中性兜底
- 要 usable_from 感知的当前状态计算(点时间纪律:可用日=report_date+4 交易日,别用 report_date)
- 参考:survivors_live 现有描述符写法 + `_positioning_arrays` 的状态定义
**T3 [机械·Sonnet 建·Opus 审] #5 W3:app-4.js 全量双语** — ✅ 完成(2026-07-07)
- Sonnet 建(~223 vpL·SPCX/CGT/恐贪/指数/个股/时钟/小游戏·Plotly 占位符保留·里程碑 label
  渲染时 vpL·`_CLOCK_CN_DOW`/`CGT_CURRENCIES` 消费处包 vpL);Opus 审 APPROVE(插值两侧齐·
  免责语忠实·零逻辑/存储改动·reRenderAppTools 幂等)。
- **集成缺口(主脑亲接)**:renderAll 覆盖 SPCX追踪/指数/实时/个股/恐贪/时钟;CGT计算器+SPCX明细/
  计算+小游戏不在 renderAll → 新增幂等 `reRenderAppTools()`(app-4)+dashboard.html toggle 加一行调用。
- **实测**:playwright 切换 → SPCX 零残留中文·CGT 完整变英文(含 AUD 税务免责语)·html lang=en·零报错。
- 后端自由散文 i18n **不在本任务**(用户单独决定);#5 五文件(app-1/2/3/4/5)双语**全完成**。
**T4 [判断·日历 ~2026-08 初] #2 KB 首批晋升验收**
- 锚 2026-06-26 + 2026-07-05;min_oos_n=30 攒够后 kb_ledger 首批晋升
- 验收=亲验 oos_gate 裁决合理性(逐条看数字),不是看它跑完
**T5 [判断·日历 ~2026-08] #3 AI 预测页增强** — ⚠️ **前提未达成,已改做别的(2026-09-03·42b4c1c)**
- 原计划:等 ~20+ 结算样本后"按信心分桶"丰富 prediction.html。
- 核实:已结算 39 条,但**真正押方向(偏多/偏空)的只有 2 条**,其余全是"中性"。
  等的是方向样本,攒到的是中性样本 —— 前提没达成,而且**信心分桶其实早就建好了**(页面上一直有三桶)。
- 改做了更要紧的:**修基线**。页面原写"三桶随机基线 1/3",但三桶不等概(中性 61.5%),
  正确门槛是多数类基线;按它比,59.0% 其实**不如**"每天闭眼说中性"(p=0.692)。
  连带修 scorecard.html 用 n=1 发布"0%"加粗当头条。详见 42b4c1c。
- **仍待**:等方向下注攒够(现 2 条)才谈得上"AI 方向判断力"。**这仍是时间门,写代码加速不了。**
**T6 [机械·小] IPO 数据定期更新自动化** — ✅ 大体已完成(2026-07-07 查明)
- **自动事实层已自动化**:`fetch_ipo.py`(SEC EDGAR·S-1/424B)早在 run_all(L80)·每日随 Refresh 跑·
  **失败静默退0不阻断**(结构上不会引发 #100-104 那类门禁红)。本地实跑健康(07-07·60 S-1/48 424B)。
  之前卡 07-02 是被昨晚 CI 红连累(流水线没跑到抓 IPO 步),CI 修后自愈;265d064 已手动补新。
- **策展明星层(SpaceX/Cerebras/传闻档)硬编码在 ipo.html·本质不可自动化**:估值/传闻/承销商=人工/媒体判断,
  SEC 无此数据(见 fetch_ipo 诚实边界)。已自标"2026-06 快照"。留人工定期更新,别硬凑自动化。
**T7 [大工程] v1.5 自生长自动发现闭环 — 单独立项+重审,不要顺手做**(用户定过调;Fable 在场时做)

**⏳ 待续更新(2026-07-07 Fable 回归·当日全清)**:
- ~~R5~~ **✅ 完成**:run_all.py docstring 现有五阶段 DAG 地图(A取数→B独立统计→C信号主链→D展示/出格→E封存门禁),接手先读它。
- ~~Telegram 卡住推送~~ **✅ 完成**:`staleness_watchdog.py` 挂 quick-quotes.yml(独立班次·CI红时仍跑),
  读已提交的 signals(>3天)/llm_read(>4天)/llm_weekly(>9天) 时间戳,超期发 Telegram(tag=watchdog),
  `data/watchdog_state.json` 按(产物,日)去重防刷屏、发失败不记dedup下一班重试;5条守门测试。
  **观察哨:下次盘中(quick-quotes 班次)确认该步首跑不红**。
- **周读 07-04 未更新之谜(仍开)**:weekly-review.yml #2(07-04)"成功"却没提交 W27。已手动补 W27。
  **下周六(07-11)盯它是否正常出 W28**;若又没出:现在有 watchdog 了,周读卡>9天会自动 Telegram 敲门,
  届时查该 run 日志(commit 步/LLM调用/rebase冲突)。周读唯一生成器=weekly-review.yml(勿接回 run_all)。
- 两个 §3 边角(EVT to_datetime 防御/脱钩边界测试)核实**均已存在**,§3 已改标——不是待办。
- **陈旧可见性已上线**:周/月/日读卡片超期自曝(index/dashboard),月读七月起 relabel"上月回顾"。

**🎨 设计冲刺(SPEC 见 docs_internal/DESIGN_SPRINT_SPEC.md;Fable=设计总监,实现才外包)**:
- ✅ **D1 视觉系统**(7d9cce7·Opus建):双CSS令牌并轨(dashboard绿红黄并到正典)/数字tabular-nums/
  卡片三级重量类/--font-sys 统一。
- ✅ **D2 微图表**(f7bee6c·Sonnet建):vp_spark.js 零依赖;倾向分30日(hero双页·composite_read
  加history纯聚合)/模型概率60日(0.5参考线)/体制成分分位条(3根,诚实只画有percentile的)/恐贪7点。
  配色纪律=走势线一律中性,绝不按涨跌染线。pytest 540。
- ✅ **D3 探索式交互**(681a94a=D3a·005014d=D3b):40日概率热力横带(hover/tap tooltip·
  Pointer Events 修触屏bug)/个股行手风琴展开体检摘要/vpRangeBar 四图范围切换(原生
  rangeselector 下线,10年档 Fable 裁不补)/gloss 双语词条+15·全站 autoscan 覆盖·harness 修复。
- ⏳ **D4 克制动效 / D5 首页IA(要线框)**:待用户拍板再开。
- 设计遗留(下轮候选):JS内联色清理·hero卡片全站铺开(D5)·两套品牌紫并轨(品牌决策要用户/Fable定)·
  观察台应期带(需后端导出历史)·.fg-spark*/RANGE_SEL 死规则清理·其余日期轴图逐图接 vpRangeBar
  (组件已通用一行接入)·gloss 语言切换不刷新时旧注解不换语言(既有行为)·
  **数据新鲜度待查:insider/ndx/senate 8-18天旧**(D3b 顺手发现,流水线侧,先查后动再修)。

**🎲 连跌/反转确认候选族(用户2026-07-10提·规格①已定稿 d479c05)**:SPEC_STREAK_FAMILY.md——
两子族30候选(连跌3/4/5天事件日+连跌后首涨确认日)·先验先于数据(只数过次数未看结果)·
N_DECLARED 104→134·既有候选零翻转停机条件。**待用户点头进②审规格→建造→登记**。

**下一个该做(建议顺序)**:T3(机械·Sonnet 独立可做,无判断)最省主脑;T2(单审·中等,点时间纪律
是唯一坑)Opus 或 Fable 皆可;T4/T5 等日历(~8月初)。**T7 大工程留 Fable 在场时立项**。

**CI 观察哨**:07-07 已修 #100–104 测试红(见 §4);Refresh 只在 schedule(13:00/21:30 UTC)跑,
**不随 push 触发**——下一班 schedule 才会验证测试门禁转绿(门禁已 CI 同构,置信度高)。
COT/P·C fetch 步骤(每交易日盘后一次)CI 尚未首跑——fail-soft 只出 warning,跑后查 warning。

## 4. CI 红处置手册(2026-07-07 教训固化)

1. **查**:公开 API(无需 gh/token)——
   `Invoke-RestMethod ".../repos/Vambrocop/valpha-lab/actions/runs?per_page=10"` → 定位失败 run
   → 取其 `jobs_url` → 看哪个 step failure(job 日志 API 要授权,不用管它)
2. **复现**:`git archive HEAD` 解到临时目录 → `PYTHONUTF8=1 py -m pytest market-analysis/tests -q`
   ("本地绿 CI 红"九成 = 测试依赖了 gitignore 生成数据;CI 的数据缓存恢复在测试**之后**)
3. **修根因**,不绕门禁、不改工作流顺序迁就坏测试
4. **防复发已固化**:`tools/pre_commit_gate.py` 现在就是干净检出跑 pytest(CI 同构)——
   树内绿而门禁红 = 同款问题,提交那一刻就会被拦
5. 规矩:门禁测试不依赖 `data/raw/` 等 gitignore 数据;确需真数据的测试 → 缺数据 `pytest.skip`,
   同一性质必须另有合成数据版恒跑(样例:`test_arrays_exclude_days_without_realized_forward_window`)

## 5. 架构评估与升级路线(Fable 2026-07-07;供接手者排期,非本日任务)

**总判断**:统计核心(candidate_space → autodiscovery → oos_gate → registry → sidecar+git 双锁)
是护城河,结构健康,**别动它的架构**;债主要在 web 层重复与流水线隐式依赖。

- **R1 [小·automation-first]** docs/ 镜像漂移自动门:verify_output 加 web/↔docs/ 关键文件
  一致性检查(镜像 DRIFT 已人肉抓过≥2 次,该上机器门)
- **R2 [小·并入 T1]** 尾窗 NaN 全库清扫:grep 所有前向窗构造点(`fwd`/`> 0`/`astype(float)`),
  列清单逐一判定是否同款 bug,一次审干净
- **R3 [中]** `build_feature_df` 多脚本重复构建 → 参数哈希缓存(parquet);**先测量耗时占比再做**
- **R4 [中·克制]** web 公共微工具收敛(_fetchJson/esc/localStorage 防抛已有雏形→vp_core.js 统一);
  **不做** SPA/前端框架/构建链(中国访客+同源自托管是硬约束)
- **R5 [小]** run_all.py 阶段 DAG 注释显式化(哪步产出谁消费——新模型接手最缺这张图)
- **R6 [观察]** CI 每 2h 数据提交 → 仓库历史膨胀;暂不动(Pages 吃 main),clone 变慢再议 data 分支
- **R7** = T7(自生长闭环,单独立项)

**明确不做**(设计定调,别翻案):前端框架/打包链引入、多市场(A股/港/日韩)、任何绕门禁的捷径。

---

## 6. 后续规划:IPO 雷达扩展 + 澳洲市场(Fable 2026-07-12 战略设计 · 待用户拍板 WHAT)

> 触发:海力士(SK Hynix)2026-07-10 纳斯达克首秀,新闻层看到、IPO 雷达没覆盖(只抓 S-1/424B 美本土)。
> 用户明确要:①补雷达发现重大新股+提前预警 ②加澳洲市场(页面/个股/荐股)。
> 两案共同骨架:**不加新统计方法、不碰 C 信号主链,全落 D 层 fail-soft + 独立账本 → 分批提交低风险**。
> **澳洲市场自 2026-07-12 起纳入范围**(用户定),与仍不做的 A股/港/日韩区分开。

### 命题 A:重大 IPO 提前预警(事实/日历层 · 非荐股)
诊断:外国大厂来美两条路径现架构都漏——① 募资 IPO `F-1→424B`(F-1 漏);② 不募资 ADR 直挂 `F-6+8-A12B`(全漏)。SEC 表格无预期上市日(须交易所日历,独立第二层)。
- **A1[小·可先行·堵缺口]** `fetch_ipo.py` forms 加 **F-1**(标 foreign 徽章)+ **8-A12B**("已注册挂牌"干净信号;**不抓 F-6**=OTC ADR 噪音大)。单提交即接住下个海力士。
- **A2[核心工程]** "重大"自动分层:拟募资额(EX-FILING FEES XML)/母市场市值(yfinance)/SPAC 过滤(SIC 6770)/策展名单命中 → 🔴重大 / 🟡值得注意 / 其余原始流。**机械规则公示,防吹票机**。
- **A3** 重大档新事件 → `notify_telegram`(tag=ipo)+ append-only `ipo_alert_log.csv`(推送进账本,可审计"何时知道")。
- **A4[可选]** 时效层:Finnhub IPO calendar(免费 key·CI 可用·澳可达)给预期日;纯 SEC 是本地日频事实锚。
- **A5[可选·Fable 强荐]** 复用 `forward_ledger`:挂牌后 D1/D5/D20 vs QQQ 事实档(页面挂"IPO 长期跑输基率"=anti-hype);预警质量计分(lead_time)+ **漏报(missed)也记账**=诚实计分对自己的延伸。
- 停机点:若有人要"给 IPO 打分/评级"→ 停(那是荐股滑坡)。

### 命题 B:澳洲股市(独立 🇦🇺 区 · 不碰美股体系)
IA 裁定:**独立平行区**(非全局开关/非页内混排——避免双基准双币污染诚实计分)。index `GROUPS` 加 🇦🇺 组(第二位);首页近期仍美股为主(150盘/雷达/账本战绩都在美股),AU 攒出战绩再谈升默认。**时区隐藏点**:ASX 本地日=交易日(与美股"快一天"注释相反),每个 AU JSON 独立标 as-of、绝不与美股同框不标日期差。
- **B0[探针·先验证]** `fetch_data_au.py`(^AXJO/^AORD/AUDUSD+ASX50),报史深。多数票史不足 → 停缩池。
- **B1[MVP 可见]** index 🇦🇺 组 + `au.html`(ASX200/AUDUSD/ASX50 榜·纯描述·zh/en)。
- **B2** `stock_checkup` 参数化复用到 .AX(β 基准换 ^AXJO + **流动性档位**=AU 增值项)。
- **B3** `au_pick_ledger.csv`(**独立账本·绝不与美股混**)·bench=^AXJO·AUD 本币;**上线前先跑无调参 ASX 回测**(ASX=银行+矿业重仓,动量或不同;结果无论好坏公开,前向计分裁决)。
- **B4** AU 季节性/体制描述 · franking 策展字段 · CGT/配置器接 .AX。
- 数据先验:^AXJO~1992 / ^AORD~1980s(回测够);ASX50 大盘 20-30y 够;**franking 无免费 API → MVP 排除+注释,判定不许爬虫**;流动性坑 → 池限 ASX50 + 加流动性档位。
- 复用矩阵:直接复用 forward_ledger/notify/i18n/vp.css/watchdog/sidecar;参数化复用 checkup/pick_ledger/fetch_data;新建仅 AU 取数+au 页+franking/流动性件。**80% 是配置不是代码。**

### 建议执行顺序(Fable)
**A1(堵缺口·一提交)→ B0(探针验数据)→ 用户对开放问题拍板 → A2/A3 与 B1/B2 并行分派 Sonnet/Opus 建、六步协议审。**

### 执行波次(Fable 主循环 2026-07-12 定;A1/A2/B0/B1/D4 已上线,以下为剩余)
| 波 | 任务 | 建造→审查 | 依赖 |
|---|---|---|---|
| W0 | fetch_data_au 接 run_all + A2 curated 定档独立于 SEC + test_fetch_ipo 补 listing/adr 断言 + 注释小项 | Sonnet→Fable 直审 | 无 |
| W1 | A3 预警:ipo_alerts.py(🔴新事件→Telegram tag=ipo + append-only ipo_alert_log.csv 挂 sidecar;申报即推+状态迁移每档一次) | Sonnet→Fable 直审(append-only+去重语义) | W0 |
| W2 | B2 澳股体检:stock_checkup 参数化双跑(US 逐字节回归门;AU β=^AXJO+流动性档位)→au_checkup.json | Opus→Fable 亲审+回归门 | B1✓·与W1并行 |
| W3 | B3 澳股荐股六步:Fable 写双规格(au_pick_ledger 克隆+零调参回测+FMG身份门+披露门)→全新Opus审规格→Sonnet建账本/Opus建回测→账本Fable审·回测双审(Fable+全新Opus)→Fable亲验提交 | 见左 | W2 |
| W4a | **大跌日触发器**(用户 2026-07-19 拍板·回应"跌很多该怎么办"):单日大跌/VXSMH 飙升 → 自动把「已测规律当前态(连跌/长跨度)+极端下跌前瞻分布+条件下行+VXSMH」打包推 Telegram(纯复用现有件·事实通报非信号;去重防轰炸照 ipo_alerts 模式) | Sonnet 建→Fable 直审 | 无 |
| W4b | A5 IPO前向事实档(D1/D5/D20 vs QQQ·anti-hype·lead_time计分·missed追溯)——用户 2026-07-12 拍板:做;A4 Finnhub 不做 | Sonnet 建(复用 forward_ledger)→Fable 直审 | A3 |
| W4c | **美股荐股规则 v2 立项**(用户 2026-07-19 拍板·并行计分):v1 首批浮亏-8.4%(存储动量崩)后用户要试改进版——**铁律:v2 规则须事前理由(文献/常识),不许对着 06-26 那批倒推调参**;新规则另开账本列/标记并行公开计分,v1 照跑照认账(append-only)。Fable 写规格→全新 Opus 审→建→审 | 六步 | 无 |
| W5 主线 | **v1.5 自生长自动发现闭环**(2026-07-12 拍板:主线重心)——机器自动提新候选→自动进 FDR 分母;Fable 亲写立项规格→六步双审 | 立项时定 | W4 后 |
| 并行尾巴 | 前端完整度:D5 首页 IA(Fable 先出线框)+ 主盘全量双语——Sonnet 低速并行,不占主线 | Sonnet→Fable 审 | 随时 |
- B3 三道门(规格钉死):FMG 身份连续性(壳期截断)·披露门(回测结果无论好坏与荐股区同 commit;结果差则带结果升级用户)·独立账本(au_pick_ledger 绝不与美股混·bench=^AXJO·AUD本币)。
- 阈值现状:🔴$500M/🟡$150M/母市值$10B 已建成常量(用户未异议;要改一行改)。
- 更远(不排期):v1.5 自生长闭环(单独立项)·主盘全量双语·Valpha150 成分自动发现。

### 待用户拍板的开放问题(Fable 的 leans)
- A:重大门槛 $500M or $1B?申报就推 or 等定价?要 Finnhub key?A5 做不做(强荐)?
- B:独立区(荐)or 开关?池 ASX50(荐)or 100?基准 ^AXJO(荐·长史)or VAS.AX?接受"无调参回测→公开→前向计分"门(荐)?franking MVP 排除(荐)or 等策展?

### 用户 WHAT 拍板(2026-07-12)
- **A1:F-1 + 8-A12B + F-6 三档都加**(用户选"也保留抓 F-6",接受 OTC 噪音;F-6 打"ADR 存托·多为程序性"标签隔开,靠 A2 分层过滤,不污染"重大"信号)。
- **澳洲:全链含荐股 B0-B3**(探针→概览→体检→荐股+独立公开计分账本·带无调参回测门)。B4 深化后续。
- 细项(门槛/基准/池子/franking)执行到各阶段时按 Fable leans 逐一确认。

### B0 探针结果(2026-07-12·数据绿灯)
`fetch_data_au.py` 探 34 票(33 成功):**32 ok 回测(≥10y)·大盘池 27/29=93%·无需缩池**。近期无断更。
- **基准确认 ^AXJO**(1992起·33.6y·盖 2008/2000 完整周期,不可交易);^AORD 41.9y;VAS.AX 17.2y/STW.AX 18.5y 作"实盘可执行性"验证层。
- **数据卫生**:剔 **NCM**(Newcrest 已退市并入 Newmont);**COL** 标短史(7.6y·2018 从 Wesfarmers 分拆·B3 固定窗口回测须单独处理,类 SPCX 专属块)。
- **⚠ B3 上线前硬门禁——公司身份连续性校验**:探针发现 **FMG.AX** 一类"史深异常老"矿业票有 **ticker 重用/买壳**(FMG 1988-2002 是壳公司数据·$0.0006 极稀疏,2003 才真 Fortescue);直接当连续史回测会**静默污染动量/风险结论**。B3 门槛须加"身份连续性"检查(交叉核 IPO/更名),别只看 years/n_rows。共享 1988-01-29 起始日的那批千禧前老票都要查。
