# FAZO JUNATMA

Telegram bot and Mini App for large-file upload, 24-hour sharing, wallet extensions, manual payment review, and referrals.

The web process runs on a Render Web Service. File bytes are stored on GoFile. The GoFile account token stays on the server.

## Architecture

```
Telegram Bot
    -> Telegram Mini App
    -> FastAPI (this service)
    -> Render Web Service
    -> GoFile
```

One Render Web Service runs the API, the Mini App, and the bot. PostgreSQL stores users, files, payments, wallet transactions, and referrals. There is no payment gateway. A user pays the card shown by the bot, sends a screenshot, and an admin approves or rejects it.

## Business rules

| Rule | Value |
| --- | --- |
| New user trial | 7 days, once per Telegram account |
| Referral | +1 day per genuinely new user, added to the current expiration |
| Premium | 15 000 so‘m / 30 days, added to remaining time |
| New file | 24 hours |
| File extension | 5 000 so‘m = +24 hours, taken from the wallet |
| Payment | Manual screenshot, pending until an admin reviews it |

Pending payments do not expire after 30 minutes. That figure is only the review estimate shown to the user.

## Requirements

- Python 3.12+
- A Telegram bot token from BotFather
- A GoFile account token and account id from the GoFile profile
- PostgreSQL in production (SQLite is enough for local development)

## Local installation

```powershell
cd "C:\Users\usmon\Projects\bot junatma"
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env`. Do not commit it.

Local database (SQLite):

```
DATABASE_URL=sqlite+aiosqlite:///./fazo_junatma.db
```

Apply migrations and start the app:

```powershell
alembic upgrade head
uvicorn backend.main:app --reload
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

Expected body: `{"status":"ok"}`.

On Linux or Render’s shell, use `python3.12 -m venv .venv` and `source .venv/bin/activate`.

## Environment variables

Set these in `.env` locally and in the Render dashboard for production. The application reads only environment variables. No secret is hardcoded.

```
BOT_TOKEN
GOFILE_API_TOKEN
GOFILE_ACCOUNT_ID
ADMIN_TELEGRAM_ID
DATABASE_URL
WEBAPP_URL
PAYMENT_CARD_NUMBER
PAYMENT_CARD_NAME
GOFILE_MAX_STORAGE_GB
GOFILE_MAX_FILE_SIZE_GB
GOFILE_STORAGE_WARNING_PERCENT
GOFILE_STORAGE_BLOCK_PERCENT
```

`ADMIN_TELEGRAM_ID` is your numeric Telegram user id. `WEBAPP_URL` is the public https origin, for example `https://fazo-junatma.onrender.com`, with no trailing path. `DATABASE_URL` is the Render PostgreSQL URL (`postgres://` or `postgresql://` are both accepted).

There are no Click or Payme variables. Do not add them.

## PostgreSQL

1. Create a PostgreSQL instance in the Render dashboard.
2. Copy its internal connection string into the web service `DATABASE_URL`.
3. Run `alembic upgrade head` (the Blueprint `preDeployCommand` does this on deploy).

The app rewrites `postgres://` to `postgresql+asyncpg://` and `sslmode` to the asyncpg `ssl` parameter.

## Alembic

```powershell
alembic upgrade head
alembic revision --autogenerate -m "describe the change"
```

The initial revision is `alembic/versions/0001_initial.py`.

## Telegram bot

1. Create the bot with BotFather and put the token in `BOT_TOKEN`.
2. Set the Mini App URL to `WEBAPP_URL` (https).
3. Locally, with an `http://` `WEBAPP_URL`, the process polls Telegram.
4. With an `https://` `WEBAPP_URL`, the process registers `POST /telegram/webhook` and checks Telegram’s secret header.

The bot menu is in Uzbek Latin: file upload, my files, balance, premium, referral, payment, and help. Upload and file management open the Mini App. The admin panel is visible only to `ADMIN_TELEGRAM_ID`.

Referral links look like `https://t.me/BOT_USERNAME?start=ref_CODE`. The username is read from Telegram at startup.

## Mini App

