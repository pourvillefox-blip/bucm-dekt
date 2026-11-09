"""读取微信公众号 RSS（Wechat2RSS / WeRSS 等）并转成统一数据格式。

在 config.json 的 wechat_rss.feeds 里填入服务生成的 feed 地址即可。
只接受标题/摘要里明确提到“第二课堂”且与北中医相关的条目，宁缺毋滥。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from common import (
    DATA_DIR,
    clean_summary,
    clean_title,
    compute_status,
    extract_credit,
    extract_credit_type,
    extract_deadline,
    fetch,
    load_config,
    safe_url,
    setup_logger,
    strip_tags,
    write_json,
)

log = setup_logger("crawl_rss")

BUCM_TOKENS = ("北中医", "北京中医药大学", "岐黄", "BUCM", "bucm")
ACCOUNT_TOKENS = ("北中医", "北京中医药", "岐黄", "BUCM", "bucm",
                  "社联", "学生会", "研究生会", "青年志愿者")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node:
        if _local(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def _child_link(node: ET.Element) -> str:
    for child in node:
        if _local(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def _parse_date(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def parse_feed(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    entries: list[dict] = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = clean_title(strip_tags(_child_text(node, ("title",))))
        link = safe_url(_child_link(node))
        pub = _parse_date(_child_text(node, ("pubdate", "published", "updated", "date")))
        desc = clean_summary(strip_tags(
            _child_text(node, ("description", "summary", "content", "encoded"))))
        if title and link:
            entries.append({"title": title, "url": link, "publish_date": pub, "summary": desc})
    return entries


def crawl() -> list[dict]:
    cfg = load_config()
    rss_cfg = cfg.get("wechat_rss", {})
    if not rss_cfg.get("enabled"):
        log.info("wechat_rss 未启用")
        return []

    cutoff = date.fromisoformat(cfg["cutoff_date"][:10])
    results: list[dict] = []
    seen: set[str] = set()

    for feed in rss_cfg.get("feeds", []):
        name = feed.get("name", "微信公众号")
        url = feed.get("url", "")
        if not safe_url(url):
            log.warning("跳过非法 feed 地址：%s", url)
            continue
        try:
            entries = parse_feed(fetch(url))
        except Exception as exc:  # noqa: BLE001
            log.warning("读取 feed 失败 %s: %s", url, exc)
            continue
        log.info("feed「%s」返回 %d 条", name, len(entries))

        for entry in entries:
            pub = entry["publish_date"]
            if pub:
                try:
                    if date.fromisoformat(pub) < cutoff:
                        continue
                except ValueError:
                    pass
            blob = entry["title"] + " " + entry["summary"]
            if "第二课堂" not in blob:
                continue
            if not any(tok in blob or tok in name for tok in BUCM_TOKENS):
                continue
            key = re.sub(r"\W+", "", entry["title"])[:40]
            if key in seen:
                continue
            seen.add(key)

            credit, evidence = extract_credit(blob)
            deadline = extract_deadline(blob, pub or None)
            level = "B" if any(tok in name for tok in ACCOUNT_TOKENS) else "C"
            results.append({
                "title": entry["title"],
                "account": name,
                "publish_date": pub or None,
                "url": entry["url"],
                "summary": entry["summary"],
                "credit": credit,
                "credit_type": extract_credit_type(blob),
                "deadline": deadline,
                "status": compute_status(deadline, pub or None),
                "source_level": level,
                "source_type": "rss",
                "evidence": evidence or "",
                "link_ok": True,
                "checked_at": date.today().isoformat(),
                "verified_at": date.today().isoformat(),
            })
    return results


def main() -> None:
    items = crawl()
    cfg = load_config().get("wechat_rss", {})
    if not cfg.get("enabled") or not cfg.get("feeds"):
        return
    if not items:
        log.error("RSS 没有可用条目，保留上一份数据（不覆盖）")
        raise SystemExit(2)
    write_json(DATA_DIR / "rss.json", {
        "generated_at": date.today().isoformat(),
        "count": len(items),
        "items": items,
    })
    log.info("RSS 抓取完成，共 %d 条", len(items))


if __name__ == "__main__":
    main()
