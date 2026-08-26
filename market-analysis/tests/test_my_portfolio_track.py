"""自选组合前向跟踪的守门测试(2026-08-26)。

最要紧的是守住**入场不可回填**:一旦某只票的入场价记入账本,后续再跑绝不能被改写
——否则等于允许事后挑一个好看的起点,整个前向跟踪就没意义了。
hermetic:全部用合成价格序列,不联网、不读 data/。
"""
import datetime

import pandas as pd
import pytest

import my_portfolio_track as M


def _px(start="2026-01-01", n=40, base=100.0, step=1.0):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series([base + step * i for i in range(n)], index=idx)


@pytest.fixture
def prices():
    return {
        "AAA": _px(base=100, step=2.0),      # 涨得快
        "BBB": _px(base=100, step=-0.5),     # 跌
        "QQQ": _px(base=100, step=1.0),      # 基准中速涨
        "^AXJO": _px(base=7000, step=5.0),
        "ZZZ.AX": _px(base=40, step=0.4),
    }


def test_entry_is_next_trading_day_not_same_day(prices):
    """防抢跑:今天写进清单,入场必须是**次日**首个交易日,不能用当天价。"""
    d = prices["AAA"].index[5].date()
    out = M.run(write=False, _px=prices, _today=d, _requests={"AAA": 1})
    # 首次只登记,不入场(次日价此刻"还没发生")→ pending
    assert out["n_pending"] == 1 and out["n_open"] == 0


def test_entry_price_is_never_rewritten(prices, monkeypatch, tmp_path):
    """**核心铁律**:入场价一旦写入,后续再跑(哪怕价格变了)也绝不重写。"""
    log = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", log)
    d0 = prices["AAA"].index[5].date()
    d1 = prices["AAA"].index[6].date()                                  # 真实流程:次日才入场
    M.run(write=True, _px=prices, _today=d0, _requests={"AAA": 1})      # 登记
    M.run(write=True, _px=prices, _today=d1, _requests={"AAA": 1})      # 入场
    import forward_ledger as fl
    first = [r for r in fl.read_log(log) if r["symbol"] == "AAA"][0]
    entry_px, entry_date = first["entry_px"], first["entry_date"]
    assert entry_px not in ("", None)

    # 把价格整体抬高一倍再跑:若实现不当,入场价会被"重新计算"成新价
    bumped = {k: v * 2 for k, v in prices.items()}
    M.run(write=True, _px=bumped, _today=d1, _requests={"AAA": 1})
    again = [r for r in fl.read_log(log) if r["symbol"] == "AAA"][0]
    assert again["entry_px"] == entry_px, "入场价被重写 = 可回填,前向跟踪失去意义"
    assert again["entry_date"] == entry_date


def test_removing_from_list_marks_exited_and_keeps_row(prices, monkeypatch, tmp_path):
    """从清单删掉 → 记离场,但历史行保留(不抹)。"""
    log = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", log)
    d0, d1 = prices["AAA"].index[5].date(), prices["AAA"].index[6].date()
    M.run(write=True, _px=prices, _today=d0, _requests={"AAA": 1})
    M.run(write=True, _px=prices, _today=d1, _requests={"AAA": 1})      # 次日入场
    out = M.run(write=True, _px=prices, _today=d1, _requests={})        # 删掉
    assert out["n_exited"] == 1 and out["n_open"] == 0
    import forward_ledger as fl
    rows = fl.read_log(log)
    assert len(rows) == 1 and rows[0]["status"] == "exited"             # 行还在
    assert rows[0]["exit_date"]


def test_benchmark_split_by_market(prices, monkeypatch, tmp_path):
    """澳股(.AX)对 ^AXJO、美股对 QQQ——两市场基准不可混算。"""
    assert M._bench_for("BHP.AX") == "^AXJO"
    assert M._bench_for("AAPL") == "QQQ"
    log = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", log)
    d0, d1 = prices["AAA"].index[5].date(), prices["AAA"].index[6].date()
    M.run(write=True, _px=prices, _today=d0, _requests={"ZZZ.AX": 1})
    out = M.run(write=True, _px=prices, _today=d1, _requests={"ZZZ.AX": 1})
    assert out["holdings"][0]["bench"] == "^AXJO"


def test_excess_is_vs_same_period_benchmark(prices, monkeypatch, tmp_path):
    """超额 = 自己收益 − **同期**基准收益(不是跟全期或别的窗口比)。"""
    log = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", log)
    d0, d1 = prices["AAA"].index[5].date(), prices["AAA"].index[6].date()
    M.run(write=True, _px=prices, _today=d0, _requests={"AAA": 1})
    out = M.run(write=True, _px=prices, _today=d1, _requests={"AAA": 1})
    h = out["holdings"][0]
    assert abs(h["excess_pct"] - (h["ret_pct"] - h["bench_ret_pct"])) < 1e-6
    assert h["ret_pct"] > h["bench_ret_pct"]           # AAA 涨得比 QQQ 快


def test_not_public_scored_by_default(prices, monkeypatch, tmp_path):
    """默认 public=false:个人组合不同于模型主张,不自动绑上公开计分。"""
    log = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", log)
    out = M.run(write=True, _px=prices, _today=prices["AAA"].index[5].date(), _requests={"AAA": 1})
    assert out["public"] is False
    assert any("公开计分" in x for x in out["honesty"])


def test_missing_request_file_is_fail_soft(monkeypatch, tmp_path):
    """清单文件不存在 → 空结果,不炸(流水线里 fail-soft)。"""
    monkeypatch.setattr(M, "REQ_FILE", tmp_path / "nope.txt")
    assert M.read_requests(tmp_path / "nope.txt") == {}


def test_parses_shares_and_comments():
    """解析:代码 + 可选股数,# 注释与空行忽略,代码大写归一。"""
    import io
    p = pd.io.common.get_handle  # noqa: F841 (仅为避免未用 import 告警)
    from pathlib import Path
    tmp = Path(__file__).parent / "_tmp_req.txt"
    tmp.write_text("# 注释\n\naapl 3\nNVDA\nBHP.AX 100  # 行尾注释\n", encoding="utf-8")
    try:
        got = M.read_requests(tmp)
        assert got == {"AAPL": 3.0, "NVDA": 1.0, "BHP.AX": 100.0}
    finally:
        tmp.unlink(missing_ok=True)


def test_never_enters_with_a_future_price(prices, monkeypatch, tmp_path):
    """防前视护栏:即便价格序列里"明天"的数据已存在(回跑历史/数据源提前给),
    也绝不能用晚于 today 的价格入场——只能等 today 追上去。"""
    log = tmp_path / "ledger.csv"
    monkeypatch.setattr(M, "LOG", log)
    d0 = prices["AAA"].index[5].date()
    for _ in range(3):                                   # 同一天反复跑,也不该入场
        out = M.run(write=True, _px=prices, _today=d0, _requests={"AAA": 1})
        assert out["n_open"] == 0 and out["n_pending"] == 1
    out = M.run(write=True, _px=prices, _today=prices["AAA"].index[6].date(), _requests={"AAA": 1})
    assert out["n_open"] == 1                            # today 追上次日 → 才入场
