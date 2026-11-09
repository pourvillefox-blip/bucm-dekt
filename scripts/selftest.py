"""无网络自检：截止日期、学分、分类、标题清洗、URL 白名单。"""
from __future__ import annotations

import sys

from common import clean_summary, clean_title, extract_credit, extract_credit_type, extract_deadline, safe_url
from crawl_rss import parse_feed

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>test</title>
<item>
  <title>第二课堂学分讲座通知</title>
  <link>https://example.com/a</link>
  <pubDate>Sat, 08 Nov 2026 10:00:00 GMT</pubDate>
  <description>参与可获第二课堂0.1学分</description>
</item>
</channel></rss>""".encode("utf-8")

DEADLINE_CASES = [
    ("活动时间：11月1日，报名截止：10月20日", "2026-10-01", "2026-10-20"),
    ("报名截止1月5日", "2026-11-10", "2027-01-05"),
    ("报名时间：11月1日至11月20日", "2026-10-25", "2026-11-20"),
    ("请于2026年11月30日前提交材料", "2026-11-01", "2026-11-30"),
    ("活动时间：11月1日", "2026-10-01", None),
]

CREDIT_CASES = [
    ("完整参与可认证第二课堂综合素质0.1学分", "0.1"),
    ("第二课堂成绩占20分，及格线60分", None),
    ("可获得第二课堂1学分", "1"),
]

TYPE_CASES = [
    ("第四届学院杯健康操大赛", "学术科技"),
    ("暑期社会实践团纪实", "社会实践"),
    ("志愿服务时长认证", "志愿服务"),
]

TITLE_CASES = [
    ("春意盎然|BISU三月 第二课堂 校园文化 活动 图鉴", "春意盎然|BISU三月第二课堂校园文化活动图鉴"),
]

SUMMARY_CASES = [
    ("日期：2026-11-06 | 访问量： 为帮助同学们理清赛事思路", "为帮助同学们理清赛事思路"),
    ("作者：张三 | 来源：校团委 | 正文第一句", "正文第一句"),
    ("正文<img src=\"x.png\">继续", "正文 继续"),
    ("正文<img src=\"x.png\"", "正文"),
]

URL_CASES = [
    ("https://example.com/a", "https://example.com/a"),
    ("javascript:alert(1)", ""),
    ("file:///C:/secret.txt", ""),
    ("", ""),
]


def run() -> int:
    failures = 0

    for text, pub, expected in DEADLINE_CASES:
        got = extract_deadline(text, pub)
        if got != expected:
            failures += 1
            print(f"FAIL deadline {text!r} -> {got!r}, expected {expected!r}")

    for text, expected in CREDIT_CASES:
        got, _ = extract_credit(text)
        if got != expected:
            failures += 1
            print(f"FAIL credit {text!r} -> {got!r}, expected {expected!r}")

    for text, expected in TYPE_CASES:
        got = extract_credit_type(text)
        if got != expected:
            failures += 1
            print(f"FAIL type {text!r} -> {got!r}, expected {expected!r}")

    for text, expected in TITLE_CASES:
        got = clean_title(text)
        if got != expected:
            failures += 1
            print(f"FAIL title {text!r} -> {got!r}, expected {expected!r}")

    for text, expected in SUMMARY_CASES:
        got = clean_summary(text)
        if got != expected:
            failures += 1
            print(f"FAIL summary {text!r} -> {got!r}, expected {expected!r}")

    for text, expected in URL_CASES:
        got = safe_url(text)
        if got != expected:
            failures += 1
            print(f"FAIL url {text!r} -> {got!r}, expected {expected!r}")

    feed = parse_feed(SAMPLE_RSS)
    if len(feed) != 1 or feed[0]["url"] != "https://example.com/a" or feed[0]["publish_date"] != "2026-11-08":
        failures += 1
        print(f"FAIL rss parse -> {feed!r}")

    if failures:
        print(f"{failures} 个用例失败")
        return 1
    total = (len(DEADLINE_CASES) + len(CREDIT_CASES) + len(TYPE_CASES)
             + len(TITLE_CASES) + len(SUMMARY_CASES) + len(URL_CASES) + 1)
    print(f"全部通过（{total} 个用例）")
    return 0


if __name__ == "__main__":
    sys.exit(run())
