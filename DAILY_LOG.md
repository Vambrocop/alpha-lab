# 每日日志 · DAILY LOG

> 用户 2026-06-18 要求：**每个工作日一条**，对照"之前计划做了没做"。
> 三段式：① 今天做了什么　② 对照之前计划（done / 未 done，**核实过、不背 log**）　③ 待办 / 未决。
> 与 `OPTIMIZATION_LOG.md` 分工：那里是**版本评分卡 + 想法 backlog + 否决记录**；这里是**每日流水 + 计划对照**。
> （新一天在最上方加，逆序，一眼看到最新。）

---

## 2026-07-28

### ① 今天做了什么
- **找回 llm_weekly W28/W29(1746b46)**：远端 append-only 周报账本被多 workflow 抢 main 挤掉两周真实
  LLM 读数,只剩 W26。从 git 逐字节找回(95a0408=W28·dba2a81=W29,非伪造),--rebless 留痕重封,已推。
- **⚠ 自酿事故:防缩水门(d69accc)搞挂主流水线**。我建的 append-only 防缩水门挂进 5 个 workflow,
  上线后 refresh-data **每次 push 都被门拦(退1)**,07-24→07-27 连红,站上分析数据滞留 07-23(仅 intraday
  quotes 在更新)。诊断:公开 check-run annotations API 拿到 `[ledger-guard]…会丢行` → 定位是门在拦。
  **立即摘门(73deb44)** 恢复主流水线(合我自己 SPEC 的停机点:门致停摆就地放宽)。
- **门暴露了真 bug 并修掉(9d007ea)**：refresh-data「Re-assert ledgers from git」步骤**只护 2/19**
  账本 → actions/cache 命中陈旧缓存时其余 17 个保持缩水版 → `git add -A` 提交缩水版 → 丢行。步骤自己
  06-30 的注释早点出这险却只护了俩。改为**覆盖全部 SPECS 账本 + manifest**(逐个 checkout·kb_ledger
  未晋升时 || true 跳过),清单漂移由 `test_reassert_covers_ledgers.py` 守。失败模式安全(纯 checkout+||true,
  不阻断 push)。

### ② 对照计划 / 教训
- **反复犯的错:部署本地测不了的 CI 改动就上线**——防缩水门与它要修的缓存 bug 都是 CI-cache 专属、
  本地无法复现。已写进记忆 [[ci-gate-and-diagnosis]]:断言远端状态前先 fetch;CI 逻辑要可本地测。
- W28/W29 恢复不受事故影响,始终在 origin。

### ③ 待办 / 未决
- **[gating] 验 refresh-data 变绿**：re-assert 全账本修已推(9d007ea)但**未经一次真跑验证**;下次 cron
  13:00 UTC(或手动 Run workflow)后核对「Commit & push」步转绿。**在此之前不再改 CI**。
- **优化 backlog(验证绿后再动·见 OPTIMIZATION_LOG)**：#1 别缓存 git 账本(根治)·#2 `git add -A`→显式
  暂存·#3 publish 逻辑抽成可本地测的 `tools/ci_publish.py`·#4 防缩水门以 warn-only 试用期重挂做纵深防御。
- 事件历史透镜(SPEC_EVENT_LENS)仍待用户放行 ②审→建。

## 2026-07-07

### ① 今天做了什么
- **CI 红 #100–104 修复(e9276b6)**：根因=#7 新增 H-1 路由测试被 `_factor_map` 无条件
  `build_feature_df()`(读 gitignore 的 combined_prices.csv)拖挂 + 尾窗守门测试直吃真数据。
  修:`_factor_map` 空列表短路;守门锁拆"合成版恒跑 + 真数据版缺则 skip"。干净检出彩排 504 绿。
- **防复发护栏(同提交)**:`tools/pre_commit_gate.py` 升级为 **git archive 干净检出跑 pytest**(CI 同构)——
  活演练:修复前索引被 deny(4 failed),修复后放行。"本地绿 CI 红"这类问题以后提交那刻即拦。
- **接力手册 `HANDOVER.md` 新建**:Fable 缺席时 Opus 当主脑/Sonnet 建造的角色表、任务队列
  (T1 _regime_arrays 双审 → T2 描述符 → T3 app-4 双语 → T4 KB 验收 ~8月初)、CI 红处置手册、
  架构升级路线 R1–R7(R1 docs 镜像漂移自动门 / R2 尾窗全库清扫并入 T1 / R4 web 微工具克制收敛)。
  CLAUDE.md 执行协议首行加指针。
