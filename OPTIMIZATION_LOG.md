# 优化日志 & 自评分卡

> 用户 2026-06-16 要求:① 资源有限,可慢但**求完整**,什么没做都记这里;② 审查中冒出的好点子也存;
> ③ 多维**自评分卡**按版本追踪,看提升了多少;④ 功能想法 backlog。
> 每次有实质升级,在"§1 评分卡历史"加一行(同维度重打分),就能看出提升幅度。

---

## 🔍 Codex 加固轮 · 主脑复审(2026-06-18)

> Codex 跑了一轮 hardening pass(未提交,见工作树 + 根目录 `CLAUDE_HANDOFF.md`)。主脑**亲验**:pytest 161 绿、verify_output 全过、账本 append-only 红线守住(原始行 byte 一致,仅追加 hash 列 + 2 条 overnight 新行)。**结论:本轮可提交,模型/安全/账本工作扎实。**

**主脑已就地补的小修(本轮)**
- `vol_model.py` 终审拟合补 `if final_feats` 空集兜底(扩窗折已有 `continue`、终审漏了;极端不触发,防崩)。
- `paper_trading.py` / `track_predictions.py` 补 `sys.stdout.reconfigure(utf-8)`,与 Codex 给 verify_output/run_all 的控制台加固对齐。
- `ledger_hash.py` 文档说明哈希链**真实保证**:相对上次封存的篡改证据,非不可变历史(见下「verify-before-seal」)。

**⚠️ 假警报教训(防重复踩,呼应 §4c)**
- 复审中一度判定 overnight note "乱码损坏"(`��ҹ...`)。**root-cause 后是假警报**:文件是合法 UTF-8(raw bytes `\xe9\x9a\x94\xe5\xa4\x9c…`=「隔夜…成本」),pandas `to_csv` 默认 utf-8、round-trip `MATCH=True`。"乱码"纯是**我自己的 cp936 控制台显示伪影**,非数据损坏。**教训:终端显示 ≠ 磁盘真相,改代码前先看 raw bytes**——差点去"修"一个不存在的 bug。

**记下的好点子 / 待决**
- **verify-before-seal**(让 hash 链真有牙):run_all 现在 `seal → … → verify`,同一轮 verify 抓不到篡改(重封会"祝福"改动)。可在重封前对已提交账本单独 verify 一次,让"外部手改"在被祝福前被门拦下。中等改动、动 run_all 顺序,留作提案。
- **MODEL_VERSION**:Codex 的 `_usable_features` 只丢"恒定/损坏"零信息列 → 预测实质不变,**未 bump 版本可接受**;若从严,可在 commit message 注明"行为中性"。
- **paper_ledger 同日行重排**:load 的 `sort_values(["date","strategy"])` 把 06-16 的 trend/momentum 两行换了序(内容一致、仅顺序;hash 链顺序相关故重封)。良性,记此备查。
- **Codex handoff 自列 Deferred**(并入 §4 backlog 候选):全 CSP 迁移(inline `onclick`→`addEventListener`,分阶段 report-only→enforce)、CI 依赖 lockfile(`requirements-lock.txt`)、data-health 点开抽屉(哪些源缓存/过期)、CI 跑 `site_audit.py --mobile`、页脚账本状态行(行数/最新 hash 前缀/校验时间)。

---

## 🌅 明天可做(2026-06-16 收工,优先排序,给明天的启发)

> 主脑推荐先做 ①+②(闭环 + 最该补的 UX 短板);③④ 是好的功能延伸;⑤⑥⑦ 卫生/稳健。

1. **验 FRED secret + 闭环 HY**(~10min):去 Actions 手动触发一次 "Refresh market data"(Run workflow),跑完查 `market_regime.json` 信用维度 `history_start` = 2000-01-03 → secret 生效;若 ≈2023 → 排查 secret 命名/位置。
2. ✅ **导航/信息架构(2026-06-16 已做,5da83c4)**:登记簿 14 面板分 5 组(规律真伪/风险与不确定性/个股因子/事件因果/探索中vs已死)+ intro 预告。
3. ✅ **R3 羊群维度(2026-06-16 已做)**:R1 体制盘新增"个股共动(羊群)"维度——8 只大盘股近60日平均两两相关 + 历史分位(高=危机式趋同/分散失效)。当前 0.14[各走各的]。描述性、非预测。
4. ✅ **个股版"大跌后完整分布"(2026-06-16 已做,6629f8e)**:个股体检加 compute_dip_distribution(复用 R3 _fwd_distribution);NVDA 大跌后20日最坏-51%/~43%继续亏。下行标红+非抄底。
5. **分段透镜推广到 factor_audit**:因子在"现代段(2000后)"还在不在(很多因子也被套利),与 placebo 分段同口径。
6. **测试覆盖补全**:run_all 级聚合(stock_checkup summary / market_regime / overreaction distribution)无单测,补几个防漂移(审查提过)。
7. **全量 run_all 端到端跑一次**:静态体检已过(全在 run_all、docs 同步),跑一次全量确认集成无序列问题 + 一次性刷新所有数据。

## 🎯 版本路线(2026-06-16 定;现 ≈ v0.98 · 2026-06-24，逼近 v1.0)

> **v1.0 命门 = 可懂性(「又专业又能被人看懂」)**：用户实测反馈"首页/Telegram 太抽象、不知道什么意思"——
> 揭穿上版把 UX 记 5 偏高(结构好≠看得懂)。差 v1.0 的三件:① 可懂性 hover 注释组件全站化(现仅 hero)
> ② 新手首达引导("3 步看懂") ③ 完整移动端实测。设计铁律=**「两层呈现」**:每个专业结论顶一行大白话
> takeaway + 收起的"展开看专业细节",新手看第一层、老手点开有全套统计。

> **持续优化、无终点**——v1.0 / v2.0 都是里程碑不是终点;每轮都让它更诚实、更清楚、更全貌(红线不变)。

**v1.0 里程碑标准**:"能放心丢给一个陌生人、他在**手机上**也看得明白、不会误读成荐股"。到 v1.0 需:
- **UX/设计(最大杠杆)**:移动端响应式 + 新手引导("先看什么")+ 视觉统一 + 空/错状态。
- **系尾**:FRED secret 落地(信用全史·你点一下)· R3 羊群维度 · 分段推广到 factor_audit。
- **加固**:聚合层补单测 · 全量 run_all 端到端跑一次 · 全库再审一轮。

**v1.x / v2.x 愿景(加强方向,红线不变)**:
- 扩个股 universe + 个股各模块已齐(EVT/规律/区间/异动/大跌分布);
- 更多诚实诊断(更多事件因果、更多风险体制维度)+ 更好可视化(交互图、体制时间线);
- 性能(置换缓存按需)、可访问性、(可选)国际化。
- 🔴 **红线已重定调(2026-06-22,见 CLAUDE.md「方向与边界」)**:早期"不预测/不荐股/不上 DL"是起步护栏,现逐步突破——正纳入预测/荐股/DL/LLM。**真正不破的是质量地基**:不绕 verify/pytest 门禁、账本 append-only 绝不改历史、秘钥只走 Secrets、**公开计分/标不确定性**(预测越多越要守=护城河)。"加强"=更诚实、更清楚、更全貌 + 敢预测敢认账。

## §1 多维自评分卡(1–5;每次升级追加一版)

维度(为本项目定制——把"诚实/红线"单列,它是命门):

