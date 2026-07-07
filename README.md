# 👑🎳 Drei-Königs-Bowling

A bowling score tracker for you and your friends. Account-based, multi-player sessions with frame-by-frame scoring and full statistics.

## Features

- **Account system** — admin creates accounts for players; each player can change their own username/password
- **Frame-by-frame scoring** — enter rolls for all 10 frames with automatic correct scoring (strikes, spares, bonus calculation)
- **Quick entry** — skip the frames and just enter the final score when you're lazy
- **Multi-player sessions** — add multiple players per session; ranks are calculated automatically
- **Statistics** — per-player averages, high/low games, strike/spare rates, placement history (1st/2nd/3rd)
- **Practice games** — mark games as practice to exclude them from stats (toggle on/off)
- **Edit & delete** — fix mistakes by editing or deleting any game
- **Backup & restore** — automatic daily backups, manual backup/restore via the UI
- **Mobile-friendly** — works on phones and tablets

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 and log in with:

- **Username:** `flep98`
- **Password:** `1234`

From there you can create accounts for your friends.

## Production

```bash
gunicorn wsgi:app -b 0.0.0.0:5000 --workers=2
```

| Env var | Default | Description |
|---------|---------|-------------|
| `PORT` | `5000` | Port to listen on |
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode |

## Stack

- Flask + Flask-Login + Flask-SQLAlchemy
- SQLite
- Vanilla JS (no framework)
- Gunicorn
