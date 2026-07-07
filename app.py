import os
import shutil
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
if os.path.exists(key_file):
    with open(key_file) as f:
        app.secret_key = f.read().strip()
else:
    app.secret_key = os.urandom(64).hex()
    with open(key_file, "w") as f:
        f.write(app.secret_key)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bowling.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DB_PATH = os.path.join(BASE_DIR, "instance", "bowling.db")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class GameSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    entries = db.relationship(
        "Game", backref="session", lazy="joined",
        cascade="all, delete-orphan", order_by="Game.rank"
    )


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("game_session.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    rank = db.Column(db.Integer, nullable=True)
    practice = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    frames = db.relationship(
        "Frame", backref="game", lazy="joined",
        order_by="Frame.frame", cascade="all, delete-orphan"
    )
    player = db.relationship("User", lazy="joined")


class Frame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    frame = db.Column(db.Integer, nullable=False)
    roll1 = db.Column(db.Integer, nullable=False, default=0)
    roll2 = db.Column(db.Integer, nullable=True)
    roll3 = db.Column(db.Integer, nullable=True)


# ── Scoring ──────────────────────────────────────────────

def bowling_score(frames):
    total = 0
    for i, f in enumerate(frames):
        r1 = f.roll1
        r2 = f.roll2 if f.roll2 is not None else 0
        r3 = f.roll3 if f.roll3 is not None else 0
        if i < 9:
            if r1 == 10:
                total += 10
                nf = frames[i + 1]
                total += nf.roll1
                if nf.roll1 == 10 and i + 1 < 9:
                    total += frames[i + 2].roll1
                else:
                    total += nf.roll2 if nf.roll2 is not None else 0
            elif r1 + r2 == 10:
                total += 10 + frames[i + 1].roll1
            else:
                total += r1 + r2
        else:
            total += r1 + r2 + r3
    return total


def frame_stats(frames):
    strikes = 0
    spares = 0
    for f in frames:
        if f.roll1 == 10:
            strikes += 1
        elif f.roll2 is not None and f.roll1 + f.roll2 == 10:
            spares += 1
    return strikes, spares


def assign_ranks(entries):
    entries.sort(key=lambda g: g.total_score, reverse=True)
    for i, g in enumerate(entries):
        if i > 0 and g.total_score == entries[i-1].total_score:
            g.rank = entries[i-1].rank
        else:
            g.rank = i + 1


def compute_player_stats(user, include_practice=False):
    q = Game.query.filter_by(user_id=user.id)
    if not include_practice:
        q = q.filter_by(practice=False)
    games = q.order_by(Game.id.desc()).all()
    all_scores = [g.total_score for g in games]
    total_strikes = 0
    total_spares = 0
    total_frames = 0
    for g in games:
        if g.frames:
            s, sp = frame_stats(g.frames)
            total_strikes += s
            total_spares += sp
            total_frames += len(g.frames)

    placements = {}
    for g in games:
        if g.rank:
            placements[g.rank] = placements.get(g.rank, 0) + 1

    last_five = games[:5]
    last_five_scores = [g.total_score for g in last_five]

    closed = total_strikes + total_spares

    if not all_scores:
        return {
            "count": 0, "avg": 0, "high": 0, "low": 0,
            "strikes": 0, "spares": 0, "closed": 0,
            "strike_pct": 0, "spare_pct": 0, "closed_pct": 0,
            "last_five": [], "placements": {}, "sessions": 0,
            "score_history": [],
        }

    nsf = total_frames - total_strikes
    return {
        "count": len(all_scores),
        "avg": round(sum(all_scores) / len(all_scores), 1),
        "high": max(all_scores),
        "low": min(all_scores),
        "strikes": total_strikes,
        "spares": total_spares,
        "closed": closed,
        "strike_pct": round(total_strikes / total_frames * 100, 1) if total_frames else 0,
        "spare_pct": round(total_spares / nsf * 100, 1) if nsf else 0,
        "closed_pct": round(closed / total_frames * 100, 1) if total_frames else 0,
        "last_five": last_five,
        "best_in_last_five": max(last_five_scores) if last_five_scores else 0,
        "score_history": all_scores[::-1],
        "placements": placements,
        "sessions": len(set(g.session_id for g in games)),
    }


# ── Auth ─────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def seed_admin():
    admin = User.query.filter_by(username="flep98").first()
    if not admin:
        admin = User(username="flep98", is_admin=True)
        admin.set_password("1234")
        db.session.add(admin)
        db.session.commit()


# ── Backup ───────────────────────────────────────────────

def backup_database():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"bowling_{ts}.db")
    shutil.copy2(DB_PATH, dest)
    backups = sorted(os.listdir(BACKUP_DIR))
    while len(backups) > 30:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))


