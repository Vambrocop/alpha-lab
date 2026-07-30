"""ebm_duel.py — 玻璃箱可解释模型(EBM)vs 同信息 LR 前向胜率对决(SPEC_EBM.md R3·③建)

定位(§0):不是又一个吹票黑箱,是把 20 日前向胜率加一个玻璃箱竞争者。晋升门=诚实赢
**同信息基线**(B2·用户拍板):EBM vs 喂完全相同连续特征矩阵的 Logistic 回归——只有模型形态
不同,赢了才能归因于"玻璃箱形态值这个钱"。输了登负结果,绝不硬塞上站。

**完全独立/standalone**(B5):不 import、不编辑 walk_forward.py / build_feature_df / run_all.py /
cpcv.py。自建连续特征矩阵(下方 build_ebm_features),自跑 walk-forward,自算门槛统计。
FOLDS/HORIZON 等常量与 walk_forward.py 数值上一致(同期切分口径),但在本文件本地硬编码,
zero import 耦合——walk_forward 以后怎么改,这个文件都不会被牵连(也不会牵连它)。

**依赖隔离**(B4·硬红线):`interpret` 只在显式 opt-in 环境预装。本脚本对 `import interpret`
失败 fail-soft——打印跳过、不写任何产物、exit 0。绝不在运行时 `pip install`。

DoF 冻结(§1):5 个连续特征 + 变换/回看/PIT 滞后全部写死在下方常量,③建不许加/调一个。
"""
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

SCRIPTS = Path(__file__).parent
RAW_DIR = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"

# ══════════════════════════════════════════════════════════════════
# 冻结 DoF(§1)——③建不许加/调一个;调参/加特征须新立项
# ══════════════════════════════════════════════════════════════════
HORIZON = 20              # 前向 20 日涨跌·同现有对决同靶(§1)
PURGE = HORIZON           # purge 边界=horizon(§3:20 日重叠前向窗口)
EMBARGO = 5               # embargo 缓冲(§3:≥5 交易日,防特征自相关;取下限 5)
MOM_SKIP = 21             # 6-1 跳月动量:跳过最近 21 个交易日(§1.1·同 pick v2 口径)
MOM_LOOKBACK = 126        # 动量回看窗 126 交易日(t-147 = t-21-126)
VOL_WINDOW = 63           # 已实现波动窗(§1.2)
VIX_PCT_WINDOW = 756      # VIX 滚动分位窗·3 年(§1.3)
PIT_LAG = 1               # T10Y2Y / CREDIT_SPREAD 均为日频·滞后 1 交易日(§1.4/§1.5,见下方频率核验记录)

FEATURE_COLS = ["mom_6_1", "vol_63", "vix_pct_756", "t10y2y_lag1", "credit_spread_lag1"]

# 与 walk_forward.py 的 FOLDS 数值上相同(同期切分口径·§3),本地硬编码、不 import(B5 零耦合)。
FOLDS = [
    (2000, 2012, 2014),
    (2000, 2014, 2016),
    (2000, 2016, 2018),
    (2000, 2018, 2020),
    (2000, 2020, 2022),
    (2000, 2022, 2024),
]

# CREDIT_SPREAD(Baa-10Y·FRED BAA10Y)频率核验记录(§1.5 停机点条件的核验结果,非猜测)：
# fetch_data.py 里该列注释明写"日频"；本地对 combined_prices.csv 实测(2000-2026,~8000 行)显示
# 相邻交易日取值变化占比 ~67%、游程中位数=1(几乎逐日跳动，非月度台阶式重复)——两条证据都指向
# 真日频，非月频 ffill 出来的台阶。故按§1.5"日频→滞后1日"处理，未触发"频率不明→停"的停机点。

