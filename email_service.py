
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Настройки берутся из .env. Если их там нет, используются текущие значения как default
GMAIL_USER = os.getenv('GMAIL_EMAIL')
GMAIL_PASS = os.getenv('GMAIL_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))

logger = logging.getLogger("EmailService")

class EmailService:
    @staticmethod
    def send_email(subject: str, recipient: str, html_content: str):
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
            <p style="color: #666; font-size: 13px;">Срок действия кода: 10 минут. Если вы не делали этот запрос, просто удалите письмо.</p>
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
            <p style="color: #666; font-size: 13px;">Если вы не запрашивали сброс пароля, ваш аккаунт в безопасности, ничего делать не нужно.</p>
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
            <p style="font-size: 16px;">Срок действия лицензии для бота <b>{bot_name}</b> истекает через:</p>
            <div style="font-size: 24px; font-weight: bold; color: {color}; margin: 20px 0;">
                {days_left} дн.
            </div>
            <p style="font-size: 14px; color: #aaa;">Чтобы бот продолжал работать без пауз, пожалуйста, продлите лицензию в личном кабинете.</p>
            <div style="margin-top: 30px;">
                <a href="https://t.me/Kotickr" style="background: #3b82f6; color: #fff; padding: 15px 30px; text-decoration: none; border-radius: 12px; font-weight: bold;">Продлить через Telegram</a>
            </div>
        </div>
        """
        return cls.send_email(subject, recipient, content)