| 维度 | 含义 |
|---|---|
| 统计严谨 | 方法论专业度(多重比较/复制/稳健性/独立审) |
| 诚实·红线 | 展示空/否/被套利、绝不预测方向、不被误读 |
| 正确性 | 测试覆盖、verify 门、审查抓 bug |
| 新颖性 | 方法升级幅度(受"不加模型/不上DL"自限) |
| 设计/UX | 可读性、可视化、交互 |
| 性能/快 | 加载速度、流水线耗时、CI 稳定 |
| 可维护 | 模块化、复用、协议化、复杂度控制 |

### 评分历史
| 日期 / 版本 | 统计严谨 | 诚实·红线 | 正确性 | 新颖性 | 设计/UX | 性能/快 | 可维护 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 2026-06-16 · 个股体检块0–3 | 5 | 5 | 5 | 4 | 3 | 4 | 4 | 基线。三关稳健门/独立审抓出faded bug=严谨;UX 仍朴素;月份检验永远 inconclusive 待优化 |
| 2026-06-16 · 个股体检6块全完成 | 5 | 5 | 5 | 4 | 3 | 4 | 4 | 广度提升(非维度跳变):块4保形/块5综述卡/块6风险状态完成,4轮独立审又抓出 n_test真分母/绿灯误读/脱钩边界。**设计UX仍3=最该提**(表格密、缺迷你可视化) |
| 2026-06-16 · 诚实坟场页 + UX迷你可视化 | 5 | 5 | 5 | 4 | **4** | 4 | 4 | 坟场页(聚合死掉的模型/规律);体检页加保形区间条+波动分位条(纯CSS无依赖)→ **UX 3→4**(直观传达"范围非方向""当前风险位置");仍可加更多分段可视化 |
| 2026-06-16 · 理论轨+探索区+R3全貌 | 5 | 5 | 5 | **5** | 4 | 4 | 4 | placebo分段(揭FDR幸存者被套利)/R2 Fed model证伪/🔬探索区(康波等猜测,补全真-死-探索中生命周期)/CI方法论护栏/R3短期反转。**关键:两次顶住"短期可用/强势推荐"红线压力,把R3接成"完整分布(40-46%继续亏/最坏-31%)"反制抄底误读**→ 新颖性4→5(探索区lifecycle)。更新/推送机制已体检(全在run_all、docs同步)。 |
| 2026-06-16 · placebo分段 + CI护栏 + R1体制盘 | 5 | 5 | 5 | **5** | 4 | 4 | 4 | placebo分段揭示FDR幸存者(星期/圣诞)2000后已套利;CI §3j方法论护栏(automation-first);R1当前风险体制盘(宏观维度)。**新颖性4→5**(分段揭穿+宏观体制是真升级)。性能项测量后撤回(§4c) |
| 2026-07-02 · 双模型全库审→四批文案收口+账本双护栏 | 5 | 5 | 5 | 4.5 | 4.5 | 4.5 | 5 | **Sonnet5+Fable5 独立 A/B 全库审(同 brief)→Opus 复核**:每道审都抓真问题(回测面板假"高度显著"p=0.43·主信号环 TIER_META 假完成·测试判别带盲区·VIX 恐慌轴符号反·日期非零填充绕过倒填检查)。落地:**P0~P0-8 四批诚实文案收口(全站操作指令清零)**、门禁真空补齐(valpha150 家族防 NaN 白屏+strict-JSON 二道门+outlook disclaimer 门)、**账本双层防篡改**(sidecar 链 13 账本+registry git-HEAD 4c 门·实弹演练篡改被抓/非规范倒填被拒)、测试 411→452(见证修让显著性阈值真被锁)、backtest 空输入 fail-closed 显式诊断。**新颖性 4.5**=流程/护栏创新(双模型 A/B 审工作流+双锁外部真相)而非统计方法升级,不给 5;**UX 4.5 持平不动**(本轮未动可懂性·主盘仍密=v1.0 命门在前)。诚实不 inflate |
| 2026-06-24(晚) · v1.0/1.5/2.0 委派波：5 worktree 子代理并行 | 5 | 5 | 5 | 5 | **4.5→5（v1.0 达成）** | 4.5 | 5 | **v1.0 三件套全落地 → 逼近/达成 v1.0**：① hover 词典组件全站化(DRY·18测) ② 新手首达引导(3步·a11y) ③ 移动端+空错兜底(6页)；外加 v1.5 **LLM 周报**(grounded·17测·待 cron+key) + v2.0 **情绪 spike**(Polymarket NO-GO / Reddit CONDITIONAL·harness 建好)。**强编排验证**：6 步协议「审查者≠建造者」抓出 2 个建造者自测漏掉的**真 bug**——onboarding 用 ASCII 引号→整页 JS 崩、spike harness `grp.name` 崩；worktree 隔离 + 最小重叠设计让 4 家同改 index.html 只手解 2 处冲突。pytest 259 绿·全页 node 解析过·E harness 跑通。可懂性子轴随 hover 组件化再上一台阶 |
| 2026-06-24(下午) · 可懂性关：去抽象+术语翻译+诚实白话校准 + Kronos定论/上页 | 5 | 5 | 5 | 5 | **5→4.5(诚实下修)** | 4.5 | 5 | **用户实测"首页/Telegram 太抽象·不知道什么意思"→ 戳破上版 UX=5 偏高(结构好≠看得懂)，诚实回调 4.5。本版补可懂性子轴(3.5→4.3)**：① hero/日报删裸分(0.138)/tier、置信→把握；② **②校准落地**：方向信号 `|prob−50%|≤4` 直说"≈掷硬币·无验证优势·别当真"，不再把 52% 装"看涨"；③ AI 解读专业词(VIX/收益率曲线/信用利差/相关性/分散性)前端兜底翻译(plainify/plf/_plainify·JS×2+Py·首现且未自解释才补·幂等不二次注)铺到 index/dashboard/Telegram 三处；④ **Kronos 大样本定论**(n=270·方向51.9%·p=0.29·还低于57.4%基率·扣成本跑输买入持有→❌无 edge)+ **新增 kronos.html**(结论/轨迹/4课/严格划界)= 护城河内容。**可懂性 = v1.0 命门**(hover 组件全站化/新手引导/两层呈现 待做)。node 双语+幂等校验·pytest 234 绿 |
| 2026-06-24(上午) · 日报修复 + 主盘分组(v1.0 UX关) + Finnhub + Kronos诚实实验 | 5 | 5 | 5 | 5 | **4.5→5** | **4→4.5** | 5 | **红线方向彻底落地 + 护城河被实战验证**：① 修了 Telegram 日报【永远不发】的真 bug（workflow 把未设 secret 当空串 → `LLM_PROVIDER=""` 击穿 `.get` 默认 → 一直判"未配置"跳过）+ 日推加料（结论买/持/避 + 纳指方向 + 数据日期）；② **主盘 dashboard 7 面板分 3 组留白 + 顶部结论 hero + 标"数据截至X日"**（澳洲跨时区）= **v1.0 最后 UX 结构关补上（UX 4.5→5：结构到位，完整移动端审/onboarding 仍可打磨）**；③ **Finnhub 财报日历**（免费 key 实测有效·📅 迫近财报风险标·历史 OHLCV 转付费故只用日历/quote）；④ 个股 昨日/近一周/近一月 铺到 大盘表/点单/雷达三处；⑤ **性能① Plotly 懒加载**（移到 body 末·首屏不等 1.4MB·4→4.5）；⑥ **🤖 Kronos DL 诚实实验**（AAAI-2026 金融 K 线基础模型·隔离在 Kronos 项目跑）：walk-forward vs 随机游走，初版 sample=1 → 方向 51%（p=0.46 掷硬币）、收益 MAE 比"预测不动"还差 2 倍 → **诚实负结果（待 sample=5 公平复核）**。这恰恰是护城河：**敢试被吹的 DL、也敢公开认它没 edge**，有计分为证，不 inflate。 |
| 2026-06-23 · 红线重定调(敢预测敢认账·计分护城河) + 去重大扫 | 5 | 5 | 5 | 5 | 4 | 4 | **5** | 红线从"不预测"重定调为"敢预测敢认账·守公开计分"(见 CLAUDE.md「方向与边界」)。落地:LLM 大白话日读(provider 无关·Gemini/DeepSeek)、BTC动量→纳指/参议院持股/体制→前向 **三条红线诚实回测**、**公开计分校准卡=四站调研里没人敢露的护城河**、证据库总览、🎓期权教学沙盒、📱持仓感知告警。**可维护 4→5**:去重①②③④(util_io.write_json 替 25 写者·append_daily_log 替 6 账本·stats_util.forward_returns·共享 vp.css 替 8 页)——3 个 helper 收 ~40 调用点,全**逐字节等价+真账本 temp 副本核对+pytest 233+CI 绿**。**UX 4→4.5**:首页加 canvas 倾向仪表 + "今日结论"hero(偏积极/纳指看涨**先给结论**再挂战绩)、主盘+野蛮hub 措辞从旧红线重定调为"敢给方向·公开计分";**但 dashboard.html 只改字未改布局、仍密** = v1.0 前最后的 UX 关。诚实记账:红线含义已变(预测+公开问责),护城河靠诚实计分,不 inflate。 |
| 2026-06-19 · Valpha Lab 三层体系 + 5路审查 | 5 | 5 | 5 | 5 | 4 | 4 | 4 | **广度大增**:8 个工具页(Valpha150/板块/雷达综合评分/配置器CGT币种/野蛮/IPO三档/方法论/v2.0自生长衰减追踪)+ 全工具页双语 + 移动端@media全覆盖 + WCAG AA对比度 + 表头键盘可访问。**5 路多维审(correctness/security/a11y/honesty/simplicity)诚实审零越界通过、简洁审确认自包含合理**。**设计/UX 仍记 4 不抬**:工具页已达 v1.0 观感(手机可读/键盘可达)，但**主盘 dashboard.html 仍密、未双语**——它是整体观感的 drag，抬分需先收拾主盘。诚实记账:广度↑但最难的页未动，不inflate |

