"""staleness_watchdog.py — 数据卡住看门狗:核心产物超期 → Telegram 主动告警(按日去重)。

为什么独立于主流水线(2026-07-07 用户需求·CI 红教训):
  refresh-data 卡住(如 #100-104 测试红)时,流水线内的任何自检都不会跑——
  卡住恰恰是它最沉默的时候。本脚本挂在 quick-quotes.yml(独立 workflow·盘中每10分·
  与 refresh-data 不同 concurrency 组),读的是【已提交到仓库】的产物时间戳
  (= 访客实际看到的东西),超期就发 Telegram。页面端的"⚠疑似卡住"徽章是被动等人看,
  这里是主动敲门——两道互补。

阈值按各产物的正常更新周期(与前端徽章同口径,略放宽给 CI 延迟留余量):
  signals.json  每交易日多次   >3 天 = 整条流水线卡住(周末最长 ~2.5 天)
  llm_read.json 每交易日一次   >4 天 = 日读卡住(长周末 3 天 + 1 天余量)
  llm_weekly.json 每周六一次   >9 天 = 周读卡住(正常 7 天 + 2 天余量)

防刷屏:quick-quotes 每 10 分钟一班 → 按 (产物,UTC日期) 去重,同一产物同一天只发一条,
状态记 data/watchdog_state.json(由 workflow 提交持久化;丢了最多当天重发一条,无害)。
全程 fail-soft:文件缺失/解析失败按"卡住"处理(缺产物本身就是事故);Telegram 未配置静默跳过。

单独跑:$env:PYTHONUTF8='1'; py market-analysis/scripts/staleness_watchdog.py
"""
import datetime
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPTS = Path(__file__).parent
WEB = SCRIPTS.parent / "web"
STATE = SCRIPTS.parent / "data" / "watchdog_state.json"

# (键, 文件, 时间戳字段, 超期天数阈值, 人话名, 类型)
#   kind="live"          时敏产物,紧阈值,超期=真卡住该报警(流水线断了)。
#   kind="known-limited" SEC 源(insider/ipo):SEC 封 CI 数据中心 IP,只随本地跑 run_all 补充。
#     前端标注扛日常诚实披露;watchdog 只做**松阈值兜底**(连本地补充都断了这么久才响),措辞是"该本地补"非"卡住"。
#     (2026-07-10 军师定案:accept+label+本地兜底,不花钱绕封锁;详见 HANDOVER 陈旧数据条。)
CHECKS = [
    ("signals",    WEB / "signals.json",     "generated", 3,  "信号流水线 signals.json", "live"),
    ("llm_daily",  WEB / "llm_read.json",    "generated", 4,  "大白话日读 llm_read.json", "live"),
    ("llm_weekly", WEB / "llm_weekly.json",  "generated", 9,  "本周回顾 llm_weekly.json", "live"),
    ("insider",    WEB / "insider.json",     "generated", 21, "内部人买入 insider.json", "known-limited"),
    ("ipo",        WEB / "ipo_filings.json", "generated", 21, "IPO申报 ipo_filings.json", "known-limited"),
    ("ndx",        WEB / "ndx.json",         "generated", 14, "纳指100成分 ndx.json", "live"),  # 解析器坏=可修bug,该催
    # 美债研究:纯本地算(只吃 combined_prices,不联网、不碰 SEC)→ CI 每次全量跑都该刷新 = live。
    # 阈值 5 天:全量只在工作日盘前/盘后跑,跨周末最大自然间隔约 3 天,留 2 天给 CI 延迟。
    ("treasury",   WEB / "treasury_stock_link.json", "generated", 5, "美债→美股 treasury_stock_link.json", "live"),
]

# 同一超期项最多每 SNOOZE_DAYS 天提醒一次(此前是每天;而且 watchdog_state.json 被 CI 缓存回灌反复
# 冲回旧日期 → 去重记忆丢失 → 一天轰炸多条。加长窗口 + refresh-data 把它纳入 re-assert 防回灌,双管齐下)。
SNOOZE_DAYS = 7