def auto_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        return
    backups = sorted(os.listdir(BACKUP_DIR))
    if backups:
        latest = backups[-1]
        try:
            ts_part = latest.replace("bowling_", "").replace(".db", "")
            last_time = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
            if datetime.now() - last_time < timedelta(days=1):
                return
        except ValueError:
            pass
    backup_database()


# ── Routes ───────────────────────────────────────────────

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if not current_user.is_admin:
        flash("Only the admin can create new accounts.", "danger")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")
        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return render_template("register.html")
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Account '{username}' created!", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")


# ── Admin: User Management ───────────────────────────────

@app.route("/admin/users")
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("Only the admin can manage users.", "danger")
        return redirect(url_for("dashboard"))
    users = User.query.order_by(User.username).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit_user(user_id):
    if not current_user.is_admin:
        flash("Only the admin can edit users.", "danger")
        return redirect(url_for("dashboard"))
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        is_admin = request.form.get("is_admin") == "on"

        if not username:
            flash("Username cannot be empty.", "danger")
        elif username != user.username and User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
        else:
            user.username = username
            user.is_admin = is_admin
            if password:
                if password != confirm:
                    flash("Passwords do not match.", "danger")
                    return render_template("edit_user.html", edit_user=user)
                user.set_password(password)
            db.session.commit()
            flash(f"User '{username}' updated.", "success")
            return redirect(url_for("admin_users"))
    return render_template("edit_user.html", edit_user=user)


