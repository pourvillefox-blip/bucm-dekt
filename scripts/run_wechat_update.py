"""每 12 小时只刷新微信公众号 RSS，并构建/部署网页。"""
from __future__ import annotations

import sys
from datetime import datetime

from common import DATA_DIR, ROOT, setup_logger, write_json
from notify import send_email
from run_update import run

log = setup_logger("wechat_update")


def main() -> int:
    started = datetime.now()
    status, error = "ok", ""
    try:
        run("crawl_rss.py", required=True, timeout=1200)
        run("build_site.py", required=True, timeout=300)
        run("deploy.py", required=False, timeout=300)
    except Exception as exc:  # noqa: BLE001
        status, error = "error", str(exc)
        log.error("公众号刷新失败：%s", exc)
        send_email(
            "[告警] 公众号刷新失败",
            f"时间：{started:%Y-%m-%d %H:%M}\n错误：{exc}\n\n"
            f"请检查 WeRSS（http://127.0.0.1:8001）和日志：{ROOT / 'logs'}",
            topic="wechat_refresh",
        )
    finally:
        try:
            write_json(DATA_DIR / "last_wechat_update.json", {
                "status": status,
                "started_at": started.isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "error": error,
            })
        except Exception as exc:  # noqa: BLE001
            log.error("写 last_wechat_update.json 失败：%s", exc)
    log.info("公众号刷新结束：%s", status)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
