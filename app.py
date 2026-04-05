import os
import sqlite3
from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database.betting_db import DATABASE_PATH, SUPPORTED_LANGS, TRANSLATIONS, BettingDB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BETTING_DB = BettingDB()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("BETTING_APP_SECRET", "dev-secret-change-me")

def get_lang() -> str:
    lang = session.get("lang", "vi")
    return lang if lang in SUPPORTED_LANGS else "vi"


def t(key: str, **kwargs) -> str:
    lang = get_lang()
    text = TRANSLATIONS.get(lang, {}).get(key)
    if text is None:
        text = TRANSLATIONS["en"].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text


@app.before_request
def set_default_language():
    if session.get("lang") not in SUPPORTED_LANGS:
        session["lang"] = "vi"


@app.teardown_appcontext
def close_db(_exception):
    BETTING_DB.close_db()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            flash(t("flash.sign_in_required"), "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        user = get_current_user()
        if user is None or user["role"] != "admin":
            flash(t("flash.admin_only"), "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def normal_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        user = get_current_user()
        if user is None or user["role"] != "user":
            flash(t("flash.normal_only"), "danger")
            return redirect(url_for("admin_dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def get_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    return BETTING_DB.get_db().execute(
        """
        SELECT id, username, balance, created_at, role, full_name, email, phone
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


@app.context_processor
def inject_globals():
    return {
        "current_user": get_current_user(),
        "now_iso": datetime.now(UTC).isoformat(),
        "current_lang": get_lang(),
        "t": t,
    }


@app.template_filter("money")
def format_money(value):
    return f"{float(value):,.2f}"


@app.template_filter("kickoff")
def format_kickoff(value):
    return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M UTC")


@app.route("/")
def index():
    featured_matches = BETTING_DB.get_db().execute(
        """
        SELECT *
        FROM matches
        ORDER BY kickoff_at ASC
        LIMIT 3
        """
    ).fetchall()
    return render_template("index.html", featured_matches=featured_matches)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        user = get_current_user()
        if user and user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if len(username) < 3:
            flash(t("flash.username_min"), "danger")
        elif len(password) < 6:
            flash(t("flash.password_min"), "danger")
        else:
            db = BETTING_DB.get_db()
            existing_user = db.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if existing_user:
                flash(t("flash.username_taken"), "danger")
            else:
                admin_count = db.execute(
                    "SELECT COUNT(*) AS total FROM users WHERE role = 'admin'"
                ).fetchone()["total"]
                role = "admin" if admin_count == 0 else "user"

                db.execute(
                    "INSERT INTO users (username, password_hash, created_at, role) VALUES (?, ?, ?, ?)",
                    (
                        username,
                        generate_password_hash(password),
                        datetime.now(UTC).replace(microsecond=0).isoformat(),
                        role,
                    ),
                )
                db.commit()
                flash(t("flash.account_created"), "success")
                if role == "admin":
                    flash(t("flash.first_admin_assigned"), "info")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        user = get_current_user()
        if user and user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = BETTING_DB.get_db().execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash(t("flash.invalid_credentials"), "danger")
        else:
            selected_lang = session.get("lang", "vi")
            session.clear()
            session["user_id"] = user["id"]
            session["lang"] = selected_lang if selected_lang in SUPPORTED_LANGS else "vi"
            flash(t("flash.login_success"), "success")
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    selected_lang = session.get("lang", "vi")
    session.clear()
    session["lang"] = selected_lang if selected_lang in SUPPORTED_LANGS else "vi"
    flash(t("flash.logout_success"), "info")
    return redirect(url_for("index"))


@app.route("/language/<lang>")
def set_language(lang: str):
    session["lang"] = lang if lang in SUPPORTED_LANGS else "vi"
    next_url = request.args.get("next", "")
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(request.referrer or url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = BETTING_DB.get_db()
    user = get_current_user()

    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))

    upcoming_matches = db.execute(
        """
        SELECT *
        FROM matches
        WHERE status = 'scheduled'
        ORDER BY kickoff_at ASC
        """
    ).fetchall()

    recent_bets = db.execute(
        """
        SELECT bets.*, matches.home_team, matches.away_team, matches.score_home, matches.score_away, matches.result
        FROM bets
        JOIN matches ON matches.id = bets.match_id
        WHERE bets.user_id = ?
        ORDER BY bets.placed_at DESC
        LIMIT 8
        """,
        (user["id"],),
    ).fetchall()

    stats = db.execute(
        """
        SELECT
            COUNT(*) AS total_bets,
            COALESCE(SUM(stake), 0) AS total_staked,
            COALESCE(SUM(CASE WHEN status = 'won' THEN payout ELSE 0 END), 0) AS total_returns,
            COALESCE(SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END), 0) AS wins
        FROM bets
        WHERE user_id = ?
        """,
        (user["id"],),
    ).fetchone()

    return render_template(
        "dashboard.html",
        user=user,
        upcoming_matches=upcoming_matches,
        recent_bets=recent_bets,
        stats=stats,
    )


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = BETTING_DB.get_db()
    user = get_current_user()
    matches = db.execute(
        """
        SELECT *
        FROM matches
        ORDER BY kickoff_at ASC
        """
    ).fetchall()
    users = db.execute(
        """
        SELECT id, username, role, balance, full_name, email, phone, created_at
        FROM users
        ORDER BY id ASC
        """
    ).fetchall()

    return render_template(
        "admin_dashboard.html",
        user=user,
        matches=matches,
        users=users,
    )


@app.route("/bet", methods=["POST"])
@normal_required
def place_bet():
    db = BETTING_DB.get_db()
    user = get_current_user()
    outcome = request.form.get("outcome", "")

    try:
        match_id = int(request.form.get("match_id", "0"))
        stake = round(float(request.form.get("stake", "0")), 2)
    except ValueError:
        flash(t("flash.valid_stake"), "danger")
        return redirect(url_for("dashboard"))

    if outcome not in {"home", "draw", "away"}:
        flash(t("flash.valid_outcome"), "danger")
        return redirect(url_for("dashboard"))

    match = db.execute(
        "SELECT * FROM matches WHERE id = ?",
        (match_id,),
    ).fetchone()

    if match is None or match["status"] != "scheduled":
        flash(t("flash.match_unavailable"), "danger")
        return redirect(url_for("dashboard"))

    if datetime.fromisoformat(match["kickoff_at"]) <= datetime.now(UTC):
        flash(t("flash.betting_closed"), "danger")
        return redirect(url_for("dashboard"))

    if stake < 5:
        flash(t("flash.minimum_stake"), "danger")
        return redirect(url_for("dashboard"))

    if stake > user["balance"]:
        flash(t("flash.insufficient_balance"), "danger")
        return redirect(url_for("dashboard"))

    odds_map = {
        "home": match["home_odds"],
        "draw": match["draw_odds"],
        "away": match["away_odds"],
    }
    placed_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    db.execute(
        """
        INSERT INTO bets (user_id, match_id, outcome, odds, stake, placed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user["id"], match_id, outcome, odds_map[outcome], stake, placed_at),
    )
    db.execute(
        "UPDATE users SET balance = balance - ? WHERE id = ?",
        (stake, user["id"]),
    )
    db.commit()

    flash(t("flash.bet_placed"), "success")
    return redirect(url_for("dashboard"))


@app.route("/profile/update", methods=["POST"])
@normal_required
def update_profile():
    user = get_current_user()
    db = BETTING_DB.get_db()
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()

    if email and "@" not in email:
        flash(t("flash.invalid_email"), "danger")
        return redirect(url_for("dashboard"))

    db.execute(
        """
        UPDATE users
        SET full_name = ?, email = ?, phone = ?
        WHERE id = ?
        """,
        (full_name or None, email or None, phone or None, user["id"]),
    )
    db.commit()
    flash(t("flash.profile_updated"), "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/matches/update", methods=["POST"])
@admin_required
def admin_update_match():
    db = BETTING_DB.get_db()
    try:
        match_id = int(request.form.get("match_id", "0"))
        home_odds = float(request.form.get("home_odds", "0"))
        draw_odds = float(request.form.get("draw_odds", "0"))
        away_odds = float(request.form.get("away_odds", "0"))
    except ValueError:
        flash(t("flash.invalid_match_data"), "danger")
        return redirect(url_for("admin_dashboard"))

    home_team = request.form.get("home_team", "").strip()
    away_team = request.form.get("away_team", "").strip()
    kickoff_at = request.form.get("kickoff_at", "").strip()
    stadium = request.form.get("stadium", "").strip()
    status = request.form.get("status", "scheduled").strip()

    if not home_team or not away_team or not stadium:
        flash(t("flash.invalid_match_data"), "danger")
        return redirect(url_for("admin_dashboard"))

    if status not in {"scheduled", "settled"}:
        flash(t("flash.invalid_match_data"), "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        kickoff_iso = datetime.fromisoformat(kickoff_at).replace(microsecond=0).isoformat()
    except ValueError:
        flash(t("flash.invalid_match_data"), "danger")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        """
        UPDATE matches
        SET home_team = ?, away_team = ?, kickoff_at = ?, stadium = ?,
            home_odds = ?, draw_odds = ?, away_odds = ?, status = ?
        WHERE id = ?
        """,
        (
            home_team,
            away_team,
            kickoff_iso,
            stadium,
            home_odds,
            draw_odds,
            away_odds,
            status,
            match_id,
        ),
    )
    db.commit()
    flash(t("flash.match_updated"), "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/update", methods=["POST"])
@admin_required
def admin_update_user():
    db = BETTING_DB.get_db()
    current = get_current_user()

    try:
        target_user_id = int(request.form.get("user_id", "0"))
        balance = round(float(request.form.get("balance", "0")), 2)
    except ValueError:
        flash(t("flash.invalid_user_data"), "danger")
        return redirect(url_for("admin_dashboard"))

    role = request.form.get("role", "user").strip()
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()

    if role not in {"admin", "user"} or balance < 0:
        flash(t("flash.invalid_user_data"), "danger")
        return redirect(url_for("admin_dashboard"))

    if email and "@" not in email:
        flash(t("flash.invalid_email"), "danger")
        return redirect(url_for("admin_dashboard"))

    if target_user_id == current["id"] and role != "admin":
        flash(t("flash.cannot_demote_self"), "danger")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        """
        UPDATE users
        SET role = ?, balance = ?, full_name = ?, email = ?, phone = ?
        WHERE id = ?
        """,
        (role, balance, full_name or None, email or None, phone or None, target_user_id),
    )
    db.commit()
    flash(t("flash.user_updated"), "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/history")
@normal_required
def history():
    bets = BETTING_DB.get_db().execute(
        """
        SELECT bets.*, matches.home_team, matches.away_team, matches.score_home, matches.score_away, matches.result
        FROM bets
        JOIN matches ON matches.id = bets.match_id
        WHERE bets.user_id = ?
        ORDER BY bets.placed_at DESC
        """,
        (session["user_id"],),
    ).fetchall()
    return render_template("history.html", bets=bets)


@app.route("/settle", methods=["POST"])
@normal_required
def settle():
    settled_count = BETTING_DB.settle_due_matches()
    if settled_count:
        flash(t("flash.settled_matches", count=settled_count), "success")
    else:
        flash(t("flash.no_settle_ready"), "info")
    return redirect(url_for("dashboard"))


BETTING_DB.init_db()
BETTING_DB.seed_matches()


if __name__ == "__main__":
    app.run(debug=True)