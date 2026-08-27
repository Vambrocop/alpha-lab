"""自选组合对决(多盘·澳元记账)的守门测试(2026-08-26)。

守两条命门:
  ① **入场不可回填**:股数/入场价一旦记入账本,后续再跑绝不能被改写——否则等于允许
     事后挑一个好看的起点,整个前向跟踪就没意义。
  ② **防前视**:绝不能用晚于 today 的价格入场(哪怕数据里"明天"已存在)。
外加:澳元折算把汇率算进去、多盘分别记账、默认不公开计分。
hermetic:全部合成序列,不联网、不读 data/。
"""
import pandas as pd
import pytest

import my_portfolio_track as M


def _s(base=100.0, step=1.0, n=40, start="2026-01-01"):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series([base + step * i for i in range(n)], index=idx)


@pytest.fixture
def px():
    return {
        "AAA": _s(100, 2.0),        # 涨得快
        "BBB": _s(100, 0.5),
        "QQQ": _s(100, 1.0),
        "^AXJO": _s(7000, 5.0),
        "ZZZ.AX": _s(40, 0.4),
        "AUDUSD=X": _s(0.65, 0.0),  # 汇率先设常数(单独测汇率影响时再变)
    }


@pytest.fixture
def log(tmp_path, monkeypatch):
    p = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", p)
    return p


def _days(px):
    return px["AAA"].index[5].date(), px["AAA"].index[6].date()


def test_entry_waits_for_next_trading_day(px, log):
    """今天写进清单只登记,不入场(次日价此刻"还没发生")。"""
    d0, _ = _days(px)
    out = M.run(write=True, _px=px, _today=d0, _requests={("盘A", "AAA"): 10000})
    assert out["n_pending"] == 1 and out["n_portfolios"] == 0


def test_never_enters_with_a_future_price(px, log):
    """**防前视**:即便序列里"明天"的价已存在(回跑历史/数据源提前给),也不能用它入场。"""
    d0, d1 = _days(px)
    for _ in range(3):
        out = M.run(write=True, _px=px, _today=d0, _requests={("盘A", "AAA"): 10000})
        assert out["n_portfolios"] == 0 and out["n_pending"] == 1
    out = M.run(write=True, _px=px, _today=d1, _requests={("盘A", "AAA"): 10000})
    assert out["n_portfolios"] == 1                      # today 追上次日才入场


def test_shares_and_entry_never_rewritten(px, log):
    """**核心铁律**:股数/入场价锁定后,价格翻倍再跑也不许变。"""
    d0, d1 = _days(px)
    M.run(write=True, _px=px, _today=d0, _requests={("盘A", "AAA"): 10000})
    M.run(write=True, _px=px, _today=d1, _requests={("盘A", "AAA"): 10000})
    import forward_ledger as fl
    r0 = fl.read_log(log)[0]
    shares, epx = r0["shares"], r0["entry_px"]
    assert shares not in ("", None)

    bumped = {k: (v * 2 if k != "AUDUSD=X" else v) for k, v in px.items()}
    M.run(write=True, _px=bumped, _today=d1, _requests={("盘A", "AAA"): 10000})
    r1 = fl.read_log(log)[0]
    assert r1["shares"] == shares and r1["entry_px"] == epx, "被重写 = 可回填,跟踪失去意义"


def test_aud_conversion_uses_fx_for_us_stock(px, log):
    """美股按澳元记账:A$10,000 ÷ (美元价/汇率) = 股数;澳股(.AX)不折算。"""
    d0, d1 = _days(px)
    M.run(write=True, _px=px, _today=d0, _requests={("盘A", "AAA"): 10000, ("盘A", "ZZZ.AX"): 10000})
    M.run(write=True, _px=px, _today=d1, _requests={("盘A", "AAA"): 10000, ("盘A", "ZZZ.AX"): 10000})
    import forward_ledger as fl
    rows = {r["symbol"]: r for r in fl.read_log(log)}
    us, au = rows["AAA"], rows["ZZZ.AX"]
    usd_px, rate = float(us["entry_px"]), float(us["fx_entry"])
    assert abs(float(us["shares"]) - 10000 / (usd_px / rate)) < 1e-3   # 折算正确
    assert float(au["fx_entry"]) == 1.0                                # 澳股不折算
    assert abs(float(au["shares"]) - 10000 / float(au["entry_px"])) < 1e-3


