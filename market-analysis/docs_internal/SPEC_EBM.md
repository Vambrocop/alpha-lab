# SPEC_EBM — 玻璃箱可解释模型(EBM)前向胜率对决(R2·过 ② 独立审)

> Fable 主脑写(2026-07-28)。**R3:②独立审判 GO-WITH-CHANGES(6 BLOCKER+7 SHOULD);B2 基线口径用户拍板
> 「同信息 LR 当门」;②b 重审 R2 → B1/B2/B4/B5/B6 PASS,余一处 B3 措辞 blocker(block_bootstrap_diff 算不出
> ΔAUC→须新写成对块自助)+3 一行 SHOULD,本 R3 全落。**
> 定位:不是又一个吹票黑箱,是把 20 日前向胜率**加一个玻璃箱竞争者**,诚实赢**同信息基线**才晋升、
> 输了登负结果(Kronos 先例)。护城河=诚实计分,不是模型花哨。
> 六步:①规格 → ②独立审(done)→ ②b 重审(done·GO)→ ⑤修规格→R3(done)→ ③建 → ④双审 → ⑥亲验。
> **门:③ 不早于 CI(re-assert 全账本)验证变绿。规格侧已 GO。**

## 0. 诚实红线(命门)
- **对着同信息基线比**(B2·用户拍板):晋升门=EBM vs **喂完全相同连续特征矩阵的 Logistic 回归**——
  只有模型形态不同,EBM 赢了才能归因于"玻璃箱形态值这个钱"。现有上线的二值+日历 LR **只作参照并列显示**
  (答"整套新做法比现在线上强不强"),**不作晋升门**(它信息集不同,赢了归因不清)。
- **赢的定义写死**(B6):主指标=**汇总 OOS 的 AUC**;门槛=**ΔAUC(EBM−同信息LR)的块自助置信区间不含 0**
  且 **Brier 不更差**。准确率因基率≈57%(恒涨即57%)会误导 → 仅作次要 sanity,不作门。
- **DoF 冻结**:特征集/horizon/变换/回看/分位窗**事前写死本 spec**(§1),③建时一个都不许加/调;
  EBM 交叉项首版关(`interactions=0`·纯可加)。调参/加特征须新立项 + 充分横期。
- **无前瞻/PIT**(S2):按各序列真实频率与发布滞后取值(§1.2);分位用**滚动**窗;样本限在全部特征都有的
  公共区间(不让"缺值"编码成体制)。
- **输了就认**:不过门 → 明写"无 edge·不晋升",进 `OPTIMIZATION_LOG §4c`;**绝不**硬塞上站。
- 晋升后仍标描述性、会错、过去≠未来;进公开计分走 append-only 账本、**只记晋升日起真前向**(S6·不回填)。

## 1. 特征与目标(自建·不碰 build_feature_df)
> **B1 修正**:`walk_forward.build_feature_df()` 只出**二值**特征,本 spec 要的连续因子它不产。原始序列
> **确在 `data/raw/combined_prices.csv`**(`T10Y2Y`/`CREDIT_SPREAD`(Baa-10Y)/`VIX`/`YIELD_*`)+ `NASDAQ_COMP_long.csv`。
> 故 **ebm_duel.py 自建连续特征矩阵**,不改 build_feature_df(顺带修 B5/S5:不污染 cpcv/factor_pruning 消费者)。
- **目标**:`fwd_up_20d` = NASDAQ_COMP 未来 20 交易日涨跌(与现有对决同靶·同 HORIZON=20,可并列参照)。
- **冻结特征集(5 个·经济动机明确·`interactions=0`)**——每个写死变换/回看/PIT:
  1. **6-1 跳月动量**:`px[t-21]/px[t-147]-1`(NASDAQ·跳最近月·同 pick v2 口径)。连续 %。
  2. **63日实现波动**:近 63 交易日日收益 std × √252(N1:选 63d≈季度中期波动·非现码 20d;此为**冻结选择**,不调)。
  3. **VIX 滚动分位**:VIX 现值在**滚动 756 交易日(3年)**窗内的百分位 [0,1]。**滚动非全样本**(防前瞻)。
  4. **收益率曲线 10Y-2Y**:`T10Y2Y`(FRED 日频),取 as-of **滞后 1 交易日**。连续(%)。
  5. **信用利差 Baa-10Y**:`CREDIT_SPREAD`。**③建先验其真实频率**:日频→滞后1日;月频→滞后至该月值真发布日
    (遇频率/发布日不明→**停下报告**,不硬取)。连续(%)。
