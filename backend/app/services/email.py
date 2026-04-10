import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def _send(to: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        start_tls=True,
    )


async def send_verification_email(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/verify?token={token}"
    await _send(
        to=to,
        subject="SpritzMap — E-Mail-Adresse bestätigen",
        html=f"""
        <p>Hallo,</p>
        <p>bitte bestätige deine E-Mail-Adresse:</p>
        <p><a href="{link}" style="background:#e8500a;color:white;padding:10px 20px;
           border-radius:6px;text-decoration:none;font-weight:bold;">
           E-Mail bestätigen
        </a></p>
        <p>Der Link ist 24 Stunden gültig.</p>
        <p style="color:#aaa;font-size:0.85em">Falls du dich nicht registriert hast,
        ignoriere diese E-Mail.</p>
        """,
    )


async def send_reset_email(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    await _send(
        to=to,
        subject="SpritzMap — Passwort zurücksetzen",
        html=f"""
        <p>Hallo,</p>
        <p>du hast ein neues Passwort angefordert:</p>
        <p><a href="{link}" style="background:#e8500a;color:white;padding:10px 20px;
           border-radius:6px;text-decoration:none;font-weight:bold;">
           Passwort zurücksetzen
        </a></p>
        <p>Der Link ist 1 Stunde gültig.</p>
        <p style="color:#aaa;font-size:0.85em">Falls du kein neues Passwort angefordert hast,
        ignoriere diese E-Mail.</p>
        """,
    )
