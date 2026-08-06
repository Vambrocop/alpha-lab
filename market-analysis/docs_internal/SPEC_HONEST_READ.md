# SPEC_HONEST_READ — 大白话读三个诚实研究(LLM·喂真数据·死守 copy-guard)

> Opus 主循环写(2026-08-06)。定位:把 [[SPEC_DIP_HOLD]]/vixvol/[[SPEC_FEAR_GREED]] 三个 **describe-only** 研究,
> 用 Gemini 翻成新手能懂的**大白话**,放在各页顶部。**honesty-critical 公开生成**:LLM 极易把"深跌后历史多涨""现在偏贪婪"
> 顺嘴译成买卖建议——本 spec 的命门就是**把这条堵死**。六步:①规格(本文)→ ②审 → ③建 → ④审 → ⑥亲验。
> 复用 `llm_core._llm` / `_active_model`(与 llm_daily_read 同基建);无 GEMINI_API_KEY 静默跳过、不阻断流水线。

## 0. 诚实红线(命门 · ④ 强制盯这条)
- **绝不译成买卖/方向/择时**:输出**只能**陈述"历史上如此 · 这不是信号 · 会错 · 非投资建议";
  **绝不**出现「该买/该卖/建议买入/建议卖出/现在买/赶紧买/抄底吧/加仓/清仓/满仓/止损位」这类**肯定式**操作词。
  (与三个研究 spec 的「LLM 文案铁律」一致——那几处就点名禁止 LLM 把结论译成方向。)
- **喂真数据 · 防瞎编**:prompt 里只给**脚本从三个 JSON 里真读出来的数字/结论**;LLM 不得引入任何未给的数字或断言。
  数字缺失(某 JSON 拉不到)→ 该研究这段跳过,不硬编。
- **说人话**:凡专业词(VIX/实现波动/回撤/基率/前向收益/去聚集)必须紧跟一句最朴素的括号解释(同 llm_daily_read 铁律 2)。
- **保留各研究自己的诚实结论方向**:dip=浅跌白等/深跌样本极少/持有久才是正道;vixvol=测波动不测方向;
  feargreed=当前读数 + 「贪婪之后历史并不更差 → 不是卖出信号」。不许 LLM 改写成更"可操作"的口气。
- 免责句必带;`generated` 具体日期;过去≠未来。

## 1. 输入(脚本从三个 JSON 提炼「真事实包」喂 LLM,不整份倒给)
- `dip_hold.json`:`base_rate.h252`(持有1年 up/mean)、`any_robust`(应 False)、几个代表 cell(≥5%/≥20%/≥30% × 252d 的 up/mean/verdict/n_independent)、`low_proximity`(52周最低点那格)、`verdict_note`。
- `vix_vol.json`:`r_vix`、`r_past`、一句"测波动不测方向"。
- `fear_greed.json`:`current.composite`/`current.band`、逆向表是否全 `not-contrarian`、极度贪婪 60d 的 `diff_mean`(是否 ≥0=不降反升)、`verdict_note`、`components_used`(标近似非 CNN)。
- 三包各自带该研究的「铁律提醒」(非信号/描述/会错)拼进 prompt。

## 2. 生成
- 每研究一段(2-4 句大白话);一次调用出三段(结构化:`### dip` / `### vixvol` / `### feargreed` 分隔,便于切分),或分三次调用。**冻结:分三次调用**(单研究 prompt 更聚焦、防串味、某段失败不带崩其余)。
- 模型 = `_active_model()`;温度走 llm_core 默认。

## 3b. 正向必点检查(R2·审查 HIGH#1):防"诚实要点被生成丢掉"
- 事实包喂对 ≠ 生成会保留。每研究可挂一个 `require_fn`:输出**缺**该研究命门要点 → 判不合格,重试;仍缺则**置空**
  (box 隐藏,宁可不显示也不上误导读数)。**dip 必点**:「浅到中跌(5~15%)并不比随便买强、只有深跌才更高」——
  同时在 prompt 里加该研究 `emphasis` 硬性要求。这是负向 FORBIDDEN 守门的**对称正向补**。

## 3. 后置诚实守门(命门 · 肯定式操作词才拦,别误伤免责句)
- 生成后扫描每段:命中**肯定式**禁词(见 §0 列表,如「该买」「建议卖出」「赶紧买」「清仓」)→ 该段判失败:
  **重试一次**;仍命中 → 该段**置空 + 落 append-only 日志标 `guard_blocked`**(绝不把越界文案上线)。
- **不拦**免责式否定(「这不是买入信号」「不该读成贪婪就卖」——含禁词但是正当否定,同 honesty-guard 教训 [[honesty-guard-test-disclaimers]])。
  实现(R2·审查 HIGH#2/MEDIUM#3 加固):守门列**明确操作指令**短语——补齐抄底页最诱人的
  **抄底/逢低/买进/建仓/加码/减仓/离场/梭哈/止盈**(此前漏);先**归一化去空白/分隔符**(防「建 议 买」「赶紧、买」绕过);
  否定判定用**小窗回看**(命中词前 8 字内、不跨句读,出现否定字即放行——单字版会误拦「这不是建议买入」),
  且「**不妨**」不算否定(它是"其实建议"的肯定语气)。**故意不含含糊的「该买/该卖」**(与 应该/不该 碰撞),交 prompt 铁律。

## 4. 输出与展示
- `honest_reads.json`(write_json 写 web+docs):`{generated, model, reads:{dip:{text,guard}, vixvol:{...}, feargreed:{...}}, caveat}`;
  `guard` ∈ `{ok, blocked}`(前端 blocked 时不显示该段,只显示"AI 读数暂缺")。
- append-only `honest_read_log.csv`:`date,study,model,guard,text`(可追责·绝不改历史行)。
- 前端:三页各在 intro 下方加一个 **muted「🗣️ 大白话(AI 生成·喂真数字)」盒**,活读 `honest_reads.json[study]`;
  拉不到 / guard=blocked → 整盒不显示(优雅降级)。zh 段为主(LLM 出中文);EN 下显示一句"AI plain-language read (zh only)"占位或同段。
- **前端不得再加工 LLM 文案**(不截断成标题、不高亮成信号)。

## 5. 集成 run_all
- 新步骤放在**三个研究 + fetch 之后**(读它们刷新后的 JSON);**不入 light**(LLM);**fail-soft**:无 key / 生成失败 → 静默退 0,不阻断(同 llm_daily_read)。

## 6. 测试(mock LLM·不打网络)
1. prompt 组装:三个真事实包的关键数字都进了 prompt、且带铁律提醒;
2. 后置守门:喂含「该买/建议卖出」的假输出 → 判 blocked;喂含「这不是买入信号」的正当否定 → 判 ok(不误伤);
3. 数字缺失(某 JSON 缺)→ 该段跳过、不崩;
4. 无 key → run() 静默跳过、退 0;
5. 输出结构:reads 三键齐、每段带 guard 字段、honest_read_log 追行格式对。

## 7. 停机点(遇到停下报告)
- 想让 LLM 输出带方向/买卖/择时,或放宽 §0 禁词 → 停(纯描述硬红线);
- 想把 LLM 读数接进任何计分/预测账本(它不是预测、无可结算标的)→ 停;
- 后置守门想改成"软提示不拦" → 停(越界文案绝不上线是命门)。
