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
    logo_url = html.escape(f"{settings.frontend_url_value}/favicon.png", quote=True)
    return f"""<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;background:#05070f;font-family:Arial,sans-serif;color:#e8eef8">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="background:#05070f;padding:32px 12px">
<tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="max-width:560px;background:#0d1728;border:1px solid #263a58;border-radius:16px">
<tr><td style="padding:32px">
<img src="{logo_url}" width="72" height="72" alt="Galaxy Map"
     style="display:block;margin:0 auto 20px;border:0;border-radius:16px">
<p style="margin:0 0 8px;text-align:center;color:#9bb0d0;font-size:14px">THE UNIVERSE</p>
<h1 style="margin:0 0 24px;text-align:center;font-size:26px">{html.escape(heading)}</h1>
<p>Здравствуйте, {html.escape(name)}.</p>
<p>Ваш код:</p>
<p style="margin:20px 0;padding:16px;text-align:center;background:#111f35;border-radius:10px;
          font-size:32px;font-weight:700;letter-spacing:8px">{html.escape(code)}</p>
<p style="margin:24px 0 0;color:#9bb0d0;font-size:14px">{html.escape(footer)}</p>
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""
