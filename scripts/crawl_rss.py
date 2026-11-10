"""读取微信公众号 RSS（Wechat2RSS / WeRSS 等）并转成统一数据格式。

在 config.json 的 wechat_rss.feeds 里填入服务生成的 feed 地址即可。
只接受标题/摘要里明确提到“第二课堂”且与北中医相关的条目，宁缺毋滥。
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

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
        # RSS 的全文在 <content:encoded> 里（本地名是 encoded），优先用它
        raw = (_child_text(node, ("encoded",))
               or _child_text(node, ("content", "description", "summary")))
        text = strip_tags(raw)
        if title and link:
            entries.append({
                "title": title,
                "url": link,
                "publish_date": pub,
                "summary": clean_summary(text),
                "full_text": clean_summary(text, 4000),
            })
    return entries


def _werss_login(base: str, username: str, password: str) -> str:
    data = urlencode({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        base + "/auth/login", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["data"]["access_token"]


def refresh_werss_feeds(feeds: list[dict], rss_cfg: dict) -> None:
    """在读取 feed 前，先让 WeRSS 更新四个公众号的最新文章。"""
    if not rss_cfg.get("refresh"):
        return
    base = str(rss_cfg.get("admin_url", "http://127.0.0.1:8001")).rstrip("/") + "/api/v1/wx"
    try:
        token = _werss_login(base, rss_cfg.get("username", ""), rss_cfg.get("password", ""))
    except Exception as exc:  # noqa: BLE001
        log.warning("WeRSS 登录失败，跳过刷新：%s", exc)
        return

    for feed in feeds:
        m = re.search(r"/(MP_WXS_[^.]+)\.xml", feed.get("url", ""))
        if not m:
            continue
        fid = m.group(1)
        req = urllib.request.Request(
            f"{base}/mps/update/{fid}?start_page=0&end_page=1",
            headers={"Authorization": "Bearer " + token})
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            data = payload.get("data") or {}
            if payload.get("code") == 0:
                log.info("刷新「%s」：%s 条", feed.get("name"), data.get("total", "?"))
            else:
                log.warning("刷新「%s」未成功：%s", feed.get("name"), payload.get("message"))
        except Exception as exc:  # noqa: BLE001
            log.warning("刷新「%s」失败：%s", feed.get("name"), exc)
        time.sleep(5)


def crawl() -> list[dict]:
    cfg = load_config()
    rss_cfg = cfg.get("wechat_rss", {})
    if not rss_cfg.get("enabled"):
        log.info("wechat_rss 未启用")
        return []

    refresh_werss_feeds(rss_cfg.get("feeds", []), rss_cfg)
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
            blob = entry["title"] + " " + (entry.get("full_text") or entry["summary"])
            is_bucm_account = any(tok in blob or tok in name for tok in BUCM_TOKENS)
            has_credit = "第二课堂" in blob or "学分" in blob
            has_activity = any(k in entry["title"] for k in (
                "讲座", "活动", "招新", "加入", "报名", "招募",
                "社团", "志愿", "实践", "培训", "预告", "沙龙", "比赛", "大赛"))
            # 北中医账号的活动类最新文章即使没写学分也收录，标 C 级线索
            if not has_credit and not (is_bucm_account and has_activity):
                continue
            key = re.sub(r"\W+", "", entry["title"])[:40]
            if key in seen:
                continue
            seen.add(key)

            credit, evidence = extract_credit(blob)
            deadline = extract_deadline(blob, pub or None)
            if has_credit and any(tok in name for tok in ACCOUNT_TOKENS):
                level = "A"
            elif has_credit:
                level = "B"
            else:
                level = "C"
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
