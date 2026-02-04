
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import sys

# Настраиваем логирование
logger = logging.getLogger("EmailService")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class EmailService:
    @staticmethod
    def send_email(subject: str, recipient: str, html_content: str):
        # Считываем переменные прямо здесь, чтобы они подхватились после загрузки .env
        gmail_user = os.getenv('GMAIL_EMAIL')
        gmail_pass = os.getenv('GMAIL_PASSWORD')
        smtp_server = os.getenv('SMTP_SERVER')
        
        raw_port = os.getenv('SMTP_PORT')
        try:
            smtp_port = int(raw_port)
        except (ValueError, TypeError):
            smtp_port = 587

        logger.info(f"📧 Попытка отправки письма на {recipient} с темой '{subject}'...")
        
        if not gmail_user or not gmail_pass:
            logger.error("❌ Ошибка: Данные почты (GMAIL_EMAIL/GMAIL_PASSWORD) не найдены в окружении!")
            return False
        try:
            msg = MIMEMultipart()
            msg['From'] = f"BotEngine Pro <{gmail_user}>"
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(gmail_user, gmail_pass)
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
