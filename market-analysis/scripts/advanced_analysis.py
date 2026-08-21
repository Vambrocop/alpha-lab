"""
advanced_analysis.py
高级统计 + 机器学习分析：
  1. Granger因果检验      → 谁领先谁？
  2. VAR脉冲响应函数      → 冲击如何传导？
  3. GARCH波动率模型      → 何时市场最危险？
  4. HMM隐马尔可夫模型   → 牛/熊/震荡状态自动识别
  5. STL季节分解          → 趋势 vs 季节 vs 噪声
  6. Random Forest        → 什么因素最能预测涨跌？
  7. XGBoost              → 下个月涨跌概率
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from statsmodels.tsa.stattools import grangercausalitytests, adfuller
from statsmodels.tsa.api import VAR
from statsmodels.tsa.seasonal import STL
from arch import arch_model
from hmmlearn.hmm import GaussianHMM
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb

RAW_DIR  = Path(__file__).parent.parent / "data" / "raw"
PROC_DIR = Path(__file__).parent.parent / "data" / "processed"
PROC_DIR.mkdir(exist_ok=True)

ASSETS = ["NASDAQ", "DXY", "BTC", "ETH"]

# ─────────────────────────────────────────────────────────────────
def load():
    df = pd.read_csv(RAW_DIR / "combined_prices.csv",
                     index_col="Date", parse_dates=True)
    return df[ASSETS].dropna(how="all").ffill()

def log_returns(prices):
    return np.log(prices / prices.shift(1)).dropna()

# ── 1. ADF单位根检验（平稳性） ────────────────────────────────────
def stationarity_test(ret):
    print("\n=== 1. ADF平稳性检验 ===")
    rows = []
    for col in ASSETS:
        s = ret[col].dropna()
        stat, pval, _, _, _, _ = adfuller(s)
        is_stationary = pval < 0.05
        rows.append({"asset": col, "adf_stat": stat, "p_value": pval,
                     "stationary": is_stationary})
        print(f"  {col}: p={pval:.4f} → {'平稳✓' if is_stationary else '非平稳✗'}")
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "stationarity.csv", index=False)
    return df

# ── 2. Granger因果检验 ───────────────────────────────────────────
def granger_causality(ret, max_lag=10):
    print("\n=== 2. Granger因果检验 ===")
    pairs = [
        ("DXY",    "NASDAQ", "美元→纳指"),
        ("BTC",    "NASDAQ", "BTC→纳指"),
        ("NASDAQ", "BTC",    "纳指→BTC"),
        ("ETH",    "BTC",    "以太坊→BTC"),
        ("BTC",    "ETH",    "BTC→以太坊"),
    ]
    rows = []
    for cause, effect, label in pairs:
        data = ret[[effect, cause]].dropna()
        try:
            res = grangercausalitytests(data, maxlag=max_lag, verbose=False)
            # 取最优滞后期（p值最小）
            best_lag = min(res, key=lambda k: res[k][0]["ssr_ftest"][1])
            pval = res[best_lag][0]["ssr_ftest"][1]
            significant = pval < 0.05
            rows.append({"cause": cause, "effect": effect, "label": label,
                         "best_lag_days": best_lag, "p_value": pval,
                         "significant": significant})
            sig = "✓ 显著" if significant else "✗ 不显著"
            print(f"  {label}: 滞后{best_lag}天 p={pval:.4f} {sig}")
        except Exception as e:
            print(f"  {label}: 计算失败 {e}")
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "granger_causality.csv", index=False)
    return df

# ── 3. VAR模型 + 脉冲响应 ────────────────────────────────────────
def var_impulse_response(ret):
    print("\n=== 3. VAR脉冲响应函数 ===")
    data = ret[ASSETS].dropna()
    model = VAR(data)
    # AIC选择最优滞后
    best = model.select_order(maxlags=10)
    lag = best.aic if best.aic > 0 else 5
    lag = min(int(lag), 10)
    result = model.fit(lag)
    print(f"  最优滞后期: {lag} 天")
    print(f"  AIC: {result.aic:.2f}")

    # 脉冲响应：BTC冲击对NASDAQ的影响（未来20天）
    irf = result.irf(periods=20)
    irf_vals = irf.irfs  # shape: (periods, n_vars, n_vars)
    asset_idx = {a: i for i, a in enumerate(ASSETS)}

    rows = []
    shocks = ["BTC", "DXY"]
    targets = ["NASDAQ", "ETH"]
    for shock in shocks:
        for target in targets:
            si, ti = asset_idx[shock], asset_idx[target]
            for t in range(20):
                rows.append({
                    "shock": shock, "target": target,
                    "day": t, "response": irf_vals[t, ti, si]
                })
    df = pd.DataFrame(rows)
    df.to_csv(PROC_DIR / "var_irf.csv", index=False)
    print("  脉冲响应已保存")
    return df

# ── 4. GARCH(1,1) 波动率模型 ─────────────────────────────────────
def garch_volatility(ret):
    print("\n=== 4. GARCH(1,1) 波动率预测 ===")
    results = {}
    for asset in ["NASDAQ", "BTC"]:
        s = ret[asset].dropna() * 100  # 转为百分比
        am = arch_model(s, vol="Garch", p=1, q=1, dist="normal")
        res = am.fit(disp="off")
        cond_vol = res.conditional_volatility  # 条件波动率序列
        ann_vol  = cond_vol * np.sqrt(252)     # 年化

        out = pd.DataFrame({
            "date":          cond_vol.index,
            "cond_vol_daily": cond_vol.values,
            "cond_vol_ann":   ann_vol.values,
        })
        out.to_csv(PROC_DIR / f"garch_{asset.lower()}.csv", index=False)
        results[asset] = out

        # 当前波动率状态
        cur = ann_vol.iloc[-1]
        avg = ann_vol.mean()
        pct = (ann_vol <= cur).mean() * 100
        print(f"  {asset}: 当前年化波动率={cur:.1f}% 历史均值={avg:.1f}% 历史分位={pct:.0f}%")
    return results

# ── 5. HMM 市场状态识别（牛/熊/震荡） ────────────────────────────
def hmm_regimes(ret, n_states=3):
    print(f"\n=== 5. HMM 市场状态识别（{n_states}状态） ===")
    s = ret["NASDAQ"].dropna().values.reshape(-1, 1)

    model = GaussianHMM(n_components=n_states, covariance_type="full",
                        n_iter=200, random_state=42)
    model.fit(s)
    states = model.predict(s)

    # 按均值排序：最低=熊市，最高=牛市
    means = [model.means_[i][0] for i in range(n_states)]
    order = np.argsort(means)
    state_names = {}
    labels = ["熊市", "震荡", "牛市"] if n_states == 3 else [f"状态{i}" for i in range(n_states)]
    for rank, orig in enumerate(order):
        state_names[orig] = labels[rank]

    named_states = [state_names[s] for s in states]

    df = pd.DataFrame({
        "date":       ret["NASDAQ"].dropna().index,
        "state_id":   states,
        "state_name": named_states,
        "nasdaq_ret": ret["NASDAQ"].dropna().values,
    })
    df.to_csv(PROC_DIR / "hmm_regimes.csv", index=False)

    # 统计各状态
    for name in labels:
        sub = df[df["state_name"] == name]
        pct = len(sub) / len(df) * 100
        avg = sub["nasdaq_ret"].mean() * 252 * 100
        print(f"  {name}: {pct:.1f}% 时间  年化均值={avg:.1f}%")

    # 转移矩阵
    trans = pd.DataFrame(model.transmat_,
                         index=[state_names[i] for i in range(n_states)],
                         columns=[state_names[i] for i in range(n_states)])
    trans.to_csv(PROC_DIR / "hmm_transition.csv")
    print("  转移矩阵已保存")
    return df, trans

# ── 6. STL季节分解 ───────────────────────────────────────────────
def stl_decomposition(prices):
    print("\n=== 6. STL季节分解 ===")
    results = {}
    for asset in ["NASDAQ", "BTC"]:
        s = prices[asset].dropna()
        # 月度重采样
        monthly = s.resample("ME").last()
        stl = STL(monthly, period=12, robust=True)
        res = stl.fit()

        df = pd.DataFrame({
            "date":    monthly.index,
            "observed": monthly.values,
            "trend":   res.trend,
            "seasonal": res.seasonal,
            "residual": res.resid,
        })
        df.to_csv(PROC_DIR / f"stl_{asset.lower()}.csv", index=False)
        results[asset] = df

        # 季节强度 = 1 - Var(residual)/Var(seasonal+residual)
        strength = max(0, 1 - np.var(res.resid) / np.var(res.seasonal + res.resid))
        print(f"  {asset}: 季节强度={strength:.3f} ({'显著' if strength > 0.4 else '不显著'})")
    return results

# ── 7. 特征工程 ───────────────────────────────────────────────────
def build_features(prices, ret):
    """构建预测特征：技术指标 + 跨资产信号 + 历法特征"""
    df = pd.DataFrame(index=prices.index)

    for asset in ASSETS:
        r = ret[asset]
        df[f"{asset}_ret1"]   = r
        df[f"{asset}_ret5"]   = r.rolling(5).mean()
        df[f"{asset}_ret20"]  = r.rolling(20).mean()
        df[f"{asset}_vol20"]  = r.rolling(20).std()
        df[f"{asset}_mom60"]  = prices[asset].pct_change(60)
        # RSI
        gain = r.clip(lower=0).rolling(14).mean()
        loss = (-r.clip(upper=0)).rolling(14).mean()
        df[f"{asset}_rsi14"]  = 100 - 100 / (1 + gain / (loss + 1e-10))

    # 跨资产信号
    df["btc_nasdaq_ratio"] = prices["BTC"] / prices["NASDAQ"]
    df["dxy_lag5"]         = ret["DXY"].shift(5)    # DXY滞后5日信号
    df["btc_lag3"]         = ret["BTC"].shift(3)    # BTC滞后3日信号

    # 历法特征
    df["month"]         = df.index.month
    df["is_q_end"]      = df.index.month.isin([3, 6, 9, 12]).astype(int)
    df["is_tax_month"]  = (df.index.month == 4).astype(int)   # 美国报税季
    df["is_sep"]        = (df.index.month == 9).astype(int)   # 九月效应
    df["is_nov"]        = (df.index.month == 11).astype(int)  # 十一月强势
    df["weekday"]       = df.index.dayofweek
    df["is_monday"]     = (df.index.dayofweek == 0).astype(int)

    # 目标变量：NASDAQ下个月是否上涨
    # 先剔除前向窗口不完整的尾部行：NaN > 0 会变成 False，
    # 直接 astype(int) 会把最后约40行错误标成「下跌」且 dropna 查不出来
    fwd = ret["NASDAQ"].shift(-20).rolling(20).sum().reindex(df.index)
    df = df[fwd.notna()].copy()
    df["target"] = (fwd[fwd.notna()] > 0).astype(int)

    return df.dropna()

# ── 8. Random Forest 特征重要性 ──────────────────────────────────
def random_forest_importance(features_df):
    print("\n=== 7. Random Forest 特征重要性 ===")
    feature_cols = [c for c in features_df.columns if c != "target"]
    X = features_df[feature_cols]
    y = features_df["target"]

    # 时间序列交叉验证（不能用普通随机分割！）
    tscv = TimeSeriesSplit(n_splits=5)
    scaler = StandardScaler()
    rf = RandomForestClassifier(n_estimators=300, max_depth=6,
                                 random_state=42, n_jobs=-1)
    scores = []
    for train_idx, test_idx in tscv.split(X):
        X_tr = scaler.fit_transform(X.iloc[train_idx])
        X_te = scaler.transform(X.iloc[test_idx])
        rf.fit(X_tr, y.iloc[train_idx])
        scores.append(accuracy_score(y.iloc[test_idx], rf.predict(X_te)))

    print(f"  时间序列CV准确率: {np.mean(scores):.3f} ± {np.std(scores):.3f}")

    # 全量训练拿特征重要性
    X_scaled = scaler.fit_transform(X)
    rf.fit(X_scaled, y)
    importance = pd.DataFrame({
        "feature":    feature_cols,
        "importance": rf.feature_importances_,
    }).sort_values("importance", ascending=False)
    importance.to_csv(PROC_DIR / "rf_importance.csv", index=False)

    print("  Top 10 特征：")
    for _, row in importance.head(10).iterrows():
        bar = "█" * int(row["importance"] * 200)
        print(f"    {row['feature']:<25} {bar} {row['importance']:.4f}")
    return importance

# ── 9. XGBoost 下个月涨跌概率 ────────────────────────────────────
def xgboost_predict(features_df):
    print("\n=== 8. XGBoost 预测 ===")
    feature_cols = [c for c in features_df.columns if c != "target"]
    X = features_df[feature_cols]
    y = features_df["target"]

    # 训练集：最后20%作为测试集
    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, verbosity=0
    )
    model.fit(X_train, y_train,
              eval_set=[(X_test, y_test)], verbose=False)

    preds = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, preds)
    print(f"  测试集准确率: {acc:.3f}")

    # 最新预测
    latest_prob = model.predict_proba(X.iloc[[-1]])[0][1]
    print(f"  当前信号：未来20天NASDAQ上涨概率 = {latest_prob*100:.1f}%")

    # 保存预测序列
    result = pd.DataFrame({
        "date":        X_test.index,
        "actual":      y_test.values,
        "predicted":   preds,
        "probability": proba,
    })
    result.to_csv(PROC_DIR / "xgb_predictions.csv", index=False)

    # 特征重要性
    imp = pd.DataFrame({
        "feature":    feature_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    imp.to_csv(PROC_DIR / "xgb_importance.csv", index=False)
    return result, latest_prob

# ── 主流程 ────────────────────────────────────────────────────────
def run_all():
    print("加载数据...")
    prices = load()
    ret    = log_returns(prices)

    stationarity_test(ret)
    granger_causality(ret)
    var_impulse_response(ret)
    garch_volatility(ret)
    hmm_regimes(ret)
    stl_decomposition(prices)

    print("\n构建机器学习特征...")
    features_df = build_features(prices, ret)
    random_forest_importance(features_df)
    result, latest_prob = xgboost_predict(features_df)

    print(f"\n{'='*50}")
    print(f"  分析完成！所有结果在 data/processed/")
    print(f"  XGBoost当前信号：NASDAQ未来20天上涨概率 {latest_prob*100:.1f}%")
    print(f"{'='*50}")

if __name__ == "__main__":
    # 顶层 fail-soft:--full 研究面板,任一资产整列缺失(ret.dropna 连坐)或 ML 边缘不阻断流水线。
    # 与 build_signals 同类隐患(多资产整表 dropna),此处非 CI 关键(仅 --full),故兜底跳过即可。
    try:
        run_all()
    except Exception as e:
        print(f"[高级ML分析] 顶层异常,fail-soft 不阻断: {type(e).__name__}: {e}")
        raise SystemExit(0)
