# DTEK Power Outage Scraper

[![CI](https://github.com/OWNER/REPO/actions/workflows/python-app.yml/badge.svg)](https://github.com/OWNER/REPO/actions)

Overview

This is a small Python project that scrapes DTEK's outage schedule for a given address, detects changes between runs, and sends notifications via email and Telegram when the schedule changes. The main script is `main.py`.

Requirements

- Python 3.8 or newer
- Install dependencies from `requirements.txt` if present

Quick install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run

```bash
python main.py
```

Project layout

- `main.py` — main scraper & notification logic
- `telegram_notification.py` — Telegram async helper
- `env_vars.json` — optional local fallback for environment variables
- `last_state.json` — persisted state used to detect changes

Environment variables

The app reads configuration from environment variables (or from `env_vars.json` as a fallback). Common variables:

- `CITY`, `STREET`, `HOUSE_NUM` — address to query
- `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` — SMTP credentials and sender address
- `SMTP_HOST`, `SMTP_PORT` — SMTP server (defaults in code may point to Gmail)
- `EMAIL_RECIPIENT` — email to receive notifications
- `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram bot credentials
- `STATE_FILE` — path for persisted state (defaults to `last_state.json`)

Local testing (MailHog)

Use MailHog to test email delivery locally:

```bash
# macOS: install and run MailHog
brew install mailhog
mailhog &                        # web UI: http://localhost:8025, SMTP: localhost:1025
# run main.py with local SMTP
SMTP_HOST=localhost SMTP_PORT=1025 SMTP_FROM=no-reply@local python main.py
```

Quick SMTP debug (prints emails to console):

```bash
python3 -m smtpd -n -c DebuggingServer localhost:1025 &
SMTP_HOST=localhost SMTP_PORT=1025 SMTP_FROM=no-reply@local python main.py
```

Test notification helper without running Selenium

```bash
python - <<'PY'
from main import send_off_intervals_via_email
send_off_intervals_via_email("you@example.com", ["00:00 - 01:00","12:30 - 13:00"], "2026-01-02")
PY
```

State persistence and CI

The workflow persists the last fetched state to a separate Git branch named `state` (file: `last_state.json`) so subsequent runs can detect changes. The GitHub Actions workflow should have write permissions to create/update that branch.

CI notes

- The provided CI workflow installs Python, caches pip, installs dependencies, runs a syntax check (`python -m py_compile main.py`) and `flake8` linting.
- The workflow intentionally does not run the Selenium browser flow on CI because it requires a system browser and network access. If you need full end-to-end tests on CI, run inside a container that provides Chrome/chromedriver.

Adding secrets to GitHub Actions

Go to your repository → Settings → Secrets and variables → Actions → New repository secret. Add the variables used by the project (SMTP credentials, recipient, address, Telegram tokens, etc.).

License

If you want, I can also update the CI workflow or add a simple CONTRIBUTING section next.

