"""
Shopkeep Setup — Connect your Etsy shop to Discord.

This script walks you through connecting your Etsy account to Shopkeep.
You only need to run this once. When it's done, your bot is ready to start.

Usage:
    python scripts/etsy_auth.py
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
API_BASE = "https://openapi.etsy.com/v3"

SCOPES = ["transactions_r", "listings_r", "shops_r", "profile_r"]

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_step(n: int, text: str):
    print(f"\n[{n}] {text}")
    print("    " + "─" * (len(text) + 2))


def _make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _user_id_from_token(access_token: str) -> str | None:
    """Etsy embeds the user ID as the numeric prefix of the access token."""
    prefix = access_token.split(".")[0]
    return prefix if prefix.isdigit() else None


# ── Local callback server ─────────────────────────────────────────────────────

_callback_result: dict = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Ignore secondary browser requests (favicon, etc.) once we have a result
        if _callback_result:
            self.send_response(200)
            self.end_headers()
            return

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Ignore requests that aren't the OAuth callback (no code or error param)
        if not params:
            self.send_response(200)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if "code" in params:
            _callback_result["code"] = params["code"][0]
            _callback_result["state"] = params.get("state", [None])[0]
            self.wfile.write(
                b"<h2 style='font-family:sans-serif;margin:40px'>Connected! "
                b"You can close this tab and return to the terminal.</h2>"
            )
        elif "error" in params:
            _callback_result["error"] = params["error"][0]
            self.wfile.write(
                f"<h2 style='font-family:sans-serif;margin:40px'>Error: {params['error'][0]}</h2>".encode()
            )

    def log_message(self, *_):
        pass


def _start_callback_server(port: int) -> http.server.HTTPServer:
    server = http.server.HTTPServer(("localhost", port), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ── OAuth flow ────────────────────────────────────────────────────────────────

def run_oauth_flow(api_key: str, redirect_uri: str) -> dict:
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or 80

    code_verifier, code_challenge = _make_pkce_pair()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": api_key,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    server = _start_callback_server(port)
    print(f"    Opening your browser to Etsy...")
    webbrowser.open(auth_url)
    print(f"    If the browser didn't open, visit this URL:")
    print(f"    {auth_url}")

    deadline = time.time() + 120
    while not _callback_result and time.time() < deadline:
        time.sleep(0.2)
    server.shutdown()

    if "error" in _callback_result:
        raise RuntimeError(f"Etsy returned an error: {_callback_result['error']}")
    if "code" not in _callback_result:
        raise RuntimeError("Timed out waiting for Etsy authorization (2 min limit).")
    if _callback_result.get("state") != state:
        raise RuntimeError("Security check failed (state mismatch). Please try again.")

    code = _callback_result["code"]
    print("    Authorization approved! Fetching tokens...")

    resp = requests.post(
        TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": api_key,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        },
    )
    resp.raise_for_status()
    return resp.json()


# ── Shop lookup ───────────────────────────────────────────────────────────────

def get_shop(access_token: str, api_key: str, shared_secret: str, shop_name: str) -> dict | None:
    """Look up a shop by name using the public shops endpoint."""
    resp = requests.get(
        f"{API_BASE}/application/shops",
        headers={"x-api-key": f"{api_key}:{shared_secret}"},
        params={"shop_name": shop_name},
    )
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results") or ([data] if data.get("shop_id") else [])
    for shop in results:
        if shop.get("shop_name", "").lower() == shop_name.lower():
            return shop
    return None


# ── .env writer ───────────────────────────────────────────────────────────────

def update_env(updates: dict[str, str]) -> None:
    """Write or update key=value pairs in the .env file."""
    env_path = os.path.abspath(ENV_PATH)

    # Read existing lines
    existing: list[str] = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            existing = f.readlines()

    # Update in-place for keys that already exist
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in existing:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0]
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append any keys that weren't already present
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Shopkeep Setup — Connect your Etsy shop to Discord")
    print("=" * 60)
    print("""
This script connects your Etsy shop to the Shopkeep Discord bot.
You'll need two things from your Etsy Developer account:
  - API Key (also called "keystring")
  - Redirect URI registered in your app (e.g. http://localhost:3000/callback)

You can find these at: https://www.etsy.com/developers/your-apps
""")

    # ── Step 1: Collect credentials ───────────────────────────────────────────
    _print_step(1, "Enter your Etsy API credentials")

    api_key = os.getenv("ETSY_API_KEY") or input("    Etsy API Key (keystring): ").strip()
    if not api_key:
        raise SystemExit("API key is required.")

    shared_secret = os.getenv("ETSY_SHARED_SECRET") or input("    Etsy Shared Secret: ").strip()
    if not shared_secret:
        raise SystemExit("Shared secret is required.")

    redirect_uri = (
        os.getenv("ETSY_REDIRECT_URI") or
        input("    Redirect URI [http://localhost:3000/callback]: ").strip() or
        "http://localhost:3000/callback"
    )

    shop_name = (
        os.getenv("ETSY_SHOP_NAME") or
        input("    Your Etsy shop name (e.g. CastilloCurios): ").strip()
    )
    if not shop_name:
        raise SystemExit("Shop name is required.")

    # ── Step 2: OAuth ─────────────────────────────────────────────────────────
    _print_step(2, "Authorize Shopkeep with your Etsy account")
    print("    A browser window will open. Log in to Etsy and click 'Allow Access'.")
    input("    Press Enter to continue...")

    tokens = run_oauth_flow(api_key, redirect_uri)

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    expires_in = tokens.get("expires_in", 3600)
    expires_at = int(time.time()) + expires_in

    print(f"    Tokens received (expires in {expires_in // 60} minutes, auto-refreshed by bot).")

    # ── Step 3: Shop lookup ───────────────────────────────────────────────────
    _print_step(3, f"Looking up shop '{shop_name}'")

    shop = get_shop(access_token, api_key, shared_secret, shop_name)
    if not shop:
        print(f"    WARNING: Could not find a shop named '{shop_name}' in your account.")
        print(f"    Double-check the spelling and try again, or manually set ETSY_SHOP_ID in .env.")
        shop_id = None
    else:
        shop_id = shop["shop_id"]
        print(f"    Found: {shop['shop_name']} (ID: {shop_id})")

    # ── Step 4: Write .env ────────────────────────────────────────────────────
    _print_step(4, "Saving configuration to .env")

    env_updates = {
        "ETSY_API_KEY": api_key,
        "ETSY_REDIRECT_URI": redirect_uri,
        "ETSY_ACCESS_TOKEN": access_token,
        "ETSY_REFRESH_TOKEN": refresh_token,
    }
    if shop_id:
        env_updates["ETSY_SHOP_ID"] = str(shop_id)

    update_env(env_updates)
    print(f"    Saved to {os.path.abspath(ENV_PATH)}")

    # Also write token cache for reference
    cache_path = os.path.join(os.path.dirname(__file__), ".etsy_tokens.json")
    with open(cache_path, "w") as f:
        json.dump(
            {"access_token": access_token, "refresh_token": refresh_token,
             "expires_at": expires_at, "shop_id": shop_id},
            f, indent=2,
        )

    # ── Done ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print("""
Your Etsy shop is now connected. Next steps:

  1. Make sure DISCORD_BOT_TOKEN and ORDER_CHANNEL_ID are set in .env
  2. Start the bot:  python -m src.bot.discord_bot
     (or with Tilt:  tilt up)

The bot will automatically refresh your Etsy tokens — you won't
need to run this script again.
""")


if __name__ == "__main__":
    main()
