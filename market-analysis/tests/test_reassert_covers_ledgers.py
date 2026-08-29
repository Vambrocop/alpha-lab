"""test_reassert_covers_ledgers — refresh-data 的「Re-assert append-only ledgers from git」
步骤必须覆盖全部 SPECS append-only 账本(2026-07-28:此前只护 2/19,缓存回灌陈旧版账本 →
git add -A 把缩水版提交 → 真 bug,被防缩水门暴露)。

本测试脱 CI 可跑:读 workflow 原文,断言每个 SPECS 账本 basename 都出现在该步骤的 run 块里。
防「加了新账本却忘了加进 re-assert 清单」的漂移。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ledger_sidecar import SPECS  # noqa: E402

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "refresh-data.yml"


def _reassert_run_block():
    text = WF.read_text(encoding="utf-8")
    # 抓「Re-assert append-only ledgers from git」这一步到下一个 "- name:" 之间的原文
    m = re.search(r"Re-assert append-only ledgers from git.*?(?=\n      - name:)",
                  text, re.S)
    assert m, "refresh-data.yml 找不到 Re-assert 步骤"
    return m.group(0)


def test_reassert_covers_all_specs_ledgers():
    block = _reassert_run_block()
    missing = [f for f, _ in SPECS if Path(f).name not in block]
    assert not missing, (
        "refresh-data 的 Re-assert 步骤漏了这些 append-only 账本(缓存可能灌回陈旧版→丢行): "
        + ", ".join(missing))


def test_reassert_also_pins_manifest():
    # manifest(ledger_hashchain.csv)也须回 git 真相,否则 seal 会在陈旧 manifest 上追加
    assert "ledger_hashchain.csv" in _reassert_run_block()


def test_reassert_also_pins_my_portfolio_input_and_ledger():
    """2026-08-27:自选组合被缓存回灌吃掉过一次——CI 的 data 缓存把用户填的四盘配置
    (my_portfolio.txt,**输入清单**不是账本)抹回旧版,再被 git add -A 提交;
    下一轮清单为空 → 9 笔持仓会被全判「离场」。故输入清单与其账本都必须在 re-assert 名单里。
    这条测试守住它别再被漏掉(与上面守 SPECS 账本同一思路)。"""
    block = _reassert_run_block()
    for name in ("my_portfolio.txt", "my_portfolio_ledger.csv"):
        assert name in block, f"{name} 不在 CI re-assert 名单 → 缓存回灌会再次抹掉它"
