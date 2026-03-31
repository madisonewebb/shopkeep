"""
SQLite persistence layer for Shopkeep bot.
Stores shops, listings, receipts, and per-guild Etsy connections.
"""

import json
import time
from contextlib import asynccontextmanager

import aiosqlite

# Set by discord_bot.py before init_db() is called
DB_PATH: str = "./shopkeep.db"

_CREATE_GUILDS = """
CREATE TABLE IF NOT EXISTS guilds (
    guild_id         INTEGER PRIMARY KEY,
    guild_name       TEXT,
    etsy_shop_id     INTEGER,
    order_channel_id INTEGER,
    setup_token      TEXT    UNIQUE,
    setup_token_exp  INTEGER,
    connected_at     INTEGER,
    created_at       INTEGER NOT NULL
)
"""

_CREATE_ETSY_TOKENS = """
CREATE TABLE IF NOT EXISTS etsy_tokens (
    guild_id      INTEGER PRIMARY KEY REFERENCES guilds(guild_id),
    access_token  TEXT    NOT NULL,
    refresh_token TEXT    NOT NULL,
    expires_at    INTEGER NOT NULL
)
"""

_CREATE_PKCE_STATE = """
CREATE TABLE IF NOT EXISTS pkce_state (
    state         TEXT    PRIMARY KEY,
    code_verifier TEXT    NOT NULL,
    setup_token   TEXT    NOT NULL,
    guild_id      INTEGER NOT NULL,
    expires_at    INTEGER NOT NULL
)
"""

_CREATE_SHOPS = """
CREATE TABLE IF NOT EXISTS shops (
    shop_id                   INTEGER PRIMARY KEY,
    shop_name                 TEXT    NOT NULL,
    user_id                   INTEGER NOT NULL,
    title                     TEXT,
    announcement              TEXT,
    currency_code             TEXT    NOT NULL DEFAULT 'USD',
    is_vacation               INTEGER NOT NULL DEFAULT 0,
    listing_active_count      INTEGER,
    digital_listing_count     INTEGER,
    login_name                TEXT,
    accepts_custom_requests   INTEGER DEFAULT 0,
    url                       TEXT,
    num_favorers              INTEGER DEFAULT 0,
    languages                 TEXT,
    shop_location_country_iso TEXT,
    create_date               INTEGER,
    fetched_at                INTEGER NOT NULL
)
"""

_CREATE_LISTINGS = """
CREATE TABLE IF NOT EXISTS listings (
    listing_id              INTEGER PRIMARY KEY,
    shop_id                 INTEGER NOT NULL REFERENCES shops(shop_id),
    user_id                 INTEGER NOT NULL,
    title                   TEXT    NOT NULL,
    description             TEXT,
    state                   TEXT    NOT NULL DEFAULT 'active',
    quantity                INTEGER NOT NULL DEFAULT 0,
    url                     TEXT,
    num_favorers            INTEGER DEFAULT 0,
    is_customizable         INTEGER DEFAULT 0,
    is_personalizable       INTEGER DEFAULT 0,
    listing_type            TEXT,
    tags                    TEXT,
    materials               TEXT,
    price_amount            INTEGER NOT NULL,
    price_divisor           INTEGER NOT NULL DEFAULT 100,
    price_currency_code     TEXT    NOT NULL DEFAULT 'USD',
    views                   INTEGER DEFAULT 0,
    is_digital              INTEGER DEFAULT 0,
    who_made                TEXT,
    when_made               TEXT,
    creation_timestamp      INTEGER,
    last_modified_timestamp INTEGER,
    fetched_at              INTEGER NOT NULL
)
"""

_CREATE_RECEIPTS = """
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id            INTEGER PRIMARY KEY,
    shop_id               INTEGER NOT NULL REFERENCES shops(shop_id),
    receipt_type          INTEGER NOT NULL DEFAULT 0,
    seller_user_id        INTEGER NOT NULL,
    buyer_user_id         INTEGER,
    buyer_email           TEXT,
    name                  TEXT,
    city                  TEXT,
    state                 TEXT,
    zip                   TEXT,
    country_iso           TEXT,
    status                TEXT    NOT NULL,
    payment_method        TEXT,
    is_paid               INTEGER NOT NULL DEFAULT 0,
    is_shipped            INTEGER NOT NULL DEFAULT 0,
    is_gift               INTEGER NOT NULL DEFAULT 0,
    gift_message          TEXT,
    grandtotal_amount     INTEGER NOT NULL,
    grandtotal_divisor    INTEGER NOT NULL DEFAULT 100,
    grandtotal_currency   TEXT    NOT NULL DEFAULT 'USD',
    subtotal_amount       INTEGER,
    total_shipping_amount INTEGER,
    total_tax_amount      INTEGER,
    discount_amount       INTEGER DEFAULT 0,
    create_timestamp      INTEGER NOT NULL,
    update_timestamp      INTEGER,
    fetched_at            INTEGER NOT NULL,
    notified_at           INTEGER
)
"""


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(_CREATE_GUILDS)
        await db.execute(_CREATE_ETSY_TOKENS)
        await db.execute(_CREATE_PKCE_STATE)
        await db.execute(_CREATE_SHOPS)
        await db.execute(_CREATE_LISTINGS)
        await db.execute(_CREATE_RECEIPTS)
        await db.commit()


