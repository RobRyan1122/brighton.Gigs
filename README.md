Brighton Gigs

Brighton Gigs is a Python automation pipeline that scrapes live music events from venue websites, normalises the data, and generates shareable poster graphics. It’s designed to be easily adapted for other cities by swapping out the scraper modules for ones targeting different venue websites, while keeping the rest of the pipeline (CSV output, graphics, and distribution) unchanged.

the background art is by Jack Humpherson

Get Started
git clone https://github.com/RobRyan1122/brighton.Gigs.git
cd brighton.Gigs

can be run localy by adding email passowrds and recipients to config.py or through github actions by storing them as repo vars and secrets
