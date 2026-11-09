"""邮件告警，带冷却避免刷屏。"""
from __future__ import annotations

import json
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from common import DATA_DIR, atomic_write_text, load_config, setup_logger

log = setup_logger("notify")
STATE = DATA_DIR / "alert_state.json"


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    atomic_write_text(STATE, json.dumps(state, ensure_ascii=False, indent=2))


def _cooling(topic: str, hours: float) -> bool:
    state = _load_state()
    last = state.get(topic)
    if not last:
        return False
    try:
        elapsed = datetime.now() - datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return False
    return elapsed < timedelta(hours=hours)


def send_email(subject: str, body: str, topic: str = "default") -> bool:
    cfg = load_config().get("email", {})
    if not cfg.get("enabled"):
        log.info("邮件告警未启用，跳过：%s", subject)
        return False
    if _cooling(topic, float(cfg.get("cooldown_hours", 12))):
        log.info("告警冷却中，跳过：%s", subject)
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("北中医第二课堂监控", cfg.get("username", "")))
    msg["To"] = cfg.get("to", "")

    try:
        if cfg.get("use_ssl", True):
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["smtp_host"], int(cfg.get("smtp_port", 465)), context=ctx, timeout=25) as s:
                s.login(cfg["username"], cfg["password"])
                s.sendmail(cfg["username"], [cfg["to"]], msg.as_string())
        else:
            with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587)), timeout=25) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(cfg["username"], cfg["password"])
                s.sendmail(cfg["username"], [cfg["to"]], msg.as_string())
        state = _load_state()
        state[topic] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)
        log.info("告警邮件已发送：%s", subject)
        return True
    except smtplib.SMTPServerDisconnected as exc:
        log.error("邮件发送失败：SMTP 在登录阶段被断开。请检查授权码是否有效、"
                  "QQ 邮箱是否已开启 POP3/SMTP 服务（%s）", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("邮件发送失败：%s", exc)
        return False