@asynccontextmanager
async def get_db():
    """Open a WAL-mode connection with foreign keys enabled and Row factory set."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = aiosqlite.Row
        yield conn


# ── Guild helpers ─────────────────────────────────────────────────────────────

async def create_guild(
    db: aiosqlite.Connection,
    guild_id: int,
    guild_name: str,
    setup_token: str,
    setup_token_exp: int,
) -> None:
    """Insert a new guild row (ignores if already exists)."""
    await db.execute(
        """
        INSERT OR IGNORE INTO guilds (guild_id, guild_name, setup_token, setup_token_exp, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (guild_id, guild_name, setup_token, setup_token_exp, int(time.time())),
    )


async def get_guild(db: aiosqlite.Connection, guild_id: int) -> aiosqlite.Row | None:
    cursor = await db.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,))
    return await cursor.fetchone()


async def get_guild_by_setup_token(
    db: aiosqlite.Connection, setup_token: str
) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT * FROM guilds WHERE setup_token = ?", (setup_token,)
    )
    return await cursor.fetchone()


async def get_connected_guilds(db: aiosqlite.Connection) -> list:
    """Return all guilds that have a connected Etsy shop and an order channel set."""
    cursor = await db.execute(
        """
        SELECT * FROM guilds
        WHERE etsy_shop_id IS NOT NULL AND order_channel_id IS NOT NULL
        """
    )
    return await cursor.fetchall()


async def refresh_setup_token(
    db: aiosqlite.Connection, guild_id: int, setup_token: str, setup_token_exp: int
) -> None:
    await db.execute(
        "UPDATE guilds SET setup_token = ?, setup_token_exp = ? WHERE guild_id = ?",
        (setup_token, setup_token_exp, guild_id),
    )


async def update_guild_etsy(
    db: aiosqlite.Connection, guild_id: int, etsy_shop_id: int
) -> None:
    """Mark a guild's Etsy shop as connected."""
    await db.execute(
        """
        UPDATE guilds
        SET etsy_shop_id = ?, connected_at = ?, setup_token = NULL, setup_token_exp = NULL
        WHERE guild_id = ?
        """,
        (etsy_shop_id, int(time.time()), guild_id),
    )


async def update_guild_channel(
    db: aiosqlite.Connection, guild_id: int, channel_id: int
) -> None:
    await db.execute(
        "UPDATE guilds SET order_channel_id = ? WHERE guild_id = ?",
        (channel_id, guild_id),
    )


# ── Etsy token helpers ────────────────────────────────────────────────────────

async def get_guild_tokens(
    db: aiosqlite.Connection, guild_id: int
) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT * FROM etsy_tokens WHERE guild_id = ?", (guild_id,)
    )
    return await cursor.fetchone()


async def save_guild_tokens(
    db: aiosqlite.Connection,
    guild_id: int,
    access_token: str,
    refresh_token: str,
    expires_at: int,
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO etsy_tokens (guild_id, access_token, refresh_token, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (guild_id, access_token, refresh_token, expires_at),
    )
    await db.commit()


# ── PKCE state helpers ────────────────────────────────────────────────────────

async def save_pkce_state(
    db: aiosqlite.Connection,
    state: str,
    code_verifier: str,
    setup_token: str,
    guild_id: int,
    expires_at: int,
) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO pkce_state (state, code_verifier, setup_token, guild_id, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (state, code_verifier, setup_token, guild_id, expires_at),
    )
    await db.execute("DELETE FROM pkce_state WHERE expires_at <= ?", (int(time.time()),))


async def get_pkce_state(db: aiosqlite.Connection, state: str) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT * FROM pkce_state WHERE state = ? AND expires_at > ?",
        (state, int(time.time())),
    )
    return await cursor.fetchone()


async def delete_pkce_state(db: aiosqlite.Connection, state: str) -> None:
    await db.execute("DELETE FROM pkce_state WHERE state = ?", (state,))


# ── Shop / listing / receipt helpers ─────────────────────────────────────────

