"""抓取校团委官网通知/活动，提取第二课堂学分相关信息。"""
from __future__ import annotations

import re
import time
import urllib.parse
from datetime import date

from common import (
    DATA_DIR,
    clean_summary,
    clean_title,
    compute_status,
    decode_html,
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

log = setup_logger("crawl_official")

LIST_ITEM_RE = re.compile(r"<li>(.*?)</li>", re.S)
TITLE_RE = re.compile(r'<p class="[^"]*gpArticleTitle[^"]*"[^>]*>(.*?)</p>', re.S)
DATE_RE = re.compile(r'gpArticleDate[^"]*"[^>]*>\s*(\d{4}-\d{2}-\d{2})')
HREF_RE = re.compile(r'href="([^"]+)"')


def page_url(base: str, page_index: int) -> str:
    if page_index == 0:
        return base
    if "index.htm" in base:
        return base.replace("index.htm", f"index{page_index}.htm")
    if base.endswith("/"):
        return f"{base}index{page_index}.htm"
    return f"{base}/index{page_index}.htm"


def _norm_date(value: str) -> str | None:
    parts = re.split(r"[-/.]", value.strip())
    if len(parts) != 3:
        return None
    try:
        y, m, d = (int(p) for p in parts)
    except ValueError:
        return None
    if not (2000 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_list(html: str) -> list[tuple[str, str, str]]:
    items = []
    for block in re.findall(r"<li[^>]*>(.*?)</li>", html, re.S):
        tm = TITLE_RE.search(block)
        dm = DATE_RE.search(block)
        hm = HREF_RE.search(block)
        if not (tm and dm and hm):
            continue
        title = clean_title(re.sub(r"<[^>]+>", "", tm.group(1)))
        items.append((title, dm.group(1), hm.group(1)))
    if items:
        return items

    # 第二种模板：<li><span>2026/10/16</span><a href="...">标题</a></li>
    for block in re.findall(r"<li[^>]*>(.*?)</li>", html, re.S):
        m = re.search(
            r'<span[^>]*>\s*\[?(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\]?\s*</span>\s*'
            r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        date = _norm_date(m.group(1))
        if not date:
            continue
        title = clean_title(re.sub(r"<[^>]+>", "", m.group(3)))
        if title:
            items.append((title, date, m.group(2)))
    return items


def extract_article_text(html: str) -> str:
    # 博达 CMS 用 gp-article；博物馆/生科院等用 content/article 容器
    m = re.search(r'<div[^>]*class="[^"]*gp-article[^"]*"[^>]*>', html)
    if not m:
        m = re.search(
            r'<div[^>]*class="[^"]*(?:content|article|news_content|vsbcontent)[^"]*"[^>]*>',
            html, re.I)
    if not m:
        return ""
    return strip_tags(html[m.end():m.end() + 60000])


def is_relevant(title: str, text: str) -> bool:
    """保留与第二课堂/可报名活动相关的条目，过滤公示、评奖和活动回顾。"""
    if any(x in title for x in ("公示", "名单", "评选", "推荐", "喜报",
                                "顺利", "圆满", "落幕", "收官", "纪实",
                                "回顾", "总结", "侧记", "成功举办")):
        return False
    blob = title + "\n" + text
    if "第二课堂" in blob or "学分" in blob:
        return True
    if "报名" in blob or "招募" in blob:
        return True
    activity_words = ("讲座", "报告会", "沙龙", "论坛", "宣讲", "培训",
                      "竞赛", "大赛", "活动预告", "活动通知", "活动")
    return any(word in title for word in activity_words)


def build_item(title: str, pub: str, url: str, text: str, source_name: str) -> dict:
    body = text[len(title):] if text.startswith(title) else text
    credit, evidence = extract_credit(text)
    deadline = extract_deadline(text, pub)
    level = "C"
    if credit and "第二课堂" in text:
        level = "A"
    elif "第二课堂" in (text + title) or "学分" in (text + title):
        level = "B"
    return {
        "title": title,
        "account": source_name,
        "publish_date": pub,
        "url": safe_url(url),
        "summary": clean_summary(body),
        "credit": credit,
        "credit_type": extract_credit_type(text + title),
        "deadline": deadline,
        "status": compute_status(deadline, pub),
        "source_level": level,
        "source_type": "official",
        "evidence": evidence or "",
        "link_ok": True,
        "checked_at": date.today().isoformat(),
        "verified_at": date.today().isoformat(),
    }


def crawl() -> list[dict]:
    cfg = load_config()
    cutoff = date.fromisoformat(cfg["cutoff_date"][:10])
    results: list[dict] = []
    seen_urls: set[str] = set()

    for source in cfg["official_sources"]:
        base = source["url"]
        name = source["name"]
        for p in range(int(source.get("pages", 2))):
            url = page_url(base, p)
            try:
                html = decode_html(fetch(url))
            except Exception as exc:  # noqa: BLE001
                log.warning("列表抓取失败 %s: %s", url, exc)
                break
            entries = parse_list(html)
            if not entries:
                break
            new_in_page = 0
            for title, pub, href in entries:
                try:
                    pub_date = date.fromisoformat(pub)
                except ValueError:
                    continue
                if pub_date < cutoff or pub_date > date.today():
                    continue
                full_url = urllib.parse.urljoin(url, href)
                if not full_url.lower().startswith(("http://", "https://")):
                    continue
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                try:
                    detail_html = decode_html(fetch(full_url, referer=url))
                except Exception as exc:  # noqa: BLE001
                    log.warning("详情抓取失败 %s: %s", full_url, exc)
                    continue
                text = extract_article_text(detail_html)
                if not is_relevant(title, text):
                    continue
                results.append(build_item(title, pub, full_url, text, name))
                new_in_page += 1
                time.sleep(0.4)
            log.info("%s 第%d页 新增 %d 条", name, p + 1, new_in_page)
            time.sleep(0.6)

    # 去重（同一篇可能出现在多个栏目）
    dedup: dict[str, dict] = {}
    for item in results:
        key = re.sub(r"\W+", "", item["title"])[:40]
        if key not in dedup:
            dedup[key] = item
    return list(dedup.values())


def main() -> None:
    items = crawl()
    if not items:
        log.error("官网抓取结果为空，保留上一份数据（不覆盖）")
        raise SystemExit(2)
    write_json(DATA_DIR / "official.json", {
        "generated_at": date.today().isoformat(),
        "count": len(items),
        "items": items,
    })
    log.info("官网抓取完成，共 %d 条", len(items))


if __name__ == "__main__":
    main()
