import smtplib
import os
from email.message import EmailMessage
from pathlib import Path
import mimetypes
import config

# =========================
# CONFIG
# =========================


SENDER_EMAIL = os.environ["SENDER_EMAIL"]
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]

FOLDER_PATH = config.FOLDER_PATH

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# =========================
# BUILD EMAIL
# =========================

msg = EmailMessage()
msg["Subject"] = "Daily Gig Posters"
msg["From"] = SENDER_EMAIL
msg["To"] = RECIPIENT_EMAIL
msg.set_content("Here are today's generated gig posters.")


# =========================
# ATTACH IMAGES
# =========================

for file_path in FOLDER_PATH.iterdir():
    if file_path.is_file():
        mime_type, _ = mimetypes.guess_type(file_path)

        if mime_type and mime_type.startswith("image"):
            with open(file_path, "rb") as f:
                file_data = f.read()
                file_name = file_path.name

                maintype, subtype = mime_type.split("/")

                msg.add_attachment(
                    file_data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=file_name
                )

                print(f"Attached: {file_name}")


# =========================
# SEND EMAIL
# =========================

with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
    smtp.starttls()
    smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
    smtp.send_message(msg)

print("Email sent successfully.")