@app.route("/admin/users/<int:user_id>/delete", methods=["GET", "POST"])
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        flash("Only the admin can delete users.", "danger")
        return redirect(url_for("dashboard"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for("admin_users"))
    if request.method == "POST":
        username = user.username
        db.session.delete(user)
        db.session.commit()
        flash(f"User '{username}' deleted.", "success")
        return redirect(url_for("admin_users"))
    return render_template("delete_user.html", del_user=user)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "username":
            new_username = request.form.get("username", "").strip()
            if not new_username:
                flash("Username cannot be empty.", "danger")
            elif new_username == current_user.username:
                flash("That's already your username.", "info")
            elif User.query.filter_by(username=new_username).first():
                flash("Username already taken.", "danger")
            else:
                current_user.username = new_username
                db.session.commit()
                flash("Username changed! ✅", "success")

        elif action == "password":
            old_pw = request.form.get("old_password", "")
            new_pw = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not current_user.check_password(old_pw):
                flash("Current password is wrong.", "danger")
            elif not new_pw:
                flash("New password cannot be empty.", "danger")
            elif new_pw != confirm:
                flash("Passwords do not match.", "danger")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash("Password changed! ✅", "success")

        return redirect(url_for("settings"))

    return render_template("settings.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    include_practice = request.args.get("practice") == "1"
    users = User.query.all()
    players = []
    for u in users:
        stats = compute_player_stats(u, include_practice=include_practice)
        players.append({"user": u, "stats": stats})
    players.sort(key=lambda p: p["stats"]["avg"], reverse=True)

    recent_sessions = (
        GameSession.query.order_by(
            GameSession.date.desc(), GameSession.created_at.desc()
        ).limit(10).all()
    )

    CHART_COLORS = ['#f5c842', '#6fcf97', '#eb5757', '#88c0f0', '#cd7f32', '#b0c4d8', '#e0b532', '#4a90d9', '#d94a8e', '#4ad9b5']
    chart_data = []
    for i, p in enumerate(players):
        if p["stats"]["score_history"]:
            chart_data.append({
                "name": p["user"].username,
                "scores": p["stats"]["score_history"],
                "color": CHART_COLORS[i % len(CHART_COLORS)],
            })

    return render_template(
        "dashboard.html",
        players=players,
        chart_data=chart_data,
        recent_sessions=recent_sessions,
        include_practice=include_practice,
    )


@app.route("/session/<int:session_id>")
@login_required
def view_session(session_id):
    sess = GameSession.query.get_or_404(session_id)
    return render_template("session.html", session=sess)


@app.route("/delete_game/<int:game_id>", methods=["POST"])
@login_required
def delete_game(game_id):
    game = Game.query.get_or_404(game_id)
    session_id = game.session_id
    sess = GameSession.query.get(session_id)
    if not sess:
        flash("Session not found.", "danger")
        return redirect(url_for("dashboard"))

    db.session.delete(game)
    db.session.flush()

    remaining = Game.query.filter_by(session_id=session_id).order_by(
        Game.total_score.desc()
    ).all()
    assign_ranks(remaining)

    db.session.commit()
    flash("Game deleted. ✅", "success")

    if remaining:
        return redirect(url_for("view_session", session_id=session_id))
    else:
        db.session.delete(sess)
        db.session.commit()
        flash("Session was empty and has been deleted.", "info")
        return redirect(url_for("dashboard"))


@app.route("/edit_game/<int:game_id>", methods=["GET", "POST"])
@login_required
def edit_game(game_id):
    game = Game.query.get_or_404(game_id)
    users = User.query.order_by(User.username).all()
    today_str = datetime.today().strftime("%Y-%m-%d")

    if request.method == "POST":
        date_str = request.form.get("date", "").strip()
        entry_mode = request.form.get("entry_mode", "frame")
        game_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str else game.session.date
        )

        game.session.date = game_date
        game.total_score = 0

        # Delete old frames
        for f in game.frames:
            db.session.delete(f)
        db.session.flush()

        if entry_mode == "quick":
            score_str = request.form.get(f"f_{game.user_id}_score", "0").strip()
            try:
                game.total_score = max(0, min(300, int(score_str)))
            except ValueError:
                flash("Invalid score.", "danger")
                return redirect(url_for("edit_game", game_id=game.id))
        else:
            frames = []
            for i in range(1, 11):
                r1_key = f"f{game.user_id}_{i}_r1"
                r2_key = f"f{game.user_id}_{i}_r2"
                r3_key = f"f{game.user_id}_{i}_r3"
                try:
                    r1 = max(0, min(10, int(request.form.get(r1_key, "0") or "0")))
                except ValueError:
                    flash("Invalid frame data.", "danger")
                    return redirect(url_for("edit_game", game_id=game.id))
                r2 = None
                if request.form.get(r2_key, "").strip():
                    r2 = max(0, min(10, int(request.form[r2_key])))
                r3 = None
                if request.form.get(r3_key, "").strip():
                    r3 = max(0, min(10, int(request.form[r3_key])))
                frames.append(Frame(game_id=game.id, frame=i, roll1=r1, roll2=r2, roll3=r3))
            db.session.add_all(frames)
            db.session.flush()
            full = Frame.query.filter_by(game_id=game.id).order_by(Frame.frame).all()
            game.total_score = bowling_score(full)

        # Re-rank all entries in the session
        all_entries = Game.query.filter_by(session_id=game.session_id).order_by(
            Game.total_score.desc()
        ).all()
        assign_ranks(all_entries)

        db.session.commit()
        flash("Game updated! ✅", "success")
        return redirect(url_for("view_session", session_id=game.session_id))

    # GET — pre-fill
    has_frames = bool(game.frames)
    return render_template(
        "add_game.html",
        today=game.session.date.strftime("%Y-%m-%d"),
        users=users,
        edit_game=game,
    )


@app.route("/add_game", methods=["GET", "POST"])
@login_required
def add_game():
    today_str = datetime.today().strftime("%Y-%m-%d")
    users = User.query.order_by(User.username).all()

    if request.method == "POST":
        date_str = request.form.get("date", "").strip()
        player_ids = request.form.getlist("player_ids")
        entry_mode = request.form.get("entry_mode", "frame")

        if not player_ids:
            flash("Select at least one player.", "danger")
            return render_template(
                "add_game.html", today=today_str, users=users
            )

        game_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date()
            if date_str else datetime.today().date()
        )

        session = GameSession(date=game_date)
        db.session.add(session)
        db.session.flush()

        entries = []
        for pid in player_ids:
            player = User.query.get(int(pid))
            if not player:
                continue

            if entry_mode == "quick":
                score_key = f"f_{pid}_score"
                score_str = request.form.get(score_key, "0").strip()
                if not score_str:
                    flash(f"Score required for {player.username}.", "danger")
                    db.session.rollback()
                    return render_template(
                        "add_game.html", today=today_str, users=users
                    )
                try:
                    score = max(0, min(300, int(score_str)))
                except ValueError:
                    flash(f"Invalid score for {player.username}.", "danger")
                    db.session.rollback()
                    return render_template(
                        "add_game.html", today=today_str, users=users
                    )
                is_practice = request.form.get("practice") == "1"
                game = Game(
                    user_id=player.id, total_score=score,
                    session_id=session.id, practice=is_practice,
                )
                db.session.add(game)
                entries.append(game)
            else:
                is_practice = request.form.get("practice") == "1"
                game = Game(
                    user_id=player.id, total_score=0,
                    session_id=session.id, practice=is_practice,
                )
                db.session.add(game)
                db.session.flush()

                frames = []
                for i in range(1, 11):
                    r1_key = f"f{pid}_{i}_r1"
                    r2_key = f"f{pid}_{i}_r2"
                    r3_key = f"f{pid}_{i}_r3"

                    try:
                        r1_str = request.form.get(r1_key, "0")
                        r1 = max(0, min(10, int(r1_str) if r1_str else 0))
                    except ValueError:
                        flash(f"Invalid score for {player.username}.", "danger")
                        db.session.rollback()
                        return render_template(
                            "add_game.html", today=today_str, users=users
                        )

                    r2 = None
                    if request.form.get(r2_key, "").strip():
                        try:
                            r2 = max(0, min(10, int(request.form[r2_key])))
                        except ValueError:
                            flash(f"Invalid score for {player.username}.", "danger")
                            db.session.rollback()
                            return render_template(
                                "add_game.html", today=today_str, users=users
                            )

                    r3 = None
                    if request.form.get(r3_key, "").strip():
                        try:
                            r3 = max(0, min(10, int(request.form[r3_key])))
                        except ValueError:
                            flash(f"Invalid score for {player.username}.", "danger")
                            db.session.rollback()
                            return render_template(
                                "add_game.html", today=today_str, users=users
                            )

                    frames.append(
                        Frame(
                            game_id=game.id, frame=i,
                            roll1=r1, roll2=r2, roll3=r3,
                        )
                    )

                db.session.add_all(frames)
                db.session.flush()
                full_frames = (
                    Frame.query.filter_by(game_id=game.id)
                    .order_by(Frame.frame).all()
                )
                game.total_score = bowling_score(full_frames)
                entries.append(game)

        assign_ranks(entries)

        db.session.commit()
        return redirect(url_for("view_session", session_id=session.id))

    return render_template("add_game.html", today=today_str, users=users)