# ══════════════════════════════════════════════════════════════════
# §0 诚实红线全文(机器守门防删)——逐字保留自 SPEC_EBM.md
# ══════════════════════════════════════════════════════════════════
SPEC_S0_TEXT = (
    "## 0. 诚实红线(命门)\n"
    "- **对着同信息基线比**(B2·用户拍板):晋升门=EBM vs **喂完全相同连续特征矩阵的 Logistic 回归**——\n"
    "  只有模型形态不同,EBM 赢了才能归因于\"玻璃箱形态值这个钱\"。现有上线的二值+日历 LR **只作参照并列显示**\n"
    "  (答\"整套新做法比现在线上强不强\"),**不作晋升门**(它信息集不同,赢了归因不清)。\n"
    "- **赢的定义写死**(B6):主指标=**汇总 OOS 的 AUC**;门槛=**ΔAUC(EBM−同信息LR)的块自助置信区间不含 0**\n"
    "  且 **Brier 不更差**。准确率因基率≈57%(恒涨即57%)会误导 → 仅作次要 sanity,不作门。\n"
    "- **DoF 冻结**:特征集/horizon/变换/回看/分位窗**事前写死本 spec**(§1),③建时一个都不许加/调;\n"
    "  EBM 交叉项首版关(`interactions=0`·纯可加)。调参/加特征须新立项 + 充分横期。\n"
    "- **无前瞻/PIT**(S2):按各序列真实频率与发布滞后取值(§1.2);分位用**滚动**窗;样本限在全部特征都有的\n"
    "  公共区间(不让\"缺值\"编码成体制)。\n"
    "- **输了就认**:不过门 → 明写\"无 edge·不晋升\",进 `OPTIMIZATION_LOG §4c`;**绝不**硬塞上站。\n"
    "- 晋升后仍标描述性、会错、过去≠未来;进公开计分走 append-only 账本、**只记晋升日起真前向**(S6·不回填)。"
)


