"""备份本地配置、人工数据和 WeRSS 数据库，保留最近 10 份。"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from common import DATA_DIR, ROOT, setup_logger

log = setup_logger("backup")

BACKUP_ROOT = ROOT / "backups"
KEEP = 10
WERSS_DB = Path(r"C:\Users\Fox\we-mp-rss\data\db.db")


def backup_sqlite(src: Path, dst: Path) -> None:
    con_src = sqlite3.connect(str(src))
    con_dst = sqlite3.connect(str(dst))
    try:
        con_src.backup(con_dst)
    finally:
        con_dst.close()
        con_src.close()


def prune() -> None:
    dirs = sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir()], reverse=True)
    for old in dirs[KEEP:]:
        shutil.rmtree(old, ignore_errors=True)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_ROOT / stamp
    target.mkdir(parents=True, exist_ok=True)
    files = []

    for name in ("config.json", "data/manual.json"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, target / src.name)
            files.append(name)

    if WERSS_DB.exists():
        backup_sqlite(WERSS_DB, target / "werss.db")
        files.append("werss.db")

    (target / "manifest.json").write_text(json.dumps({
        "created_at": stamp,
        "files": files,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    prune()
    log.info("备份完成：%s（%s）", target, ", ".join(files) or "无文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