@app.route("/backup")
@login_required
def backup_now():
    if not current_user.is_admin:
        flash("Only admin can create backups.", "danger")
        return redirect(url_for("dashboard"))
    backup_database()
    flash("Database backed up successfully! 💾", "success")
    return redirect(url_for("dashboard"))


@app.route("/backups")
@login_required
def list_backups():
    if not current_user.is_admin:
        flash("Only admin can access backups.", "danger")
        return redirect(url_for("dashboard"))
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = sorted(os.listdir(BACKUP_DIR), reverse=True)
    backups = []
    for f in files:
        path = os.path.join(BACKUP_DIR, f)
        if os.path.isfile(path):
            size = os.path.getsize(path)
            ts_part = f.replace("bowling_", "").replace(".db", "")
            try:
                label = datetime.strptime(ts_part, "%Y%m%d_%H%M%S").strftime(
                    "%b %d, %Y at %H:%M"
                )
            except ValueError:
                label = f
            backups.append({"file": f, "label": label, "size": size})
    return render_template("backups.html", backups=backups)


@app.route("/backup/<filename>")
@login_required
def download_backup(filename):
    if not current_user.is_admin:
        flash("Only admin can download backups.", "danger")
        return redirect(url_for("dashboard"))
    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(path):
        flash("Backup not found.", "danger")
        return redirect(url_for("list_backups"))
    return send_file(path, as_attachment=True, download_name=filename)


@app.route("/backup/<filename>/restore")
@login_required
def restore_backup(filename):
    if not current_user.is_admin:
        flash("Only admin can restore backups.", "danger")
        return redirect(url_for("dashboard"))
    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(path):
        flash("Backup not found.", "danger")
        return redirect(url_for("list_backups"))
    backup_database()
    shutil.copy2(path, DB_PATH)
    flash("Backup restored! Restart the app for changes to take effect. 💾", "success")
    return redirect(url_for("dashboard"))


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, msg="Something went wrong"), 500


def migrate_ranks():
    sessions = GameSession.query.all()
    for sess in sessions:
        games = Game.query.filter_by(session_id=sess.id).all()
        if games:
            assign_ranks(games)
    db.session.commit()

with app.app_context():
    db_exists = os.path.exists(DB_PATH)
    db.create_all()
    migrate_ranks()
    if not db_exists:
        seed_admin()
    auto_backup()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)