def _import_ebm_cls():
    """依赖隔离(B4·硬红线):interpret 只在显式 opt-in 环境预装。ImportError → 返回 None(调用方 fail-soft)。
    绝不运行时 pip install。"""
    try:
        from interpret.glassbox import ExplainableBoostingClassifier
        return ExplainableBoostingClassifier
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════════
# 1. 自建连续特征矩阵(§1)——不碰 build_feature_df
# ══════════════════════════════════════════════════════════════════
def build_ebm_features():
    """自读 combined_prices.csv + NASDAQ_COMP_long.csv,构建 5 个冻结连续特征 + fwd_up_20d 目标。

    行选择用 NASDAQ_COMP_long.csv 的真实交易日日历为准(同 walk_forward.build_feature_df 的做法：
    它也是先用 sp_long.index 筛行,combined_prices 只用来出各项技术/宏观特征)——因为
    combined_prices.csv 是多资产合并面板(含 BTC 等 7×24 资产),它自己的 NASDAQ 列在非纳指交易日
    有大量插入的 NaN 行(实测约 18%),直接用它做动量/波动会把非交易日算成"零收益日"、污染统计。
    VIX/T10Y2Y/CREDIT_SPREAD 则用 reindex(idx).ffill()——按真实交易日历对齐,缺口用最近已知值
    前填(as-of,不越权取未来值)。

    PIT:T10Y2Y/CREDIT_SPREAD 均为日频(§1.4/§1.5,CREDIT_SPREAD 频率核验见上方常量区注释)→
    在 ffill 对齐之上再 shift(1) 交易日,模拟发布滞后。VIX/价格类特征本身就是当日收盘可观测量,
    不加额外滞后。

    样本区间:5 特征 + 目标全部可用的公共窗,缺值整行剔除(不 NaN-bin,S2)。
    """
    prices = pd.read_csv(RAW_DIR / "combined_prices.csv", index_col="Date", parse_dates=True).sort_index()
    sp_long = pd.read_csv(RAW_DIR / "NASDAQ_COMP_long.csv", index_col=0, parse_dates=True).squeeze().dropna()
    sp_long = sp_long[sp_long > 0].sort_index()

    idx = sp_long.index                                  # 真实纳指交易日历(同 walk_forward 行选择基准)
    cp = prices.reindex(idx).ffill()                      # 宏观/VIX 面板对齐到真实交易日,as-of 前填

    # 特征1:6-1 跳月动量(§1.1·同 pick_ledger._select_picks_v2 口径:t-147→t-21 收盘,跳过最近21日)
    mom = sp_long.shift(MOM_SKIP) / sp_long.shift(MOM_SKIP + MOM_LOOKBACK) - 1

    # 特征2:63日已实现波动(年化,§1.2)
    ret = sp_long.pct_change()
    vol63 = ret.rolling(VOL_WINDOW).std() * np.sqrt(252)

    # 特征3:VIX 滚动756日(3年)分位(§1.3)——min_periods=window,强制满窗(不足3年history不出值,
    # 防早期样本用不足窗的分位数、且天然避免窗内混入 VIX 起点之前的 NaN 污染百分位计算)
    vix = cp["VIX"]
    vix_pct = vix.rolling(VIX_PCT_WINDOW, min_periods=VIX_PCT_WINDOW).apply(
        lambda x: (x <= x[-1]).mean(), raw=True
    )

    # 特征4:T10Y2Y 滞后1交易日(§1.4)
    t10y2y_lag1 = cp["T10Y2Y"].shift(PIT_LAG)

    # 特征5:CREDIT_SPREAD(Baa-10Y)滞后1交易日(§1.5,日频核验见上方)
    credit_lag1 = cp["CREDIT_SPREAD"].shift(PIT_LAG)

    feat = pd.DataFrame({
        "mom_6_1": mom, "vol_63": vol63, "vix_pct_756": vix_pct,
        "t10y2y_lag1": t10y2y_lag1, "credit_spread_lag1": credit_lag1,
    }, index=idx)

    # 目标:fwd_up_20d(同 walk_forward 靶:未来20交易日纳指涨跌,§1)
    vals = sp_long.to_numpy(dtype=float)
    n = len(vals)
    pos = np.arange(n)
    valid = pos + HORIZON < n
    fwd_up = np.full(n, np.nan)
    fwd_up[valid] = (vals[pos[valid] + HORIZON] > vals[pos[valid]]).astype(float)
    feat["fwd_up_20d"] = fwd_up

    feat = feat.dropna()                                  # 公共窗:全部可用,缺值整行剔除(不 NaN-bin)
    return feat


# ══════════════════════════════════════════════════════════════════
# 2. Walk-forward 切分:purge + embargo(§3)——为本对决重新推导,不照搬 cpcv 的按因子 purge
# ══════════════════════════════════════════════════════════════════
def purge_embargo_split(feat, train_end_year, test_end_year, purge=PURGE, embargo=EMBARGO):
    """expanding-window 切分:train=[数据起点, train_end_year)、test=[train_end_year, test_end_year)。

    无前瞻(S4):20 日前向窗口在 train/test 边界处会重叠 → 剔除 train 尾部 purge(=HORIZON)行
    (其标签用到了跨入 test 区间的未来价格)+ 再多剔 embargo(≥5)行做特征自相关缓冲。
    只剔 train,不动 test(标准 purged-CV 惯例:test 评估要保留完整样本)。"""
    feat = feat.sort_index()
    train_end_ts = pd.Timestamp(f"{train_end_year}-01-01")
    test_end_ts = pd.Timestamp(f"{test_end_year}-01-01")

    test_mask = (feat.index >= train_end_ts) & (feat.index < test_end_ts)   # DatetimeIndex 比较已是 ndarray
    train_mask_raw = feat.index < train_end_ts
    train_positions = np.where(train_mask_raw)[0]

    n_purge = purge + embargo
    keep_positions = train_positions[:-n_purge] if len(train_positions) > n_purge else np.array([], dtype=int)
    train_mask = np.zeros(len(feat), dtype=bool)
    train_mask[keep_positions] = True

    return feat.loc[train_mask], feat.loc[test_mask]


