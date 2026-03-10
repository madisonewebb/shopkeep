"""
SQLite persistence layer for Shopkeep bot.
Stores shops, listings, and receipts fetched from the Etsy API.
"""

import json
import time

import aiosqlite

# Set by discord_bot.py before init_db() is called
DB_PATH: str = "./shopkeep.db"

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


_CREATE_TOKENS = """
CREATE TABLE IF NOT EXISTS tokens (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    access_token  TEXT    NOT NULL,
    refresh_token TEXT    NOT NULL,
    expires_at    INTEGER NOT NULL
)
"""


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(_CREATE_SHOPS)
        await db.execute(_CREATE_LISTINGS)
        await db.execute(_CREATE_RECEIPTS)
        await db.execute(_CREATE_TOKENS)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Open a WAL-mode connection with foreign keys enabled and Row factory set."""
    conn = await aiosqlite.connect(DB_PATH)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = aiosqlite.Row
    return conn


async def upsert_shop(db: aiosqlite.Connection, shop: dict) -> None:
    """Insert or replace a shop row, mapping camelCase API fields to snake_case columns."""
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
    """Insert or replace a listing row, mapping camelCase API fields to snake_case columns."""
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
    """Upsert a list of listing dicts."""
    for listing in listings:
        await upsert_listing(db, listing)


async def upsert_receipt(db: aiosqlite.Connection, receipt: dict, already_seen: bool = False) -> bool:
    """
    Insert a new receipt row, ignoring conflicts to preserve notified_at on existing rows.
    Returns True if a new row was inserted.

    Pass already_seen=True during bootstrap to stamp notified_at immediately so the
    poll loop never treats pre-existing orders as new.
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
    """Return all receipts for a shop that have not yet been notified."""
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
    """Stamp notified_at with the current unix time."""
    await db.execute(
        "UPDATE receipts SET notified_at = ? WHERE receipt_id = ?",
        (int(time.time()), receipt_id),
    )


async def load_tokens(db: aiosqlite.Connection) -> dict | None:
    """Return the stored OAuth tokens, or None if not yet seeded."""
    cursor = await db.execute(
        "SELECT access_token, refresh_token, expires_at FROM tokens WHERE id = 1"
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def save_tokens(
    db: aiosqlite.Connection, access_token: str, refresh_token: str, expires_at: int
) -> None:
    """Upsert the singleton token row and commit."""
    await db.execute(
        """
        INSERT OR REPLACE INTO tokens (id, access_token, refresh_token, expires_at)
        VALUES (1, ?, ?, ?)
        """,
        (access_token, refresh_token, expires_at),
    )
    await db.commit()
