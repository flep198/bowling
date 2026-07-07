# 👑🎳 Drei-Königs-Bowling

A bowling score tracker for you and your friends. Account-based, multi-player sessions with frame-by-frame scoring and full statistics.

## Features

- **Account system** — admin creates accounts for players; each player can change their own username/password
- **Frame-by-frame scoring** — enter rolls for all 10 frames with automatic correct scoring (strikes, spares, bonus calculation)
- **Quick entry** — skip the frames and just enter the final score
- **Multi-player sessions** — add multiple players per session; ranks are calculated automatically
- **Dashboard** — leaderboard table with averages, high/low, strike/spare/closed rates, gutter balls, placements, and last 5 scores; sortable columns
- **Score history chart** — per-player score timeline (line chart) with dynamic Y-range, zoom/pan, and date tooltips
- **Player statistics page** — per-player deep dive with score timeline, score distribution histogram, first-throw histogram, best game / best closing rate panels, and compare mode (overlay another player's data on all charts)
- **Practice games** — mark games as practice to exclude them from stats and recent sessions (toggle on/off)
- **Edit & delete** — fix mistakes by editing or deleting any game
- **Backup & restore** — automatic daily backups, manual backup/restore via the UI
- **Mobile-friendly** — responsive design with burger menu navigation; works on phones and tablets

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
- Vanilla JS + Chart.js + chartjs-plugin-zoom
- Gunicorn
