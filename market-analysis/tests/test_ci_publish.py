"""ci_publish 的本地测试 —— 这才是把发布逻辑抽出 YAML 的全部意义。

2026-07-24~27 主流水线连红四天,根因是 commit/push 逻辑写在 workflow YAML 里、**本地跑不了**,
改一次要推上去等一轮 CI 才知道对不对。§4c 记的第一条教训就是"CI 专属逻辑本地测不了就别上线"。

所以这里不用 mock:**真的 `git init` 一个裸仓当 origin、真的 clone、真的制造推送冲突**,
让 rebase-重试那条路径在本地就能跑绿或跑红。mock 出来的 git 证明不了 rebase 会不会打架。

hermetic:全部在 tmp_path 里,不碰真仓库、不联网。
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import ci_publish  # noqa: E402


def _git(cwd, *args):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert p.returncode == 0, f"git {' '.join(args)} 失败: {p.stdout}{p.stderr}"
    return p.stdout


@pytest.fixture
def repo(tmp_path):
    """裸仓当 origin + 一个工作克隆,结构照着真项目(web/docs/data 三个产出目录)。"""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    ci_publish.configure_bot(work)
    for d in ("market-analysis/web", "docs", "market-analysis/data"):
        (work / d).mkdir(parents=True, exist_ok=True)
        (work / d / ".keep").write_text("", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "HEAD:main")
    return {"origin": origin, "work": work}


def test_no_changes_is_success_not_failure(repo, capsys):
    """没东西可提交是**正常**,不是失败 —— 周报没配 LLM key 时天天走这条路。"""
    rc = ci_publish.publish(repo["work"], "空跑")
    assert rc == 0
    assert "跳过提交" in capsys.readouterr().out


def test_commits_and_pushes_changes(repo):
    (repo["work"] / "docs" / "a.json").write_text('{"x":1}', encoding="utf-8")
    assert ci_publish.publish(repo["work"], "data: 测试") == 0
    # 断言真的落到 origin 上了,不是只在本地提交
    assert "data: 测试" in _git(repo["origin"], "log", "--oneline", "-1", "main")


def test_only_declared_paths_are_staged(repo):
    """核心防护(§2 #2):声明之外的文件**绝不**被自动提交。

    原来的 `git add -A` 会把缓存回灌的陈旧文件、scratch 文件一并提交上去。
    """
    (repo["work"] / "docs" / "good.json").write_text("{}", encoding="utf-8")
    (repo["work"] / "scratch.tmp").write_text("不该被提交", encoding="utf-8")
    (repo["work"] / "market-analysis" / "scripts").mkdir(parents=True, exist_ok=True)
    (repo["work"] / "market-analysis" / "scripts" / "oops.py").write_text("x=1", encoding="utf-8")

    assert ci_publish.publish(repo["work"], "data: 只提交声明路径") == 0
    files = _git(repo["origin"], "show", "--name-only", "--format=", "main").split()
    assert "docs/good.json" in files
    assert "scratch.tmp" not in files, "git add -A 的老毛病回来了:暂存了声明外的文件"
    assert "market-analysis/scripts/oops.py" not in files, "误改的源码被自动提交了"


def test_push_conflict_triggers_rebase_and_retry(repo, tmp_path):
    """并发场景:别人先推了 → 首推被拒 → rebase 后重试成功。

    这条是把逻辑搬出 YAML 的**主要理由** —— 6 个 workflow 抢 main,这条路径每天都在跑,
    以前只能靠祈祷,现在本地就能证明它成立。
    """
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(repo["origin"]), str(other))
    ci_publish.configure_bot(other)
    (other / "docs").mkdir(parents=True, exist_ok=True)
    (other / "docs" / "other.json").write_text("{}", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-m", "别人的并发提交")
    _git(other, "push", "origin", "HEAD:main")

    # 我们这边基于旧 main 造改动 → 首推必被拒
    (repo["work"] / "docs" / "mine.json").write_text("{}", encoding="utf-8")
    assert ci_publish.publish(repo["work"], "data: 我的提交") == 0

    log = _git(repo["origin"], "log", "--oneline", "main")
    assert "我的提交" in log and "别人的并发提交" in log, "并发两边应都保住"
    files = _git(repo["origin"], "ls-tree", "-r", "--name-only", "main").split()
    assert "docs/other.json" in files and "docs/mine.json" in files


def test_guard_failure_warns_but_never_blocks(repo, tmp_path, capsys):
    """§2 #4 的硬要求:门只许警告。

    2026-07-28 那次,门以"阻断 push"失败,把全站停更四天 —— 它防的是稀有丢行,
    造成的却是全线停摆,代价倒挂。所以重挂时必须 warn-only。
    """
    guard = tmp_path / "always_fail_guard.py"
    guard.write_text("import sys; print('假装发现缩水'); sys.exit(1)", encoding="utf-8")
    (repo["work"] / "docs" / "b.json").write_text("{}", encoding="utf-8")

    rc = ci_publish.publish(repo["work"], "data: 门报警也要发布", guard=str(guard))
    out = capsys.readouterr().out
    assert rc == 0, "门失败绝不能让发布返回失败码"
    assert "::warning::" in out and "不阻断" in out
    assert "data: 门报警也要发布" in _git(repo["origin"], "log", "--oneline", "-1", "main"), \
        "门报警时发布仍必须完成 —— 否则就是 07-28 停摆重演"


def test_guard_pass_is_quiet(repo, tmp_path, capsys):
    guard = tmp_path / "ok_guard.py"
    guard.write_text("print('全部 append-only')", encoding="utf-8")
    (repo["work"] / "docs" / "c.json").write_text("{}", encoding="utf-8")
    assert ci_publish.publish(repo["work"], "data: 门通过", guard=str(guard)) == 0
    assert "::warning::" not in capsys.readouterr().out


def test_missing_paths_are_skipped_not_fatal(repo):
    """weekly-review 只产出一部分目录 —— 缺目录必须安静跳过,不能炸。"""
    assert ci_publish.publish(repo["work"], "空", paths=["不存在的目录"]) == 0


def test_default_paths_match_real_commit_history():
    """守门:DEFAULT_PATHS 必须覆盖流水线真实提交过的顶层路径。

    加了新产出目录却忘了加进 DEFAULT_PATHS → 它永远不会被提交,而且**静默**
    (站上数据悄悄停更,和 ndx 烂 24 天是同一类事故)。这里对着真实 git 历史核。
    仓库里没有相应历史时(浅克隆/新检出)自动跳过,不误红。
    """
    # 按**作者**筛,不按 --grep:grep 会连提交正文一起匹配,把人类写的、正文里提到
    # "auto-refresh market data" 的修复提交也算进来(实测 53b0c0d 就这样误报过一次)。
    # CI 自动提交的作者恒为 github-actions[bot],这才是准确信号。
    p = subprocess.run(["git", "log", "--format=%H", "-40", "--author=github-actions"],
                       cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    shas = [s for s in p.stdout.split() if s]
    if not shas:
        pytest.skip("本检出没有 CI bot 提交历史(浅克隆),跳过")
    touched = set()
    for sha in shas:
        q = subprocess.run(["git", "show", "--name-only", "--format=", sha],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        for line in q.stdout.splitlines():
            if line.strip():
                touched.add(line.strip())
    def _covered(f):
        # 声明项既可以是目录(前缀匹配),也可以是单个文件(精确匹配)
        return any(f == d or f.startswith(d + "/") for d in ci_publish.DEFAULT_PATHS)

    uncovered = sorted({f for f in touched if not _covered(f)})
    assert not uncovered, (
        "这些文件流水线真的提交过,但不在 DEFAULT_PATHS 覆盖范围内 → 换成显式暂存后"
        f"它们会**静默停更**: {uncovered[:10]}")


def test_missing_guard_script_warns_but_publishes(repo, capsys):
    """门脚本压根不存在 → 警告 + 照常发布。门是纵深防御,不是发布的必要条件。"""
    (repo["work"] / "docs" / "d.json").write_text("{}", encoding="utf-8")
    rc = ci_publish.publish(repo["work"], "data: 门缺失也要发布",
                            guard=str(repo["work"] / "根本没有这个门.py"))
    assert rc == 0
    assert "::warning::" in capsys.readouterr().out
    assert "data: 门缺失也要发布" in _git(repo["origin"], "log", "--oneline", "-1", "main")


def test_guard_output_with_exotic_chars_cannot_crash_publish(repo, tmp_path, capsys):
    """门输出里的怪字符不许把发布器崩掉。

    实测踩到过:门的正常输出含 `⊇`,GBK 环境下父进程转述它时抛 UnicodeEncodeError,
    把整个发布器带崩。warn-only 若能被一个字符崩掉,门就又变回阻断器了。
    """
    guard = tmp_path / "exotic_guard.py"
    guard.write_text("print('账本 ⊇ origin/main ✓ ∀x∈S')", encoding="utf-8")
    (repo["work"] / "docs" / "e.json").write_text("{}", encoding="utf-8")
    assert ci_publish.publish(repo["work"], "data: 怪字符门", guard=str(guard)) == 0
    assert "data: 怪字符门" in _git(repo["origin"], "log", "--oneline", "-1", "main")


def test_real_ledger_guard_runs_clean_on_this_repo():
    """真门 + 真仓库:必须干净通过。

    门自 2026-07-28 摘下后一直没跑过,重挂前得确认它还活着(而不是挂上去天天发假警告)。
    没有 origin/main remote-tracking ref 时(全新克隆)自动跳过。
    """
    rc, _ = ci_publish._git(["rev-parse", "--verify", "origin/main"], ROOT, quiet=True)
    if rc != 0:
        pytest.skip("本检出没有 origin/main ref,跳过")
    assert ci_publish.run_guard(ROOT, ROOT / "tools" / "ci_ledger_guard.py") is True, \
        "防缩水门在当前仓库上报警了 —— 重挂前先查明,别挂上去制造假警告"


def test_tool_scripts_have_no_python3_shebang():
    """tools/ 下的脚本不许带 `#!/usr/bin/env python3`。

    Windows 的 py 启动器**会遵循 shebang**,把脚本转交给 `python3` —— 而本机 python3 指向
    Microsoft Store 占位程序,结果是**静默退出 49、stdout/stderr 全空**:本地 `py tools/x.py`
    看起来"什么都没发生"。这正好毁掉把发布逻辑搬出 YAML 的目的(为的就是本地能跑)。
    CI 用 `python x.py` 调用,shebang 本来就没用。
    (2026-09-03 实测:去掉 shebang 后同一条命令正常输出、rc=0。)
    """
    bad = []
    for f in sorted((ROOT / "tools").glob("*.py")):
        first = f.read_text(encoding="utf-8").splitlines()[:1]
        if first and first[0].startswith("#!") and "python3" in first[0]:
            bad.append(f.name)
    assert not bad, (
        f"这些脚本带 python3 shebang,在 Windows 上用 py 跑会静默退出 49: {bad}")
