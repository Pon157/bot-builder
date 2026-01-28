
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Настройки берутся из .env или используются значения по умолчанию
GMAIL_USER = os.getenv('GMAIL_EMAIL',)
GMAIL_PASS = os.getenv('GMAIL_PASSWORD',)
SMTP_SERVER = os.getenv('SMTP_SERVER',)

# Безопасное получение порта с обработкой отсутствующего значения
raw_port = os.getenv('SMTP_PORT', '587')
try:
    SMTP_PORT = int(raw_port)
except (ValueError, TypeError):
    SMTP_PORT = 587

logger = logging.getLogger("EmailService")

class EmailService:
    @staticmethod
    def send_email(subject: str, recipient: str, html_content: str):
        if not GMAIL_USER or not GMAIL_PASS:
            logger.error("❌ Email settings missing (GMAIL_EMAIL or GMAIL_PASSWORD)")
            return False
        try:
            msg = MIMEMultipart()
            msg['From'] = f"BotEngine Pro <{GMAIL_USER}>"
            msg['To'] = recipient
            msg['Subject'] = subject

            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(GMAIL_USER, GMAIL_PASS)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {recipient}: {subject}")
            return True
        except Exception as e:
            logger.error(f"❌ Email error: {e}")
            return False

    @classmethod
    def send_verification_code(cls, recipient: str, code: str):
        subject = "Код подтверждения регистрации - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; border-radius: 20px; border: 1px solid #333;">
            <h2 style="color: #3b82f6; margin-bottom: 20px;">BotEngine Pro</h2>
            <p style="font-size: 16px;">Вы начали регистрацию. Ваш секретный код:</p>
            <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #fff; background: #111; padding: 30px; text-align: center; border-radius: 15px; margin: 30px 0; border: 1px solid #3b82f6;">
                {code}
            </div>
            <p style="color: #666; font-size: 13px;">Срок действия кода: 10 минут.</p>
        </div>
        """
        return cls.send_email(subject, recipient, content)

    @classmethod
    def send_password_reset(cls, recipient: str, code: str):
        subject = "Восстановление доступа - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; border-radius: 20px; border: 1px solid #333;">
            <h2 style="color: #ef4444; margin-bottom: 20px;">Сброс пароля</h2>
            <p style="font-size: 16px;">Для установки нового пароля используйте этот код:</p>
            <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #fff; background: #111; padding: 30px; text-align: center; border-radius: 15px; margin: 30px 0; border: 1px solid #ef4444;">
                {code}
            </div>
        </div>
        """
        return cls.send_email(subject, recipient, content)

    @classmethod
    def send_license_alert(cls, recipient: str, bot_name: str, days_left: int):
        subject = f"🔔 Лицензия бота {bot_name} почти истекла"
        color = "#f59e0b" if days_left > 1 else "#ef4444"
        content = f"""
        <div style="font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; border-radius: 20px; border: 1px solid #333;">
            <h2 style="color: {color}; margin-bottom: 20px;">Уведомление о лицензии</h2>
            <p style="font-size: 16px;">Лицензия для бота <b>{bot_name}</b> истекает через {days_left} дн.</p>
            <p style="font-size: 14px; color: #aaa;">Продлите её в кабинете, чтобы бот не отключился.</p>
        </div>
        """
        return cls.send_email(subject, recipient, content)
