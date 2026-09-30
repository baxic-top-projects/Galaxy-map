from __future__ import annotations

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _send(recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.warning("SMTP is not configured; skipped email to %s", recipient)
        return
    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("Open this email in an HTML-capable client.")
    message.add_alternative(body, subtype="html")

    context = ssl.create_default_context()
    if settings.smtp_ssl:
        smtp = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=15, context=context
        )
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with smtp:
        if settings.smtp_starttls and not settings.smtp_ssl:
            smtp.starttls(context=context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def send_verification_email(recipient: str, display_name: str, code: str) -> None:
    _send(
        recipient,
        "Код подтверждения Galaxy Map",
        _code_template(
            display_name,
            "Подтверждение почты",
            code,
            "Код действует 15 минут.",
        ),
    )


def send_reset_email(recipient: str, display_name: str, code: str) -> None:
    _send(
        recipient,
        "Код сброса пароля Galaxy Map",
        _code_template(
            display_name,
            "Сброс пароля",
            code,
            "Код действует 15 минут. Если вы не запрашивали сброс, проигнорируйте письмо.",
        ),
    )


def _code_template(name: str, heading: str, code: str, footer: str) -> str:
    return f"""<!doctype html>
<html><body style="font-family:Arial,sans-serif;color:#172033">
<div style="max-width:560px;margin:auto;padding:32px">
<h1>{html.escape(heading)}</h1>
<p>Здравствуйте, {html.escape(name)}.</p>
<p>Ваш код:</p>
<p style="font-size:32px;font-weight:700;letter-spacing:8px">{html.escape(code)}</p>
<p style="color:#667085">{html.escape(footer)}</p>
</div></body></html>"""
