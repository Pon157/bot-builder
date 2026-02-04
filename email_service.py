
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import sys

logger = logging.getLogger("EmailService")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class EmailService:
    @staticmethod
    def send_email(subject: str, recipient: str, html_content: str):
        gmail_user = os.getenv('GMAIL_EMAIL')
        gmail_pass = os.getenv('GMAIL_PASSWORD')
        smtp_server = os.getenv('smtp.gmail.com')
        
        raw_port = os.getenv('SMTP_PORT', '587')
        try:
            smtp_port = int(raw_port)
        except:
            smtp_port = 587

        if not gmail_user or not gmail_pass:
            logger.error("❌ Ошибка: Учетные данные почты (GMAIL_EMAIL/GMAIL_PASSWORD) не найдены!")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = f"BotEngine Pro <{gmail_user}>"
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
                server.starttls()
                server.login(gmail_user, gmail_pass)
                server.send_message(msg)
            
            logger.info(f"✅ Письмо успешно отправлено на {recipient}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка SMTP: {str(e)}")
            return False

    @classmethod
    def send_verification_code(cls, recipient: str, code: str):
        subject = "Код подтверждения - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background-color: #050505; color: #ffffff; padding: 40px; border-radius: 24px; text-align: center; border: 1px solid #1a1a1a; max-width: 500px; margin: auto;">
            <h2 style="color: #ffffff; margin-bottom: 10px;">Подтверждение регистрации</h2>
            <div style="font-size: 42px; font-weight: 900; background: #000; color: #3b82f6; padding: 25px; border-radius: 16px; border: 1px solid #2563eb; margin: 30px 0;">{code}</div>
            <p style="color: #52525b; font-size: 11px;">Код действителен 10 минут</p>
        </div>
        """
        return cls.send_email(subject, recipient, content)

    @classmethod
    def send_password_reset(cls, recipient: str, code: str):
        subject = "Сброс пароля - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background-color: #050505; color: #ffffff; padding: 40px; border-radius: 24px; text-align: center; border: 1px solid #1a1a1a; max-width: 500px; margin: auto;">
            <h2 style="color: #ffffff; margin-bottom: 10px;">Сброс пароля</h2>
            <p style="color: #a1a1aa;">Используйте этот код для установки нового пароля:</p>
            <div style="font-size: 42px; font-weight: 900; background: #000; color: #ef4444; padding: 25px; border-radius: 16px; border: 1px solid #ef4444; margin: 30px 0;">{code}</div>
        </div>
        """
        return cls.send_email(subject, recipient, content)

    @classmethod
    def send_expiry_warning(cls, recipient: str, bot_name: str, days_left: int):
        subject = f"Внимание: Лицензия бота {bot_name} почти истекла!"
        content = f"""
        <div style="font-family: sans-serif; background-color: #050505; color: #ffffff; padding: 40px; border-radius: 24px; text-align: center; border: 1px solid #1a1a1a; max-width: 500px; margin: auto;">
            <h2 style="color: #ffffff; margin-bottom: 10px;">Продление лицензии</h2>
            <p style="color: #a1a1aa;">Уведомляем вас, что лицензия бота <b>{bot_name}</b> истекает через <b>{days_left} дня</b>.</p>
            <p style="color: #a1a1aa;">Пожалуйста, приобретите ключ и активируйте его в панели управления, чтобы избежать остановки инстанса.</p>
            <div style="margin-top: 30px; padding: 20px; border-radius: 12px; background: #111; border: 1px solid #333;">
                <p style="color: #3b82f6; font-weight: bold; margin: 0;">Инстанс: {bot_name}</p>
            </div>
        </div>
        """
        return cls.send_email(subject, recipient, content)
