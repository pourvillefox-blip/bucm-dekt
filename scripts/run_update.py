"""定时更新入口：抓官网 → 抓公众号 → 生成网页 →（可选）部署 → 记录状态。"""
from __future__ import annotations

import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from common import DATA_DIR, DOCS_DIR, ROOT, SITE_DIR, load_config, read_json_strict, setup_logger, write_json
from notify import send_email

log = setup_logger("run_update")
SCRIPTS = Path(__file__).resolve().parent

BACKUP_PATHS = [
    DATA_DIR / "official.json",
    DATA_DIR / "wechat.json",
    DATA_DIR / "combined.json",
    DOCS_DIR / "index.html",
    SITE_DIR / "index.html",
]


def run(script: str, required: bool = True, timeout: int = 900) -> bool:
    log.info("运行 %s", script)
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log.error("%s 超时（%d 秒）", script, timeout)
        if required:
            raise RuntimeError(f"{script} 超时")
        return False

    if proc.stdout.strip():
        log.info(proc.stdout.strip()[-2000:])
    if proc.returncode != 0:
        log.error("%s 失败（退出码 %d）：%s", script, proc.returncode,
                  (proc.stderr or "").strip()[-1200:])
        if required:
            raise RuntimeError(f"{script} 退出码 {proc.returncode}")
        return False
    return True


def backup() -> dict[Path, Path]:
    saved: dict[Path, Path] = {}
    for src in BACKUP_PATHS:
        if src.exists():
            dst = src.with_suffix(src.suffix + ".bak")
            shutil.copy2(src, dst)
            saved[src] = dst
    return saved


def restore(saved: dict[Path, Path]) -> None:
    for src, bak in saved.items():
        try:
            shutil.copy2(bak, src)
        except OSError as exc:
            log.error("回滚 %s 失败：%s", src, exc)
    log.warning("已回滚到上一份可用数据（%d 个文件）", len(saved))


def main() -> int:
    started = datetime.now()
    status, error = "ok", ""
    count = 0
    deploy_ok = None
    saved: dict[Path, Path] = {}

    try:
        saved = backup()
        run("crawl_official.py", required=True)
        run("crawl_wechat.py", required=False)
        run("build_site.py", required=True)

        combined = read_json_strict(DATA_DIR / "combined.json") or {}
        count = combined.get("count", 0)
        if not isinstance(count, int) or count <= 0:
            raise RuntimeError("合并结果为 0 条，拒绝发布")

        cfg = load_config()
        if cfg.get("deploy", {}).get("enabled"):
            deploy_ok = run("deploy.py", required=False)
            if not deploy_ok:
                send_email(
                    "[告警] 第二课堂网页部署失败",
                    f"数据已更新（{count} 条），但推送到 GitHub Pages 失败。\n"
                    f"时间：{datetime.now():%Y-%m-%d %H:%M}\n"
                    f"请检查日志：{ROOT / 'logs'}",
                    topic="deploy",
                )
    except Exception as exc:  # noqa: BLE001
        status, error = "error", str(exc)
        log.error("更新失败：%s", exc)
        log.error(traceback.format_exc())
        if saved:
            try:
                restore(saved)
            except Exception as restore_exc:  # noqa: BLE001
                log.error("回滚过程异常：%s", restore_exc)
        else:
            log.warning("首次运行，没有可回滚的旧数据")
        send_email(
            "[告警] 第二课堂数据更新失败",
            f"更新时间：{started:%Y-%m-%d %H:%M}\n错误：{exc}\n\n"
            + ("已尝试回滚到上一份可用数据。\n" if saved else "首次运行，无旧数据可回滚。\n")
            + f"请检查日志：{ROOT / 'logs'}",
            topic="update",
        )
    finally:
        try:
            write_json(DATA_DIR / "last_update.json", {
                "status": status,
                "deploy_ok": deploy_ok,
                "started_at": started.isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "count": count,
                "error": error,
            })
        except Exception as exc:  # noqa: BLE001
            log.error("写 last_update.json 失败：%s", exc)

    log.info("更新结束：%s（%d 条）", status, count)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
