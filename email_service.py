
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("EmailService")

class EmailService:
    @staticmethod
    def send_email(subject: str, recipient: str, html_content: str):
        gmail_user = os.getenv('GMAIL_EMAIL')
        gmail_pass = os.getenv('GMAIL_PASSWORD')
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))

        if not gmail_user or not gmail_pass:
            logger.error("SMTP credentials not found in environment")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = f"BotEngine Pro <{gmail_user}>"
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html_content, 'html'))

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent successfully to {recipient}")
            return True
        except Exception as e:
            logger.error(f"SMTP error: {str(e)}")
            return False

    @classmethod
    def send_verification_code(cls, recipient: str, code: str):
        subject = "Код подтверждения - BotEngine Pro"
        content = f"""
        <div style="font-family: sans-serif; background-color: #050505; color: #fff; padding: 40px; border-radius: 20px; text-align: center; border: 1px solid #333;">
            <h2 style="color: #3b82f6;">BotEngine Pro</h2>
            <p>Ваш код подтверждения для регистрации:</p>
            <div style="font-size: 36px; font-weight: bold; background: #111; padding: 20px; border-radius: 10px; color: #3b82f6; letter-spacing: 5px; margin: 20px 0;">{code}</div>
            <p style="color: #666; font-size: 12px;">Код действителен 10 минут.</p>
        </div>
        """
        return cls.send_email(subject, recipient, content)
