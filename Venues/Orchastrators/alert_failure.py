from pathlib import Path
import argparse
import json
import os
import smtplib
from email.message import EmailMessage


def build_alert(venue_warning=False):
    msg = EmailMessage()
    msg['Subject'] = 'Brighton Gigs: venues missing from posters' if venue_warning else 'Brighton Gigs: pipeline needs attention'
    msg['From'] = os.environ['SENDER_EMAIL']
    msg['To'] = os.environ['RECIPIENT_EMAIL']
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', 'RobRyan1122/brighton.Gigs')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    report = Path(__file__).resolve().parents[2] / 'scraper_health.md'
    details = report.read_text(encoding='utf-8') if report.exists() else 'Venue results are unavailable. See the GitHub logs.'
    intro = 'Posters were generated and emailed using the successful venues. The venues marked FAILED below were omitted.' if venue_warning else 'The Brighton Gigs pipeline failed.'
    msg.set_content(f'{intro}\n\n{details}\nRun details: {run_url}\n\nAn empty venue result may indicate a website change, a temporary outage, or no gigs in the date range.')
    return msg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--venue-warning', action='store_true')
    args = parser.parse_args()
    if args.venue_warning:
        health = Path(__file__).resolve().parents[2] / 'scraper_health.json'
        if not health.exists() or not json.loads(health.read_text(encoding='utf-8'))['failures']:
            return
    msg = build_alert(args.venue_warning)
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.environ['SENDER_EMAIL'], os.environ['SENDER_PASSWORD'])
        smtp.send_message(msg)
    print('Pipeline failure alert sent.')


if __name__ == '__main__':
    main()
