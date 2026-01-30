
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
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        
        raw_port = os.getenv('SMTP_PORT', '587')
        try:
            smtp_port = int(raw_port)
        except:
            smtp_port = 587

        if not gmail_user or not gmail_pass:
            logger.error("❌ Ошибка: Учетные данные почты (GMAIL_EMAIL/GMAIL_PASSWORD) не найдены в окружении!")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = f"BotEngine Pro <{gmail_user}>"
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            # Увеличиваем таймаут для стабильности
            with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
                server.starttls()
                server.login(gmail_user, gmail_pass)
                server.send_message(msg)
            
            logger.info(f"✅ Письмо успешно отправлено на {recipient}")
            return True
        except Exception as e:
            logger.error(f"❌ Критическая ошибка SMTP при отправке на {recipient}: {str(e)}")
            return False

    @classmethod
    def send_verification_code(cls, recipient: str, code: str):
        subject = "Код подтверждения - BotEngine Pro"
        content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #050505; color: #ffffff; padding: 40px; border-radius: 24px; text-align: center; border: 1px solid #1a1a1a; max-width: 500px; margin: auto;">
            <div style="background: #2563eb; width: 50px; height: 50px; border-radius: 12px; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 20px;">BE</div>
            <h2 style="color: #ffffff; margin-bottom: 10px; font-weight: 800; letter-spacing: -0.025em;">Подтверждение регистрации</h2>
            <p style="color: #a1a1aa; font-size: 14px; line-height: 1.5;">Используйте этот код, чтобы завершить создание аккаунта в <b>BotEngine Pro</b>.</p>
            <div style="font-size: 42px; font-weight: 900; background: #000; color: #3b82f6; padding: 25px; border-radius: 16px; border: 1px solid #2563eb; margin: 30px 0; letter-spacing: 0.2em;">{code}</div>
            <p style="color: #52525b; font-size: 11px; margin-top: 20px; text-transform: uppercase; font-weight: bold; letter-spacing: 0.1em;">Код действителен 10 минут</p>
            <hr style="border: 0; border-top: 1px solid #1a1a1a; margin: 30px 0;">
            <p style="color: #3f3f46; font-size: 10px;">Если вы не запрашивали регистрацию, проигнорируйте это письмо.</p>
        </div>
        """
        return cls.send_email(subject, recipient, content)

    @classmethod
    def send_password_reset(cls, recipient: str, code: str):
        subject = "Восстановление пароля - BotEngine Pro"
        content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #050505; color: #ffffff; padding: 40px; border-radius: 24px; text-align: center; border: 1px solid #1a1a1a; max-width: 500px; margin: auto;">
            <div style="background: #ef4444; width: 50px; height: 50px; border-radius: 12px; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 20px;">BE</div>
            <h2 style="color: #ffffff; margin-bottom: 10px; font-weight: 800; letter-spacing: -0.025em;">Сброс пароля</h2>
            <p style="color: #a1a1aa; font-size: 14px; line-height: 1.5;">Мы получили запрос на сброс пароля для вашего аккаунта.</p>
            <div style="font-size: 42px; font-weight: 900; background: #000; color: #ef4444; padding: 25px; border-radius: 16px; border: 1px solid #ef4444; margin: 30px 0; letter-spacing: 0.2em;">{code}</div>
            <p style="color: #a1a1aa; font-size: 13px;">Введите этот код в приложении, чтобы задать новый пароль.</p>
            <p style="color: #52525b; font-size: 11px; margin-top: 25px; text-transform: uppercase; font-weight: bold; letter-spacing: 0.1em;">Безопасность прежде всего</p>
        </div>
        """
        return cls.send_email(subject, recipient, content)
