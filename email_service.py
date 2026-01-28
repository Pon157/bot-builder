
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import sys

# Настраиваем логирование так, чтобы оно точно попадало в stdout (логи PM2)
logger = logging.getLogger("EmailService")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

# Настройки
GMAIL_USER = os.getenv('GMAIL_EMAIL')
GMAIL_PASS = os.getenv('GMAIL_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')

raw_port = os.getenv('SMTP_PORT', '587')
try:
    SMTP_PORT = int(raw_port)
except (ValueError, TypeError):
    SMTP_PORT = 587

class EmailService:
    @staticmethod
    def send_email(subject: str, recipient: str, html_content: str):
        logger.info(f"📧 Попытка отправки письма на {recipient} с темой '{subject}'...")
        
        if not GMAIL_USER or not GMAIL_PASS:
            logger.error("❌ Ошибка: Данные почты (GMAIL_EMAIL/GMAIL_PASSWORD) не найдены в окружении!")
            return False
        try:
            msg = MIMEMultipart()
            msg['From'] = f"BotEngine Pro <{GMAIL_USER}>"
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(GMAIL_USER, GMAIL_PASS)
                server.send_message(msg)
            
            logger.info(f"✅ Письмо успешно отправлено на {recipient}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка SMTP при отправке на {recipient}: {str(e)}")
            return False

    @classmethod
    def send_verification_code(cls, recipient: str, code: str):
        subject = "Код подтверждения регистрации - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; border-radius: 20px; border: 1px solid #333;">
            <h2 style="color: #3b82f6; margin-bottom: 20px;">BotEngine Pro</h2>
            <p style="font-size: 16px;">Ваш код для регистрации:</p>
            <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #fff; background: #111; padding: 30px; text-align: center; border-radius: 15px; margin: 30px 0; border: 1px solid #3b82f6;">
                {code}
            </div>
        </div>
        """
        return cls.send_email(subject, recipient, content)

    @classmethod
    def send_password_reset(cls, recipient: str, code: str):
        subject = "Восстановление доступа - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 40px; border-radius: 20px; border: 1px solid #333;">
            <h2 style="color: #ef4444; margin-bottom: 20px;">Сброс пароля</h2>
            <p style="font-size: 16px;">Код для смены пароля:</p>
            <div style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #fff; background: #111; padding: 30px; text-align: center; border-radius: 15px; margin: 30px 0; border: 1px solid #ef4444;">
                {code}
            </div>
        </div>
        """
        return cls.send_email(subject, recipient, content)
