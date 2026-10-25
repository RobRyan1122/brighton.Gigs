Brighton Gigs

Brighton Gigs is a Python automation pipeline that scrapes live music events from venue websites, normalises the data, and generates shareable poster graphics. It’s designed to be easily adapted for other cities by swapping out the scraper modules for ones targeting different venue websites, while keeping the rest of the pipeline (CSV output, graphics, and distribution) unchanged.

the background art is by Jack Humpherson

Get Started
git clone https://github.com/RobRyan1122/brighton.Gigs.git
cd brighton.Gigs

can be run localy by adding email passowrds and recipients to config.py or through github actions by storing them as repo vars and secrets


Venue health checks

Each scheduled or manual GitHub pipeline run validates every venue CSV for the upcoming seven-day window. Empty results, missing files, invalid columns, missing dates/names, scraper errors, or a 15-minute scraper timeout fail the run after all venues have been checked. Existing CSVs for that run are removed first so stale output cannot pass. Failed venue checks stop poster generation and delivery.

The Actions run summary and scraper_health.md artifact list venue counts and failures. A failed run sends an alert with the report and run link using the existing SENDER_EMAIL, RECIPIENT_EMAIL, and SENDER_PASSWORD settings. Alert delivery requires those settings and a working SMTP connection. Zero results can also mean a quiet week; inspect the venue before assuming the website changed. The schedule remains weekly; the workflow can also be started manually.

Run offline regression checks with: python -m unittest discover -s tests

Schedule keep-alive

After checkout, the workflow calls GitHub's enable-workflow API using GITHUB_TOKEN (Actions write permission) to refresh the weekly schedule without creating commits. This is an inactivity-prevention workaround, not an exemption from GitHub's 60-day rule. If GitHub has already disabled the workflow, enable it manually under Actions once; a disabled workflow cannot run its own keep-alive. The keep-alive runs before scraping so venue failures do not prevent it. A failed keep-alive fails the job and uses the existing failure email step.
