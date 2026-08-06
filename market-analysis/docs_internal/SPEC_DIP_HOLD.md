# SPEC_DIP_HOLD — 「跌了买、持有一年」的诚实账(回撤深度 → 前向收益·纯描述)

> Opus 主循环写(2026-08-05),回应用户策略:「想要跌了、然后持有一年以上」+「52 周内降低了多少可识别」
> +「单股跌 10-20% 是不是买入信号」。定位:**把用户这套择时直觉如实打分**——历史上从 52 周高点回撤多深、
> 持有多久,前向收益 vs「随便哪天买」的基率。**纯描述,不是买入信号,不设 edge/晋升路径**(与 [[SPEC_FEAR_EXTREMES]] 同调)。
> 六步:①规格 →(本文)→ ②独立审 → ③建 → ④双审 → ⑥亲验。

## 0. 诚实红线(命门)
- **纯描述·无晋升**:本研究**永不**输出「买入信号 / edge / 抄底建议」。只描述「历史上从高点跌了 X% 之后、
  持有 H 天,市场怎么走」+ 基率参照 + 稳健性,**明标非信号非荐股**。想做成抄底信号 → 停(§7)。
- **基率是诚实参照系(命门)**:大盘持有 1 年历史上就有约 **75% 上涨**(见 §2)。所以一个「跌了买」的口径要
  「有料」,必须**明显跑赢「随便哪天买」的基率**,不是「涨了就叫赢」——市场本来大概率就涨。
- **重叠窗口 → N 虚高(命门)**:一次深回撤会持续几十上百个交易日,逐日计数把同一场危机重复计成几百个「样本」。
  报告须**同时给 n_days(重叠日)、原始独立回撤段,与 `n_independent`(R2·与 [[SPEC_FEAR_GREED]] 一致:
  再把「前向窗口会重叠」——相隔不足持有天数——的回撤段并起来,因它们的未来收益共享同一段行情、不算真正独立)**;
  CI 用这些**互不重叠的聚类**做段级自助(每聚类一个数),`n_independent < MIN_EPISODES_CI` 一律 described-only、
  不出 CI。深回撤(≥20/30%)独立聚类本就只有 ~3-6 次危机,
  多为 described-only —— 这是诚实结果,不美化。
- **幸存者偏差(单股·命门)**:仓库 `stocks_prices.csv` 只有 20 只**活到今天的赢家**(AAPL/NVDA/TSLA…)。
  在它们身上回测「跌了买」会因幸存者偏差**严重高估**(跌 20% 后归零/退市的股根本不在数据里)。故**单股一律
  只做「当前距 52 周高/低」的描述性快照,绝不回测、绝不产出单股买入结论**。想拿这 20 只回测抄底 → 停(§7)。
- **体制依赖**:回撤买入的「有料」高度依赖牛熊环境(2000-2012 熊市多的年代买浅跌≈白买)。须报**分时代**
  (2000-2012 vs 2013-今)是否同向,并如实标「靠牛市撑着」的风险。
- 过去 ≠ 未来、会错、非投资建议。

## 1. 指标定义(全冻结·绝对阈值·PIT 平凡)
- 价格源:`SP500_long.csv`(2000+,与 [[SPEC_FEAR_EXTREMES]]/horizon_stats 同源)。限定到 2000-01-03+ 起。
- **52 周高/低**:trailing 252 交易日 rolling max / min(严格用 `[t-251, t]`,PIT 平凡无前视)。
- **回撤深度** `dd[t] = px[t]/rolling252_max[t] − 1`(≤0)。**「52 周内降低了多少」= 此 dd。**
- **距 52 周低点** `prox[t] = px[t]/rolling252_min[t] − 1`(≥0;=0 即就在低点)。
- **前向收益**:`forward_returns(px, H)`(复用 stats_util·含未来价·仅描述对齐)。
- **窗口 H(frozen)**:主口径 **252 交易日(~1 年)**=用户想要的持有期;并列报 **60 交易日**作短 vs 长对照。
- **回撤阈值(frozen·round number 无 DoF)**:dd ≤ **−5 / −10 / −15 / −20 / −30 %**。
- **低点邻近阈值(frozen)**:prox ≤ **2 / 5 / 10 %**(只在 H=252 报,作「接飞刀」对照)。
- **primary 单元(事前钉死)**:**SP500 · 回撤 ≥ 20% · 252 日** = 头条口径(深回撤+持有一年);其余全部 secondary/探索。

## 1.3 去聚集(独立回撤段·危机重置法·同 [[SPEC_FEAR_EXTREMES]] §1.3 精神)
- 对某阈值,**新回撤段**在 dd 首次 ≤ 阈值时开始;此后阻塞,直到 dd **回升到 ≥ `RECOVERY_FLOOR`(=−0.03,
  即回到距高点 3% 内 ≈ 已恢复)** 才解除阻塞、允许下一段。**RECOVERY_FLOOR 冻结 −0.03。**