**当前各维"提升方向"(2026-07-02 刷新·旧版已过期:UX 早非 3、置换缓存已被 §4c 测量否决勿再提)**
- **设计/UX(4.5→5 = v1.0 命门·最该冲)**:可懂性三件——hover 术语组件全站化(现仅 hero·vp_gloss.js 有底子)、新手"3步看懂"引导、移动端完整实测。见 §2 下一步 #1。
- **新颖性(4.5→5)**:等真方法学事件——KB 首批晋升(~2026-08-初·自生长第一次真转)、或新数据源族过双审进 FDR 池、或验证升级(CPCV/Deflated Sharpe 类·守"升级验证不加模型")。
- **性能(4.5)**:无用户可感痛点;置换已实测非瓶颈(§4c)。**不为提分而优化**,除非 profile 找到真瓶颈。
- **统计严谨/诚实/正确性/可维护(5)**:守成即胜——每个新统计走双审、账本双护栏勿松、文案改动过诚实审、TODO 即时回勾(文档债教训)。

---

## §2 未做 / 待续(什么没做都记)

**🗓️ 2026-07-28 CI 韧性 backlog(防缩水门事故根因·§4c;验证绿后按序做)：**
- [ ] **#1 别把 git 跟踪的账本放进 actions/cache(根治)**：账本真相在 git;缓存它才有"陈旧回灌"风险。cache 路径只留可再生的 raw/派生缓存、排除 `data/*.csv` 账本 → 整个"re-assert from git"步骤连同这类 bug 消失。9d007ea(re-assert 全账本)是补丁,这才是根治。
- [ ] **#2 `git add -A`→显式暂存**：refresh-data/weekly-review 的 `git add -A` 会把误入的陈旧回灌一起提交;只暂存该跑真正产出的文件(web/docs json + 本次 append 的账本)→ 陈旧文件永进不了提交。
- [ ] **#3 publish 逻辑抽成可本地测的 `tools/ci_publish.py`**：本周两次搞挂 prod 的都是 inline-yaml 的 commit/push 逻辑、本地跑不了。抽出来 + 单测 = 防下次事故的元修复。
- [ ] **#4 防缩水门 warn-only 重挂**：#1/#2 落地后,以警告(不阻断)试用期重挂做纵深防御,绝不再因门停摆。

**🗓️ 2026-06-30 本会话落地(已 push,免得"先查后动"重做)：** 自生长门4 OOS 引擎 + 知识库晋升降级(P-A/P-C·Opus双审GO) · P-D 前端"自生长看得见" · P-B 防闪烁 · 预FOMC漂移研究 → **升进 candidate_space 命门**(双审GO·N_DECLARED 74→76·补2026会议日程) · **opex_week/季末两侧先验**(双审GO·N→80·均 dead) · FX→AUD 真实收益工具(子代理) · **LLM 全活**:日读激活+月报新建(节流)+ **AI 预测**(append-only 公开计分账本+prediction.html+按信心分桶·Opus审GO)·走 `GEMINI_API_KEY` · senate 定性完结历史研究(源停更·见 §4c)。

**🎯 下一步(2026-06-30 排序)：**
- [x] **用户 1 步（2026-07-01 已验证生效）**：`GEMINI_API_KEY` secret 已设进 GitHub 且 CI 在用——bot 提交 `cd34778`(6-29 22:43 UTC) 刷出真 Gemini 日读文本(model=gemini-2.5-flash-lite)、`llm_read_log` 6-22~30 连续记录。秘钥不可读回,靠"bot 提交真 LLM 输出"这一可观测痕迹证明。日读每盘后全量跑(按天去重);周报周六;月报月末;预测每全量。
- [x] **"用上"活信号（2026-07-01 完成·常驻观察清单）**：新建 `survivors_live.py`——读 autodiscovery `verdict==survive`(5条:金叉·BTC动量·纳指回撤·九月×2)+本地算"今天是否应期"(金叉50>200/BTC动量>+5%/纳指跌进最低5%/是否9月)→`survivors_live.json`(历史edge复用autodiscovery·不重算·单一真相源)。喂 `llm_daily_read`(铁律7:休眠的绝不当当前信号·真Gemini干跑证实它主动说"其他规律今天不成立")+ composite.html 常驻观察台面板(应期绿/休眠灰)。诚实:方向由up-base算(回撤=偏负不按族名想当然)·前向OOS(门4)仍pending·描述性非预测。14单测+verify_output守门+顺修月报月初定时炸弹。KB晋升仍0(前向攒中)。
  - **Sonnet 4.6 全审抓到真诚实 bug(2026-07-01·审查好点子·f3dba85→修)**：`september` 效应 `label==1=非九月`(先验强组·见 autodiscovery `_cal_windows` l==1)，我原文把 `up_pct=54%`(其实是非九月的)当成"九月上涨率·偏正"公开了——九月实为最弱月(51%)，方向反了。修法:每条描述符显式记`触发组(label==1)/对照组`，edge 恒按真实组名拼("非九月 54% vs 九月 51%")+方向守门单测锁死。同时补:survivor 会 flicker(我快照5条→审时8条·world_cup/BTC_neg/NASDAQ_ma200 翻上来)→补全8描述符+未接入中性兜底+LLM铁律7防"未接入"越界。**教训:up_pct 恒=label==1 组，对"某期偏弱"先验(九月/世界杯/sell-in-may)那是相反的强组，别按族名想当然把 up 安到条件本身。reviewer≠builder 真值钱。**
  - **Opus 4.8 复审又抓到第二层 bug(2026-07-01·分层审查持续见效·a8c28be→修)**：修 september 时我假设"base_pct=对照组"对所有族成立——**只对日历族(_cal_windows base=label==0 补集)成立**；factor/regime/rebound 走 `_diff_windows`，`base_pct=yy.mean()=全样本基率(含触发日·非补集)`。我把它标成补集名("200线下方/未成立/其余日")——独立核实:NASDAQ_above_ma200 触发65%·全样本基率62%·**真补集(200线下方)仅55%**，数字对不上组名。修:这5条 rest 改"全样本基率"+守门测试。另修 world_cup:年份表缺 2026(真·世界杯年6/11-7/19)→显示"2026非杯年"是假的;补 2026 进 WORLD_CUP_YEARS + `_world_cup_state` 改"夏季且非杯年才应期"→2026夏正确变休眠。加"边界易闪"标注(recent_p∈(0.08,0.10]·可能退出)。**教训2:两窗口函数 base 口径不同(_cal_windows=补集 vs _diff_windows=全样本)，别一个 mental model 套所有族。Sonnet 抓一层·Opus 抓更深一层，两道审都值回票价。**