def test_fx_move_changes_aud_return(px, log):
    """汇率变动必须真实改变澳元收益(澳洲税务居民的真实体验,不能被忽略)。"""
    d0, d1 = _days(px)
    M.run(write=True, _px=px, _today=d0, _requests={("盘A", "AAA"): 10000})
    base = M.run(write=True, _px=px, _today=d1, _requests={("盘A", "AAA"): 10000})
    ret_flat = base["portfolios"][0]["ret_pct"]

    weaker = dict(px)                      # 澳元走弱(AUD 更不值钱)→ 美股折成澳元更值钱
    weaker["AUDUSD=X"] = px["AUDUSD=X"] * 0.9
    moved = M.run(write=False, _px=weaker, _today=d1, _requests={("盘A", "AAA"): 10000})
    assert moved["portfolios"][0]["ret_pct"] > ret_flat


def test_multiple_portfolios_are_booked_separately(px, log):
    """多个盘各自记账、各自算收益,不混。"""
    d0, d1 = _days(px)
    req = {("指数", "QQQ"): 10000, ("我的", "AAA"): 5000, ("我的", "BBB"): 5000}
    M.run(write=True, _px=px, _today=d0, _requests=req)
    out = M.run(write=True, _px=px, _today=d1, _requests=req)
    names = {b["portfolio"] for b in out["portfolios"]}
    assert names == {"指数", "我的"}
    mine = next(b for b in out["portfolios"] if b["portfolio"] == "我的")
    assert abs(mine["invested_aud"] - 10000) < 1e-6 and len(mine["positions"]) == 2


def test_removing_marks_exited_and_keeps_row(px, log):
    """从清单删掉 → 记离场,历史行保留。"""
    d0, d1 = _days(px)
    M.run(write=True, _px=px, _today=d0, _requests={("盘A", "AAA"): 10000})
    M.run(write=True, _px=px, _today=d1, _requests={("盘A", "AAA"): 10000})
    M.run(write=True, _px=px, _today=d1, _requests={})
    import forward_ledger as fl
    rows = fl.read_log(log)
    assert len(rows) == 1 and rows[0]["status"] == "exited" and rows[0]["exit_date"]


def test_not_public_by_default(px, log):
    """默认 public=false:个人组合不自动绑上不可撤销的公开计分。"""
    out = M.run(write=True, _px=px, _today=_days(px)[0], _requests={("盘A", "AAA"): 10000})
    assert out["public"] is False and out["currency"] == "AUD"
    assert any("公开计分" in x for x in out["honesty"])


def test_parses_portfolio_symbol_amount():
    """解析 `组合名 代码 澳元`;# 注释/空行忽略;代码大写归一;两列则退化为单盘。"""
    from pathlib import Path
    tmp = Path(__file__).parent / "_tmp_pf.txt"
    tmp.write_text("# 注释\n\n美股指数 qqq 10000\n我的选股 AAPL 2500  # 行尾\nNVDA 500\n",
                   encoding="utf-8")
    try:
        got = M.read_requests(tmp)
        assert got[("美股指数", "QQQ")] == 10000.0
        assert got[("我的选股", "AAPL")] == 2500.0
        assert got[("我的组合", "NVDA")] == 500.0        # 两列 → 默认盘名
    finally:
        tmp.unlink(missing_ok=True)


def test_missing_file_is_fail_soft(tmp_path):
    assert M.read_requests(tmp_path / "nope.txt") == {}
