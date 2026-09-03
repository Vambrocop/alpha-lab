# 刻意不写 `#!/usr/bin/env python3` shebang:Windows 的 py 启动器会遵循它、
# 转交给 `python3`,而本机 python3 指向 Microsoft Store 占位程序 → **静默退出 49,
# stdout/stderr 全空**。本地 `py tools/xxx.py` 会毫无征兆地"什么都没发生"。
# CI 用 `python xxx.py` 调用,shebang 本就无用;去掉它换来本地可跑。
"""ci_publish.py — CI 提交/推送逻辑(从 inline YAML 抽出来,为的是能在本地跑测试)。

## 为什么要抽出来(§2 #3·2026-09-03)

2026-07-24~27 主流水线连红四天、站上数据滞留——根因是**写在 workflow YAML 里的 commit/push
逻辑本地根本跑不了**,只能推上去看 CI 红不红,改一次等一轮。§4c 记的教训第一条就是
"CI 专属逻辑本地测不了就别直接上线"。把这段逻辑搬进 Python 后:

  · 可以在临时 git 仓库里跑真实的 clone/commit/rebase/push,断言每一种分支;
  · push 被拒 → 重试这条路径,以前只能祈祷,现在有测试盯着;
  · 以后改发布逻辑,先在本地变红,而不是在生产变红。

## 显式暂存(§2 #2)

原来是 `git add -A`。它的问题不是"多提交了无关文件",而是**把缓存回灌的陈旧文件一起提交**——
2026-07 那次 `market-analysis/data` 整个目录被 actions/cache 回灌成旧版,`-A` 照单全收,
把缩水的账本提交上去了。

改成只暂存流水线真正产出的三个目录(实证:近半年每一次 auto-refresh 提交都只碰这三处):
  market-analysis/web/  ·  docs/  ·  market-analysis/data/
误入工作树的任何其它东西(scratch 文件、__pycache__、误改的源码)从此进不了自动提交。

**注意这不是万能药**:陈旧文件若正好落在这三个目录里,显式暂存也拦不住——那要靠 #1
(不缓存 git 跟踪的文件)从源头解决。两者是纵深,不是替代。

## 用法

    python tools/ci_publish.py --message "chore: auto-refresh market data [skip ci]"
    python tools/ci_publish.py --message "..." --paths docs market-analysis/web
    python tools/ci_publish.py --message "..." --guard tools/ci_ledger_guard.py

退出码恒为 0(除非参数错):没东西可提交是**正常情况**,不是失败。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 流水线真正产出的路径。实证依据:`git log --grep="auto-refresh market data"` 近半年每一次
# 提交改动的顶层路径都只有这三个。加新的产出目录时**必须**同步这里,否则它不会被提交
# —— test_ci_publish.py 里有一条守门测试盯着这份清单与实际提交历史是否吻合。
DEFAULT_PATHS = [
    "market-analysis/web", "docs", "market-analysis/data",
    # 仓库根的 append-only 战绩快照(benchmark.py 写)。**不在上面三个目录里**,
    # 换显式暂存时差点漏掉 → 会让公开计分账本静默冻结。是 test_ci_publish 的
    # 覆盖率守门当场抓出来的,留此注释免得以后有人"清理"掉它。
    ".benchmark-history.json",
]

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "github-actions[bot]@users.noreply.github.com"


def _git(args, cwd, check=False, quiet=False):
    """跑一条 git,返回 (returncode, stdout+stderr)。check=True 时非零即抛。"""
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if not quiet and out.strip():
        print(f"  $ git {' '.join(args)}\n{out.rstrip()}")
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败({p.returncode}): {out.strip()}")
    return p.returncode, out


def configure_bot(cwd, name=BOT_NAME, email=BOT_EMAIL):
    """设提交身份。用 --local:绝不污染跑测试那台机器的全局配置。"""
    _git(["config", "--local", "user.name", name], cwd, check=True, quiet=True)
    _git(["config", "--local", "user.email", email], cwd, check=True, quiet=True)


def stage(cwd, paths):
    """只暂存指定路径;路径不存在时跳过(某些 workflow 不产出全部目录)。"""
    existing = [p for p in paths if (Path(cwd) / p).exists()]
    if not existing:
        return []
    _git(["add", "--", *existing], cwd, check=True)
    return existing


def has_staged_changes(cwd):
    rc, _ = _git(["diff", "--cached", "--quiet"], cwd, quiet=True)
    return rc != 0          # 非零 = 有暂存改动


def pull_rebase(cwd, remote, branch, quiet=False):
    """rebase 上游。**容错**:失败不阻断——远端可能还没有该分支(首次推送)。"""
    rc, _ = _git(["pull", "--rebase", "--autostash", remote, branch], cwd, quiet=quiet)
    return rc == 0


def push(cwd, remote, branch):
    rc, _ = _git(["push", remote, f"HEAD:{branch}"], cwd)
    return rc == 0


def _safe_print(text):
    """打印时**绝不因编码炸掉调用方**。

    warn-only 的全部意义是"门不许挡住发布"。如果转述门的输出这一步能把发布器崩掉,
    门就又变回了阻断器 —— 07-28 停摆四天正是这个失败模式。所以这里兜住编码异常,
    实在打不出就退化成 ASCII 转义,信息可以难看,但发布不能停。
    """
    try:
        print(text)
    except Exception:
        enc = (sys.stdout.encoding or "ascii")
        try:
            print(text.encode(enc, "replace").decode(enc, "replace"))
        except Exception:
            print(text.encode("ascii", "backslashreplace").decode("ascii"))


def run_guard(cwd, guard_path):
    """跑防缩水门,**warn-only**:违规只打 GitHub warning,绝不阻断发布(§2 #4)。

    2026-07-28 的教训:门以"阻断 push"的方式失败,把主流水线停了四天——
    它防的是稀有丢行,造成的是全站停更,代价倒挂。所以重挂时只许警告。

    **整个函数不向上抛任何异常**:门脚本不存在、崩溃、超时、输出编码离谱,一律降级成
    警告。门是纵深防御,不是发布的必要条件。
    返回 True=干净,False=有告警(但调用方照常发布)。
    """
    try:
        # 强制子进程 UTF-8:门的正常输出含 `⊇` 这类字符,GBK 环境下写 stdout 会抛
        # UnicodeEncodeError。子进程崩掉 → warn-only 会把它误读成"门发现了缩水"、发假警告,
        # 而假警告会训练人忽略警告,比没有警告更糟。
        # (2026-09-03 更正:我一开始把本地 rc=49 也归到这里,查下来那其实是另一回事——
        #  `#!/usr/bin/env python3` shebang 让 py 转交 Microsoft Store 占位程序而静默退出。
        #  两个问题都真实存在,但成因不同,已分别修:这里管编码,shebang 已从脚本头去掉。)
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        p = subprocess.run([sys.executable, str(guard_path)], cwd=str(cwd), env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
    except Exception as e:
        print(f"::warning::append-only 门没能运行(仅警告,不阻断发布): {type(e).__name__}: {e}")
        return False

    out = ((p.stdout or "") + (p.stderr or "")).strip()
    if p.returncode == 0:
        _safe_print(f"[门] append-only 检查通过{(': ' + out) if out else ''}")
        return True
    first = out.splitlines()[0] if out else f"退出码 {p.returncode}"
    _safe_print(f"::warning::append-only 防缩水门报告异常(仅警告,不阻断发布): {first}")
    if out:
        _safe_print(out)
    return False


def publish(cwd, message, paths=None, remote="origin", branch="main",
            guard=None, empty_note="没有改动,跳过提交"):
    """完整发布流程。返回 0=成功或无事可做;返回 1=推送最终失败。"""
    cwd = Path(cwd)
    paths = DEFAULT_PATHS if paths is None else paths
    configure_bot(cwd)

    staged_paths = stage(cwd, paths)
    if not staged_paths:
        print(f"[发布] 指定路径都不存在,跳过: {paths}")
        return 0
    if not has_staged_changes(cwd):
        print(f"[发布] {empty_note}")
        return 0

    _git(["commit", "-m", message], cwd, check=True)

    # 远端可能有并发提交(6 个 workflow 抢 main)→ 先 rebase 再推;失败重试一次。
    pull_rebase(cwd, remote, branch)

    # 门必须跑在 pull --rebase **之后**:门内绝不 fetch,它比的是工作树 vs 本地
    # origin/main remote-tracking ref,而那个 ref 靠上面这次 pull 更新。
    if guard:
        run_guard(cwd, guard)

    if push(cwd, remote, branch):
        print("[发布] 推送成功")
        return 0
    print("[发布] 首次推送失败(疑似并发),rebase 后重试一次")
    pull_rebase(cwd, remote, branch)
    if push(cwd, remote, branch):
        print("[发布] 重试推送成功")
        return 0
    print("::error::推送两次都失败")
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="CI 提交/推送(显式暂存,可本地测)")
    ap.add_argument("--message", required=True, help="提交信息")
    ap.add_argument("--paths", nargs="*", default=None,
                    help=f"要暂存的路径(默认 {DEFAULT_PATHS})")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--guard", default=None, help="防缩水门脚本路径(warn-only)")
    ap.add_argument("--empty-note", default="没有改动,跳过提交")
    ap.add_argument("--cwd", default=str(ROOT))
    a = ap.parse_args(argv)
    return publish(a.cwd, a.message, paths=a.paths, remote=a.remote, branch=a.branch,
                   guard=a.guard, empty_note=a.empty_note)


if __name__ == "__main__":
    raise SystemExit(main())
