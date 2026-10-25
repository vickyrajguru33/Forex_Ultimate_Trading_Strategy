# Ultimate Trading Strategy Scanner

This project is a detection-only Python scanner for the A+ 15-minute DXY sweep pattern. It reads market data, validates the candles, checks the DXY setup logic, and sends Telegram alerts. It does not place, modify, or close trades.

## What this project does

- Scans EURUSD, GBPUSD, and XAUUSD against DXY
- Uses the original OHLC values without transforming the market price
- Validates 15-minute candle continuity and pair timing
- Detects bullish and bearish sweep patterns
- Sends Telegram notifications with signal details and timestamps
- Tracks duplicate alerts in SQLite
- Includes optional economic news reminders and summary alerts
- Keeps the news module informational and non-blocking

## Important architecture note

This project is designed for a local Windows desktop runtime with MetaTrader 5 available. It is not meant to run directly on Vercel or other serverless platforms because the live MT5 runtime requires a desktop terminal and local IPC access.

The clean deployment setup is:

- Local Windows desktop: actual runtime, MT5 connection, Telegram alerts
- GitHub: source control and code hosting
- Vercel: optional status dashboard only, not live MT5 execution

## Project status

- Core strategy logic: implemented
- News monitoring: implemented
- Telegram integration: implemented
- Full regression tests: passing
- MT5 runtime: requires a local desktop terminal and credentials

## Recommended machine setup

### Option A: local Windows desktop (recommended)
This is the most suitable setup for live scanning.

Requirements:
- Windows 10/11
- Python 3.11+
- MetaTrader 5 terminal installed
- broker login and server details
- Telegram bot token and chat ID

### Option B: local Windows machine + Vercel dashboard
This is a hybrid layout.

- Local Windows machine runs the scanner and Telegram sender
- Vercel hosts a lightweight status page or dashboard
- The web dashboard must remain read-only

## System requirements

- Python 3.11 or newer
- Internet access to Telegram API and news API
- Access to the MT5 terminal if live scan is enabled
- A valid `.env` file with broker and Telegram values

## Installation on any machine

### 1) Clone the repo

```bash
git clone <your-repo-url>
cd Forex_Ultimate_Trading_Strategy
```

### 2) Create and activate a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you are using live MT5:

```bash
python -m pip install MetaTrader5
```

## Environment configuration

Create a `.env` file in the project root.

Example:

```env
# MT5 runtime
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_LOGIN=YOUR_LOGIN
MT5_PASSWORD=YOUR_PASSWORD
MT5_SERVER=YOUR_SERVER

# Telegram
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID

# App settings
DRY_RUN=false
APP_TIMEZONE=Asia/Kolkata
DXY_INVERT_SCALE=true

# News settings
NEWS_ALERTS_ENABLED=true
NEWS_PROVIDER=alpha_vantage
NEWS_CALENDAR_API_KEY=YOUR_NEWS_API_KEY
NEWS_TIMEZONE=Asia/Kolkata
NEWS_SUMMARY_TIME=07:00
NEWS_PRE_EVENT_MINUTES=60
NEWS_POST_EVENT_MINUTES=60
NEWS_POLL_INTERVAL_MINUTES=15
NEWS_POST_EVENT_ENABLED=true

# Prop-firm awareness (keep false unless the exact official rule is verified)
PROP_FIRM_RULES_VERIFIED=false
PROP_FIRM_NAME=
PROP_FIRM_ACCOUNT_MODEL=
PROP_FIRM_STAGE=
PROP_FIRM_RULE_SOURCE_URL=
```

Important:
- Do not commit real secrets to GitHub
- Use a local `.env` on the Windows machine
- Keep Vercel environment variables separate from the local runtime

## Local runtime startup

Run the app locally:

```bash
python main.py
```

For a local status endpoint and desktop runtime health check:

```bash
python main.py --poll-seconds 300 --status-port 8765
```

This mode is meant for a Windows desktop machine with MT5 available.

## Dry-run mode

If you want to test the output without sending a Telegram message:

```env
DRY_RUN=true
```

Then run:

```bash
python main.py
```

The app prints its alert text locally instead of sending Telegram messages.

## News monitor schedule

The project supports the following informational schedule:

- 07:00 AM IST: daily economic summary
- 1 hour before release: pre-event reminder
- 1 hour after release: post-event reminder
- News alerts are informational only and do not suppress or block valid sweep alerts

Important:
- The news module should not fetch the entire calendar every few minutes
- It can load the event set once and then check scheduled reminder windows
- Free hosting may delay exact reminder delivery, so exact timing is not guaranteed there

## Backtest and scan flow

For a real historical backtest, you need a data source available on the machine.

The project includes a historical scan script that expects a real MT5 terminal or another compatible data provider.

Example:

```bash
python historical_backtest_scan.py
```

If MetaTrader 5 is not available on this machine, the script exits safely without faking a signal.

## Safety rules

The code is intentionally designed to be detection-only:

- no order placement
- no trade execution
- no close/modify logic
- no signal injection into execution systems
- Telegram alerts are informational only

## Project structure

- `main.py` — runtime entry point
- `local_runtime.py` — local desktop runtime and status endpoint
- `config.py` — environment configuration and settings
- `mt5_client.py` — MT5 connection and symbol access
- `candle_validation.py` — candle validation and sweep logic helpers
- `sweep_detector.py` — detection logic
- `telegram_alerts.py` — Telegram formatting and delivery
- `state_store.py` — SQLite dedupe and alert state
- `news_monitor.py` — news summary and reminder logic
- `prop_firm_rules.py` — rule metadata and verified status
- `historical_backtest_scan.py` — historical scan helper
- `diagnose_mt5.py` — MT5 diagnosis utility
- `tests/` — project tests

## Testing

Run the full suite:

```bash
python -m pytest -q
```

## Common issues and fixes

### 1) MT5 not found

If you see:

```text
MT5.initialize() failed: IPC initialize failed, MetaTrader 5 x64 not found
```

Then:
- install MetaTrader 5 on the local Windows machine
- verify the terminal path in `.env`
- ensure the broker account is logged in

### 2) Telegram credential errors

Check:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- whether `DRY_RUN=true` is accidentally set

### 3) News provider errors

Check:
- `NEWS_CALENDAR_API_KEY`
- `NEWS_PROVIDER`
- whether the provider is reachable from the machine

### 4) DXY inversion confusion

The project intentionally preserves raw OHLC values for the sweep detection and only uses the DXY display inversion setting where applicable in helper logic. The strategy should not negate or reverse the market price.

## Recommended deployment architecture

### Good setup

- GitHub: code repo and CI
- Local Windows desktop: live runtime and MT5 monitoring
- Vercel: optional status page only

### Bad setup

- Deploying the MT5 scanner directly to Vercel or a serverless environment
- Running the live MT5 runtime in a Linux container or static host

## Final caution

This project is for research and detection only. It is not a trade execution system and should never be used to place or manage orders automatically.

If you plan to deploy live monitoring, keep the runtime on a local Windows machine with the MT5 terminal active and always use a safe, non-execution workflow.
