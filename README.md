# DTEK GET Schedule Project

[![CI](https://github.com/OWNER/REPO/actions/workflows/python-app.yml/badge.svg)](https://github.com/OWNER/REPO/actions)

Короткое описание

Это минимальный проект на Python, содержащий `main.py` и файл зависимостей `requirements.txt`.

Требования

- Python 3.8+
- Установленные зависимости из `requirements.txt` (если есть)

Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Запуск

```bash
python main.py
```

Структура

- `main.py` — точка входа приложения
- `requirements.txt` — зависимости (если необходимы)

Поддержка и тестирование

Если нужно — добавьте инструкцию по тестированию здесь.

Email / отправка уведомлений

- В этом проекте большинство SMTP-параметров захардкожены в `main.py` (для простоты): `smtp.gmail.com`, порт `465`, SSL включён. Требуется секреты:
  - `SMTP_USER` — логин (email) для SMTP.
  - `SMTP_PASS` — пароль / App Password для SMTP.
  - `SMTP_FROM` — адрес отправителя (обычно тот же email, что и `SMTP_USER`).
  - `EMAIL_RECIPIENT` — email получателя уведомлений.
  - `CITY` — город для поиска отключений.
  - `STREET` — улица для поиска отключений.
  - `HOUSE_NUM` — номер дома для поиска отключений.

Как добавить секреты в GitHub Actions

1. Откройте репозиторий на GitHub -> Settings -> Secrets and variables -> Actions -> New repository secret.
2. Добавьте необходимые секреты: `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `EMAIL_RECIPIENT`, `CITY`, `STREET`, `HOUSE_NUM`.
 
 State branch
 
 - The workflow persists the last fetched state to a separate Git branch named `state` (file: `last_state.json`) so subsequent runs can detect changes. The workflow will create or update this branch and force-push a single amended commit containing the latest state.
 - Ensure Actions workflow has write permissions: Repository → Settings → Actions → General → Workflow permissions: set to "Read and write permissions" so the job can push the `state` branch using the provided `GITHUB_TOKEN`.
 - If you prefer a different branch name or location for the state file, set the `STATE_FILE` environment variable (path) in `main.py` or modify the workflow step that pushes the file.

Локальное тестирование (рекомендуется с MailHog)

- Установите зависимости и активируйте окружение:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
- Тест с MailHog (Mac):
```bash
brew install mailhog
mailhog &                        # web UI: http://localhost:8025, SMTP: localhost:1025
SMTP_HOST=localhost SMTP_PORT=1025 SMTP_FROM=no-reply@local python main.py
```
- Быстрый тест с отладочным SMTP-сервером (выводит письма в консоль):
```bash
python3 -m smtpd -n -c DebuggingServer localhost:1025 &
SMTP_HOST=localhost SMTP_PORT=1025 SMTP_FROM=no-reply@local python main.py
```

Тестирование функции отправки без запуска Selenium

```bash
python - <<'PY'
from main import send_off_intervals_via_email
send_off_intervals_via_email("you@example.com", ["00:00 - 01:00","12:30 - 13:00"], "2026-01-02")
PY
```

Лицензия

Добавьте лицензию по желанию (например, MIT).

CI (GitHub Actions)

 - **Badge:** Replace OWNER and REPO with your values and add the badge to the top of this file:
	 - `[![CI](https://github.com/OWNER/REPO/actions/workflows/python-app.yml/badge.svg)](https://github.com/OWNER/REPO/actions)`

 - **What the workflow does:** Installs Python, caches pip, installs dependencies from `requirements.txt`, runs a syntax check (`python -m py_compile main.py`) and runs `flake8` linting. It intentionally does not execute the full Selenium-driven browser flow in CI because that requires system browser interaction and network access.

 - **How to publish to GitHub:**
	 1. Initialize git if you haven't: `git init`.
	 2. Add files and commit: `git add . && git commit -m "Initial project with CI"`.
	 3. Create a GitHub repo (via website or `gh`): `gh repo create OWNER/REPO --public --source=. --remote=origin`.
	 4. Push: `git push -u origin main` (or `master` if you use that branch).

 - **Notes about Selenium:** To run `main.py` on CI or GitHub-hosted runners, you'll need to ensure a compatible browser (Chrome) is available and match the `chromedriver` version; consider using a Docker container with Chrome or using actions that provide a browser. For local runs, create and activate a virtual environment and install dependencies from `requirements.txt`.