async def upsert_shop(db: aiosqlite.Connection, shop: dict) -> None:
    await db.execute(
        """
        INSERT OR REPLACE INTO shops (
            shop_id, shop_name, user_id, title, announcement, currency_code,
            is_vacation, listing_active_count, digital_listing_count, login_name,
            accepts_custom_requests, url, num_favorers, languages,
            shop_location_country_iso, create_date, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shop["shop_id"],
            shop["shop_name"],
            shop["user_id"],
            shop.get("title"),
            shop.get("announcement"),
            shop.get("currency_code", "USD"),
            1 if shop.get("is_vacation") else 0,
            shop.get("listing_active_count"),
            shop.get("digital_listing_count"),
            shop.get("login_name"),
            1 if shop.get("accepts_custom_requests") else 0,
            shop.get("url"),
            shop.get("num_favorers", 0),
            json.dumps(shop.get("languages", [])),
            shop.get("shop_location_country_iso"),
            shop.get("create_date"),
            int(time.time()),
        ),
    )


async def upsert_listing(db: aiosqlite.Connection, listing: dict) -> None:
    price = listing.get("price", {})
    await db.execute(
        """
        INSERT OR REPLACE INTO listings (
            listing_id, shop_id, user_id, title, description, state, quantity,
            url, num_favorers, is_customizable, is_personalizable, listing_type,
            tags, materials, price_amount, price_divisor, price_currency_code,
            views, is_digital, who_made, when_made, creation_timestamp,
            last_modified_timestamp, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            listing["listing_id"],
            listing["shop_id"],
            listing["user_id"],
            listing["title"],
            listing.get("description"),
            listing.get("state", "active"),
            listing.get("quantity", 0),
            listing.get("url"),
            listing.get("num_favorers", 0),
            1 if listing.get("is_customizable") else 0,
            1 if listing.get("is_personalizable") else 0,
            listing.get("listing_type"),
            json.dumps(listing.get("tags", [])),
            json.dumps(listing.get("materials", [])),
            price.get("amount", 0),
            price.get("divisor", 100),
            price.get("currency_code", "USD"),
            listing.get("views", 0),
            1 if listing.get("is_digital") else 0,
            listing.get("who_made"),
            listing.get("when_made"),
            listing.get("creation_timestamp"),
            listing.get("last_modified_timestamp"),
            int(time.time()),
        ),
    )


async def upsert_listings(db: aiosqlite.Connection, listings: list) -> None:
    for listing in listings:
        await upsert_listing(db, listing)


async def upsert_receipt(
    db: aiosqlite.Connection, receipt: dict, already_seen: bool = False
) -> bool:
    """
    Insert a new receipt row, ignoring conflicts to preserve notified_at.
    Returns True if a new row was inserted.
    """
    grandtotal = receipt.get("grandtotal", {})
    subtotal = receipt.get("subtotal", {})
    shipping = receipt.get("total_shipping_cost", {})
    tax = receipt.get("total_tax_cost", {})
    discount = receipt.get("discount_amt", {})
    notified_at = int(time.time()) if already_seen else None

    cursor = await db.execute(
        """
        INSERT OR IGNORE INTO receipts (
            receipt_id, shop_id, receipt_type, seller_user_id, buyer_user_id,
            buyer_email, name, city, state, zip, country_iso, status,
            payment_method, is_paid, is_shipped, is_gift, gift_message,
            grandtotal_amount, grandtotal_divisor, grandtotal_currency,
            subtotal_amount, total_shipping_amount, total_tax_amount,
            discount_amount, create_timestamp, update_timestamp, fetched_at,
            notified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receipt["receipt_id"],
            receipt.get("shop_id"),
            receipt.get("receipt_type", 0),
            receipt["seller_user_id"],
            receipt.get("buyer_user_id"),
            receipt.get("buyer_email"),
            receipt.get("name"),
            receipt.get("city"),
            receipt.get("state"),
            receipt.get("zip"),
            receipt.get("country_iso"),
            receipt.get("status", ""),
            receipt.get("payment_method"),
            1 if receipt.get("is_paid") else 0,
            1 if receipt.get("is_shipped") else 0,
            1 if receipt.get("is_gift") else 0,
            receipt.get("gift_message"),
            grandtotal.get("amount", 0),
            grandtotal.get("divisor", 100),
            grandtotal.get("currency_code", "USD"),
            subtotal.get("amount"),
            shipping.get("amount"),
            tax.get("amount"),
            discount.get("amount", 0),
            receipt.get("create_timestamp", int(time.time())),
            receipt.get("update_timestamp"),
            int(time.time()),
            notified_at,
        ),
    )
    return cursor.rowcount == 1


async def get_unnotified_receipts(db: aiosqlite.Connection, shop_id: int) -> list:
    cursor = await db.execute(
        """
        SELECT * FROM receipts
        WHERE shop_id = ? AND notified_at IS NULL
        ORDER BY create_timestamp ASC
        """,
        (shop_id,),
    )
    return await cursor.fetchall()


async def mark_receipt_notified(db: aiosqlite.Connection, receipt_id: int) -> None:
    await db.execute(
        "UPDATE receipts SET notified_at = ? WHERE receipt_id = ?",
        (int(time.time()), receipt_id),
    )


async def disconnect_guild(
    db: aiosqlite.Connection, guild_id: int, new_setup_token: str, new_setup_token_exp: int
) -> None:
    """Remove Etsy credentials and clear shop association for a guild."""
    await db.execute("DELETE FROM etsy_tokens WHERE guild_id = ?", (guild_id,))
    await db.execute(
        """
        UPDATE guilds
        SET etsy_shop_id = NULL, order_channel_id = NULL, connected_at = NULL,
            setup_token = ?, setup_token_exp = ?
        WHERE guild_id = ?
        """,
        (new_setup_token, new_setup_token_exp, guild_id),
    )
