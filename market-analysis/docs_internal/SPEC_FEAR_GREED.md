# SPEC_FEAR_GREED — 恐慌贪婪合成表 + 逆向情绪检验(纯描述)

> Opus 主循环写(2026-08-05),回应用户:「CNN 恐慌贪婪指数我们能做么,如果贪婪说明什么」。
> 定位:① 用仓库能算的分量合成一个 0-100「恐慌贪婪」当前读数(**明标是 CNN 7 因子的近似,我们只有 ~3-4 个**);
> ② 老实检验民间「别人贪婪我恐惧」——极度贪婪之后前向收益是否真更差、极度恐慌之后是否真更好。
> **纯描述,不是买卖信号,不设晋升**(与 [[SPEC_DIP_HOLD]]/[[SPEC_FEAR_EXTREMES]] 同调)。
> 六步:①规格(本文)→ ②审 → ③建 → ④审 → ⑥亲验。**实现请以 `dip_hold_study.py` / `dip.html` /
> `test_dip_hold_study.py` 为样板**(write_json、聚类自助、页面 vp.css/vp_i18n/vp_gloss、copy-guard、zh/en 全照搬)。

## 0. 诚实红线(命门)
- **纯描述·无晋升·非信号**:永不输出买卖/edge/择时信号。逆向检验只出「历史上各情绪档之后市场怎么走」+ 基率 + 稳健性。
  想做成「贪婪就卖/恐慌就买」信号 → 停(§7)。
- **是近似,不是 CNN 原版**:CNN 用 7 个分量(动量/强度/广度/看跌看涨/波动/避险/垃圾债)。**我们只有 ~3-4 个**,
  合成值只作粗略情绪温度,**页面须显眼标「近似·非 CNN 官方值」**。
- **逆向情绪择时出了名地弱**:极度贪婪/恐慌的独立段本就少(去聚集后十几段量级),多数档必然 described-only。
  重叠日让 N 虚高 → 报 n_days 与 n_stretches(独立段),CI 用聚类自助;独立段 < MIN_STRETCHES_CI 一律 described-only。
- **基率是诚实参照系**:市场本来大概率涨,逆向档要「有料」必须**可靠偏离基率**(不是绝对涨跌)。
- 过去 ≠ 未来、会错、非投资建议。

## 1. 分量(全冻结·每个 → 0-100 子分,50=中性,越高越贪婪)
在 `combined_prices.csv`(2000+)上算。各分量在其输入可得的日期才算。
1. **动量 momentum**:`m = SP500 / SMA125(SP500) − 1`;子分 `clip(50 + m*500, 0, 100)`(+10%→100,−10%→0)。
2. **波动 volatility(反向)**:`p = VIX 在过去 252 日中的分位(fraction 0..1)`;子分 `(1 − p) * 100`(VIX 越低越贪婪)。
3. **期限结构 term structure**:`ts = VIX3M − VIX`;子分 `clip(50 + ts*10, 0, 100)`(contango 正=贪婪)。仅 VIX3M 可得日。
4. **避险 risk appetite**:`ra = SP500 20日收益 − GOLD 20日收益`;子分 `clip(50 + ra*500, 0, 100)`。仅 GOLD 可得日。
- **合成 composite = 当日【可得子分】的算术平均**(要求 ≥2 个可得,否则该日无 composite)。
- **档位(frozen)**:`≤25 极度恐慌 · 25–45 恐慌 · 45–55 中性 · 55–75 贪婪 · ≥75 极度贪婪`。

## 2. 当前读数(gauge)
- 报:`composite`(0-100,1 位小数)、`band`(档位)、每个分量 `{name, raw_value, subscore, available}`、`as_of`。

## 3. 逆向情绪检验(事件研究·纯描述·命门)
- 历史 composite 序列(2000+;记录实际用了哪些分量、起点日期,写进 json + honesty)。
- 每档 × 窗口 H ∈ {20, 60} 交易日:入场=当日收盘(act-after 用次日亦可,但**与 dip 保持一致:直接用当日→前向 H**),
  `forward_returns(SP500, H)`。报 `n_days, up_pct, mean_pct, base_up_pct, base_mean_pct, diff_mean`。
- **去聚集(迟滞重置·R2 修)**:合成读数在档位边界会日内抖动(如 74↔76 反复穿过 75),若「变档即断段」会把
  同一段贪婪/恐慌体制碎成上百段、假装独立段多、CI 虚窄。故某档 B 的一段在读数留在**同一侧**(贪婪侧
  ={greed,extreme_greed}/恐慌侧={fear,extreme_fear}/中性={neutral})期间持续算作同一段(只收 == B 的日);
  只有读数**离开该侧**(回中性或翻对侧,或 None)才重置、下次进入 B 才算新独立段。`n_stretches` = 段数;
  报每段 `{start, days}`(前几段即可)。**理由:一次贪婪体制=一段,而非它每抖过 75 一下就多算一段。**