- **dispersion 明确剔除**(B1):定义最含糊、DoF 最高、PIT 面另在 market_structure.py → **不进冻结集**
  (留 v2 需单独定义再议)。
- **样本区间**:限在 5 特征 + 目标**全部可用**的公共窗(VIX 1990+ 约束起点);**不用 VIX3M**(2009+ 会切样本、
  且缺值易编码成体制)。缺值行整行剔除,不喂 NaN-bin(S2)。

## 2. 模型与依赖隔离
- `interpret.glassbox.ExplainableBoostingClassifier(interactions=0, random_state=42, n_jobs=1)`(S1:
  `n_jobs=1` 求可复现·bagging 并行历史上非位级确定);**钉住 `interpret` 版本**进 `requirements-ebm.txt`
  (形状函数跨版本会变)。单调约束首版**不加**(先验不够强就让数据说话)。
- **依赖隔离(B4·硬红线)**:**绝不运行时 `pip install`**(那正是本周搞挂 CI 的那类脆步)。`interpret` 只在
  **显式 opt-in 环境**预装;脚本 `ImportError` → **fail-soft 跳过**(打印+不写产物+exit 0),绝不装、绝不阻断。
- 中国访客无碍(服务端算→出 JSON,非前端 CDN)。

## 3. 验证:独立 ebm_duel.py(B5·不进关键路径)
- **独立脚本 `ebm_duel.py`**,不编辑 `walk_forward.run()`(B5:walk_forward 是默认步、喂 signals.json 关键链;
  EBM 的重算/`interpret` 依赖绝不坐上去)。自读特征矩阵,walk-forward 滚动(与现有同期切分口径),训练**两个模型**:
  ① EBM ② **同信息 LR**(`LogisticRegression(C=1.0, L2)`·喂完全相同连续矩阵;唯一差异=模型形态)。
  **标准化器仅在训练折 fit、套用到测试折**(全样本 fit=前瞻·②b新增);EBM 对单调变换不变 → 标准化不给 LR 额外信息。
- **无前瞻**(S4):walk-forward 训练期严格早于测试期;20 日重叠前向 → purge 掉边界 20 行 **+ embargo 缓冲
  (≥5 交易日,防特征自相关)**;为模型 CSCV 重新推导 purge+embargo,不照搬 cpcv 的按因子 purge。
- **门用块自助 ΔAUC/ΔBrier**(B3 修正·②b 再修):`cpcv.py` 只算单因子边际、从不训模型,且 2 候选 PBO 退化 → **不用它**。
  ⚠ **也不能用 `block_bootstrap_diff`**——②b 查实它只算"子集胜率差"(`ys[sel].mean()-ys.mean()`·收布尔掩码+结局),
  **无法喂两条概率向量、算不出 ΔAUC/ΔBrier**(照抄=把晋升门实现成错统计,正是原 B3 那类"声称复用≠实际")。
  改:③**新写一个成对块自助**——每次循环块(block=horizon=20)重采样上,对**两个模型**各算 `roc_auc_score` +
  `brier_score_loss`,收集 Δ 分布(每次重采样守"两类都在"·仿现有 `n_dropped` 逻辑);**ΔAUC(EBM−同信息LR)CI 不含 0
  且 Brier 不更差 = 赢**。稳健性:CI 在 **block∈{20,40}** 各报一次(动量126d/波动63d 记忆更长·防 CI 偏窄·②b新增)。
  test #7 对这个**新函数**验,不对 block_bootstrap_diff。(严格模型级 CSCV/PBO 留后续单独工程,不首版。)