Open the service URL inside Telegram. The page sends `initData` to the API. The backend checks the Telegram HMAC and reads the user id from that payload. A `user_id` in the query string or body is ignored.

Local browser opens without `initData` show a short explanation. API tests build a valid `initData` value with the test bot token.

## Manual payment

1. The user chooses Premium (15 000 so‘m) or a wallet top-up (5 000, 10 000, 15 000, 20 000, or another amount).
2. The bot shows `PAYMENT_CARD_NUMBER` and `PAYMENT_CARD_NAME`.
3. The user sends a screenshot in the bot chat.
4. The payment stays `pending`.
5. The admin approves or rejects it.
6. Approval of a top-up credits the wallet once. Approval of Premium adds 30 days. Rejection changes neither balance nor subscription.

`PaymentService` is the extension point. The current class is `ManualPaymentService`.

## Wallet and files

The wallet pays for file extensions only. Extending locks the user row, checks the balance, subtracts 5 000 so‘m, and adds 24 hours to the current expiration. A repeated confirmation of the same extension does not charge twice. The balance cannot go below zero.

Deleting a file asks for confirmation, checks ownership, then asks GoFile to delete the content. If GoFile does not confirm deletion, the file is still closed in this database and the response says the remote delete was not confirmed.

An in-process loop marks due files expired about every 5 minutes. Opening or listing a file does the same check immediately. This loop runs inside the web process.

## GoFile

Official reference used: [https://gofile.io/api](https://gofile.io/api) (checked 3 October 2026).

| Action | Endpoint |
| --- | --- |
| Upload | `POST https://upload.gofile.io/uploadfile` |
| Delete | `DELETE https://api.gofile.io/contents` |
| File metadata | `GET https://api.gofile.io/contents/{contentId}` |
| Account id | `GET https://api.gofile.io/accounts/getid` |
| Storage stats | `GET https://api.gofile.io/accounts/{accountId}` |

Authentication is `Authorization: Bearer`. The upload is streamed from the temporary upload file. The handler does not call `read()` on the whole object.

Direct browser-to-GoFile upload is not used. The current API token is the whole account, and the docs do not offer a scoped upload token. Sending it to the Mini App would expose the account.

`GET /contents/{id}` is Premium-only. On `error-notPremium` the app keeps the `downloadPage` URL saved at upload time (`https://gofile.io/d/...`). Both “download” and “open in browser” use that verified GoFile URL unless a Premium direct `link` is actually returned.

The app never calls billing, plan upgrade, or token-reset endpoints. Before each upload it checks `GOFILE_MAX_FILE_SIZE_GB` and `GOFILE_MAX_STORAGE_GB`. At `GOFILE_STORAGE_WARNING_PERCENT` (default 80) the admin is notified. At `GOFILE_STORAGE_BLOCK_PERCENT` (default 95) new uploads stop. If the account stats call fails, usage falls back to the sum of active file sizes in the database.

## Render

1. Push this repository to GitHub.
2. In Render, create a PostgreSQL database and a Web Service from `render.yaml`, or create the service manually.
3. Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Health check path: `/health`
5. Enter the environment variables once in the service dashboard.

`render.yaml` lists every variable with `sync: false`. Render keeps dashboard values across deploys, so secrets are not entered again and are not overwritten by a Blueprint sync. Do not put real values in `render.yaml`.

Set `WEBAPP_URL` to the Render https origin after the first deploy, then redeploy once so the bot can register the webhook. Later code deploys keep the same variables.

Docker (optional):

```powershell
docker build -t fazo-junatma .
docker run --env-file .env -p 8000:8000 fazo-junatma
```

The image contains no secrets. It runs Alembic, then uvicorn.

## Tests

```powershell
pytest
```

The tests cover the 7-day trial, one-time trial, referrals, premium, file ownership, deletion, expiration, the 5 000 so‘m extension, double-click protection, manual approval and rejection, admin authorization, storage warning and block, and Telegram `initData`.

## Logging

Logs may include Telegram user id, file id, payment id, and status. They must not include `BOT_TOKEN`, `GOFILE_API_TOKEN`, the database password, or the payment card. A redaction filter strips configured secret values from log lines.