- 段内只收合格日(dd ≤ 阈值)的前向收益。`n_episodes` = 段数;报每段起始日 + 段内最深 dd(供人看清「就 ~4 次危机」)。

## 2. 统计(每 阈值×H 一格)
- **日级(描述性,匹配对话中给用户的数)**:`n_days, up_pct, mean_pct, median_pct`。
- **基率参照**:同 H 全样本 `base_up_pct, base_mean_pct`;`diff_mean = mean_pct − base_mean_pct`。
- **段级 CI(诚实 N)**:每段取段内合格日前向收益的均值 → 得 `n_episodes` 个数;对其**有放回自助 B 次**报
  `episode_mean_pct` 与 `ci95_episode_mean`。`n_episodes < MIN_EPISODES_CI(=8)` → `too_small_no_ci=True`,
  该格 described-only、不出 CI(深回撤基本都落这)。
- **分时代**:`era1_up/mean_pct`(触发日 ≤2012)、`era2_up/mean_pct`(≥2013)、`era_same_sign`。
- **低点邻近格**:只报日级 `n_days, up_pct, mean_pct` + 基率(作接飞刀对照,不做 CI)。

## 3. 单股(纯描述快照·永不回测·§0 幸存者命门)
- 读 `stocks_prices.csv`,对每只 ≥252 日历史的票报**当前** `dd_from_52wk_high_pct`、`dist_from_52wk_low_pct`。
- 强制附 `survivorship_note`:仅 20 只幸存赢家·跌后归零/退市股不在数据·此为「离自己一年高/低多远」的事实,**非买入信号**。

## 4. verdict(三态·均非 edge/信号·硬保证)
- `described-only`(独立段 < 8 或无法分时代)/ `robust-across-crises`(段级 CI 不跨 0 且分时代同向且明显跑赢基率)
  / `crisis-driven-fragile`(跑赢基率但段级 CI 跨 0 或分时代反向)。**没有任何 edge/买入态。**

## 5. 输出与展示
- `dip_hold.json`(write_json 自动写 web+docs):`generated, as_of, price_start, recovery_floor, min_episodes_ci,
  primary_cell, base_rate{h60,h252}, drawdown_curve[{threshold_pct,horizon,...上列字段}], low_proximity[...],
  single_stocks{as_of, survivorship_note, current[{ticker,dd_from_52wk_high_pct,dist_from_52wk_low_pct}]},
  episodes{threshold_pct→[{start,deepest_dd_pct}]}, honesty[...], verdict_note`。
- 前端 `dip.html`(+docs 镜像):复用 vp.css / vp_i18n / vp_gloss;muted 不红绿;段级误差棒;活读 json;
  as-of 具体日期;zh/en;无 CDN。**文案铁律**:全页与任何 LLM 文案**绝不**把「深回撤后历史多涨」译成
  「现在可以抄底/买入」;顶部横幅 + 每处结论标「历史描述·非信号·会错」;单股表标「幸存者偏差·非信号」。
- 首页加工具磁贴 + interaction_audit PAGES 收录。

## 6. 测试(合成/固定不碰网络)
1. dd/prox 计算对齐(合成已知序列);2. rolling252 边界(< 252 日不产出);3. **去聚集**:合成一段跌破阈值→
   回升到 −2%(未过 RECOVERY_FLOOR? −2% ≥ −3% → 解除)→ 再破 = 2 段;跌破→只回到 −5%(< −3%,未解除)→再破 = 1 段;
   4. 日级 up/mean 手算对齐;5. 基率参照系;6. **段级自助 CI** 覆盖合成已知均值;7. n_episodes<8 → described-only 无 CI;
   8. 分时代 same_sign 逻辑;9. verdict 三态均可达且**无 edge/买入态**;10. 单股只出快照、`survivorship_note` 进 json(机器守门);
   11. honesty/primary_cell 进 json(防删)。

## 7. 停机点(遇到停下报告,不自行决定)
- 想给本研究加「买入信号/edge/晋升」任何一态,或把回撤直接做成抄底荐股 → **停**(纯描述硬红线);
- 想拿 20 只幸存股回测「跌了买」并当结论 → **停**(幸存者偏差·只出描述快照);
- 想按「哪个阈值/窗口看着显著」改阈值/加窗/换 primary → 停(DoF·全冻结);
- 段级 CI 跨 0 或分时代反向却想淡化、报「有料」→ 停(命门·标 fragile);
- 想引入更长历史/含退市股数据扩样本 → 停(是另立新任务,先确认数据可得 + 澳洲可达)。