- **T1 硬骨头收官(995a051 代码 + 1cb6734 数据)**:`_regime_arrays` 既有发布链的暖机段+尾窗
  y=0 双 bug(与 #7 审④同类)修掉,factor_model 尾月同款连带修,R2 全库尾窗清扫一次做完。
  真数据裁剪精确 −219;**全104池零 verdict 翻转·新旧同存活集**(golden_cross_sp500 更显著仍 survive)。
  流程:Fable 建造+写规格 → 全新 Opus 独立审(APPROVE 零 blocker,逐条核到真数据/突变测试)→
  **模型切 Opus 4.8 接主脑**收尾提交。新增合成回归锁。账本全纯追加、零历史行改。
- **R1 镜像守卫补缺口(e3d57a5)**:先查后动发现 R1 自动门已存在,但守卫漏了 `vp_i18n.js`
  (显式点名式)→ 泛化成 `vp_*.js` 前缀 + 补 test_docs_mirror.py(10测)。pytest 509→519。
- **T3 app-4.js 全量双语(Opus 主脑编排)**:Sonnet 建(~223 vpL·SPCX/CGT/恐贪/个股/时钟/小游戏·
  Plotly 占位符保留)→ Opus 审 APPROVE(插值两侧齐·免责语忠实·零逻辑改·reRenderAppTools 幂等)→
  主脑亲接 dashboard.html toggle(集成缺口:CGT/SPCX明细/小游戏不在 renderAll)→ playwright 实测切换
  (SPCX 零残留中文·CGT 含 AUD 税务免责语全变英文·零报错)。**#5 五文件双语全完成**。

### ② 对照计划
| 项 | 状态 |
|---|---|
| #7 命门相收官(昨) | ✅ 已推(6eda2b5);今日 CI 红即其首批 CI 暴露的测试数据依赖,已修 |
| T1 _regime_arrays 尾窗 bug | ✅ 完成(HANDOVER §3 已勾);双审 APPROVE |
| CI 观察哨(fetch_cot/putcall 首跑) | ⏳ Refresh 不随 push 触发;下一班 schedule(13:00 UTC)验证门禁转绿 |

### ③ 待办 / 未决
- [ ] 下一班 Refresh schedule 确认测试门禁转绿 + COT/P·C fetch 步首跑 warning 检查
- [ ] 后续任务队列全部移交 `HANDOVER.md` §3;下一个建议 **T3(机械·Sonnet 可做)** 或 **T2(单审)**
- [ ] **主脑现为 Opus 4.8**(Fable 缺席);T7 大工程留 Fable 在场时立项

## 2026-06-20

### ① 今天做了什么（全部已推）
- **③ 自生长 Phase 0+1+1b**：`candidate_space.py`(37 预注册候选·有界性测) + `quality_gate.py`(双栏BY-FDR+三态裁决·反自欺7测·纯噪声→存活≈0) + `autodiscovery.py`(候选→真统计路由，**WIP 需提速**见③)。决策已拍 🔴-A=双栏并列 / 🔴-B=DSR纳入(反过拟合诊断不破红线)。计划存 `PLAN_V15_AUTODISCOVERY.md`。
- **并行子代理**：🔳 heatmap.html(finviz式纯CSS热力图，Sonnet) + SEC Form4 内部人数据 spike(结论GO·draft fetch_insider.py未验·Opus)。
- **交互/数据灭火**(用户连发现真问题)：导航溢出(flex-wrap)·9工具页加↩返回·lab表格移动端溢出(.panel overflow-x)·**数据陈旧→CI 被禁**(改名后)→借 git 凭证 enable+dispatch **真重启 CI**(bot 已自动续刷)。
- **新工具 `tools/interaction_audit.py`**(治本)：真浏览器点全部11页每个按钮+查溢出/死按钮/失败请求/新鲜度，接进 site-audit.yml；当场抓出 lab 移动端溢出。
- **冗余+逻辑审**：清 3 个真未用 import；修 autodiscovery `_seed_for` 用内置 hash()(跨进程随机→种子不可复现)→hashlib。结论:代码本就精简。

### ② 对照计划（核实）
| 项 | 状态 |
|---|---|
| ③ Phase 0/1 | ✅ 建+测完成 |
| ③ Phase 1b | 🟡 **建好但 WIP**(run_all >280s 太慢) |
| CI 自动刷新 | ✅ 修复(曾被改名禁用→已 enable) |
| 交互问题(用户提) | ✅ 全修 |

### ③ 待办 / 未决
- [ ] **autodiscovery 提速**(下次首要)：run_all(write=False) >280s。瓶颈=日历 perm_test N=1000×10×2 + rebound `rolling().apply` 逐窗。改法:rebound 向量化前向收益、calendar 降N/复用、缓存零分布。提速后才能验证(含 SP500 日历 p 对 placebo 内建校验)+ **独立审(判断密集)** + 接 run_all。**未接 run_all、未上线**。
- [ ] ③ 续：Phase 2 账本 → 3 前端 → 4 衰减 → 5 DSR。
- [ ] **教训**(已存记忆 [[review-needs-browser-interaction]]):审查必含浏览器交互+看截图+数据查实测;自动扫描(AST/pyflakes)必 grep 复核(今天 date/timedelta/stats 假阳性)。
- [ ] 内部人 spike draft fetch_insider.py 待主脑带 UA 实地复核(backlog)。

## 2026-06-19

### ① 今天做了什么（全部已推 origin/main，10 提交）
- **Valpha Lab 三层体系成型**（用户公开命名 + 仓库改名 alpha-lab→valpha-lab）：
  - 🛰️ **Valpha150 大盘**（152 票排序板，12 板块色码 + 标签）+ build_valpha150.py + **每交易日盘后自动刷**（a39edde）
  - 📊 板块概览 · 📡 雷达（加**综合评分**）· 🎲 配置器（AUD·逆波动率×持有期·**CGT 币种 AUD/USD/CNY 切换** + 相对实时汇率 export_fx.py）
  - 🔥 野蛮专区 · 🛫 **IPO 雷达三档分级**（已上市/已递表/传闻，真数据，子代理E）· 🛡️ **诚实门方法论页**（大白话 6 道门，子代理G）
  - 🌱 **v2.0 自生长视图**（9564a72）：把已有跨族 FDR 总账做成"诚实知识库"展示 + **衰减追踪**（a127672：标登记簿里现代段已失效的真规律，"真规律也会死、不藏"，**全部保留只标注**）
- **IA**：index.html 设为根入口，dashboard.html 为完整仪表盘；导航按 4 组重排 + 分隔线（491c21e）
- **测试**：repair_ledgers/build_valpha150/export_fx 补 pytest（69a7c91，子代理F·主脑审改 2 处错断言）→ 全套 **193 绿**
- **5 路多维审查 + 修复闭环**（用户"4 subagent 多维审网页 + 修缺陷"）：
  - 五维：correctness/security/a11y/honesty/simplicity；**诚实审零越界通过**、简洁审确认自包含合理（不抽共享文件=对的）
  - ffb43a3：localStorage 顶层防抛（**= GitHub Pages"打不开"根因**，隐私模式/拦插件会抛异常中断渲染）+ index latest_tier 补 esc + --mut 对比度达 WCAG AA + lang aria-label
  - 1a0bd09：9 页移动端 @media 断点（此前**零断点**）+ valpha150/sectors 表头键盘可排序（scope/tabindex/aria-sort/Enter-Space + th:focus）+ valpha150 波动列空值统一 + advisor 首屏占位消除闪白
- **清理**：撤 v3_sparse 死嵌入、删脚本/测试（3ef0a26，结论留坟场）
- **本会话续推（审查后 next-step，均已推）**：
  - ✅ **#5 分段透镜→factor_audit**（74c5f46）：把 placebo 时间衰减揭穿推广到因子尸检。用户定 🔴 现代段=最近8年。15 因子中 **2 已淡(疑被套利)**：NASDAQ_mom20_neg / nasdaq_high_vol（全段显著→近8年测不到）。口径明确异于 OOS 裁决（in-sample 描述）。含 verify 段位门 + 5 个合成因子三态单测（pytest 198 绿）
  - ✅ **② 主盘轻量双语外壳**（56eb8df）：实测全量~1548行中文/零基建/ROI低 → 用户改选"轻量外壳"。译 导航+9 view-intro+onboarding+头部，深度面板留中文（EN 顶部说明）。自包含内联脚本只动 [data-i18n]+nav 文案、不碰 JS 面板内文。site_audit 0 报错

### ② 对照之前计划（核实过，不背 log）
| 之前的待办 | 状态 |
|---|---|
| S1/S6/S5/S2（06-14 审查后续） | ✅ **全完成**（LOOP_DECISIONS 已记；CLAUDE"下一步=S1/S6/S5/S2"已**过时**，本次一并改正） |
| 整站 relayout / IA 重组 | ✅ 已做（491c21e：4 组重排 + 分隔线 + 诚实底线着陆句） |
| v3_sparse 撤展示 + 取精华进坟场 | ✅ 已做（3ef0a26） |
| v1.5/v2.0 自生长 | 🟡 **展示层已做**（跨族 FDR 知识库 + 衰减追踪）；**自动发现闭环（候选→质量门→并入）仍未做** |
| #5 分段透镜→factor_audit | ✅ **本会话完成**（74c5f46）——唯一真欠的旧任务已清；揭 2 因子现代段被套利 |

### ③ 待办 / 未决（均非缺陷——审查缺陷已清零；#5/② 本会话已完成）
- [ ] **v1.5 自生长自动发现闭环**：发现候选→质量门→并入登记簿/坟场→度量（现仅展示层）——**最大工程，建议单独立项 + 重审**
- [ ] 可选更深：conformal 合成覆盖测试 · event_study 升置换检验 · CSP meta（需浏览器实测，盲加可能白屏）
- [ ] IPO 数据定期更新机制 · Valpha150 成分**季度复盘**（数据日刷已自动；成分发现待做）
- [ ] 主盘双语：若日后要"全量"再升级（现为轻量外壳：导航+intro 英文、深度面板中文）
- [ ] #5 可选更深（spec 列）：现代段也可推到 conformal 时间切；factor 多窗梯度（5/8年）若用户想看衰减速度

## 2026-06-18

### ① 今天做了什么
- **环境**：瘦身 ~/.claude（79 skill 归档、关 7 插件、auto-compact 重开、allow 121→33）；发布开源仓库 **`dont-fool-yourself`**（诚实统计方法论）
- **复审 Codex 加固轮**（`1e2af35`）+ 主脑小修：vol_model 空集兜底、stdout utf-8、ledger_hash 文档；亲验 pytest 161 绿、账本 append-only 守住
- **新功能（均已推 `cd58579` / 工作树）**：
  - 📡 data-health 抽屉（逐源 live/缓存/过期）
  - 📋 每日诚实摘要 `daily_digest`（三层：事实/留意/探索 + 红线运行时门禁，否定语境放行）
  - 🎲 试胆区 `tipjar`（朴素动量玩具预测，**6652 天 49.9% ≈ 掷硬币**，公开计分、娱乐非建议）
  - 📈 观点/预测 `outlook`（**授权的"出格"区**：纳指方向 + 个股看好/看淡 + 免责）——新建 view + nav
- **CI**：浏览器审计只在全量刷新跑（`7f4c44d`，省盘中 30 分钟白烧）；**复审 Codex CSP 迁移**（onclick→data-*+委托，事件迁移完整，无死按钮）
- **数据/清理**：复活 `horizon_stats`（持有期基率）回 run_all；加个股 **闪迪 SNDK**（fetch_data + stock_checkup + export_stocks 三处）；CLAUDE.md 加"观点区是授权例外"注
- **实时性**：Refresh CI 在 `1e2af35` **实测 SUCCESS**（此前 `714c05b` failure 已修）——真绿勾，不再凭推理

### ② 对照之前计划（OPTIMIZATION_LOG "7 项明天可做"，逐项核实）
| # | 任务 | 状态（看代码/数据） |
|---|---|---|
| 1 | 验 FRED / 闭环 HY | 🟢 信用维度全史已确认 `2000-01-03`（用 Baa-10Y，不靠 secret）；HY-secret 多余、不必做 |
| 2 | 导航/IA 登记簿分组 | ✅ 已做（五组在 index.html:311）；**广义整站 relayout = 新活，待做** |
| 3 | R3 羊群维度 | ✅ 已做 |
| 4 | 个股大跌完整分布 | ✅ 已做 |
| 5 | 分段透镜→factor_audit | ❌ **仍欠**（唯一真欠的旧任务） |
| 6 | 聚合层单测 | ✅ 已做（test_stock_checkup/market_regime/overreaction 在） |
| 7 | 全量 run_all 端到端 | ✅ 已做（今日多次） |

### ③ 待办 / 未决
- [ ] **v3_sparse**：撤展示 + 取精华进坟场（已定，待执行：先确认坟场有结论）
- [ ] **整站 relayout**：9 标签 IA 重组（主脑出方案 → 浏览器验证；含"诚实底线一句话"着陆）
- [ ] **#5 分段透镜推广到 factor_audit**（唯一真欠的旧任务）→ **spec 已写：`market-analysis/docs_internal/SPEC_FACTOR_SEGMENT.md`**；明天先拍 🔴 判断点（现代段怎么切：A/B/C + 年限）再建
- [ ] **🛰️ 个股发现包**：扩 universe + 雷达 screener + 板块（housekeeping 之后）
- [ ] **胆子大的页面**：📈观点 + 🎲试胆 已是出格区；用户要保留/可更大胆——按需调
- [ ] **本批收口**：全量 run_all 确认（horizon 复活 + 闪迪 + outlook 集成）→ 提交推送
- [ ] 之后：**v1.5 自生长闭环**（发现候选→质量门→并入登记簿/坟场→度量）
