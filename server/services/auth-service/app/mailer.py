from __future__ import annotations

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode

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


def send_verification_email(recipient: str, display_name: str, token: str) -> None:
    link = f"{settings.frontend_url_value}/verify-email?{urlencode({'token': token})}"
    _send(
        recipient,
        "Verify your Galaxy account",
        _template(display_name, "Verify your email", "Confirm email", link, "This link expires soon."),
    )


def send_reset_email(recipient: str, display_name: str, token: str) -> None:
    link = f"{settings.frontend_url_value}/reset-password?{urlencode({'token': token})}"
    _send(
        recipient,
        "Reset your Galaxy password",
        _template(
            display_name,
            "Reset your password",
            "Choose a new password",
            link,
            "If you did not request this, you can ignore this email.",
        ),
    )


def _template(name: str, heading: str, action: str, link: str, footer: str) -> str:
    return f"""<!doctype html>
<html><body style="font-family:Arial,sans-serif;color:#172033">
<div style="max-width:560px;margin:auto;padding:32px">
<h1>{html.escape(heading)}</h1>
<p>Hello {html.escape(name)},</p>
<p><a href="{html.escape(link, quote=True)}"
style="background:#4457ff;color:white;padding:12px 18px;text-decoration:none;border-radius:6px">
{html.escape(action)}</a></p>
<p style="color:#667085">{html.escape(footer)}</p>
</div></body></html>"""
