from pathlib import Path
import os
import smtplib
from email.message import EmailMessage


def build_alert():
    msg = EmailMessage()
    msg['Subject'] = 'Brighton Gigs: pipeline needs attention'
    msg['From'] = os.environ['SENDER_EMAIL']
    msg['To'] = os.environ['RECIPIENT_EMAIL']
    run_url = (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
               f"/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    report = Path(__file__).resolve().parents[2] / 'scraper_health.md'
    details = report.read_text(encoding='utf-8') if report.exists() else 'The pipeline failed before venue results were available. See the GitHub logs.'
    msg.set_content(f'The Brighton Gigs pipeline failed.\n\n{details}\nRun details: {run_url}\n\nAn empty venue result may indicate a website change, a temporary outage, or no gigs in the date range.')
    return msg


def main():
    msg = build_alert()
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ['SENDER_EMAIL'], os.environ['SENDER_PASSWORD'])
        smtp.send_message(msg)
    print('Pipeline failure alert sent.')


if __name__ == '__main__':
    main()
