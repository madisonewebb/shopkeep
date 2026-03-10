"""
Shopkeep web server.

Handles the user-facing setup flow:
  1. Landing page with "Add to Discord" invite link
  2. /connect/<setup_token> — user enters shop name, starts Etsy OAuth
  3. /callback/etsy       — Etsy redirects here after auth; stores tokens + shop_id

Run with:
    python -m src.web.app
"""

import base64
import hashlib
import os
import secrets
import time
import urllib.parse

import requests
from flask import Flask, redirect, render_template, request, url_for
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

# In-memory PKCE state: state_param -> {code_verifier, setup_token, shop_name}
# Only lives for the duration of one OAuth flow (minutes).
_pkce_state: dict[str, dict] = {}


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    invite_url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&permissions=2048"
        f"&scope=bot"
    )
    return render_template("index.html", invite_url=invite_url)


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
        shop_name = request.form.get("shop_name", "").strip()
        if not shop_name:
            return render_template("connect.html", setup_token=setup_token,
                                   guild_name=guild["guild_name"], error="Please enter your shop name.")

        code_verifier, code_challenge = _make_pkce_pair()
        state = secrets.token_urlsafe(16)
        _pkce_state[state] = {
            "code_verifier": code_verifier,
            "setup_token": setup_token,
            "shop_name": shop_name,
            "guild_id": guild["guild_id"],
        }

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

    return render_template("connect.html", setup_token=setup_token,
                           guild_name=guild["guild_name"], error=None)


@app.route("/callback/etsy")
def etsy_callback():
    state = request.args.get("state")
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return render_template("error.html", message=f"Etsy authorization denied: {error}")

    if not code or state not in _pkce_state:
        return render_template("error.html", message="Invalid OAuth callback. Please try again.")

    pkce = _pkce_state.pop(state)
    code_verifier = pkce["code_verifier"]
    guild_id = pkce["guild_id"]
    shop_name = pkce["shop_name"]

    # Exchange code for tokens
    resp = requests.post(
        ETSY_TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": ETSY_API_KEY,
            "redirect_uri": ETSY_REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier,
        },
    )
    if not resp.ok:
        return render_template("error.html", message="Token exchange failed. Please try again.")

    tokens = resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expires_at = int(time.time()) + tokens.get("expires_in", 3600)

    # Look up shop_id by name
    shop_resp = requests.get(
        f"{ETSY_API_BASE}/application/shops",
        headers={"x-api-key": f"{ETSY_API_KEY}:{ETSY_SHARED_SECRET}"},
        params={"shop_name": shop_name},
    )
    if not shop_resp.ok:
        return render_template("error.html", message="Could not find your Etsy shop. Please try again.")

    data = shop_resp.json()
    results = data.get("results") or ([data] if data.get("shop_id") else [])
    shop = next(
        (s for s in results if s.get("shop_name", "").lower() == shop_name.lower()),
        None,
    )
    if not shop:
        return render_template(
            "error.html",
            message=f"Could not find a shop named \"{shop_name}\". Check the spelling and try again.",
        )

    shop_id = shop["shop_id"]

    # Persist to DB
    webdb.save_guild_tokens(guild_id, access_token, refresh_token, expires_at)
    webdb.update_guild_etsy(guild_id, shop_id)

    return render_template("success.html", shop_name=shop["shop_name"])


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
