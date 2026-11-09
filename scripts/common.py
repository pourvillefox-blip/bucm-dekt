"""公共工具：抓取、解码、正文提取、学分/截止日期识别。仅用标准库。"""
from __future__ import annotations

import gzip
import json
import logging
import os
from logging.handlers import RotatingFileHandler
import re
import tempfile
import time
import urllib.error
import urllib.request
import zlib
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
SITE_DIR = ROOT / "site"
DOCS_DIR = ROOT / "docs"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def setup_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        fh = RotatingFileHandler(
            LOG_DIR / f"{name}.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def fetch(url: str, timeout: int = 25, retries: int = 3, referer: str | None = None) -> bytes:
    last: Exception | None = None
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"unsupported url scheme: {url}")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "close",
                },
            )
            if referer:
                req.add_header("Referer", referer)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                raw = gzip.decompress(raw)
            elif "deflate" in enc:
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            return raw
        except urllib.error.HTTPError as exc:
            last = exc
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                raise
        except Exception as exc:  # noqa: BLE001
            last = exc
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url} ({last})")


def decode_html(raw: bytes) -> str:
    m = re.search(rb'charset=["\']?\s*([\w-]+)', raw[:4000], re.I)
    encodings: list[str] = []
    if m:
        encodings.append(m.group(1).decode("ascii", "ignore"))
    encodings += ["utf-8", "gb18030"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def strip_tags(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(?:p|div|li|h[1-6]|tr)>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html)
    html = re.sub(r"[ 　]", " ", html)
    html = re.sub(r"[ \t\r\f\v]+", " ", html)
    html = re.sub(r"\n\s*\n+", "\n", html)
    return html.strip()


def sentence_around(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(text.rfind("。", 0, start), text.rfind("；", 0, start),
               text.rfind("\n", 0, start), start - radius)
    right_candidates = [p for p in (text.find("。", end), text.find("；", end),
                                    text.find("\n", end)) if p != -1]
    right = min(right_candidates) if right_candidates else min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left + 1: right + 1]).strip()[:160]


CREDIT_PATTERNS = [
    r"第二课堂[^。；\n]{0,40}?(\d+(?:\.\d+)?)\s*学分",
    r"计入第二课堂[^。；\n]{0,30}?(\d+(?:\.\d+)?)\s*分",
    r"第二课堂[^。；\n]{0,30}?(\d+(?:\.\d+)?)\s*分",
    r"(\d+(?:\.\d+)?)\s*学分[^。；\n]{0,20}?第二课堂",
    r"(\d+(?:\.\d+)?)\s*个?\s*第二课堂学分",
]


def extract_credit(text: str) -> tuple[str | None, str | None]:
    """返回 (学分数, 证据句)。只接受 0.1–5 之间的活动学分，排除成绩分。"""
    if not text:
        return None, None
    for pat in CREDIT_PATTERNS:
        for m in re.finditer(pat, text):
            try:
                value = float(m.group(1))
            except ValueError:
                continue
            if not (0 < value <= 5):
                continue
            snippet = text[max(0, m.start() - 15): m.end() + 10]
            if any(bad in snippet for bad in ("成绩", "总分", "及格", "满分", "占", "学分制")):
                continue
            return m.group(1), sentence_around(text, m.start(), m.end())
    return None, None


def extract_credit_type(text: str) -> str:
    if not text:
        return "未分类"
    if "志愿" in text:
        return "志愿服务"
    if any(k in text for k in ("社会实践", "暑期实践", "实践团", "实习实践")):
        return "社会实践"
    if any(k in text for k in ("竞赛", "大赛", "挑战杯", "创新创业", "学科竞赛")):
        return "学术科技"
    if any(k in text for k in ("讲座", "报告会", "沙龙", "论坛", "宣讲")):
        return "讲座活动"
    if "社团" in text:
        return "社团活动"
    return "综合素质"