- [ ] **P-E 自动提案层**：自生长最后一块(最高风险后门)——在预声明元空间枚举未注册格点→proposals 待审(不算p/不进分母/不上战绩),按 SELF_GROWING_PLAN §4/§7④ 硬门槛 + 双审。
- [~] **LLM 展示更显眼**：✅ index.html 已接"🗓️本月回顾"card(2026-07-01·f6bc1c2·月报此前无页引用=不可见)+ 周报card已有 + AI预测已7页露出;**余**:dashboard.html 主盘导航露出 LLM 三件套(小·待做)。
- [x] **数据卫生体检(2026-07-01 已跑)**：`git ls-files` 扫过——**无误提交的大二进制**(无 .pkl/.parquet/.db)。最大 `signals_history.json` 1.6MB(×docs=3.2MB)=前端历史图必需·有意提交;`senate_trades.csv` 410KB=已搁置历史研究死数据(按搁置决定保留)。结论:无需清理。

**🎯 下一步(2026-07-02 晚·Fable 5 主脑全局判断·基于双模型全库审+本轮全部收口)：**
**现状判定:本轮(07-01~02)把"诚实债+工程债"清得很干净**——文案零操作指令(P0/P0-6/P0-7/P0-8 四批扫净)、发布门禁无真空(NaN/strict-JSON/outlook/registry 4c)、公开账本双层防篡改(sidecar 链+git HEAD 外部真相)、测试 452。**代码质量不再是瓶颈;可懂性与数据积累才是。**排序:
1. ✅ **v1.0 可懂性冲刺(2026-07-03 完成·efb6d20)**:① hover 术语全站化——vp_gloss v1.1 加 `vpGlossScan` 自动扫描(TreeWalker·全页首现·幂等·防"显著性"错切·2s 二次扫接 fetch 渲染)+词表 11→24 条(Fable 亲草·金叉标"不是买入指令")+27 页 data-autoscan(老 6 页手动模式不动);② 新手引导统一"3步看懂"(温度计/查真假→登记簿坟场/看战绩→计分卡·双语)+dashboard 补 ❓ 重开钮;③ 桌面+移动 interaction_audit 全✓+playwright 功能实测(zh 每页 4-5 注解·EN 0 注解·❓重开✓);④ methodology"🧪工程自评"块(7 维快照·短板行重点样式公开认"主盘密度仍偏高")。**真机实测仍欢迎用户手机上翻一遍**。
2. **[时间触发·~2026-08-初] KB 首批晋升验收**——锚 2026-06-26+min_oos_n 30 → 日频效应约 30 交易日后首批 confirmed 可期(queue 已 6 条存活者)。届时验收全链路(门4→KB晋升→survivors_live→前端→可选 Telegram 通知"知识库首次自生长"),这是自生长真正"活"的第一刻。**放日历·现在不用动。**
3. **[等数据] AI 预测展示丰富**——SPY 5日预测日日 append,~8月有 20+ 结算样本时按信心分桶命中才有统计意义,届时丰富 prediction.html。别过早优化。
4. ✅ **LLM 输出 XSS 确认(2026-07-03 审毕·零缺陷·未改一行)**:逐 sink 清单 11 处——LLM 文本进 innerHTML 的全过 esc()/escc()/vpAnnotate()(核实 vpAnnotate 整串先转义·tooltip 只来自静态词表),其余 textContent;唯一责任重大 sink(prediction.html 的 LLM 自由文本 reason)esc() 在位;新 vpGlossScan 只动文本节点不开新注入面。结论:LLM→前端转义闭环。
5. **[大·排后] dashboard 深度面板双语**——app-js content-i18n 单独立项(20+ 容器跨 9 页共用);中文用户是主受众,排在中文可懂性之后。
6. ✅ **运维两项(2026-07-03·56acb38)**:① overreaction 账本——调查揭出**从未被 git 跟踪**(.gitignore 负模式对未跟踪文件失效·靠 actions/cache 假活数月)→ git add -f 建跟踪(创世=当时态·不伪造历史)+merge=text 挪出 union+CI 缓存防护+收编 sidecar;**实弹又抓到 sidecar 键 bug**(manifest 存 basename、查用子目录 fname → verify-before-seal 静默跳过)→修+2回归锁。② IPO 策展快照渐旧横幅(>2月自动提醒·SEC 自动层兜底)。454 tests。
7. **[探索型·用户方向] 新数据源**(社交情绪等):先验证"够长历史可回测+澳洲可达"再立项,照 candidate_space 双审纪律进 FDR 池。
8. ✅ **backtest 空输入③层(2026-07-03 用户拍板做③·a210d87·推翻早前默认)**:三下游审计后改优雅降级续跑(records=[]→warning+数值dtype空帧自然降级+degraded标记;app-3 诚实占位替代原"静默画空图+假63.1%基线";builder 主动纠正"显示最近成功结果"措辞——无 last-known-good 缓存,照实描述)。454 tests。
- [x] ~~§1 评分卡补 2026-07-02 行~~(2026-07-02 已补·含"提升方向"节刷新——旧版还写 UX=3/建议已否决的置换缓存,已过期校正)。

**🎯 #7 命门相收官(2026-07-05·六步全走·84afac0+a1adcf7)**:positioning(COT 16)+options_sentiment(P/C 8) 进 FDR 池,N 80→104。**双审各抓真问题**:审②Opus 实测状态持续期裁 block 必须放大(hold+p90=71/111·块敏感性1翻转验证=旧块假阳被压)+2 BLOCKER(dispatch静默退化/年代错配);审④Opus 抓阻断bug——尾部无已实现前向窗被捏造 y=0 压制活信号,修正翻转公开头条(**🆕纳指仓位极空信号 legacy_lo_h60_nq 首度存活** p=0.000·+18.6pp)。全量507 tests。**follow-up 两条**:① `_regime_arrays` 同款尾窗bug(既有代码·会影响 golden_cross 已发布p·需单独审后修) ② 新存活者 survivors_live 描述符待接(现以"未接入"中性兜底·接入需 usable_from 感知的当前态计算)。老survivor 8→6(world_cup/p5边界者被刷·上轮已标易闪)。

