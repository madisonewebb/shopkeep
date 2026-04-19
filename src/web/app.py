"""
Shopkeep web server.

Handles the user-facing setup flow:
  1. Landing page with "Add to Discord" invite link
  2. /connect/<setup_token> — user clicks "Authorize with Etsy" to start OAuth
  3. /callback/etsy       — Etsy redirects here after auth; stores tokens + shop_id

Run with:
    python -m src.web.app
"""

import base64
import hashlib
import mimetypes
import os
import secrets
import time
import urllib.parse

mimetypes.add_type('font/otf', '.otf')

import requests
from flask import Flask, redirect, render_template, request
from dotenv import load_dotenv

from src.web import db as webdb

load_dotenv()

app = Flask(__name__)

ETSY_API_KEY = os.environ["ETSY_API_KEY"]
ETSY_SHARED_SECRET = os.environ["ETSY_SHARED_SECRET"]
ETSY_REDIRECT_URI = os.environ["ETSY_WEB_REDIRECT_URI"]
DISCORD_CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
WEB_BASE_URL = os.environ["WEB_BASE_URL"]

ETSY_AUTH_URL = "https://www.etsy.com/oauth/connect"
ETSY_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
ETSY_API_BASE = "https://openapi.etsy.com/v3"

ETSY_SCOPES = "transactions_r listings_r shops_r profile_r"

PKCE_STATE_TTL = 600  # 10 minutes

webdb.init_pkce_table()


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _user_id_from_token(access_token: str) -> str | None:
    """Etsy embeds the user ID as the numeric prefix of the access token."""
    prefix = access_token.split(".")[0]
    return prefix if prefix.isdigit() else None


# ── Routes ────────────────────────────────────────────────────────────────────

def _invite_url() -> str:
    return (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&permissions=19456"
        f"&scope=bot%20applications.commands"
    )


@app.route("/")
def index():
    return render_template("index.html", invite_url=_invite_url())


@app.route("/connect/<setup_token>", methods=["GET", "POST"])
def connect(setup_token: str):
    guild = webdb.get_guild_by_setup_token(setup_token)

    if not guild:
        return render_template("error.html", message="This setup link is invalid.")

    if guild["setup_token_exp"] and guild["setup_token_exp"] < time.time():
        return render_template("error.html", message="This setup link has expired. Use !status in Discord to get a new one.")

    if guild["etsy_shop_id"]:
        return render_template("error.html", message="This server already has an Etsy shop connected.")

    if request.method == "POST":
        code_verifier, code_challenge = _make_pkce_pair()
        state = secrets.token_urlsafe(16)
        expires_at = int(time.time()) + PKCE_STATE_TTL

        webdb.save_pkce_state(state, code_verifier, setup_token, guild["guild_id"], expires_at)

        params = {
            "response_type": "code",
            "client_id": ETSY_API_KEY,
            "redirect_uri": ETSY_REDIRECT_URI,
            "scope": ETSY_SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return redirect(ETSY_AUTH_URL + "?" + urllib.parse.urlencode(params))

    return render_template("connect.html", setup_token=setup_token, guild_name=guild["guild_name"])


@app.route("/callback/etsy")
def etsy_callback():
    state = request.args.get("state")
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return render_template("error.html", message=f"Etsy authorization denied: {error}")

    pkce = webdb.get_pkce_state(state) if state else None
    if not code or not pkce:
        return render_template("error.html", message="Invalid OAuth callback. Please try again.")

    webdb.delete_pkce_state(state)

    # Exchange code for tokens
    resp = requests.post(
        ETSY_TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": ETSY_API_KEY,
            "redirect_uri": ETSY_REDIRECT_URI,
            "code": code,
            "code_verifier": pkce["code_verifier"],
        },
    )
    if not resp.ok:
        return render_template("error.html", message="Token exchange failed. Please try again.")

    tokens = resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expires_at = int(time.time()) + tokens.get("expires_in", 3600)

    # Look up the authenticated user's own shop — verifies ownership
    user_id = _user_id_from_token(access_token)
    if not user_id:
        return render_template("error.html", message="Could not determine your Etsy user ID. Please try again.")

    shop_resp = requests.get(
        f"{ETSY_API_BASE}/application/users/{user_id}/shops",
        headers={
            "x-api-key": f"{ETSY_API_KEY}:{ETSY_SHARED_SECRET}",
            "Authorization": f"Bearer {access_token}",
        },
    )
    if not shop_resp.ok:
        return render_template("error.html", message="Could not retrieve your Etsy shop. Make sure your account has an active shop.")

    data = shop_resp.json()
    results = data.get("results") or ([data] if data.get("shop_id") else [])
    if not results:
        return render_template("error.html", message="No Etsy shop found on your account.")

    shop = results[0]
    shop_id = shop["shop_id"]

    # Persist to DB
    webdb.save_guild_tokens(pkce["guild_id"], access_token, refresh_token, expires_at)
    webdb.update_guild_etsy(pkce["guild_id"], shop_id)

    return render_template("success.html", shop_name=shop["shop_name"])


@app.route("/commands")
def commands():
    return render_template("commands.html", invite_url=_invite_url())


@app.route("/about")
def about():
    return render_template("about.html", invite_url=_invite_url())


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", invite_url=_invite_url())


@app.route("/terms")
def terms():
    return render_template("terms.html", invite_url=_invite_url())


@app.route("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