def _mk_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def extract_deadline(text: str, publish_date: str | None) -> str | None:
    """从正文里找报名截止日期；找不到返回 None。

    只接受两种强信号：截止类词后面紧跟的日期；日期后面紧跟“前/之前 + 报名/提交”等。
    避免把“活动时间：11月1日”误当成截止日期。
    """
    if not text:
        return None
    hint_year = int(publish_date[:4]) if publish_date else date.today().year
    pub = parse_iso(publish_date)
    candidates: list[str] = []

    def add(year: int, month: int, day: int) -> None:
        iso = _mk_date(year, month, day)
        if iso:
            candidates.append(iso)

    # 1) 截止/截至/报名截止 + 日期
    for m in re.finditer(
        r"(?:截止|截至|报名截止|申报截止|提交截止|报送截止)[^。\n]{0,15}?"
        r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日", text):
        add(int(m.group(1)) if m.group(1) else hint_year, int(m.group(2)), int(m.group(3)))

    # 2) 日期 + 前/之前 + 报名/提交等
    for m in re.finditer(
        r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日[^。\n]{0,6}?"
        r"(?:前|之前|以前)(?:报名|提交|报送|反馈|完成|截止)", text):
        add(int(m.group(1)) if m.group(1) else hint_year, int(m.group(2)), int(m.group(3)))

    # 3) 报名时间 X 至 Y，取区间结束日
    for m in re.finditer(
        r"(?:报名|申报|提交)时间[^。\n]{0,30}?(\d{1,2})月(\d{1,2})日"
        r"[^。\n]{0,4}?(?:至|到|—|-|~)"
        r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日", text):
        add(int(m.group(3)) if m.group(3) else hint_year, int(m.group(4)), int(m.group(5)))

    if not candidates:
        return None

    # 跨年回卷：明显早于发布日的日期，年份 +1
    fixed = []
    for iso in candidates:
        d = parse_iso(iso)
        if pub and d and d < pub and (pub - d).days > 180:
            try:
                d = d.replace(year=d.year + 1)
            except ValueError:
                pass
        fixed.append(d.isoformat() if d else iso)

    upcoming = [c for c in fixed if not pub or c >= pub.isoformat()]
    pool = upcoming or fixed
    return max(pool)


def clean_summary(text: str, limit: int = 180) -> str:
    """去掉 CMS 正文开头的 日期/访问量/作者 等元信息，截断到指定长度。"""
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"<[^>]*>", " ", t)   # 转义后还原出来的完整标签
    t = re.sub(r"<[^>]*$", " ", t)   # 未闭合的残缺标签
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^当前位置[:：][^»]{0,40}»\s*\S{0,20}\s*", "", t)
    t = re.sub(r"(?:发布日期|发布时间)\s*[：:]\s*\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?\s*", "", t)
    # 形如 “日期：2026-11-06 | 访问量： …” 的元信息段
    t = re.sub(
        r"(?:日期|访问量|浏览量|点击量|作者|来源|编辑|审核|字号|字体|"
        r"发布时间|更新时间|阅读量)\s*[：:]\s*[^|]{0,60}?\s*\|\s*",
        "", t)
    t = re.sub(r"^(?:\|\s*)+", "", t)
    # 残留的 “访问量：  ” 这类只有标签没有值的
    t = re.sub(
        r"^(?:日期|访问量|浏览量|点击量|作者|来源|编辑|审核|字号)\s*[：:]\s*"
        r"(?:\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?|\d+)?\s*",
        "", t)
    t = t[:limit].strip()
    return re.sub(r"<[^>]*$", "", t).strip()


def clean_title(title: str) -> str:
    """去掉搜索高亮/换行带来的多余空格，尤其是汉字之间的空格。"""
    t = re.sub(r"\s+", " ", (title or "")).strip()
    t = re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", t)
    t = re.sub(r"\s+([，。、；：！？）】》」』])", r"\1", t)
    t = re.sub(r"([（【《「『])\s+", r"\1", t)
    return t


def matches_keywords(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_status(deadline: str | None, publish_date: str | None, today: date | None = None) -> str:
    today = today or date.today()
    d = parse_iso(deadline)
    if d:
        return "active" if d >= today else "ended"
    p = parse_iso(publish_date)
    if p and (today - p) <= timedelta(days=60):
        return "active"
    return "unknown"


def atomic_write_text(path: Path, text: str) -> None:
    """同目录临时文件 + os.replace，避免断电/崩溃留下半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def write_json(path: Path, data) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path: Path, default=None):
    """宽松读取：文件缺失或损坏都返回 default。用于非关键路径。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_json_strict(path: Path):
    """严格读取：文件不存在返回 None，存在但损坏直接抛错。用于构建输入。"""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_url(url, schemes: tuple[str, ...] = ("http://", "https://")) -> str:
    if not isinstance(url, str):
        return ""
    u = url.strip()
    return u if u.lower().startswith(schemes) else ""
