import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email(subject: str, body_text: str) -> None:
    if not settings.smtp_host or not settings.notify_email_from or not settings.notify_email_to:
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.notify_email_from
    msg["To"] = settings.notify_email_to
    msg.set_content(body_text)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)

