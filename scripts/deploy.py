"""提交并推送网页到 GitHub Pages（docs 目录）。"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime

from common import ROOT, load_config

PATHS = [
    "docs",
    "data/combined.json",
    "data/manual.json",
    "scripts",
    "site/template.html",
    ".gitignore",
    "README.md",
]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def fail(msg: str, proc: subprocess.CompletedProcess | None = None) -> int:
    print(msg)
    if proc is not None and proc.stderr.strip():
        print(proc.stderr.strip())
    return 1


def main() -> int:
    if not (ROOT / ".git").exists():
        return fail("尚未初始化 git。请先按 README 的「部署到 GitHub Pages」步骤操作。")

    if not git("remote", "-v").stdout.strip():
        return fail("未配置 git remote。请先执行：git remote add origin <仓库地址>")

    if git("rev-parse", "--verify", "HEAD").returncode != 0:
        print("仓库还没有任何 commit，先创建初始提交。")

    add = git("add", *PATHS)
    if add.returncode != 0:
        return fail("git add 失败", add)

    if git("diff", "--cached", "--quiet").returncode == 0:
        print("没有需要提交的变更。")
        return 0

    cfg = load_config().get("deploy", {})
    name = cfg.get("git_name") or "BUCM DEKT Bot"
    email = cfg.get("git_email") or "bucm-dekt@localhost"
    msg = f"data: update {datetime.now():%Y-%m-%d %H:%M}"

    commit = git("-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-m", msg)
    if commit.returncode != 0:
        return fail("git commit 失败", commit)
    print(commit.stdout.strip())

    push = git("push", "origin", "HEAD")
    if push.returncode != 0:
        return fail("推送失败", push)
    print("已推送，GitHub Pages 通常 1 分钟内生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