# ══════════════════════════════════════════════════════════════════
# 3. 两个模型:EBM vs 同信息 LR(§2/§3)
# ══════════════════════════════════════════════════════════════════
def fit_same_info_lr(X_train, y_train, X_test):
    """同信息 LR 基线(B2 用户拍板):喂与 EBM 完全相同的连续特征矩阵,唯一差异=模型形态。
    标准化器仅在训练折 fit、套用到测试折(②b新增·全样本fit=前瞻=bug)。"""
    scaler = StandardScaler().fit(X_train)
    Xtr = scaler.transform(X_train)
    Xte = scaler.transform(X_test)
    lr = LogisticRegression(C=1.0, penalty="l2", solver="lbfgs", max_iter=2000)
    lr.fit(Xtr, y_train)
    return lr.predict_proba(Xte)[:, 1]


def fit_ebm(ebm_cls, X_train, y_train, X_test):
    """EBM(§2):interactions=0(首版纯可加)·random_state=42·n_jobs=1(S1:求位级可复现,
    bagging 并行历史上非位级确定)。喂原始(未标准化)连续矩阵——EBM 对单调变换不变,
    标准化不给它任何额外信息,同信息公平性不受影响(§3/test#6)。"""
    ebm = ebm_cls(interactions=0, random_state=42, n_jobs=1)
    ebm.fit(X_train, y_train)
    return ebm.predict_proba(X_test)[:, 1]


# ══════════════════════════════════════════════════════════════════
# 4. 新写的成对块自助 ΔAUC/ΔBrier(B3 修正·②b 再修)
#    —— 不用 block_bootstrap_diff:它只算"子集胜率差"，喂不了两条概率向量、算不出 ΔAUC/ΔBrier。
# ══════════════════════════════════════════════════════════════════
def paired_block_bootstrap(y, p_a, p_b, block=20, B=2000, seed=42):
    """循环块自助(块长=block):每次重采样上对两个模型(p_a 通常=EBM、p_b=同信息LR)各算
    roc_auc_score + brier_score_loss,收集 Δ=a-b 分布。若某次重采样只抽到单一类别(AUC 无定义)
    → 跳过并计入 n_dropped(仿 walk_forward.block_bootstrap_diff 的 n_dropped 惯例,透明化)。"""
    y = np.asarray(y, dtype=float)
    p_a = np.asarray(p_a, dtype=float)
    p_b = np.asarray(p_b, dtype=float)
    n = len(y)
    if n == 0:
        return None
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    auc_diffs, brier_diffs = [], []
    n_dropped = 0
    for _ in range(B):
        starts = rng.integers(0, n, n_blocks)
        idx = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        ys = y[idx]
        if len(np.unique(ys)) < 2:
            n_dropped += 1
            continue
        pa, pb = p_a[idx], p_b[idx]
        auc_diffs.append(roc_auc_score(ys, pa) - roc_auc_score(ys, pb))
        brier_diffs.append(brier_score_loss(ys, pa) - brier_score_loss(ys, pb))

    if not auc_diffs:
        return None
    auc_diffs = np.array(auc_diffs)
    brier_diffs = np.array(brier_diffs)
    auc_lo, auc_hi = np.percentile(auc_diffs, [2.5, 97.5])
    br_lo, br_hi = np.percentile(brier_diffs, [2.5, 97.5])
    obs_auc = float(roc_auc_score(y, p_a) - roc_auc_score(y, p_b))
    obs_brier = float(brier_score_loss(y, p_a) - brier_score_loss(y, p_b))
    return {
        "block": block, "B": B, "n_used": int(len(auc_diffs)), "n_dropped": n_dropped,
        "auc_diff_obs": round(obs_auc, 4),
        "auc_ci95": [round(float(auc_lo), 4), round(float(auc_hi), 4)],
        "brier_diff_obs": round(obs_brier, 4),
        "brier_ci95": [round(float(br_lo), 4), round(float(br_hi), 4)],
    }


