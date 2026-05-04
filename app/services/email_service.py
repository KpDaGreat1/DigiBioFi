"""Transactional email helpers for verification and password reset."""

from email.message import EmailMessage
import logging
import smtplib
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when transactional email delivery fails."""


def is_email_configured() -> bool:
    return all(
        [
            settings.smtp_host.strip(),
            settings.smtp_host.strip() != "smtp.example.com",
            settings.smtp_user.strip(),
            settings.smtp_password.strip(),
            settings.emails_from_email.strip(),
        ]
    )


def _build_message(*, subject: str, recipient: str, text_body: str, html_body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.emails_from_name} <{settings.emails_from_email}>"
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message


def send_email(*, subject: str, recipient: str, text_body: str, html_body: str) -> None:
    if not is_email_configured():
        raise EmailDeliveryError("Email delivery is not configured.")

    message = _build_message(
        subject=subject,
        recipient=recipient,
        text_body=text_body,
        html_body=html_body,
    )

    last_error = None
    for attempt in range(1, 3):
        try:
            if settings.smtp_ssl:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.send_message(message)
                return

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.ehlo()
                if settings.smtp_tls:
                    server.starttls()
                    server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Email delivery attempt %s failed for recipient=%s via host=%s port=%s",
                attempt,
                recipient,
                settings.smtp_host,
                settings.smtp_port,
            )
            if attempt < 2:
                time.sleep(0.5)

    logger.error("Email delivery failed after retries: %s", last_error)
    raise EmailDeliveryError("Email delivery failed.") from last_error


def send_verification_email(*, recipient: str, username: str, verification_url: str) -> None:
    safe_name = username or "there"
    subject = "Verify your DigiBioFi email"
    text_body = (
        f"Hi {safe_name},\n\n"
        "Please verify your DigiBioFi account by opening the link below:\n\n"
        f"{verification_url}\n\n"
        f"This link expires in {settings.email_verification_expire_hours} hours.\n\n"
        "If you did not create this account, you can ignore this email."
    )
    html_body = f"""
    <html>
      <body style=\"font-family: Arial, sans-serif; color: #0f172a; line-height: 1.6;\">
        <p>Hi {safe_name},</p>
        <p>Please verify your DigiBioFi account by using the link below:</p>
        <p><a href=\"{verification_url}\">Verify my email</a></p>
        <p>This link expires in {settings.email_verification_expire_hours} hours.</p>
        <p>If you did not create this account, you can ignore this email.</p>
      </body>
    </html>
    """
    send_email(
        subject=subject,
        recipient=recipient,
        text_body=text_body,
        html_body=html_body,
    )


def send_password_reset_email(*, recipient: str, username: str, reset_url: str) -> None:
    safe_name = username or "there"
    subject = "Reset your DigiBioFi password"
    text_body = (
        f"Hi {safe_name},\n\n"
        "We received a request to reset your DigiBioFi password. Use the link below to continue:\n\n"
        f"{reset_url}\n\n"
        f"This link expires in {settings.password_reset_expire_minutes} minutes.\n\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = f"""
    <html>
      <body style=\"font-family: Arial, sans-serif; color: #0f172a; line-height: 1.6;\">
        <p>Hi {safe_name},</p>
        <p>We received a request to reset your DigiBioFi password.</p>
        <p><a href=\"{reset_url}\">Reset my password</a></p>
        <p>This link expires in {settings.password_reset_expire_minutes} minutes.</p>
        <p>If you did not request this, you can ignore this email.</p>
      </body>
    </html>
    """
    send_email(
        subject=subject,
        recipient=recipient,
        text_body=text_body,
        html_body=html_body,
    )
