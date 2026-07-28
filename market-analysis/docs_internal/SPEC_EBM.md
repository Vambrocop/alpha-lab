# SPEC_EBM — 玻璃箱可解释模型(Explainable Boosting Machine)作为前向胜率的第三竞争者

> Fable 主脑亲写(2026-07-28)。用户拍板"先做 EBM,再考虑其他"。定位:**不是又一个吹票黑箱**,
> 而是把现有 `walk_forward` 的 20 日前向胜率对决**加一个玻璃箱竞争者**——诚实赢了简单基线才晋升,
> 输了登负结果(Kronos 先例)。护城河是诚实计分,不是模型花哨。
> 六步:①规格(本文) → ②全新 Opus 独立审规格 → ③建 → ④双审实现(公开统计结论=双审) → ⑤修 → ⑥亲验+提交。
> **门:CI 修复(re-assert 全账本)验证变绿前不开工 ③。**

## 0. 诚实红线(本功能的命门)
- **对着基线比,不孤立报**:EBM 的 OOS 指标必须**同时**对 ① 基率(base rate)② 现有 Logistic 基线
  (`walk_forward` 的 `fwd_up_20d` LR)报;"看着不错"不算数,**赢基线**才算数。
- **DoF 控制**:特征集 + horizon **事前冻结**(用现成 `BINARY_FEATURES`/连续版,不新造、不事后挑);
  EBM 交叉项**首版关**(`interactions=0`,纯可加)——先证纯可加形状够不够,别一上来放交叉项过拟合。
- **多重灵活性要 deflate**:EBM 比 LR 灵活 → 天然更会过拟合。**CPCV + PBO**(复用 `cpcv.py`)评"这点
  OOS 优势会不会是灵活性偷来的";优势不过 PBO 就当没有。
- **无前瞻**:PIT 特征、walk-forward only、CPCV 的 purge+embargo 罩住 20 日前向窗(复用现成)。
- **输了就认**:EBM 不过基线 → 明写"无 edge·不晋升",进 `OPTIMIZATION_LOG §4c` 负结果登记
  (像 Kronos n=270 定论);**绝不**因为建了就硬塞上站。
- 晋升后仍标:描述性、会错、过去≠未来;若进公开计分走 append-only 账本。

## 1. 目标与特征(复用 walk_forward,零新造)
- **目标**:`fwd_up_20d`(NASDAQ_COMP 20 交易日前向涨跌·`walk_forward.py:150` 已算)。与现有对决同靶,可直接比。
- **特征**:复用 `walk_forward.build_feature_df()`。**EBM 喂连续版因子**(动量%/63日实现波动/VIX 分位/
  10Y-2Y 斜率/Baa-10Y 信用利差/共动-分散),因为 EBM 的价值=**连续输入的形状函数**;二值特征上 EBM 退化成
  加权和(丢了形状优势)。**LR 基线用同样的信息集**(现成连续或其二值化),保证比得公平。
- **小集先验**:5–8 个经济动机明确的因子,**不做 kitchen-sink**;特征清单写死进 spec,③建时不许加。

## 2. 模型(interpret 的 EBM)
- `interpret.glassbox.ExplainableBoostingClassifier`,首版:`interactions=0`(纯可加·GAM 形态)、
  默认 outer/inner bags、随机种子固定(可复现)。**单调约束可选**(如动量对胜率设单调↑)——但**只有先验
  强到敢锁方向才加**,否则留数据说话(诚实优先于好看)。
- **依赖隔离**:`interpret` 偏重(numba/llvmlite 类) → **不进 `requirements-core.txt`**;单列
  `requirements-ebm.txt` 或让脚本缺库时 `pip install` 兜底 + 静默跳过(不阻断主流水线)。**绝不进每日关键
  CI 路径**(本周 CI 才出过事)——EBM 步骤门控同 `--full`/独立步,fail-soft。中国访客无碍(服务端算→出 JSON,
  非前端 CDN)。

## 3. 验证(复用 walk_forward + cpcv,加 EBM 为第三方)
- **接进现有对决**:`walk_forward` 现在 duel「朴素贝叶斯 vs 逻辑回归」→ **加第三方 EBM**,同一 walk-forward
  滚动、同 `fwd_up_20d`、同测试期切分,产出每期 OOS 指标。
- **报的指标**:OOS 准确率、**AUC**、**Brier**(校准很关键·别只看准确率)、hit vs 基率、对 LR 的 Δ。
- **CPCV/PBO**(`cpcv.py`):EBM vs LR 的组合净化交叉验证 + PBO(过拟合概率);EBM 的中位 OOS 优势须**正且
  PBO 低**才算真。
- 若做校准图:复用现成校准/可靠性机件,标"20 日窗自相关·块口径"。

## 4. 晋升门(赢才上,输就登)
- **赢**(EBM OOS 稳超 LR + 基率、过 CPCV/PBO):→ 晋升,出**形状函数展示**(§5)+ 可选进公开预测计分账本。
  同时**收编隔离的 XGBoost「下个月涨跌」**:EBM 是它的可验证玻璃箱替代,晋升即取代那块 6-09 死面板。
- **输**(不超基线/不过 PBO):→ **不晋升**,`OPTIMIZATION_LOG §4c` 登"EBM 无 edge·测量结论",dashboard
  的陈旧 SHAP/multivariate 面板一并退役(下架死数据),诚实收尾。**输是一种结果,照样登。**

## 5. 输出与展示(晋升后)
- `ebm_forward.json`(web+docs):`generated`、`target/horizon`、`oos`(EBM vs LR vs 基率:acc/auc/brier)、
  `cpcv`(PBO/中位Δ)、`shapes`(每因子的 x→贡献 折线点·**看得见的因子形状**)、`latest`(当前各因子取值 +
  当前预测概率)、`honesty`(§0 声明全文·机器守门防删)。
- 新页 `ebm.html`(或并入现有体制/预测页):顶部诚实横幅 + "赢没赢基线"记分卡置顶(不藏丑)+ 每因子形状图
  (muted·不红绿煽情)+ 当前读数。zh/en、vp.css、无 CDN、as-of 具体日期、活读 json。
- **晋升进公开计分**才写 append-only 预测账本(新账本入 `ledger_sidecar.SPECS` + 漂移/护栏);未晋升不写账本。

## 6. 测试(≥8)
1. 特征/目标复用 walk_forward(同 `fwd_up_20d`·同 build_feature_df,非另造);
2. 无前瞻:训练期不含测试期前向窗(purge/embargo 生效·合成序列验);
3. EBM 接进 duel 后 LR/NB 旧结果**逐字节不变**(回归靶子:加竞争者不改既有);
4. `interactions=0` 纯可加(spec 锁);5. CPCV/PBO 对 EBM 跑通、PBO∈[0,1];
6. 缺 `interpret` 库 → 该步 fail-soft 跳过、主流水线不红(依赖隔离验);
7. honesty 声明进 json(机器守门);8. 晋升门逻辑:合成"EBM 不过基线" → 判定 not-promote(不写账本)。

## 停机点(遇到停下报告,不自行决定)
- EBM OOS **险胜/边界**(Δ 小、PBO 中等)→ **停**,报"晋升与否是判断点",交用户拍板(别自我说服上站);
- 想放开 `interactions`/加特征/调参提升 OOS → **停**(DoF 棘轮;首版冻结,调参须新立项 + 充分横期);
- 想给未验证模型加 SHAP/形状当"发现" → 停(先验证模型本身,别给噪声描眉);
- 想把 EBM 预测写进 append-only 计分账本 → 仅**晋升门通过后**,且新账本走 sidecar + 护栏,经用户确认。
