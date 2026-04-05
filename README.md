# Football Betting Demo

This project is a demo football betting website built with Flask and SQLite.

## Features

- User registration and login
- Virtual credit balance for demo betting
- Upcoming football fixtures with odds
- Bet placement for home win, draw, or away win
- Bet history and simple personal stats
- Demo settlement flow for finished matches

## Run locally

1. Create or activate a Python environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Start the app:

   ```bash
   python app.py
   ```

4. Open `http://127.0.0.1:5000`.

## Notes

- The app uses SQLite and creates `betting.db` automatically on first run.
- New users start with 1000 demo credits.
- Match settlement is deterministic and intended only for local demo use.