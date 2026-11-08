"""通过搜狗微信搜索抓取公众号线索（尽力而为，反爬时自动放弃本次）。"""
from __future__ import annotations

import re
import time
import urllib.parse
from datetime import date, datetime

from common import (
    DATA_DIR,
    clean_title,
    compute_status,
    decode_html,
    extract_credit,
    extract_credit_type,
    extract_deadline,
    fetch,
    load_config,
    matches_keywords,
    setup_logger,
    strip_tags,
    write_json,
)

log = setup_logger("crawl_wechat")

SOGOU = "https://weixin.sogou.com/weixin?type=2&query="
BLOCK_RE = re.compile(r'<li id="sogou_vr_11002601_box_.*?</li>', re.S)


def parse_results(html: str) -> list[dict]:
    out = []
    for block in BLOCK_RE.findall(html):
        title_m = re.search(r"<h3>.*?>(.*?)</a>", block, re.S)
        summary_m = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', block, re.S)
        account_m = re.search(r'<span class="all-time-y2">(.*?)</span>', block, re.S)
        ts_m = re.search(r"timeConvert\('(\d+)'\)", block)
        if not title_m:
            continue
        title = clean_title(strip_tags(title_m.group(1)))
        summary = strip_tags(summary_m.group(1)) if summary_m else ""
        account = strip_tags(account_m.group(1)) if account_m else "微信公众号"
        pub = ""
        if ts_m:
            try:
                pub = datetime.fromtimestamp(int(ts_m.group(1))).date().isoformat()
            except (ValueError, OSError):
                pub = ""
        out.append({"title": title, "summary": summary, "account": account, "publish_date": pub})
    return out


def crawl() -> tuple[list[dict], bool]:
    cfg = load_config()
    cutoff = date.fromisoformat(cfg["cutoff_date"][:10])
    keywords = cfg["keywords"]
    delay = float(cfg.get("wechat_delay_seconds", 6))
    results: list[dict] = []
    seen: set[str] = set()
    blocked = False

    for query in cfg.get("wechat_queries", []):
        url = SOGOU + urllib.parse.quote(query)
        try:
            html = decode_html(fetch(url, referer="https://weixin.sogou.com/"))
        except Exception as exc:  # noqa: BLE001
            log.warning("搜索失败 %s: %s", query, exc)
            time.sleep(delay)
            continue

        if "antispider" in html or "请输入验证码" in html:
            log.warning("触发搜狗反爬，停止本次微信抓取")
            blocked = True
            break

        rows = parse_results(html)
        log.info("查询「%s」返回 %d 条", query, len(rows))
        if not rows:
            time.sleep(delay)
            continue

        for row in rows:
            pub = row["publish_date"]
            if pub:
                try:
                    if date.fromisoformat(pub) < cutoff:
                        continue
                except ValueError:
                    pass
            blob = row["title"] + " " + row["summary"]
            # 公众号是补充线索，只保留明确提到"第二课堂"且与北中医相关的条目
            if "第二课堂" not in blob:
                continue
            bucm_tokens = ("北中医", "北京中医药大学", "岐黄", "BUCM", "bucm")
            if not any(tok in blob or tok in row["account"] for tok in bucm_tokens):
                continue
            if not matches_keywords(blob, keywords):
                continue
            key = re.sub(r"\W+", "", row["title"])[:40]
            if key in seen:
                continue
            seen.add(key)

            credit, evidence = extract_credit(blob)
            deadline = extract_deadline(blob, pub or None)
            # 只有北中医校内账号发的才给 B，其他账号降为 C（仅线索）
            account_is_bucm = any(tok in row["account"] for tok in
                                  ("北中医", "北京中医药", "岐黄", "BUCM", "bucm",
                                   "社联", "学生会", "研究生会", "青年志愿者"))
            level = "B" if account_is_bucm else "C"
            results.append({
                "title": row["title"],
                "account": row["account"],
                "publish_date": pub,
                "url": SOGOU + urllib.parse.quote(row["title"]),
                "summary": row["summary"][:180],
                "credit": credit,
                "credit_type": extract_credit_type(blob),
                "deadline": deadline,
                "status": compute_status(deadline, pub or None),
                "source_level": level,
                "source_type": "wechat",
                "evidence": evidence or "",
                "verified_at": date.today().isoformat(),
                "link_note": "在搜狗微信中检索原文",
            })
        time.sleep(delay)

    return results, blocked


def main() -> None:
    items, blocked = crawl()
    if blocked:
        log.error("触发反爬，保留上一份公众号数据（不覆盖）")
        raise SystemExit(3)
    if not items:
        log.error("公众号抓取结果为空，保留上一份数据（不覆盖）")
        raise SystemExit(2)
    write_json(DATA_DIR / "wechat.json", {
        "generated_at": date.today().isoformat(),
        "count": len(items),
        "items": items,
    })
    log.info("公众号抓取完成，共 %d 条", len(items))


if __name__ == "__main__":
    main()