def _age_days(ts, now):
    """时间戳(ISO datetime 'Z' 或纯日期 'YYYY-MM-DD')→ 距 now 的整天数;解析失败返回 None。"""
    if not ts:
        return None
    try:
        s = str(ts).strip()
        if len(s) == 10:                                  # 'YYYY-MM-DD'(signals.json 口径)
            dt = datetime.datetime.fromisoformat(s).replace(tzinfo=datetime.timezone.utc)
        else:
            dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return max(0, int((now - dt).total_seconds() // 86400))
    except Exception:
        return None


def find_stale(now=None):
    """返回超期产物 [(key, 人话名, age_days|None, ts|None, kind)];缺文件/坏时间戳视同卡住(age=None)。"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stale = []
    for key, path, field, limit, label, kind in CHECKS:
        ts = None
        try:
            ts = json.loads(path.read_text(encoding="utf-8")).get(field)
        except Exception:
            pass
        age = _age_days(ts, now)
        if age is None or age > limit:
            stale.append((key, label, age, ts, kind))
    return stale


def _load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _over_snooze(last_alert, now):
    """上次提醒日(YYYY-MM-DD)距今 >= SNOOZE_DAYS 才再提醒;没提醒过 / 解析失败 → 提醒。"""
    if not last_alert:
        return True
    try:
        last = datetime.datetime.fromisoformat(str(last_alert)[:10]).replace(tzinfo=datetime.timezone.utc)
        return (now - last).days >= SNOOZE_DAYS
    except Exception:
        return True


def run(now=None, state_path=STATE):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stale = find_stale(now)
    if not stale:
        print("[看门狗] 全部新鲜,无告警")
        return []

    state = _load_state() if state_path == STATE else (
        json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {})
    today = now.strftime("%Y-%m-%d")
    fresh_alerts = [s for s in stale if _over_snooze(state.get(s[0]), now)]
    if not fresh_alerts:
        print(f"[看门狗] {len(stale)} 项超期但近 {SNOOZE_DAYS} 天已提醒过,去重跳过")
        return []

    # 只有 known-limited 源超期 → 是"该本地补"的提醒而非事故;有 live 源超期 → 真卡住
    any_live = any(s[4] != "known-limited" for s in fresh_alerts)
    lines = ["🐶 Valpha 看门狗:数据卡住了" if any_live else "🐶 Valpha 看门狗:SEC 源该本地补了"]
    for _, label, age, ts, kind in fresh_alerts:
        if age is None:
            lines.append(f"· {label}:缺失或时间戳不可读(视同卡住)")
        elif kind == "known-limited":
            lines.append(f"· {label}:已 {age} 天未刷新 · SEC 限 CI 抓取,本地跑 run_all 即补(最后 {ts})")
        else:
            lines.append(f"· {label}:已 {age} 天未更新(最后 {ts})")
    lines.append("")
    lines.append("排查:live 类看 Actions 是否红(HANDOVER §4);known-limited 类=本地跑 run_all 补齐。")

    sent = False
    try:
        import notify_telegram
        sent = notify_telegram.send("\n".join(lines), tag="watchdog")
    except Exception as e:
        print(f"[看门狗] Telegram 发送异常(非致命): {e}")
    print(f"[看门狗] 超期 {len(fresh_alerts)} 项,Telegram {'已发' if sent else '未发(未配置/失败,前端徽章仍兜底)'}")

    # 发成功才记 dedup(发失败下一班重试);state 只增不删,轻量无上限问题(键=3个产物)
    if sent:
        for key, *_ in fresh_alerts:
            state[key] = today
        try:
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print(f"[看门狗] 状态写入失败(下一班可能重发一条,无害): {e}")
    return fresh_alerts


if __name__ == "__main__":
    run()