# ══════════════════════════════════════════════════════════════════
# 5. 晋升门(§0/§4)——三态:promote / not_promote / borderline_stop
# ══════════════════════════════════════════════════════════════════
def _ci_direction(ci):
    """CI 相对 0 的方向:'positive'=整段>0(EBM显著占优)·'negative'=整段<0(EBM显著更差)·'zero'=含0(不显著)。"""
    lo, hi = ci
    if lo > 0:
        return "positive"
    if hi < 0:
        return "negative"
    return "zero"


def promotion_gate(boot20, boot40, brier_ebm, brier_lr):
    """晋升门(§0/B6):ΔAUC(EBM-同信息LR)块自助 CI 不含0 + Brier 不更差;block∈{20,40}
    都要同向显著(§3稳健性:动量126d/波动63d记忆更长,防 CI 偏窄)。

    §4"险胜/边界"是 spec 刻意留白的人工判断点("报晋升与否=判断点,交用户拍板,绝不自我说服上站")——
    这里给一个显式、保守的三态启发式把它变成可运行代码,但真实"多接近算边界"仍是③建阶段一个
    有记录的实现选择(见 build 报告),不是 spec 明文数值,遇到真实数据算出 borderline 需汇报而非自行拍板。
    """
    d20, d40 = _ci_direction(boot20["auc_ci95"]), _ci_direction(boot40["auc_ci95"])
    brier_ok = bool(brier_ebm <= brier_lr)

    if d20 == "positive" and d40 == "positive" and brier_ok:
        return {"verdict": "promote", "block20_dir": d20, "block40_dir": d40, "brier_ok": brier_ok,
                "reason": "ΔAUC CI(block20/40)均不含0且EBM占优,Brier不更差——过门(§0)"}
    if d20 == "negative" and d40 == "negative":
        return {"verdict": "not_promote", "block20_dir": d20, "block40_dir": d40, "brier_ok": brier_ok,
                "reason": "ΔAUC CI(block20/40)均不含0且EBM更差——无edge,登OPTIMIZATION_LOG §4c(§0)"}
    if d20 == "zero" and d40 == "zero" and boot20["auc_diff_obs"] <= 0 and boot40["auc_diff_obs"] <= 0:
        return {"verdict": "not_promote", "block20_dir": d20, "block40_dir": d40, "brier_ok": brier_ok,
                "reason": "ΔAUC CI含0且点估计非正——无edge,登OPTIMIZATION_LOG §4c(§0)"}
    return {"verdict": "borderline_stop", "block20_dir": d20, "block40_dir": d40, "brier_ok": brier_ok,
            "reason": "险胜/边界或跨block方向不稳(§4停机点)——晋升与否交用户拍板,不自我说服上站"}


# ══════════════════════════════════════════════════════════════════
# 6. 展示辅助(§5,仅晋升后产出)
# ══════════════════════════════════════════════════════════════════
def extract_shapes(ebm, feature_cols):
    """§5:每因子 x→贡献折线("看得见的形状")。interpret 0.7.8 explain_global().data(i) 返回
    {'names': bin边界(len=n+1), 'scores': 每bin贡献(len=n)}——interactions=0 下均为单因子项。"""
    shapes = {}
    eg = ebm.explain_global()
    for i, col in enumerate(feature_cols):
        d = eg.data(i)
        shapes[col] = {
            "x_bin_edges": [float(v) for v in d.get("names", [])],
            "contribution": [float(v) for v in d.get("scores", [])],
        }
    return shapes


def build_honesty_field(verdict):
    return {
        "section": "SPEC_EBM.md §0 诚实红线(命门)",
        "text": SPEC_S0_TEXT,
        "verdict": verdict,
        "note": "本字段机器守门:严禁静默删除;晋升/不晋升/停机点判定见 gate 字段。",
    }


