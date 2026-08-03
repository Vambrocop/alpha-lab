"""test_staleness_watchdog.py — 看门狗守门:超期检测阈值 / 缺失视同卡住 / 按日去重 / 发失败不记 dedup。
全合成数据 + mock notify_telegram.send,不联网、不碰真 web/data(CI 干净检出安全)。"""
import datetime
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import staleness_watchdog as wd

NOW = datetime.datetime(2026, 7, 7, 12, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture()
def fake_web(tmp_path, monkeypatch):
    """三个产物指到 tmp,默认全新鲜;state 也指到 tmp。"""
    web = tmp_path / "web"; web.mkdir()
    files = {"signals": "signals.json", "llm_daily": "llm_read.json", "llm_weekly": "llm_weekly.json"}
    checks = [
        ("signals",    web / "signals.json",    "generated", 3, "信号流水线 signals.json", "live"),
        ("llm_daily",  web / "llm_read.json",   "generated", 4, "大白话日读 llm_read.json", "live"),
        ("llm_weekly", web / "llm_weekly.json", "generated", 9, "本周回顾 llm_weekly.json", "live"),
        ("insider",    web / "insider.json",    "generated", 21, "内部人买入 insider.json", "known-limited"),
    ]
    files["insider"] = "insider.json"
    monkeypatch.setattr(wd, "CHECKS", checks)
    state = tmp_path / "watchdog_state.json"
    monkeypatch.setattr(wd, "STATE", state)

    def write(key, ts):
        (web / files[key]).write_text(json.dumps({"generated": ts}), encoding="utf-8")

    write("signals", "2026-07-07")                    # 0 天
    write("llm_daily", "2026-07-07T03:52:34Z")        # 0 天
    write("llm_weekly", "2026-07-05T04:34:54Z")       # 2 天
    write("insider", "2026-07-07T00:00:00Z")          # 0 天(known-limited·默认新鲜,免污染既有断言)
    return {"write": write, "state": state, "web": web}


def test_all_fresh_no_alert(fake_web):
    assert wd.find_stale(NOW) == []


def test_threshold_boundaries(fake_web):
    w = fake_web["write"]
    w("signals", "2026-07-04")            # 恰 3 天 = 不超(>3 才告)
    assert wd.find_stale(NOW) == []
    w("signals", "2026-07-03")            # 4 天 > 3 → 告
    assert [s[0] for s in wd.find_stale(NOW)] == ["signals"]
    w("signals", "2026-07-07")
    w("llm_weekly", "2026-06-27T15:21:06Z")   # 9 天(周读 W26 实况) = 不超(>9 才告,正常周期内)
    assert wd.find_stale(NOW) == []
    w("llm_weekly", "2026-06-26T15:00:00Z")   # 10 天 → 告
    assert [s[0] for s in wd.find_stale(NOW)] == ["llm_weekly"]


def test_missing_or_bad_file_counts_as_stale(fake_web):
    (fake_web["web"] / "llm_read.json").unlink()                       # 缺文件
    (fake_web["web"] / "signals.json").write_text("{not json", encoding="utf-8")  # 坏 JSON
    keys = [s[0] for s in wd.find_stale(NOW)]
    assert "llm_daily" in keys and "signals" in keys
    assert all(s[2] is None for s in wd.find_stale(NOW) if s[0] in ("llm_daily", "signals"))


def test_run_sends_and_dedups_same_day(fake_web, monkeypatch):
    monkeypatch.setattr(wd, "CHECKS", [c for c in wd.CHECKS if c[0] == "llm_daily"])   # 隔离:只看 llm_daily,免得 +7 天时别的项也过期干扰 snooze 断言
    fake_web["write"]("llm_daily", "2026-07-01T00:00:00Z")   # 6 天 > 4 → 告
    calls = []
    import notify_telegram
    monkeypatch.setattr(notify_telegram, "send", lambda text, **kw: calls.append(text) or True)
    first = wd.run(NOW, state_path=fake_web["state"])
    assert len(first) == 1 and len(calls) == 1
    assert "日读" in calls[0] and "6 天" in calls[0]
    # 同日第二班:去重,不再发
    second = wd.run(NOW, state_path=fake_web["state"])
    assert second == [] and len(calls) == 1
    # 次日仍卡:7 天 snooze 窗内不再打扰(此前每天发→改成最多每 SNOOZE_DAYS 天一次·防轰炸)
    third = wd.run(NOW + datetime.timedelta(days=1), state_path=fake_web["state"])
    assert third == [] and len(calls) == 1
    # 满 SNOOZE_DAYS 天仍卡:才再发一条
    fourth = wd.run(NOW + datetime.timedelta(days=wd.SNOOZE_DAYS), state_path=fake_web["state"])
    assert len(fourth) == 1 and len(calls) == 2


def test_send_failure_does_not_record_dedup(fake_web, monkeypatch):
    """发失败(未配置/网络挂)不记 dedup → 下一班还会重试,不会静默丢告警。"""
    fake_web["write"]("llm_daily", "2026-07-01T00:00:00Z")
    import notify_telegram
    monkeypatch.setattr(notify_telegram, "send", lambda text, **kw: False)
    wd.run(NOW, state_path=fake_web["state"])
    assert not fake_web["state"].exists() or "llm_daily" not in json.loads(
        fake_web["state"].read_text(encoding="utf-8"))
