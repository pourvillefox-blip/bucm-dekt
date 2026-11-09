"""健康检查：页面可用、数据新鲜、条目数一致、抓取成功、线上页面同步。"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlencode

from common import DOCS_DIR, DATA_DIR, ROOT, UA, load_config, read_json, read_json_strict, setup_logger, write_json
from notify import send_email

log = setup_logger("healthcheck")
MARKER = "北中医第二课堂"
PLACEHOLDER = "/*__DATA__*/"
PAYLOAD_RE = re.compile(r"window\.__DEKT_DATA__\s*=\s*(\{.*?\});\s*</script>", re.S)


def parse_payload(html: str) -> dict | None:
    m = PAYLOAD_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def check_page_file() -> tuple[bool, str, int]:
    page = DOCS_DIR / "index.html"
    if not page.exists():
        return False, "docs/index.html 不存在", 0
    html = page.read_text(encoding="utf-8", errors="ignore")
    if MARKER not in html:
        return False, "页面缺少预期标记", 0
    if PLACEHOLDER in html:
        return False, "页面数据占位符未替换，构建失败", 0
    data = parse_payload(html)
    if not data:
        return False, "页面内嵌数据无法解析", 0
    count = data.get("count")
    if not isinstance(count, int) or count <= 0:
        return False, f"页面条目数为 {count}", 0
    return True, f"页面正常（{count} 条，{page.stat().st_size // 1024} KB）", count


def check_data_freshness(cfg: dict) -> tuple[bool, str]:
    try:
        data = read_json_strict(DATA_DIR / "combined.json")
    except json.JSONDecodeError as exc:
        return False, f"combined.json 损坏：{exc}"
    if not data:
        return False, "combined.json 不存在或为空"
    count = data.get("count", 0)
    if not isinstance(count, int) or count <= 0:
        return False, "合并数据为 0 条"
    gen = data.get("generated_at")
    if not gen:
        return False, "combined.json 缺少 generated_at"
    try:
        ts = datetime.strptime(gen, "%Y-%m-%d %H:%M")
    except ValueError:
        return False, f"generated_at 格式异常：{gen}"
    age = datetime.now() - ts
    limit = timedelta(days=int(cfg.get("stale_days", 4)))
    if age > limit:
        return False, f"数据已 {age.days} 天未更新（阈值 {limit.days} 天）"
    return True, f"数据更新于 {gen}（{age.days} 天前，{count} 条）"


def check_sources() -> tuple[bool, str]:
    counts = {}
    names = ["official.json", "wechat.json", "manual.json"]
    if (DATA_DIR / "rss.json").exists():
        names.append("rss.json")
    for name in names:
        try:
            data = read_json_strict(DATA_DIR / name)
        except json.JSONDecodeError as exc:
            return False, f"{name} 损坏：{exc}"
        if data is None:
            counts[name] = 0
            continue
        items = data.get("items", [])
        counts[name] = len(items) if isinstance(items, list) else 0
    if sum(counts.values()) == 0:
        return False, "三个数据源都是 0 条"
    detail = " / ".join(f"{n.replace('.json', '')} {c}" for n, c in counts.items())
    return True, f"数据源：{detail}"


def check_consistency(combined_count: int) -> tuple[bool, str]:
    try:
        data = read_json_strict(DATA_DIR / "combined.json") or {}
    except json.JSONDecodeError:
        return False, "combined.json 损坏"
    actual = data.get("count")
    if actual != combined_count:
        return False, f"页面 {combined_count} 条与合并数据 {actual} 条不一致"
    return True, f"页面与合并数据一致（{actual} 条）"


def check_last_update(cfg: dict) -> tuple[bool, str]:
    info = read_json(DATA_DIR / "last_update.json", {}) or {}
    if not info:
        return False, "缺少 last_update.json"
    if info.get("status") != "ok":
        return False, f"上次抓取失败：{info.get('error', '未知错误')}"
    try:
        ts = datetime.fromisoformat(info["finished_at"])
    except (KeyError, ValueError):
        return False, "last_update.json 时间格式异常"
    limit = timedelta(days=int(cfg.get("stale_days", 4)) + 1)
    if datetime.now() - ts > limit:
        return False, f"上次成功抓取于 {ts:%Y-%m-%d %H:%M}，已超过 {limit.days} 天"
    return True, f"上次抓取成功（{info.get('count', '?')} 条）"


def check_werss(cfg: dict) -> tuple[bool, str]:
    """检查 WeRSS 服务与微信读书登录态，避免 Cookie 过期后静默断流。"""
    rss = cfg.get("wechat_rss", {}) or {}
    if not rss.get("enabled"):
        return True, "未启用公众号 RSS"
    base = str(rss.get("admin_url", "")).rstrip("/")
    if not base:
        return True, "未配置 WeRSS 地址"

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base + "/", timeout=15) as resp:
            if resp.status != 200:
                return False, f"WeRSS 返回 HTTP {resp.status}"
        data = urlencode({
            "username": rss.get("username", ""),
            "password": rss.get("password", ""),
        }).encode("utf-8")
        req = urllib.request.Request(
            base + "/api/v1/wx/auth/login", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with opener.open(req, timeout=20) as resp:
            token = json.loads(resp.read().decode("utf-8"))["data"]["access_token"]
        req = urllib.request.Request(
            base + "/api/v1/wx/weread/qr/status",
            headers={"Authorization": "Bearer " + token})
        with opener.open(req, timeout=20) as resp:
            status = json.loads(resp.read().decode("utf-8")).get("data", {})
    except Exception as exc:  # noqa: BLE001
        return False, f"WeRSS 不可用：{exc}"

    if not status.get("login_status"):
        return False, f"微信读书登录态异常：{status.get('msg', '未知')}"
    return True, "WeRSS 正常，微信读书已授权"


def check_remote(cfg: dict, local_count: int) -> tuple[bool, str]:
    url = (cfg.get("site_url") or "").strip()
    if not url:
        return True, "未配置 site_url，跳过线上检查"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        })
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        return False, f"线上页面无法访问：{exc}"
    if MARKER not in body:
        return False, "线上页面内容异常（缺少标记）"
    data = parse_payload(body)
    if not data:
        return False, "线上页面数据无法解析"
    remote_count = data.get("count", 0)
    if not isinstance(remote_count, int) or remote_count <= 0:
        return False, f"线上页面条目数为 {remote_count}"
    gen = data.get("generated_at")
    try:
        ts = datetime.strptime(gen, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return False, f"线上页面 generated_at 异常：{gen}"
    limit = timedelta(days=int(cfg.get("stale_days", 4)))
    if datetime.now() - ts > limit:
        return False, f"线上页面已 {(datetime.now() - ts).days} 天未更新"
    if remote_count != local_count:
        return False, f"线上 {remote_count} 条与本地 {local_count} 条不一致（可能未部署）"
    return True, f"线上页面正常（{remote_count} 条，更新于 {gen}）"


def main() -> int:
    cfg = load_config()
    checks: list[tuple[str, tuple[bool, str]]] = []

    page_ok, page_msg, page_count = check_page_file()
    checks.append(("page", (page_ok, page_msg)))

    data_ok, data_msg = check_data_freshness(cfg)
    checks.append(("data", (data_ok, data_msg)))

    src_ok, src_msg = check_sources()
    checks.append(("sources", (src_ok, src_msg)))

    if page_ok:
        checks.append(("consistency", check_consistency(page_count)))
    checks.append(("last_update", check_last_update(cfg)))
    checks.append(("werss", check_werss(cfg)))
    checks.append(("remote", check_remote(cfg, page_count)))

    failures = [(name, msg) for name, (ok, msg) in checks if not ok]

    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "ok": not failures,
        "checks": {name: {"ok": ok, "message": msg} for name, (ok, msg) in checks},
    }
    write_json(DATA_DIR / "health.json", result)

    for name, (ok, msg) in checks:
        log.info("%s %s: %s", "OK" if ok else "FAIL", name, msg)

    if failures:
        body = "北中医第二课堂汇总页健康检查失败\n\n" + "\n".join(
            f"- {name}: {msg}" for name, msg in failures
        )
        body += f"\n\n检查时间：{datetime.now():%Y-%m-%d %H:%M}\n项目目录：{ROOT}"
        send_email("[告警] 第二课堂汇总页异常", body, topic="health")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
