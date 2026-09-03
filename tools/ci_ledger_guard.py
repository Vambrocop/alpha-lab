# 刻意不写 `#!/usr/bin/env python3` shebang:Windows 的 py 启动器会遵循它、
# 转交给 `python3`,而本机 python3 指向 Microsoft Store 占位程序 → **静默退出 49,
# stdout/stderr 全空**。本地 `py tools/xxx.py` 会毫无征兆地"什么都没发生"。
# CI 用 `python xxx.py` 调用,shebang 本就无用;去掉它换来本地可跑。
"""ci_ledger_guard.py — CI append-only 防缩水门(SPEC_LEDGER_GUARD)。

push 前跑:工作树的每个 append-only 账本必须是 origin/main 对应账本的 **append-only 超集**
——origin 的身份列序列必须是本地身份列序列的**前缀**。违反(历史行被挤掉/乱序/丢)→ 退出 1,
阻断 push,job 红 + 告警;绝不静默把 origin 上的稀有公开计分行盖掉。

缘起:llm_weekly W28/W29 两周真实 LLM 读数被 6 个 workflow 并发抢 main 的 rebase/autostash 挤掉。
口径复用 ledger_sidecar.SPECS 的身份列(单一真相源);比对用明文身份元组前缀(纯 stdlib,可点名丢了哪行)。
本门管「工作树 vs origin」,sidecar 管「文件 vs manifest」,两把尺同一把柄。

铁律:**门内绝不 fetch**——只比工作树 vs 本地 origin/main remote-tracking ref(由 workflow 紧邻的
`git pull --rebase` 更新)。门内再 fetch 会拉到未整合的更新 → 假缩水。故门必须跑在 pull --rebase 之后。
"""
import csv
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "market-analysis" / "scripts"))

from ledger_sidecar import SPECS, DATA  # 单一真相源:账本清单 + 身份列口径


def append_only_violation(o_header, o_rows, l_header, l_rows, core_spec):
    """纯函数(脱 git 可单测):origin 身份前缀是否在 local 上复现。

    返回 None=放行(超集/豁免),或诊断串=违规(点名丢失的前 3 个身份元组)。
    o_rows/l_rows = list[dict](csv.DictReader 视角)。core_spec=None → 身份=全表头。
    """
    core = list(core_spec) if core_spec else list(o_header)
    # schema 变更豁免:合法代码改表头 ≠ 丢历史行,不误判
    if core_spec is None and list(o_header) != list(l_header):
        return None
    if any(c not in l_header or c not in o_header for c in core):
        return None  # 身份列不在两侧表头(schema 漂移)——无法比对,不误判为丢行

    def ids(rows):
        return [tuple(r.get(c, "") for c in core) for r in rows]

    o_ids, l_ids = ids(o_rows), ids(l_rows)
    if o_ids == l_ids[: len(o_ids)]:
        return None  # origin 是 local 的身份前缀 → append-only 超集,放行
    lost = [t for t in o_ids if t not in set(l_ids)]

    def _short(t):  # 纯 append 账本身份=全行(含长文本列)→ 截断,CI 日志才读得下去
        return tuple((v[:40] + "…") if len(v) > 40 else v for v in t)

    return (f"origin 的 {len(o_ids)} 行身份前缀在本地未复现"
            f"(丢/乱序 {len(lost)} 行,例:{[_short(t) for t in lost[:3]]})")


def _parse_csv(text):
    rdr = csv.DictReader(io.StringIO(text))
    rows = list(rdr)
    return list(rdr.fieldnames or []), rows


def _origin_ledger(rel):
    """git show origin/main:<rel> → (header, rows) 或 None(该账本尚不在 origin)。"""
    r = subprocess.run(["git", "show", f"origin/main:{rel}"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None
    return _parse_csv(r.stdout)


def check(specs=SPECS, data_dir=DATA):
    """遍历 SPECS → 违规列表 [(fname, msg)]。"""
    violations = []
    for fname, core_spec in specs:
        rel = f"market-analysis/data/{fname}"
        origin = _origin_ledger(rel)
        if origin is None:
            continue  # 新账本尚未上 origin — 无历史可保护
        o_header, o_rows = origin
        lp = Path(data_dir) / fname
        if not lp.exists():
            violations.append((fname, f"origin 有 {len(o_rows)} 行,本地文件却不存在"))
            continue
        l_header, l_rows = _parse_csv(lp.read_text(encoding="utf-8"))
        msg = append_only_violation(o_header, o_rows, l_header, l_rows, core_spec)
        if msg:
            violations.append((fname, msg))
    return violations


def main():
    violations = check()
    if violations:
        print("::error::[ledger-guard] append-only 账本相对 origin/main 会丢行 — 拒绝 push:")
        for f, m in violations:
            print(f"  ✗ {f}: {m}")
        print("  → 极可能是并发 workflow 竞态挤掉了稀有行;origin 上的行受保护,本次不推。"
              "查明后从合并后检出重推(或 --rebless 走 sidecar 留痕)。")
        sys.exit(1)
    print(f"[OK] ledger-guard:{len(SPECS)} 个 append-only 账本均 ⊇ origin/main")


if __name__ == "__main__":
    main()