def _score_block(y, probs, thresh=0.5):
    auc = float(roc_auc_score(y, probs)) if len(set(y.tolist())) > 1 else None
    return {
        "auc": round(auc, 4) if auc is not None else None,
        "brier": round(float(brier_score_loss(y, probs)), 4),
        "acc": round(float(accuracy_score(y, (probs >= thresh).astype(int))), 4),
    }


def _base_rate_block(y):
    """次要 sanity(§0):恒定基率打分,准确率≈base_rate 会显得"高"但无信息量,不作门。"""
    rate = float(np.mean(y))
    probs = np.full(len(y), rate)
    return {
        "positive_rate": round(rate, 4),
        "brier": round(float(brier_score_loss(y, probs)), 4),
        "acc": round(float(accuracy_score(y, (probs >= 0.5).astype(int))), 4),
        "note": "常数基率预测·AUC 对常数打分无定义·仅 sanity 参照,不作门(§0)",
    }


def _load_existing_lr_context():
    """并列参照(非门,§3):现有上线二值+日历 LR 的 OOS 数。只读既有产物 JSON,
    不 import / 不碰 walk_forward.py(B5)。"""
    path = PROC_DIR / "walk_forward_results.json"
    if not path.exists():
        return {"available": False, "note": "walk_forward_results.json 不存在,未产出参照"}
    try:
        with open(path, encoding="utf-8") as f:
            wf = json.load(f)
        logit = wf.get("duel_summary", {}).get("logit", {})
        return {
            "available": True,
            "auc_pooled": logit.get("auc_pooled"),
            "note": "现有上线二值+日历LR(walk_forward.py)——信息集不同,仅参照,不作晋升门(§3)",
        }
    except Exception as e:
        return {"available": False, "note": f"读取失败:{e}"}


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════
def run(write=True):
    ebm_cls = _import_ebm_cls()
    if ebm_cls is None:
        print("[SKIP] ebm_duel: interpret 未安装(依赖隔离·B4)——跳过,不写任何产物,exit 0")
        return None

    feat = build_ebm_features()
    if len(feat) < 500:
        print(f"[SKIP] ebm_duel: 公共窗样本不足({len(feat)}行),跳过")
        return None

    fold_results = []
    y_pool, ebm_pool, lr_pool = [], [], []

    print("=== ebm_duel: EBM vs 同信息 LR(SPEC_EBM.md R3)===")
    print(f"{'测试期':<12}{'n_train':>8}{'n_test':>8}{'AUC(EBM)':>10}{'AUC(LR)':>10}")
    print("-" * 50)

    for train_start, train_end, test_end in FOLDS:
        train_df, test_df = purge_embargo_split(feat, train_end, test_end)
        if len(train_df) < 200 or len(test_df) < 50:
            continue
        X_train = train_df[FEATURE_COLS].to_numpy(dtype=float)
        y_train = train_df["fwd_up_20d"].to_numpy(dtype=int)
        X_test = test_df[FEATURE_COLS].to_numpy(dtype=float)
        y_test = test_df["fwd_up_20d"].to_numpy(dtype=int)
        if len(set(y_train.tolist())) < 2 or len(set(y_test.tolist())) < 2:
            continue

        lr_probs = fit_same_info_lr(X_train, y_train, X_test)
        ebm_probs = fit_ebm(ebm_cls, X_train, y_train, X_test)

        auc_ebm = float(roc_auc_score(y_test, ebm_probs))
        auc_lr = float(roc_auc_score(y_test, lr_probs))
        fold_results.append({
            "train": f"{train_start}-{train_end}", "test": f"{train_end}-{test_end}",
            "n_train": len(train_df), "n_test": len(test_df),
            "auc_ebm": round(auc_ebm, 4), "auc_lr": round(auc_lr, 4),
        })
        print(f"  {train_end}-{test_end:<6}{len(train_df):>8}{len(test_df):>8}{auc_ebm:>10.3f}{auc_lr:>10.3f}")

        y_pool.append(y_test)
        ebm_pool.append(ebm_probs)
        lr_pool.append(lr_probs)

    if not fold_results:
        print("[SKIP] ebm_duel: 无可用折(样本不足),跳过")
        return None

    y_all = np.concatenate(y_pool)
    ebm_all = np.concatenate(ebm_pool)
    lr_all = np.concatenate(lr_pool)

    oos = {
        "ebm": _score_block(y_all, ebm_all),
        "same_info_lr": _score_block(y_all, lr_all),
        "base_rate": _base_rate_block(y_all),
    }

    boot20 = paired_block_bootstrap(y_all, ebm_all, lr_all, block=20)
    boot40 = paired_block_bootstrap(y_all, ebm_all, lr_all, block=40)
    gate = promotion_gate(boot20, boot40, oos["ebm"]["brier"], oos["same_info_lr"]["brier"])

    print(f"\n=== 拼接样本外对决(n={len(y_all)})===")
    print(f"  EBM        : AUC={oos['ebm']['auc']}  Brier={oos['ebm']['brier']}  Acc={oos['ebm']['acc']}")
    print(f"  同信息LR   : AUC={oos['same_info_lr']['auc']}  Brier={oos['same_info_lr']['brier']}  Acc={oos['same_info_lr']['acc']}")
    print(f"  基率(sanity): rate={oos['base_rate']['positive_rate']}  Brier={oos['base_rate']['brier']}")
    print(f"  ΔAUC block20: {boot20['auc_diff_obs']:+.4f}  CI95={boot20['auc_ci95']}  n_dropped={boot20['n_dropped']}")
    print(f"  ΔAUC block40: {boot40['auc_diff_obs']:+.4f}  CI95={boot40['auc_ci95']}  n_dropped={boot40['n_dropped']}")
    print(f"  门: {gate['verdict']} —— {gate['reason']}")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target": "fwd_up_20d", "horizon_days": HORIZON,
        "feature_cols": FEATURE_COLS,
        "sample_window": [str(feat.index.min().date()), str(feat.index.max().date())],
        "n_folds": len(fold_results), "folds": fold_results,
        "n_oos": int(len(y_all)),
        "oos": oos,
        "bootstrap": {"block20": boot20, "block40": boot40},
        "gate": gate,
        "context_existing_lr": _load_existing_lr_context(),
        "honesty": build_honesty_field(gate["verdict"]),
    }

    if gate["verdict"] == "promote":
        X_full = feat[FEATURE_COLS].to_numpy(dtype=float)
        y_full = feat["fwd_up_20d"].to_numpy(dtype=int)
        ebm_full = ebm_cls(interactions=0, random_state=42, n_jobs=1)
        ebm_full.fit(X_full, y_full)
        out["shapes"] = extract_shapes(ebm_full, FEATURE_COLS)

        scaler_full = StandardScaler().fit(X_full)
        lr_full = LogisticRegression(C=1.0, penalty="l2", solver="lbfgs", max_iter=2000)
        lr_full.fit(scaler_full.transform(X_full), y_full)

        latest_row = feat[FEATURE_COLS].iloc[-1]
        latest_X = latest_row.to_numpy(dtype=float).reshape(1, -1)
        out["latest"] = {
            "date": str(feat.index[-1].date()),
            "features": {c: float(v) for c, v in latest_row.items()},
            "prob_ebm": float(ebm_full.predict_proba(latest_X)[:, 1][0]),
            "prob_same_info_lr": float(lr_full.predict_proba(scaler_full.transform(latest_X))[:, 1][0]),
        }
    else:
        out["shapes"] = None
        out["latest"] = None

    if write:
        PROC_DIR.mkdir(parents=True, exist_ok=True)
        with open(PROC_DIR / "ebm_forward.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] ebm_forward.json 写入 {PROC_DIR / 'ebm_forward.json'}")

    return out


if __name__ == "__main__":
    run()