- **聚类自助 CI**:复用 `dip_hold_study.cluster_bootstrap`(import 之)——按段重采样、保留段内全部日、算日加权均值 CI。
  `MIN_STRETCHES_CI = 8`;段 < 8 → `too_small_no_ci=True`、described-only、无 CI。
- **是否可靠偏离基率**:`ci_differs_base = (ci_hi < base_mean_pct) or (ci_lo > base_mean_pct)`(CI 整段在基率一侧)。
- **verdict(三态·均非信号·硬保证)**:
  - `described-only`(段 < 8);
  - `contrarian-holds`(**极度贪婪**档 `diff_mean<0` 且 `ci_differs_base` 且 CI 在基率下方;**或 极度恐慌**档 `diff_mean>0`
    且 `ci_differs_base` 且 CI 在基率上方)——即数据支持「逆向」方向且可靠;
  - `not-contrarian`(段≥8 但不满足上一条)。
- `ALLOWED_VERDICTS=("described-only","contrarian-holds","not-contrarian")`,均不含 signal/buy/sell/edge 词根。
  (R2 修:初稿曾用 `no-contrarian-edge`,含"edge"词根与本命门自相矛盾,已改名。)

## 4. 输出与展示
- `fear_greed.json`(write_json 写 web+docs):
  `{generated, as_of, composite_start, components_used, current{composite, band, components[...]},
    contrarian{bands:[{band, horizon, n_days, n_stretches, up_pct, mean_pct, base_up_pct, base_mean_pct,
    diff_mean, ci95_mean, ci_differs_base, too_small_no_ci, verdict}], stretches_by_band{band→[{start,days}]}},
    honesty[...], verdict_note}`。
- 前端 `feargreed.html`(+docs 镜像):
  - 顶部诚实横幅 + copy-guard(**绝不**把「贪婪」译成「该卖」、「恐慌」译成「该买」);
  - **仪表**:0-100 条/弧 + 当前 composite + band + 分量分解(muted,不红绿煽情);**显眼标「近似·非 CNN 官方值」**;
  - **逆向检验表**:每档 × 窗口,muted badge 三态,误差棒 + 基率参考线(照 dip.html);
  - 活读 json;as-of 具体日期;zh/en;vp.css;vp_i18n;vp_gloss;**无 CDN**。
- 首页 `grp_method` 组在 `t_vixvol` 之后加磁贴:key `t_feargreed`、emoji `🌡️`、href `feargreed.html`;
  i18n `t_feargreed`/`t_feargreed_d` 一并加(zh/en)。**web 与 docs 两份 index.html 都要改**。
- `tools/interaction_audit.py` 的 `PAGES` 加 `"feargreed.html"`。

## 5. 冻结常量
`SMA_WIN=125`,`VIX_PCT_WIN=252`,`RA_WIN=20`,`HORIZONS=[20,60]`,`BANDS`边界 `[25,45,55,75]`,
`MIN_STRETCHES_CI=8`,`B_BOOT=2000`,`SEED_BASE=20260805`。基准价格=`combined_prices.csv` 的 `SP500` 列(2000+)。

## 6. 测试(合成/固定不碰网络·以 test_dip_hold_study.py 为样板)
1. 各子分映射边界(m=+0.10→100、−0.10→0、0→50;VIX 分位 0→100、1→0;ts、ra 同理 clip);
2. 档位分类(24.9→极度恐慌、50→中性、80→极度贪婪,边界值归属明确);
3. composite = 可得子分均值(缺 1 个分量时用剩余平均;<2 个 → 无 composite);
4. 去聚集:合成 band 序列,连续同档并为一段、变档断段,数对段数;
5. 聚类自助 CI 覆盖合成已知均值(可直接测 import 来的 cluster_bootstrap);
6. `ci_differs_base` 逻辑(CI 整段在基率一侧才 True);
7. verdict 三态可达 且 **无 signal/buy/sell/edge 词根**;极度贪婪 diff<0+可靠→contrarian-holds;
8. 段 < 8 → described-only 无 CI;
9. 集成 run():结构齐全、honesty 含「近似」「非 CNN」、components_used 进 json、verdict_note 不含「该买/该卖」。

## 7. 停机点(遇到停下报告,不自行决定)
- 想把本表做成买卖/择时信号、或把「贪婪→卖/恐慌→买」写成建议 → 停(纯描述硬红线);
- 想按「哪组分量/权重/档位看着显著」改分量集/加权/挪边界 → 停(DoF·全冻结);
- 某档 CI 跨基率却想说「有逆向料」→ 停(标 no-contrarian-edge);
- 想引入没有长历史的分量塞进历史逆向检验 → 停(只可进当前 gauge,不进历史检验);
- 分量数据缺失面广导致 composite 覆盖太短(如 <10 年)→ 停下报告(可能需换分量或降级)。
