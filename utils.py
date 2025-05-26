import smtplib
import os
import threading
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import make_response

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def cache_static(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        response = make_response(view_func(*args, **kwargs))
        response.cache_control.max_age = 3600
        return response

    return wrapper


def run_in_thread(func, *args, **kwargs):

    thread = threading.Thread(target=func, args=args, kwargs=kwargs)
    thread.start()
    return thread


def _send_email_sync(to_address, subject, html_body):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_address = os.environ.get("SMTP_USERNAME")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to_address

    text_part = MIMEText("Please view this email in an HTML compatible client.", "plain")
    html_part = MIMEText(html_body, "html")
    message.attach(text_part)
    message.attach(html_part)
    if not all([smtp_server, smtp_port, smtp_username, smtp_password, from_address]):
        logger.error("Missing SMTP configuration parameters.")
        return
    with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=5) as server:
        server.login(smtp_username, smtp_password)
        server.sendmail(from_address, to_address, message.as_string())


def send_email(to_address, subject, html_body):
    if not all([to_address, subject, html_body]):
        logger.error("Missing required parameters to send email.")
        return

    try:
        run_in_thread(_send_email_sync, to_address, subject, html_body)
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
