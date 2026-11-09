"""检查 Wechat2RSS 收录申请状态：issue 是否关闭、公开列表里是否出现目标账号。"""
from __future__ import annotations

import json
import re
import subprocess
import sys

from common import decode_html, fetch, setup_logger
from notify import send_email

log = setup_logger("check_w2r")

REPO = "ttttmr/Wechat2RSS"
ISSUE = 716
LIST_URL = "https://wechat2rss.xlab.app/list/all/"
TOKENS = ("北京中医药", "北中医", "岐黄", "BUCM", "bucm", "社联", "学生会", "研究生会")


def issue_state() -> dict:
    proc = subprocess.run(
        ["gh", "issue", "view", str(ISSUE), "--repo", REPO,
         "--json", "state,stateReason,updatedAt,comments,url"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "").strip() or "gh issue view 失败")
    return json.loads(proc.stdout)


def public_feeds() -> list[tuple[str, str]]:
    html = decode_html(fetch(LIST_URL))
    pairs = re.findall(
        r'href="(https://wechat2rss\.xlab\.app/feed/[0-9a-f]+\.xml)"[^>]*>([^<]+)</a>', html)
    return [(name.strip(), url) for url, name in pairs]


def main() -> int:
    issue = issue_state()
    feeds = public_feeds()
    hits = [(name, url) for name, url in feeds
            if any(tok in name for tok in TOKENS)]

    log.info("issue #%d: %s（评论 %d 条，更新于 %s）",
             ISSUE, issue["state"], len(issue.get("comments", [])), issue["updatedAt"])
    log.info("公开列表共 %d 个账号，命中 %d 个", len(feeds), len(hits))
    for name, url in hits:
        log.info("命中：%s -> %s", name, url)

    changed = issue["state"] != "OPEN" or bool(hits)
    if changed:
        body = [
            f"Wechat2RSS 收录申请状态变化：{issue['url']}",
            f"issue 状态：{issue['state']}",
            f"评论数：{len(issue.get('comments', []))}",
        ]
        for c in issue.get("comments", []):
            body.append(f"- {c.get('author', {}).get('login', '?')}: {c.get('body', '')[:200]}")
        body.append("")
        body.append("公开列表命中：")
        body += [f"- {n}: {u}" for n, u in hits] or ["- 暂无"]
        send_email("[更新] Wechat2RSS 收录申请有变化", "\n".join(body), topic="w2r")
    return 0


if __name__ == "__main__":
    sys.exit(main())
