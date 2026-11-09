"""合并抓取结果，生成自包含的静态网页（docs/index.html）。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime

from common import (
    DATA_DIR,
    DOCS_DIR,
    ROOT,
    SITE_DIR,
    atomic_write_text,
    clean_summary,
    clean_title,
    compute_status,
    parse_iso,
    load_config,
    read_json_strict,
    safe_url,
    setup_logger,
    write_json,
)

log = setup_logger("build_site")

TEMPLATE = SITE_DIR / "template.html"
PLACEHOLDER = "/*__DATA__*/null"


def normalize(item: dict, today: date) -> dict | None:
    if not isinstance(item, dict):
        return None
    item = dict(item)
    title = clean_title(str(item.get("title") or ""))
    url = safe_url(item.get("url"))
    if not title or not url:
        log.warning("跳过无标题或链接不合法的条目：%r", item.get("title"))
        return None
    if item.get("link_ok") is False:
        log.warning("跳过失效链接：%r", title)
        return None

    status = compute_status(item.get("deadline"), item.get("publish_date"), today)
    # 没有截止日期的新闻/通知，不轻易标成“进行中”
    if not item.get("deadline") and status == "active":
        pub_date = parse_iso(item.get("publish_date"))
        recent = bool(pub_date and 0 <= (today - pub_date).days <= 14)
        if not recent or not any(k in title for k in (
                "报名", "招募", "预告", "招新", "加入", "即将", "来袭", "开放", "启动")):
            status = "unknown"

    summary = str(item.get("summary") or "")
    if summary.startswith(title):
        summary = summary[len(title):].lstrip(" ：:，,。.;；")
    summary = clean_summary(summary)

    item["title"] = title
    item["url"] = url
    item["summary"] = summary
    item["status"] = status
    item["credit"] = item.get("credit") or None
    item["source_level"] = item.get("source_level") or "C"
    item["source_type"] = item.get("source_type") or "manual"
    item["publish_date"] = str(item.get("publish_date") or "") or None
    item["deadline"] = str(item.get("deadline") or "") or None
    item["id"] = hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]
    return item


def dedupe(items: list[dict]) -> list[dict]:
    """同一活动可能在官网和公众号重复出现，优先保留官方/高等级那条。"""
    rank = {"official": 4, "manual": 3, "rss": 2, "wechat": 1}
    level_rank = {"A": 3, "B": 2, "C": 1}
    chosen: dict[str, dict] = {}
    for item in items:
        key = re.sub(r"\W+", "", item["title"])[:30]
        if not key:
            continue
        old = chosen.get(key)
        if old is None:
            chosen[key] = item
            continue
        new_score = (rank.get(item.get("source_type", "manual"), 0),
                     level_rank.get(item.get("source_level", "C"), 0))
        old_score = (rank.get(old.get("source_type", "manual"), 0),
                     level_rank.get(old.get("source_level", "C"), 0))
        if new_score > old_score:
            chosen[key] = item
    return list(chosen.values())


def sort_key(item: dict):
    # 配合 reverse=True：1（进行中）排在 0 前面，再按日期倒序
    return (
        1 if item.get("status") == "active" else 0,
        item.get("publish_date") or "",
    )


def main() -> None:
    cfg = load_config()
    today = date.today()

    def load_source(name: str) -> list[dict]:
        data = read_json_strict(DATA_DIR / name)
        if data is None:
            return []
        if not isinstance(data, dict):
            raise RuntimeError(f"{name} 格式错误：顶层不是对象")
        items = data.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError(f"{name} 格式错误：items 不是数组")
        return items

    official = load_source("official.json")
    wechat = load_source("wechat.json")
    rss = load_source("rss.json")
    manual = load_source("manual.json")
    log.info("读入 官网 %d 条 / 公众号 %d 条 / RSS %d 条 / 人工 %d 条",
             len(official), len(wechat), len(rss), len(manual))

    items = [x for x in (normalize(i, today) for i in official + wechat + rss + manual) if x]
    items = dedupe(items)
    items.sort(key=sort_key, reverse=True)

    sources = [s["name"] for s in cfg.get("official_sources", [])]
    sources.append("微信公众号（搜狗微信检索，仅作线索）")
    if rss:
        sources.append("微信公众号 RSS（Wechat2RSS / WeRSS）")
    sources.append("人工核验补充（公众号原文）")

    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cutoff_date": cfg.get("cutoff_date"),
        "count": len(items),
        "items": items,
        "sources": sources,
    }

    write_json(DATA_DIR / "combined.json", data)

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError("模板缺少数据占位符 /*__DATA__*/，拒绝生成空页面")

    payload = json.dumps(data, ensure_ascii=False)
    # 彻底转义 < > &，避免 </script> 和 <!--<script> 破坏页面
    payload = (payload.replace("<", "\\u003c")
                      .replace(">", "\\u003e")
                      .replace("&", "\\u0026"))
    html = template.replace(PLACEHOLDER, payload)
    if "window.__DEKT_DATA__" not in html:
        raise RuntimeError("生成结果缺少数据挂载点")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(DOCS_DIR / "index.html", html)
    atomic_write_text(SITE_DIR / "index.html", html)

    # GitHub Pages 需要的空文件
    atomic_write_text(DOCS_DIR / ".nojekyll", "")

    log.info("网页已生成：%s（%d 条）", DOCS_DIR / "index.html", len(items))


if __name__ == "__main__":
    main()