**✅ follow-up①收官(2026-07-07·T1·995a051+1cb6734)**:`_regime_arrays` 修**两个**同类 bug——(a)尾部 hold 天前向窗未实现 `(NaN>0)→0.0` 捏造下跌且 dropna 删不掉;(b)golden_cross 暖机段(前199天200日均线未定义)被 bool→False 当"信号不成立"混进基率。修法:`cond=(ma50>ma200).astype(float).where(ma200.notna())`+fwd 以 float 先进 df 再 dropna 后派生 y。`factor_model.build_features` 尾月同款一并修。**R2 全库尾窗清扫连带做完**(其余构造点 _positioning/_rebound/_optsent/advanced_analysis 已合规;fomc_study 同日 up-rate 非前向·池外·非同类)。**影响(公开口径变更·双审级)**:真数据裁剪精确 −219(199暖机+20尾窗);全104池新旧复算**零 verdict 翻转·新旧同存活集**(golden_cross_sp500 p 0.001→0.000 更显著仍 survive;nasdaq 仍 dead)。流程:Fable 建+全新 Opus 审(APPROVE 零 blocker·逐条核到真数据/突变测试/OOS 消费者兼容)→ Opus 4.8 接主脑收尾。新增合成回归锁 `test_regime_arrays_exclude_warmup_and_unrealized_tail`。**教训**:这类尾窗/暖机 NaN→False 捏造是本项目反复出现的 bug 类(#7 两处+今 regime/factor_model),凡新建前向窗数组一律"先 float 进 dropna 再派生 y、暖机段 where(notna)"。**follow-up② 仍开**(survivors_live 描述符=HANDOVER T2)。

**🔥 CI 红 #100–104(2026-07-07·e9276b6)**:#7 上线后首批 schedule CI 全红。根因=测试偷偷依赖 gitignore 生成数据——`compute_results` 无条件跑 `_factor_map→build_feature_df()` 读 `data/raw/combined_prices.csv`(本地有·CI 干净检出无);尾窗守门测试直吃真数据。修:`_factor_map` 空列表短路 + 守门锁拆"合成恒跑/真数据缺则 skip"。**防复发**:`pre_commit_gate.py` 升级为 `git archive` 索引树到临时目录跑 pytest(**CI 同构**)——本地绿 CI 红这类问题提交那刻即拦,活演练修前 deny 修后放行。**新铁律**:门禁/CI 测试不依赖 gitignore 数据;需真数据的测试缺则 skip + 必有合成版恒跑同一性质。

**🔭 backlog vs 代码现实 侦察核对(2026-07-02·Explore 子代理)：文档落后代码 1-2 周。** 大批"待做"其实早建好审好(块4/5/6·R1/R2/R3·坟场·分段透镜·insider/pick_ledger·自生长P-A~D·LLM系列·survivors/flicker·heatmap/risk 全已建·已上线)。**真·未做(核实无实现)仅**：① P-E(已 NO-GO·§4c) ② dashboard.html 主盘 LLM 三件套导航露出(小) ③ dashboard 全量双语(中·可选·工具页已有范例) ④ IPO 数据定期更新自动化(小-中·缓·用户需求再说)。**其余"下一步"多为文档债,非代码债。**

**个股体检 loop(STOCK_CHECKUP_SPEC.md)——✅ 6 块全部完成(2026-06-16·4轮独立 Opus 审·本 TODO 曾过期,2026-07-02 校正)：**
- [x] 块4 保形区间(`compute_conformal`·20日90% split-conformal 双边区间+实测覆盖·复用 conformal.py)
- [x] 块5 裁决卡 + 诚实登记簿(`summary` 聚合·风险画像综述卡·审修 null-β/中性措辞/0真规律重述)
- [x] 块6 风险型异动监测(`compute_anomaly`·当前波动/相关分位·被动per-stock免FDR·审修绿灯误读)
  > 详见 `STOCK_CHECKUP_SPEC.md` 98-106 行(全 [x])。**教训:文档 TODO 落后代码 1-2 周 → 每完成一块即时回勾,别攒**。

**理论/体制轨**
- ✅ R1 当前市场风险体制盘(VIX/曲线/期限结构,已完成;见 §4b)
- ✅ R2 Fed model 证伪(纯登记簿,2026-06-16):加进 🪦 坟场"模型/假设被否"——流行但学术已证伪(Asness 2003 相关通胀非真实价值)。
- ✅ R3 行为金融:短期反转(过度反应,2026-06-16)——极端下跌日次日反弹检验(置换+全样本vs现代分段)。结果:**real(持续)**,全样本 p=0.023、现代 p=0.001(不像日历效应被套利)。独立审 APPROVE→修红线措辞("持续"→"统计可见·经济不可用"、去掉加粗均差防"抄底"误读、补 faded 分支测试)。**羊群**:暂以 market_structure 的相关性体制覆盖,未单列(可后续)。
- ✅ **🔬 探索区(2026-06-16,用户提议+我重构红线)**:用户想要"短期/猜测性、有一两次ok"的东西单独成页。**红线重构**:不做"X年可用"(=预测,越线),改做"怀疑训练场"——未过稳健检验的开放假设(康波/库兹涅茨/基钦逐点超但全局不显著、placebo 裸显著没过FDR、无定论项),强制框架"极可能噪声、不可交易、非预测;保留逐次重验→过了升登记簿、证伪进坟场"。补全 真/死/探索中 三态生命周期。前端聚合 placebo/cycles/stock_checkup,无新后端。
- ✅ **信用维度已补(2026-06-16,换源解决)**:ICE 高收益利差 BAMLH0A0HYM2 在 FRED **仅开放~2年**(API+key 验证后仍只2年=访问限制,非我们的bug)→ **改用穆迪 Baa-10Y(BAA10Y,全史2000+、无限制)**作信用压力代理,经 FRED 官方 API(env `FRED_API_KEY`,无则回退)取全史。R1 已加"信用利差 Baa-10Y"体制(现值1.53/全史分位/标签)。**剩用户动作:把 FRED_API_KEY 加为 GitHub Actions secret,否则 CI 回退 graph CSV(信用分位只算~2年)**。
- ~~🐛 HY 截断(原记)~~——**不是** merge/缓存 bug:`fetch_data.fetch_fred` 用的 `fredgraph.csv?id=BAMLH0A0HYM2` **端点本身只返回近 2 年**(实测 794 行全是 2023-06 起;加 `&cosd=1990-01-01` 被忽略、字节数一致)。FRED 图表 CSV 端点默认范围受限。**修法**:换 FRED 正式 observations 端点(API key)或 downloaddata 端点取全史(BAMLH0A0HYM2 实际 1996+),需逐序列验证(GS10 等可能也悄悄被截、combined 里是旧全史缓存)。修好后 R1 加信用维度。**已 time-box,不在长会话尾部钻**。
  - **2026-06-16 续:无 key 路径全试遍,都不通**——graph CSV 对该日频序列硬截 2 年(cosd/coed/fq 全被忽略;GS10 月频同端点却返全史)、downloaddata CSV 301 拦截、DBnomics 404。**干净修需决策**:① 免费 FRED API key(违背"无需Key"约定) ② 抓 /data HTML(143KB 含全史,但脆) ③ 找对 DBnomics 路径。**= 待用户拍板的决策项**,不硬塞脆弱方案。

---

## §3 审查冒出的好点子(NICE-TO-HAVE backlog,非阻断)

- ~~**块1(EVT)**:`compute_basic_risk`/`compute_evt` 对非 DatetimeIndex 输入会抛错(未来防御加一行 `pd.to_datetime`)~~ **✅ 已做**(两函数均有 `px.index = pd.to_datetime(px.index)` 防御行,2026-07-07 Fable 核实);`xi_sensitivity`(阈值稳定性)可留作 tooltip——仍开。
- **块3(规律真伪)**:
  - "主导组一致"用 argmax,而 SSB 显著可能由**低**离群组驱动 → 当前偏保守(只会更严),可考虑改"最大|偏离|组"。
  - 近期窗硬编码 5 年(`365*5` 日历日);**月份效应**因此恒不可测(~60<100)→ 月/日或该用不同近期窗策略。
  - 月份效应因每组 n≈26<30 **结构性恒 inconclusive**(几乎无证伪力)——要么接受+注明,要么抬高数据下限让月累计≥30/组。
  - `min_group_n` 报全样本值,但分半门面对的是半样本 n(显示偏乐观,cosmetic)。
- **通用**:置换零分布可缓存复用,省 CPU(配合资源限制)。
- **块4(保形区间)**:审查 SHOULD-FIX(coverage 真分母 n_test、补"无条件非预测"caveat)+ NICE(带符号边界、修测试除零)全采纳,无遗留。
- **块5(综述卡)**:审查 SHOULD-FIX(null-β渲染、"更稳/更颠"改中性敏感度防误读、登记簿0真重述)全采纳。
- **块6(风险状态)**:审查 SHOULD-FIX(绿灯误读→正常态中性灰、脱钩四舍五入边界)全采纳;NICE 脱钩"无关好坏方向"已加。~~遗留 NICE:加 decoupled 边界测试(分位≤5)~~ **✅ 已有**(`test_compute_anomaly_decoupled_boundary` 两端语义锁,2026-07-07 Fable 核实)。
- **backtest.py 空/无重叠输入崩溃(2026-07-02·Wave2-D 补测时 Sonnet5 STOP 发现·Fable5 裁定)**:`run_backtest()` 在 `daily={}` 或 daily 日期与长历史CSV零重叠时 `records=[]` → `pd.DataFrame([]).dropna(subset=[...])` 抛 KeyError;run_all subprocess+sys.exit(1) → 会中止整条流水线。**Fable 裁定:真 bug 但低触发(需上游CSV灾难性损坏·backtest 不在 LIGHT_STEPS)、且当前是 fail-closed(发布前中止·Pages 续服务旧好数据)对"上游损坏"恰是诚实**。**最小安全修(单独小任务·非本波)**:不是"降级续跑"(builder 原提议·会把响亮 fail-closed 换成无声诚实性退化·方向反了),而是把隐式 KeyError 换成显式 `raise ValueError("信号与CSV日期零重叠·上游数据损坏")`——保 fail-closed、不碰发布结构、报错可行动。届时 test_backtest 两条 `pytest.raises(KeyError)` 同步改 `pytest.raises(ValueError, match=...)`。若将来要真降级续跑,前置=先审下游消费者(build_signals嵌入/verify_output/app.js 渲染)。
  - **✅ 已解决(#7 批次,2026-07-07 Opus 核实)**:实际实现走的是**降级路径**(`records=[]`→数值型空 frame + `degraded=True` 标记供 build_signals/前端感知),**非**本note 主张的 ValueError。即:审下游消费者的前置确实做了,选择了"带可检测标记的结构化降级"而非硬 fail-closed。已有 3 条测试覆盖(test_empty_daily_signals_degrades_gracefully 等·degraded=True/False 分路)。与 Fable 老主张方向不同但**已上线+测试+下游可感知**,是可辩护的设计,不重开。**此小任务关闭。**

---

## §4 功能想法 backlog(用户 2026-06-16 头脑风暴 + 早先)

- ✅ **"诚实坟场"页(已完成 2026-06-16)**:前端聚合页 `loadGraveyard`——死掉的东西分类立坟:模型/假设被否(v3稀疏/RDD)、曾认为有效现已测不到(节前效应)、个股 faded(AAPL星期)/数据窥探、被FDR刷掉(月份效应、跨族28→5)、民间周期被否。同源消费 placebo/fdr/cycles/stock_checkup,无新后端。展示-tier 自审(红线:措辞均"否定结果",无可交易暗示)。
- ✅ **分段呈现推广(placebo 已完成 2026-06-16)**:placebo 每个日历效应加"全样本 vs 现代(2000后)"分段。**重磅发现**:唯二过 FDR 的指数级日历效应(星期/圣诞)在 2000 后都已测不到(星期 p=0.001→0.81、圣诞→0.20)——全样本显著只是 2000 前遗物,已喂进诚实坟场。独立审修:加 recent_min_group_n 检验力门(月份现代每组26<30→不误判)、"被套利"软化为"很可能"、标注口径与个股块不同。**cycles 不做分段**(诚实异议:谱周期检测需长历史,近5年测不出周期,硬切=造噪声)。
- 信用/流动性体制盘(=下一轨 R1) · Fed model 证伪(R2) · 行为金融(R3)。
- SPCX 等代理工具**溢价/折价 vs 净值**透明化(早先讨论;事实披露非持股建议)。
- 仓位/风险预算计算器(贴合澳洲 AUD 场景;按回撤分布算 p95 亏损 AUD,算风险不算方向)。
- **聪明钱/内部人「诚实检验」(2026-06-20 用户授权红线-例外·单独页)**:不做"跟单/跟政客买"(那破红线),做**"跟内部人/聪明钱买是否真有样本外 edge,还是幸存者+叙事"**的检验(placebo/FDR/样本外,大概率被打回)——天然是 **v1.5 自动发现的一个新候选族**(geography 已在 `candidate_space.py` 注释留位)。数据:**SEC Form 4**(EDGAR 免费结构化,需服务端带 User-Agent;WebFetch 探测被 403 是 UA 限制非不可得)是可行起点;**国会议员**(STOCK Act 披露,又脏又散)缓做。**建议建+审配对按依赖串行**(数据→统计→前端,各配不同模型独立审),非 6 路并行(有依赖+子代理不能跑代码)。红线:单独成页、框"非跟单/非荐股/检验非预测"。
  - **2026-06-20 Opus spike 完成 → 结论 GO**：SEC EDGAR Form 4 是免费/合规/一手/可服务端稳定取的干净源(优于第三方聚合);路径=daily-index 扫近期 Form 4 → 解析 `<ownershipDocument>` 只取 P(买)+A(Acquired) → company_tickers.json 做 CIK→ticker。draft `market-analysis/scripts/fetch_insider.py`(**未实地验证**:daily-index 列分隔/XML XPath/company_tickers 结构待主脑带 UA 复核;UA 邮箱已改 env `SEC_UA_CONTACT`)。复核法:`py fetch_insider.py` 先设 LOOKBACK_DAYS=1/MAX_FILINGS=20 最小验;工程坑=请求量节流(抓 .xml 而非整份 .txt)。统计上大概率仍被 placebo/FDR 打回——那正是这页要诚实呈现的。
- **finviz 式市场热力图(描述性 viz)**:板块/市值树状图按涨跌着色,纯描述合红线,Plotly 可做(半天级),比现 sectors 表直观。screener 部分 valpha150 已覆盖;分析师目标价类**别碰**(方向预测)。

---

## §4b 后续升级优化思考(2026-06-16,主脑头脑风暴,按价值排序)

> 用户要求"思考后续能升级优化什么"。下列按 价值/契合度 排,均守红线(描述/证伪,非预测)。

1. ✅ **R1 当前市场风险体制盘(已完成 2026-06-16)**:market_regime.py——VIX(2000+)/收益率曲线10Y-2Y(2000+)/VIX期限结构(2006+)各现值+历史分位+体制标签+综合描述。描述非预测。**HY信用利差诚实排除**(FRED源有1996+但缓存仅2yr,跨不了信用周期)。独立审 REQUEST_CHANGES→修:各指标独立 asof(曲线GS10/GS2月频滞后,now 05-03 如实显示)、"急性压力"软化、composite 加"描述非预测"。⚠ 待修 bug 见 §2。
2. ~~**性能:缓存置换零分布**~~ → **测量后撤回(2026-06-16)**:实测 placebo 2.9s(含1.2万次置换)、stock_checkup 10s。**置换不是瓶颈**,per-perm 缓存徒增复杂度无收益。真问题=KO 每次走 yfinance 实时抓(未进缓存),**已修**(KO 加进 fetch_data 清单,下次刷新进缓存自动消除)。教训:先测量再优化。
3. **CI 方法论完整性护栏(automation-first)**:加一个门——任何"真规律/可交易"主张若未过 FDR+分段/分半,CI 失败。把"诚实纪律"焊进流水线,防未来回归。呼应 [[automation-first-fixes]]。
4. **"当前市场环境"总览卡(综合)**:把 VIX体制+信用+相关性体制+回撤风险 综合成一句"现在大盘风险环境",和个股块6"当前风险状态"对称。(与 R1 部分重叠,可合并。)
5. **分段透镜再推广**:placebo 已做;可给 factor_audit 加"现代段因子还在不在"(很多因子也被套利);conformal 已有时间序切。
6. **导航/信息架构(UX 深化)**:面板已很多,加"诚实底线一句话"着陆 + 更好的分组/锚点,降信息过载。配合评分卡 设计维 继续往上。
7. **测试覆盖补全**:run_all 级聚合(summary 等)目前无单测;补几个防漂移。

**主脑推荐先做**:① R1(最大价值、补宏观维度)或 ② 性能缓存(资源受限下立竿见影、零风险)。③ CI 护栏 便宜且防回归,可随手加。

## §4c 试过但否决 / 测量结论(用户 2026-06-16:否定决策也记,可追溯)

> 记"试了/想了但决定不做"的事 + 怎么判的 + 结论。和"做了什么"同样重要——防以后重复踩。

- **亚洲金丝雀(KOSPI/TAIEX/ASX)→ 次日美股·无可交易增量(2026-08-01·轻量探针·测量结论)**：用户直觉"亚洲领先美股·可当指示"。探针 `research/asian_canary_probe.py`(2010–2026·日频·同日历日近似对齐)测:亚洲隔夜 vs 美股隔夜 gap / 盘中(开→收)/ 全日。**结论**:corr(亚洲,美股隔夜 gap)=**+0.29~+0.37**(亚洲确实指示隔夜方向·用户直觉对),但 **corr(亚洲,美股盘中 open→close)≈0(−0.04~+0.03)**;控住 gap 后亚洲对盘中的**增量 R²=0.0001~0.0019 ≈ 0**(9 对里最大 0.0019)。= 亚洲信息在美股**开盘价已被完全 price 进去**,开盘后没剩可交易的边际——正是"超出期货已 priced-in 就没了"的有效市场。**无 edge·不写全 spec·止步**(用户预案:探针无增量→登负结果停)。**可逆**:若换真盘中期货 ES=F/NQ=F 当控制、精修时区/假日对齐、或只在极值恐慌日条件下再看,可重探。相关 [[SPEC_FEAR_EXTREMES]](恐慌极值继续做)。

- **EBM 玻璃箱模型预测 20 日方向 → not_promote·无 edge(2026-07-29·SPEC_EBM 六步走完·测量结论)**：用户拍板"先做 EBM"。走完 ①规格→②独立审(6 BLOCKER)→②b 重审→③Sonnet 建→④Opus 审(逐行+修 4 个**测试自身** bug·非代码 bug)→⑤→⑥。诚实对决=EBM vs **喂完全相同 5 连续特征的 Logistic**(同信息基线·B2 用户拍板·只模型形态不同),2003–2026 walk-forward 6 折·n_oos=3018·purge20+embargo5·标准化只训练折 fit。**结果:两模型都没 edge**——EBM AUC=**0.446**、同信息 LR AUC=**0.461**(**均 <0.5**·≈掷硬币还略反向);Acc EBM 52.9%/LR 64.7% **都低于基率 66.6%**("恒看涨"准确率就 66.6%·两模型还不如它);**ΔAUC(EBM−LR)=−0.015·成对块自助 CI block20[−0.09,+0.07]/block40[−0.11,+0.08] 均含 0** → 玻璃箱形态没比线性多挤出任何东西。**判 not_promote·不接站**(§0 输了就认)。5 因子(6-1动量/63d波动/VIX滚动分位/10Y-2Y/Baa-10Y)predict 20 日纳指方向=没用。`ebm_duel.py`(3e6754c)留作可重跑工具(独立·fail-soft·未接 run_all·interpret 走 requirements-ebm opt-in);全套 correctness 单测在(证方法本身对·负结果非 bug 所致)。**可逆**:换特征/横期是新立项,非调参(冻结集棘轮)。相关 [[fable5-reviews]]。

- **防缩水门 → 上线即摘(2026-07-28·自酿事故·测量结论)**：为防 append-only 账本被多 workflow 竞态挤掉行,建 `ci_ledger_guard.py`(push 前比工作树 vs origin 身份前缀)挂进 5 个 workflow。**结果:refresh-data 每次 push 被门拦、主流水线连红 07-24→07-27、站上分析数据滞留 07-23**(公开 check-run annotations API 定位是门在拦)→ **立即摘门(73deb44)**。教训:① **CI-cache 专属逻辑本地测不了就别直接上线**(门与它要修的缓存 bug 都无法本地复现);② 门失败模式太硬(阻断 push=停摆)远比它防的"稀有丢行"严重。**但门暴露并促成修掉真 bug**:re-assert 只护 2/19 账本→缓存陈旧回灌被 `git add -A` 提交成缩水版(9d007ea 修:护全部 SPECS 账本+manifest+漂移测试)。门本身待根治(§2 #1/#2)+改 warn-only 后再作纵深防御重挂。可逆。门脚本/测试/规格仍在仓库(未挂接)。

- **per-perm 置换缓存 → 否决(测量驱动)**:实测 placebo 2.9s、stock_checkup 10s,1.2万次置换才 2.9s → **置换非瓶颈**,缓存徒增复杂度零收益。真瓶颈=KO 每次走 yfinance(未进缓存),已修(加进 fetch_data 清单)。**教训:先测量再优化**。
- **cycles 分段(全样本 vs 近期)→ 否决(诚实异议)**:谱周期检测需长历史,近 5 年根本测不出周期,硬切=制造噪声。故 placebo 做了分段(日历效应近期可测)、cycles 不做。
- **精简审查一轮(2026-06-16,受 ponytail 极简理念启发)**:扫本程新增代码。**仅 1 处真冗余**——登记簿/坟场/探索区各内联一份相同 fetch-json 助手 → 合为模块级 `_fetchJson`(3→1,7c332c1)。其余候选(market_regime/stock_checkup/overreaction 的分位 `(x<v).mean()*100`、各方法 SP500 加载)**跨模块、各有差异,强行 DRY 增耦合 → 按纪律不动**。**结论:代码本就精简**(既有"不加框架/复用已审 primitive/先测量后优化"的纪律,已达 ponytail 想要的极简效果,无需装该插件)。
- **event_study 升置换检验 → 否决/缓做(诚实红线,2026-06-19,子代理A 撞线停手)**：`event_study.py:153` 现用参数 t 检验算 `p_value`/`significant`，已嵌进**已发布的 signals.json**。换置换检验会**翻转已发布的 `significant`**(n=2~7 极小样本、厚尾)，属"擅改公开统计结论"，越线。**两个降险事实**：①前端本就**不渲染** event_study 的 significant/裸 p(app-1.js:424 / app-5.js:740 注释"去掉绿红方向色与裸 p")；②跨族 FDR 收的"事件因果"族走的是 **event_causal.json(方法B,已是 block-bootstrap 非参)**，不是这条 t 检验。故 event_study t 检验=遗留**展示型**链路、显著性已被前端隐藏。**结论：保留不动(方案A)**；若将来要透明对照，可加 `p_value_perm` 附加列、不改原字段(方案B,待用户拍)。
- **CSP meta → no-go(调研结论,2026-06-19,子代理A)**：清点全 10 页——0 外部 CDN(Plotly 同源)、0 内联 `onclick=` 属性，但**每页都有内联 `<script>` + 海量内联 `style=`，且 Plotly 用 `new Function`(刚需 `unsafe-eval`)**。任何能跑的 CSP 必须 `script-src 'unsafe-eval' + 内联`、`style-src 'unsafe-inline'` → **等于没加**(XSS 防护被抵消，而本站本就 0 外部源、收益≈0)。**将来想加的前置**：Plotly 换 strict-CSP bundle(去 unsafe-eval)、内联 script 抽外部 .js、内联 style 迁 style.css/class，**然后浏览器逐条实测**(盲加必白屏)。未写任何 CSP。
- **参议院「政治钱」实时源 → 搁置(调研结论,2026-06-30)**：原源(timothycarambat senate-stock-watcher)**已停更**(最新交易 2019-12)；house/senate-stock-watcher S3 桶已下线；anderseline 等免费爬虫无干净结构化数据文件。**2026 年免费、无密钥、还更新的国会交易源基本没了。** 现实活源全要钱/key：**Finnhub `congressional-trading`=付费高级档**(免费 key 只覆盖财报日历·congress 返 403·且按代码查非整包)、Quiver/Unusual Whales/FinBrain/AInvest 全付费。**决策**：senate 信号历史结论已是 null(跟议员买≈打平·无 edge)，为没 edge 的信号付费/造脆弱爬虫 ROI 差 → **当"完结历史研究"保留**(fetch_senate/senate_signal docstring 已焊"源停更·完结·故意不进流水线")。**将来若愿付费想复活**：候选 = Finnhub premium / Quiver API / FMP senate 端点 / 自爬 House Clerk XML+PDF(脆弱大工程)。
- **P-E 自动提案层 → NO-GO(2026-07-02·规格审②后否决·自生长闭环收官)**：走完六步①②(主脑写规格 §12 → 全新 Opus 审规格),**在写码前**挑出根本缺陷、主脑核实证据后采纳 NO-GO。**三条硬理由**：① **价值是幻觉**——`candidate_space` 已是 80 候选完整枚举、当前族内无未注册格点 → proposals 只能回声"builder 手划进元空间超集"的那条,不是机器发现。② **泄漏无法证伪**——元空间成员由看过数据的 builder 划;方案A两个招牌先验(周一效应/死叉)**本仓库都已 peek**(`timing_analysis.py` `dow_stats`/`sell_score` 实证)。③ **会永久污染 append-only 账本**——P-E 诱导人往 registry 写被 peek 洗白的锚点,`declared_date` 不可改 → 污染永久撤不掉。death_cross 还是不进计分账本的看跌预测(破"敢预测敢认账")。**结论**:CLAUDE.md 标它"最高风险后门"、计划审早已"推迟到最后"——**推迟≠必建**;自生长闭环 **P-A/B/C/D 已跑通=完整收尾**,P-E "开了没用+开了有险"进坟场。落点二(外部论文表对账器)可过审但价值极有限/维护成本高,未采纳。详见 `SELF_GROWING_PLAN.md §12`。**可逆**:将来若有干净的外部冻结清单来源可重议。
- **块3 §3 两判断项(argmax主导组 / 月份近期窗)→ 代码全弃·分析存档(2026-07-02·Sonnet 建+分析·Opus 双审)**：走完"判断密集→子代理建+全新 Opus 审"。子代理在 worktree 实现两版(默认=现状·404测试绿)并量化,**Opus 双审抓出子代理一处实质错误 + 纠正一个误导框架**,主脑采纳 → **两处代码均不采纳(全惰性 + 会碰边界裁决),worktree 弃码**。留下的真知识:
  - **项 A(主导组 argmax(均值) vs argmax(|偏离|))**：NO-GO。① 切默认会**擅改一个骑 q=0.05 边界的已发布 verdict**——子代理称"AAPL 星期几 flip 未改三态(rejected)"是**数据快照偶然**(那份 q=0.0599 吞了 flip;更新一周数据 q=0.036→absdev 真把 faded↔data_snoop 改了)。改已发布统计结论=撞红线(同本节 event_study 那次)。② 加诊断字段=纯惰性(前端零消费·published JSON 平白多3键)。③ **纠正框架**:"absdev=放松裁决"**是错的**——它不单调更松,换的是"哪个组须跨半一致"的判据,方向随数据两边走(合成:data_snoop→real 放松;真实 AAPL:faded→data_snoop 收紧)。④ "absdev 更贴近 SSB"方向对但**不精确**:真正主导 SSB 的组=argmax `n_g·dev²`,absdev 丢了 n_g 权重,组不等大时≠真主贡献组(dow/月份近均衡故够用,别宣称精确)。
  - **项 B(月份近期窗恒不可测)**：NO-GO 动参数。**两层瓶颈**(Opus 核实属实):①近期窗~60月<100门槛→recent_testable 恒 False;②更根本:19票 yfinance 2000起、最长319月,月份 min_group_n 全在5–26 <MIN_GROUP_N=30,判定树里更早就拦下→近期窗压根用不上。候选②(调大年数)=**纸面改善**(recent_testable 0/18→17/18 但 verdict 分布**纹丝不动**);候选③(抬门槛)本 universe **无一票**够30年历史→结构不可行。真前置=**"要不要为 AAPL/KO/INTC 等老票放宽 `_fetch_ticker` 抓1980s数据"的数据获取层决策**,不是本函数参数 → 存档待议。候选①(月频近期窗结构性不可测的诚实标注)价值真实,但要兑现须接 per-stock 体检前端(app-2.js 渲染·撞"app-js 双语/改造需单独立项"边界)→ 本轮只存档,将来连同体检前端改造一起上。
  - **教训**:两层审(Sonnet 建+分析 · 全新 Opus 双审)再次值回票价——Opus 逮住"AAPL 未改裁决"这个**数据快照偶然**(实为 q=0.05 边界脆弱)、并戳破"absdev=放松"的错误前提。**别为理论洁癖去动一个骑 FDR 边界的已发布裁决**。
- (后续否决决策续记于此)

## §5 工作流原则(资源 & 数据卫生)

- **资源**:GPU/CPU 有限 → 可慢,但**每块求完整**(建→统计块独立审→修→pytest/verify/audit→镜像→提交)。统计块按风险分级:公开统计结论必独立审,初等描述(如 R²)可自审。
- **数据卫生(用户 2026-06-16 提)**:原则=**留代码、删可再生数据**(代码确定性可重跑重生)。本项目现状已大体如此:
  - `data/raw/*.csv`(yfinance 缓存)= 可再生,CI 用 actions/cache 复用、本地可删后重抓;
  - 发布的 `web/*.json`、`docs/*.json`、`signals_history.json` = **网站产品本身,必须留**(不是中间数据);
  - 实验/作图的临时数据 = 用完即删,留脚本即可。
  - **待查**:是否有大体积可再生中间产物被误提交进 git(后续抽空 `git ls-files` 体检一遍,记这里)。
- **CI**:refresh-data 流水线步骤已加瞬时失败重试一次(ebd0408),防单次抓取抖动白丢整轮。
