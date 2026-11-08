Brighton Gigs

Brighton Gigs is a Python automation pipeline that scrapes live music events from venue websites, normalises the data, and generates shareable poster graphics. It’s designed to be easily adapted for other cities by swapping out the scraper modules for ones targeting different venue websites, while keeping the rest of the pipeline (CSV output, graphics, and distribution) unchanged.

the background art is by Jack Humpherson

Get Started
git clone https://github.com/RobRyan1122/brighton.Gigs.git
cd brighton.Gigs

can be run localy by adding email passowrds and recipients to config.py or through github actions by storing them as repo vars and secrets


Venue health checks

Each scheduled or manual GitHub pipeline run validates every venue CSV for the upcoming seven-day window. Empty results, missing files, invalid columns, missing dates/names, scraper errors, or a 15-minute scraper timeout are reported after all venues have been checked. Existing CSVs for that run are removed first so stale output cannot pass. When some venues fail, posters are generated and emailed using only successful venues from that run, followed by a separate warning email naming omitted venues. Old CSVs from failed venues are excluded. If every venue fails, the pipeline stops and sends a failure email.

The Actions run summary and scraper_health.md artifact list venue counts and failures. A failed run sends an alert with the report and run link using the existing SENDER_EMAIL, RECIPIENT_EMAIL, and SENDER_PASSWORD settings. Alert delivery requires those settings and a working SMTP connection. Zero results can also mean a quiet week; inspect the venue before assuming the website changed. The schedule remains weekly; the workflow can also be started manually.

Run offline regression checks with: python -m unittest discover -s tests

Schedule keep-alive

After checkout, the workflow calls GitHub's enable-workflow API using GITHUB_TOKEN (Actions write permission) to refresh the weekly schedule without creating commits. This is an inactivity-prevention workaround, not an exemption from GitHub's 60-day rule. If GitHub has already disabled the workflow, enable it manually under Actions once; a disabled workflow cannot run its own keep-alive. The keep-alive runs before scraping so venue failures do not prevent it. A failed keep-alive fails the job and uses the existing failure email step.

Date handling

Scrapers preserve explicit website years. Alphabet, Hope & Ruin, and Prince Albert infer missing years using the requested start/end range and write full dates into their CSVs. Shared inference supports all months, year boundaries, and leap days; without a match in the range it chooses the nearest occurrence to the reference date. A yearless website cannot distinguish multiple occurrences of the same day in a range spanning more than a year. Graphics use the CSV filename date range when older input omits a year, with the current date as the standalone fallback. Regression tests cover date handling for all eight venues. Dust processes all listed events rather than assuming chronological ordering.
