import os
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib


async def send_email(to_address, subject, html_body):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_address = smtp_username  

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to_address

    text_part = MIMEText("Please view this email in an HTML compatible client.", "plain")
    html_part = MIMEText(html_body, "html")
    message.attach(text_part)
    message.attach(html_part)

    await aiosmtplib.send(
        message,
        hostname=smtp_server,
        port=smtp_port,
        username=smtp_username,
        password=smtp_password,
        use_tls=True,
        timeout=10,
    )