- **并列参照**(非门):同表列出现有上线二值+日历 LR 的 OOS 数(答"新做法比线上强不强"),明标"信息集不同·仅参照"。

## 4. 晋升门(赢才上·输就登)
- **赢**(§0 定义:ΔAUC CI 不含 0 + Brier 不更差,跨 OOS 稳):→ 晋升,出形状函数展示(§5)+ 可选进公开预测计分。
  同时收编隔离的 XGBoost「下月涨跌」为其可验证玻璃箱替代(N2:此收编与 SHAP/multivariate 死面板退役是
  **独立 housekeeping**,不进"效度关键"构建,免得给边界晋升施压)。
- **险胜/边界**(ΔAUC CI 贴 0、跨折不稳)→ **停机点**:报"晋升与否=判断点",交用户拍板,**绝不自我说服上站**。
- **输** → 不晋升,`OPTIMIZATION_LOG §4c` 登"EBM 无 edge·测量结论",陈旧 SHAP/multivariate 死面板一并退役。
- **MODEL_VERSION**(N3):EBM 竞争者若晋升到会上站的产物,bump `MODEL_VERSION` 并在 commit 记新旧指标对比。

## 5. 输出与展示(晋升后)
- `ebm_forward.json`(web+docs):`generated`、`target/horizon`、`oos`(EBM vs 同信息LR vs 基率:AUC/Brier/acc)、
  `bootstrap`(ΔAUC CI)、`context`(现有上线 LR 的 OOS·标信息集不同)、`shapes`(每因子 x→贡献折线·**看得见的形状**)、
  `latest`(当前各因子值+当前概率)、`honesty`(§0 全文·机器守门防删)。
- 新页/并入体制页:诚实横幅 + "赢没赢同信息基线"记分卡置顶(不藏丑)+ 5 条形状图(muted·不红绿煽情)+ 当前读数;
  zh/en·vp.css·无 CDN·as-of 具体日期·活读 json。
- **append-only 预测账本仅晋升后写,且只记晋升日起真前向**(S6·2000-2024 回测绝不回填进计分);新账本入
  `ledger_sidecar.SPECS` + 护栏。

## 6. 测试(≥10·脱网/合成)
1. 特征自建正确:5 因子各按 §1 变换/回看手算对齐(合成序列);2. **无前瞻**:训练期不含测试期前向窗
  (purge+embargo 生效);3. PIT:月频序列(若 Baa 月频)按滞后取值、不取未来发布值;4. `interactions=0` 纯可加;
5. 门逻辑:合成"EBM 不过基线"→ 判 not-promote(不写账本);合成"稳赢"→ promote;6. **同信息公平性**:EBM 与 LR
  的**源特征/行逐列相同**(标准化是唯一的每列单调变换·EBM 对其不变→不给 LR 额外信息;守 B2·②b 澄清:不是断言
  标准化后数组逐字节相同);7. **新写的成对块自助** ΔAUC/ΔBrier CI 计算正确(合成两组已知差·非 block_bootstrap_diff);
8. 缺 `interpret`→fail-soft
  跳过、exit 0、不写产物、主流水线不红(B4);9. `build_feature_df`/cpcv/factor_pruning 输出**逐字节不变**
  (证 ebm_duel 未污染·S5);10. honesty 声明进 json(机器守门);11.(S1)固定种子/版本→两次拟合位级一致。

## 7. 停机点(遇到停下报告)
- ΔAUC 险胜/边界 → 停,晋升与否交用户;- 想放开 interactions/加特征/调参提升 OOS → 停(DoF 棘轮·须新立项);
- Baa/任一序列频率或发布滞后不明 → 停(不硬取,防 PIT 泄漏);- 想给未验证模型加形状当"发现" → 停;
- 想把 EBM 预测写进 append-only 计分账本 → 仅晋升门过后 + 新账本走 sidecar/护栏 + 用户确认;
- 想回填历史进计分账本 → 停(只记晋升日起真前向)。
