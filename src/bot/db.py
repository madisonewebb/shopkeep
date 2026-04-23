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
    image_url               TEXT,
    fetched_at              INTEGER NOT NULL
)
"""

_CREATE_SHIPPING_PRESETS = """
CREATE TABLE IF NOT EXISTS shipping_presets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL REFERENCES guilds(guild_id),
    name         TEXT    NOT NULL,
    carrier      TEXT    NOT NULL,
    mail_class   TEXT    NOT NULL,
    package_type TEXT    NOT NULL DEFAULT '',
    weight_oz    REAL    NOT NULL,
    length_in    REAL    NOT NULL,
    width_in     REAL    NOT NULL,
    height_in    REAL    NOT NULL,
    created_at   INTEGER NOT NULL,
    UNIQUE(guild_id, name)
)
"""

_CREATE_SHIPPO_KEYS = """
CREATE TABLE IF NOT EXISTS shippo_keys (
    guild_id     INTEGER PRIMARY KEY REFERENCES guilds(guild_id),
    api_key      TEXT    NOT NULL,
    addr_name    TEXT,
    addr_street1 TEXT,
    addr_street2 TEXT,
    addr_city    TEXT,
    addr_state   TEXT,
    addr_zip     TEXT,
    addr_country TEXT    NOT NULL DEFAULT 'US',
    addr_phone   TEXT,
    created_at   INTEGER NOT NULL
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
    first_line            TEXT,
    second_line           TEXT,
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
    expected_ship_date    INTEGER,
    fetched_at            INTEGER NOT NULL,
    notified_at           INTEGER
)
"""

_CREATE_SHIPPING_REMINDERS = """
CREATE TABLE IF NOT EXISTS shipping_reminders (
    receipt_id  INTEGER NOT NULL REFERENCES receipts(receipt_id),
    days_before INTEGER NOT NULL,
    sent_at     INTEGER NOT NULL,
    PRIMARY KEY (receipt_id, days_before)
)
"""

_CREATE_TRANSACTIONS = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id      INTEGER PRIMARY KEY,
    receipt_id          INTEGER NOT NULL REFERENCES receipts(receipt_id),
    shop_id             INTEGER NOT NULL REFERENCES shops(shop_id),
    listing_id          INTEGER,
    title               TEXT,
    quantity            INTEGER NOT NULL DEFAULT 1,
    price_amount        INTEGER NOT NULL DEFAULT 0,
    price_divisor       INTEGER NOT NULL DEFAULT 100,
    price_currency      TEXT    NOT NULL DEFAULT 'USD',
    create_timestamp    INTEGER NOT NULL,
    image_url           TEXT,
    selected_variations  TEXT,
    personalization_msg  TEXT,
    fetched_at           INTEGER NOT NULL
)
"""

_CREATE_REVIEWS = """
CREATE TABLE IF NOT EXISTS reviews (
    transaction_id   INTEGER PRIMARY KEY,
    shop_id          INTEGER NOT NULL REFERENCES shops(shop_id),
    listing_id       INTEGER,
    buyer_user_id    INTEGER,
    rating           INTEGER NOT NULL,
    review           TEXT,
    language         TEXT,
    image_url        TEXT,
    create_timestamp INTEGER NOT NULL,
    update_timestamp INTEGER,
    fetched_at       INTEGER NOT NULL,
    notified_at      INTEGER
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
        await db.execute(_CREATE_SHIPPING_PRESETS)
        await db.execute(_CREATE_SHIPPING_REMINDERS)
        await db.execute(_CREATE_TRANSACTIONS)
        await db.execute(_CREATE_REVIEWS)
        await db.execute(_CREATE_SHIPPO_KEYS)
        try:
            await db.execute("ALTER TABLE shippo_keys ADD COLUMN addr_phone TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE listings ADD COLUMN image_url TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE receipts ADD COLUMN expected_ship_date INTEGER")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN ship_reminder_days TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN ship_reminder_time TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN ship_reminder_tz TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN backlog_threshold INTEGER")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN backlog_warned INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN digest_time TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN digest_tz TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN digest_last_sent INTEGER")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN goal_amount INTEGER")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN goal_milestones_sent TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN goal_month TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE transactions ADD COLUMN selected_variations TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE transactions ADD COLUMN personalization_msg TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE receipts ADD COLUMN first_line TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE receipts ADD COLUMN second_line TEXT")
        except Exception:
            pass  # column already exists
        try:
            await db.execute(
                "ALTER TABLE shipping_presets ADD COLUMN package_type TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass  # column already exists
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
            last_modified_timestamp, image_url, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ((listing.get("images") or [{}])[0]).get("url_570xN")
            or ((listing.get("images") or [{}])[0]).get("url_170x135"),
            int(time.time()),
        ),
    )


async def upsert_listings(db: aiosqlite.Connection, listings: list) -> None:
    for listing in listings:
        await upsert_listing(db, listing)


async def upsert_transactions(
    db: aiosqlite.Connection, receipt_id: int, shop_id: int, transactions: list
) -> None:
    """Upsert line-item transactions from a receipt. Ignores conflicts (write-once)."""
    now = int(time.time())
    for t in transactions:
        price = t.get("price") or {}
        image = (t.get("listing_image") or {})
        image_url = image.get("url_75x75") or image.get("url_170x135")
        variations = t.get("selected_variations") or t.get("variations")
        variations_json = json.dumps(variations) if variations is not None else None
        personalization_msg = t.get("personalization_message") or None
        await db.execute(
            """
            INSERT INTO transactions (
                transaction_id, receipt_id, shop_id, listing_id, title,
                quantity, price_amount, price_divisor, price_currency,
                create_timestamp, image_url, selected_variations, personalization_msg, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                selected_variations = COALESCE(excluded.selected_variations, selected_variations),
                personalization_msg = COALESCE(excluded.personalization_msg, personalization_msg),
                image_url = COALESCE(excluded.image_url, image_url)
            """,
            (
                t["transaction_id"],
                receipt_id,
                shop_id,
                t.get("listing_id"),
                t.get("title"),
                t.get("quantity", 1),
                price.get("amount", 0),
                price.get("divisor", 100),
                price.get("currency_code", "USD"),
                t.get("create_timestamp", now),
                image_url,
                variations_json,
                personalization_msg,
                now,
            ),
        )


async def get_bestsellers(
    db: aiosqlite.Connection,
    shop_id: int,
    since_timestamp: int,
    ranked_by: str = "units",
    limit: int = 5,
) -> list:
    """Return top listings by units sold or revenue for a shop since a given timestamp.

    ranked_by: "units" (default) or "revenue".
    Excludes transactions from canceled receipts.
    """
    order_col = "units_sold" if ranked_by == "units" else "total_revenue"
    cursor = await db.execute(
        f"""
        SELECT
            t.listing_id,
            t.title,
            t.image_url,
            SUM(t.quantity) AS units_sold,
            SUM(t.quantity * CAST(t.price_amount AS REAL) / t.price_divisor) AS total_revenue,
            t.price_currency AS currency
        FROM transactions t
        JOIN receipts r ON r.receipt_id = t.receipt_id
        WHERE t.shop_id = ?
          AND t.listing_id IS NOT NULL
          AND t.create_timestamp >= ?
          AND LOWER(r.status) != 'canceled'
        GROUP BY t.listing_id, t.title
        ORDER BY {order_col} DESC
        LIMIT ?
        """,
        (shop_id, since_timestamp, limit),
    )
    return await cursor.fetchall()


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
    expected_ship_date = receipt.get("expected_ship_date") or max(
        (t.get("expected_ship_date") for t in receipt.get("transactions", []) if t.get("expected_ship_date")),
        default=None,
    )

    cursor = await db.execute(
        """
        INSERT OR IGNORE INTO receipts (
            receipt_id, shop_id, receipt_type, seller_user_id, buyer_user_id,
            buyer_email, name, first_line, second_line, city, state, zip, country_iso, status,
            payment_method, is_paid, is_shipped, is_gift, gift_message,
            grandtotal_amount, grandtotal_divisor, grandtotal_currency,
            subtotal_amount, total_shipping_amount, total_tax_amount,
            discount_amount, create_timestamp, update_timestamp, expected_ship_date,
            fetched_at, notified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receipt["receipt_id"],
            receipt.get("shop_id"),
            receipt.get("receipt_type", 0),
            receipt["seller_user_id"],
            receipt.get("buyer_user_id"),
            receipt.get("buyer_email"),
            receipt.get("name"),
            receipt.get("first_line"),
            receipt.get("second_line"),
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
            expected_ship_date,
            int(time.time()),
            notified_at,
        ),
    )
    is_new = cursor.rowcount == 1

    # For existing rows, keep mutable fields current (notified_at is preserved by INSERT OR IGNORE)
    if not is_new:
        await db.execute(
            """
            UPDATE receipts
            SET name=?, first_line=?, second_line=?, city=?, state=?, zip=?, country_iso=?,
                is_shipped=?, status=?, update_timestamp=?, expected_ship_date=?, fetched_at=?
            WHERE receipt_id = ?
            """,
            (
                receipt.get("name"),
                receipt.get("first_line"),
                receipt.get("second_line"),
                receipt.get("city"),
                receipt.get("state"),
                receipt.get("zip"),
                receipt.get("country_iso"),
                1 if receipt.get("is_shipped") else 0,
                receipt.get("status", ""),
                receipt.get("update_timestamp"),
                expected_ship_date,
                int(time.time()),
                receipt["receipt_id"],
            ),
        )

    return is_new


async def get_receipts_status_snapshot(
    db: aiosqlite.Connection, receipt_ids: list
) -> dict:
    """Return {receipt_id: {"is_shipped": int, "status": str}} for all known receipt IDs."""
    if not receipt_ids:
        return {}
    placeholders = ",".join("?" * len(receipt_ids))
    cursor = await db.execute(
        f"SELECT receipt_id, is_shipped, status FROM receipts WHERE receipt_id IN ({placeholders})",
        receipt_ids,
    )
    rows = await cursor.fetchall()
    return {row["receipt_id"]: {"is_shipped": row["is_shipped"], "status": row["status"]} for row in rows}


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


# ── Shipping reminder helpers ─────────────────────────────────────────────────


async def get_pending_reminders(
    db: aiosqlite.Connection,
    shop_id: int,
    days_before: int,
    lower: int,
    upper: int,
) -> list:
    """Return unshipped receipts whose ship date falls within [lower, upper) that haven't had this reminder sent."""
    cursor = await db.execute(
        """
        SELECT r.*
        FROM receipts r
        WHERE r.shop_id = ?
          AND r.is_shipped = 0
          AND r.expected_ship_date IS NOT NULL
          AND r.expected_ship_date >= ?
          AND r.expected_ship_date < ?
          AND NOT EXISTS (
              SELECT 1 FROM shipping_reminders sr
              WHERE sr.receipt_id = r.receipt_id
                AND sr.days_before = ?
          )
        ORDER BY r.expected_ship_date ASC
        """,
        (shop_id, lower, upper, days_before),
    )
    return await cursor.fetchall()


async def get_receipt_transactions(
    db: aiosqlite.Connection,
    receipt_id: int,
) -> list[dict]:
    """Return transactions for a receipt with selected_variations parsed from JSON."""
    cursor = await db.execute(
        "SELECT * FROM transactions WHERE receipt_id = ? ORDER BY transaction_id ASC",
        (receipt_id,),
    )
    rows = await cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        raw = d.get("selected_variations")
        if raw:
            try:
                d["selected_variations"] = json.loads(raw)
            except Exception:
                d["selected_variations"] = []
        else:
            d["selected_variations"] = []
        result.append(d)
    return result


async def mark_reminder_sent(
    db: aiosqlite.Connection,
    receipt_id: int,
    days_before: int,
) -> None:
    await db.execute(
        """
        INSERT OR IGNORE INTO shipping_reminders (receipt_id, days_before, sent_at)
        VALUES (?, ?, ?)
        """,
        (receipt_id, days_before, int(time.time())),
    )


async def get_guild_reminder_config(
    db: aiosqlite.Connection,
    guild_id: int,
) -> dict | None:
    """Return reminder config for a guild, or None if reminders are not set.

    Returns a dict with keys: days (list[int]), time (str | None), tz (str | None).
    """
    cursor = await db.execute(
        "SELECT ship_reminder_days, ship_reminder_time, ship_reminder_tz FROM guilds WHERE guild_id = ?",
        (guild_id,),
    )
    row = await cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return {
        "days": json.loads(row[0]),
        "time": row[1],
        "tz": row[2],
    }


async def set_guild_reminder_days(
    db: aiosqlite.Connection,
    guild_id: int,
    days: list[int],
) -> None:
    await db.execute(
        "UPDATE guilds SET ship_reminder_days = ? WHERE guild_id = ?",
        (json.dumps(days), guild_id),
    )


async def set_guild_reminder_time(
    db: aiosqlite.Connection,
    guild_id: int,
    time_str: str,
    tz: str,
) -> None:
    await db.execute(
        "UPDATE guilds SET ship_reminder_time = ?, ship_reminder_tz = ? WHERE guild_id = ?",
        (time_str, tz, guild_id),
    )


async def disable_guild_reminders(
    db: aiosqlite.Connection,
    guild_id: int,
) -> None:
    await db.execute(
        "UPDATE guilds SET ship_reminder_days = NULL, ship_reminder_time = NULL, ship_reminder_tz = NULL WHERE guild_id = ?",
        (guild_id,),
    )


async def get_listing_quantity_snapshot(
    db: aiosqlite.Connection, listing_ids: list[int]
) -> dict[int, int]:
    """Return {listing_id: quantity} for all known listing IDs."""
    if not listing_ids:
        return {}
    placeholders = ",".join("?" * len(listing_ids))
    cursor = await db.execute(
        f"SELECT listing_id, quantity FROM listings WHERE listing_id IN ({placeholders})",
        listing_ids,
    )
    rows = await cursor.fetchall()
    return {row["listing_id"]: row["quantity"] for row in rows}


async def get_active_listings(db: aiosqlite.Connection, shop_id: int) -> list:
    """Return all active listings for a shop, ordered by title."""
    cursor = await db.execute(
        """
        SELECT listing_id, title, quantity, url,
               price_amount, price_divisor, price_currency_code
        FROM listings
        WHERE shop_id = ? AND state = 'active'
        ORDER BY title ASC
        """,
        (shop_id,),
    )
    return await cursor.fetchall()


async def get_receipts_since(
    db: aiosqlite.Connection, shop_id: int, since_timestamp: int
) -> list:
    """Return all non-canceled receipts for a shop created on or after since_timestamp."""
    cursor = await db.execute(
        """
        SELECT grandtotal_amount, grandtotal_divisor, grandtotal_currency
        FROM receipts
        WHERE shop_id = ? AND create_timestamp >= ? AND LOWER(status) != 'canceled'
        """,
        (shop_id, since_timestamp),
    )
    return await cursor.fetchall()


# ── Shipping preset helpers ───────────────────────────────────────────────────

async def add_preset(
    db: aiosqlite.Connection,
    guild_id: int,
    name: str,
    carrier: str,
    mail_class: str,
    weight_oz: float,
    length_in: float,
    width_in: float,
    height_in: float,
    package_type: str = "",
) -> bool:
    """Insert a new preset. Returns True if inserted, False if name already exists."""
    cursor = await db.execute(
        """
        INSERT OR IGNORE INTO shipping_presets
            (guild_id, name, carrier, mail_class, package_type, weight_oz, length_in, width_in, height_in, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, name, carrier, mail_class, package_type, weight_oz, length_in, width_in, height_in, int(time.time())),
    )
    return cursor.rowcount == 1


async def list_presets(db: aiosqlite.Connection, guild_id: int) -> list:
    """Return all presets for a guild, ordered by name."""
    cursor = await db.execute(
        "SELECT * FROM shipping_presets WHERE guild_id = ? ORDER BY name ASC",
        (guild_id,),
    )
    return await cursor.fetchall()


async def delete_preset(db: aiosqlite.Connection, guild_id: int, name: str) -> bool:
    """Delete a preset by name. Returns True if a row was deleted."""
    cursor = await db.execute(
        "DELETE FROM shipping_presets WHERE guild_id = ? AND name = ?",
        (guild_id, name),
    )
    return cursor.rowcount == 1


async def get_labelable_receipts(db: aiosqlite.Connection, shop_id: int) -> list:
    """Return paid, unshipped receipts for label autocomplete, newest first."""
    cursor = await db.execute(
        """
        SELECT r.receipt_id, r.name, r.create_timestamp,
               GROUP_CONCAT(
                   CASE WHEN t.quantity > 1 THEN t.quantity || 'x ' || t.title ELSE t.title END,
                   ', '
               ) AS items
        FROM receipts r
        LEFT JOIN transactions t ON t.receipt_id = r.receipt_id AND t.shop_id = r.shop_id
        WHERE r.shop_id = ? AND r.is_paid = 1 AND r.is_shipped = 0
          AND LOWER(r.status) != 'canceled'
        GROUP BY r.receipt_id
        ORDER BY r.create_timestamp DESC
        LIMIT 25
        """,
        (shop_id,),
    )
    return await cursor.fetchall()


async def get_preset_by_name(db: aiosqlite.Connection, guild_id: int, name: str):
    """Return a single preset row by name, or None."""
    cursor = await db.execute(
        "SELECT * FROM shipping_presets WHERE guild_id = ? AND name = ?",
        (guild_id, name),
    )
    return await cursor.fetchone()


# ── Review helpers ────────────────────────────────────────────────────────────

async def upsert_review(
    db: aiosqlite.Connection, review: dict, already_seen: bool = False
) -> bool:
    """
    Insert a new review row, ignoring conflicts to preserve notified_at.
    Returns True if a new row was inserted.
    """
    notified_at = int(time.time()) if already_seen else None
    cursor = await db.execute(
        """
        INSERT OR IGNORE INTO reviews (
            transaction_id, shop_id, listing_id, buyer_user_id,
            rating, review, language, image_url,
            create_timestamp, update_timestamp, fetched_at, notified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review["transaction_id"],
            review["shop_id"],
            review.get("listing_id"),
            review.get("buyer_user_id"),
            review["rating"],
            review.get("review"),
            review.get("language"),
            review.get("image_url_fullxfull"),
            review.get("create_timestamp", int(time.time())),
            review.get("update_timestamp"),
            int(time.time()),
            notified_at,
        ),
    )
    return cursor.rowcount == 1


async def get_unnotified_reviews(db: aiosqlite.Connection, shop_id: int) -> list:
    cursor = await db.execute(
        """
        SELECT r.*, t.title AS listing_title
        FROM reviews r
        LEFT JOIN transactions t ON t.transaction_id = r.transaction_id
        WHERE r.shop_id = ? AND r.notified_at IS NULL
        ORDER BY r.create_timestamp ASC
        """,
        (shop_id,),
    )
    return await cursor.fetchall()


async def mark_review_notified(db: aiosqlite.Connection, transaction_id: int) -> None:
    await db.execute(
        "UPDATE reviews SET notified_at = ? WHERE transaction_id = ?",
        (int(time.time()), transaction_id),
    )


async def get_goal_config(
    db: aiosqlite.Connection, guild_id: int
) -> dict | None:
    """Return goal config for a guild, or None if no goal is set.

    Returns a dict with keys: amount_cents (int), milestones_sent (list[int]), month (str).
    """
    cursor = await db.execute(
        "SELECT goal_amount, goal_milestones_sent, goal_month FROM guilds WHERE guild_id = ?",
        (guild_id,),
    )
    row = await cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return {
        "amount_cents": row[0],
        "milestones_sent": json.loads(row[1]) if row[1] else [],
        "month": row[2],
    }


async def set_goal_amount(
    db: aiosqlite.Connection, guild_id: int, amount_cents: int
) -> None:
    """Set the monthly revenue goal. Resets milestone tracking."""
    import datetime as _dt
    current_month = _dt.date.today().strftime("%Y-%m")
    await db.execute(
        """
        UPDATE guilds
        SET goal_amount = ?, goal_milestones_sent = ?, goal_month = ?
        WHERE guild_id = ?
        """,
        (amount_cents, json.dumps([]), current_month, guild_id),
    )


async def disable_goal(db: aiosqlite.Connection, guild_id: int) -> None:
    await db.execute(
        "UPDATE guilds SET goal_amount = NULL, goal_milestones_sent = NULL, goal_month = NULL WHERE guild_id = ?",
        (guild_id,),
    )


async def update_goal_milestones(
    db: aiosqlite.Connection, guild_id: int, milestones_sent: list[int], month: str
) -> None:
    await db.execute(
        "UPDATE guilds SET goal_milestones_sent = ?, goal_month = ? WHERE guild_id = ?",
        (json.dumps(milestones_sent), month, guild_id),
    )


async def get_digest_config(
    db: aiosqlite.Connection, guild_id: int
) -> dict | None:
    """Return digest config for a guild, or None if disabled.

    Returns a dict with keys: time (str), tz (str), last_sent (int | None).
    """
    cursor = await db.execute(
        "SELECT digest_time, digest_tz, digest_last_sent FROM guilds WHERE guild_id = ?",
        (guild_id,),
    )
    row = await cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return {"time": row[0], "tz": row[1], "last_sent": row[2]}


async def set_digest_config(
    db: aiosqlite.Connection, guild_id: int, time_str: str, tz: str
) -> None:
    await db.execute(
        "UPDATE guilds SET digest_time = ?, digest_tz = ? WHERE guild_id = ?",
        (time_str, tz, guild_id),
    )


async def disable_digest(db: aiosqlite.Connection, guild_id: int) -> None:
    await db.execute(
        "UPDATE guilds SET digest_time = NULL, digest_tz = NULL, digest_last_sent = NULL WHERE guild_id = ?",
        (guild_id,),
    )


async def mark_digest_sent(db: aiosqlite.Connection, guild_id: int, sent_at: int) -> None:
    await db.execute(
        "UPDATE guilds SET digest_last_sent = ? WHERE guild_id = ?",
        (sent_at, guild_id),
    )


async def get_receipts_due_within(
    db: aiosqlite.Connection, shop_id: int, within_seconds: int, now: int
) -> list:
    """Return unshipped, non-canceled receipts with a ship deadline in the next within_seconds."""
    deadline = now + within_seconds
    cursor = await db.execute(
        """
        SELECT receipt_id, name, grandtotal_amount, grandtotal_divisor,
               grandtotal_currency, expected_ship_date
        FROM receipts
        WHERE shop_id = ?
          AND is_shipped = 0
          AND LOWER(status) != 'canceled'
          AND expected_ship_date IS NOT NULL
          AND expected_ship_date <= ?
        ORDER BY expected_ship_date ASC
        """,
        (shop_id, deadline),
    )
    return await cursor.fetchall()


async def get_shop_currency(db: aiosqlite.Connection, shop_id: int) -> str:
    """Return the currency_code for a shop, defaulting to USD."""
    cursor = await db.execute(
        "SELECT currency_code FROM shops WHERE shop_id = ?", (shop_id,)
    )
    row = await cursor.fetchone()
    return row["currency_code"] if row else "USD"


async def get_open_order_count(db: aiosqlite.Connection, shop_id: int) -> int:
    """Return the number of open, unshipped, non-canceled receipts for a shop."""
    cursor = await db.execute(
        """
        SELECT COUNT(*) FROM receipts
        WHERE shop_id = ? AND is_shipped = 0 AND LOWER(status) != 'canceled'
        """,
        (shop_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0


async def get_backlog_config(
    db: aiosqlite.Connection, guild_id: int
) -> dict | None:
    """Return backlog config for a guild, or None if the feature is disabled.

    Returns a dict with keys: threshold (int), warned (bool).
    """
    cursor = await db.execute(
        "SELECT backlog_threshold, backlog_warned FROM guilds WHERE guild_id = ?",
        (guild_id,),
    )
    row = await cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return {"threshold": row[0], "warned": bool(row[1])}


async def set_backlog_threshold(
    db: aiosqlite.Connection, guild_id: int, threshold: int | None
) -> None:
    """Set the backlog threshold. Pass None to disable the feature."""
    await db.execute(
        "UPDATE guilds SET backlog_threshold = ?, backlog_warned = 0 WHERE guild_id = ?",
        (threshold, guild_id),
    )


async def set_backlog_warned(
    db: aiosqlite.Connection, guild_id: int, warned: bool
) -> None:
    await db.execute(
        "UPDATE guilds SET backlog_warned = ? WHERE guild_id = ?",
        (1 if warned else 0, guild_id),
    )


async def is_returning_buyer(
    db: aiosqlite.Connection,
    shop_id: int,
    buyer_user_id: int | None,
    current_receipt_id: int,
) -> bool:
    """Return True if this buyer has any prior notified receipts for the shop."""
    if not buyer_user_id:
        return False
    cursor = await db.execute(
        """
        SELECT 1 FROM receipts
        WHERE shop_id = ? AND buyer_user_id = ? AND receipt_id != ? AND notified_at IS NOT NULL
        LIMIT 1
        """,
        (shop_id, buyer_user_id, current_receipt_id),
    )
    return await cursor.fetchone() is not None


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


# ── Shippo helpers ────────────────────────────────────────────────────────────

async def get_shippo_config(db: aiosqlite.Connection, guild_id: int):
    cursor = await db.execute("SELECT * FROM shippo_keys WHERE guild_id = ?", (guild_id,))
    return await cursor.fetchone()


async def save_shippo_key(db: aiosqlite.Connection, guild_id: int, api_key: str) -> None:
    await db.execute(
        """
        INSERT INTO shippo_keys (guild_id, api_key, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET api_key = excluded.api_key
        """,
        (guild_id, api_key, int(time.time())),
    )


async def save_shippo_address(
    db: aiosqlite.Connection,
    guild_id: int,
    name: str,
    street1: str,
    street2: str,
    city: str,
    state: str,
    zip_code: str,
    country: str,
    phone: str = "",
) -> None:
    await db.execute(
        """
        INSERT INTO shippo_keys (guild_id, api_key, addr_name, addr_street1, addr_street2,
                                 addr_city, addr_state, addr_zip, addr_country, addr_phone, created_at)
        VALUES (?, COALESCE((SELECT api_key FROM shippo_keys WHERE guild_id = ?), ''),
                ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            addr_name    = excluded.addr_name,
            addr_street1 = excluded.addr_street1,
            addr_street2 = excluded.addr_street2,
            addr_city    = excluded.addr_city,
            addr_state   = excluded.addr_state,
            addr_zip     = excluded.addr_zip,
            addr_country = excluded.addr_country,
            addr_phone   = excluded.addr_phone
        """,
        (guild_id, guild_id, name, street1, street2, city, state, zip_code, country, phone,
         int(time.time())),
    )


async def delete_shippo_config(db: aiosqlite.Connection, guild_id: int) -> None:
    await db.execute("DELETE FROM shippo_keys WHERE guild_id = ?", (guild_id,))



async def mark_receipt_shipped(db: aiosqlite.Connection, receipt_id: int) -> None:
    await db.execute(
        "UPDATE receipts SET is_shipped = 1 WHERE receipt_id = ?",
        (receipt_id,),
    )


async def get_unshipped_paid_receipt_ids(db: aiosqlite.Connection, shop_id: int) -> list[int]:
    """Return receipt_ids that are locally marked paid+unshipped."""
    cursor = await db.execute(
        "SELECT receipt_id FROM receipts WHERE shop_id = ? AND is_paid = 1 AND is_shipped = 0",
        (shop_id,),
    )
    rows = await cursor.fetchall()
    return [row["receipt_id"] for row in rows]


async def mark_receipts_shipped_bulk(db: aiosqlite.Connection, receipt_ids: list[int]) -> None:
    """Mark multiple receipts as shipped in one statement."""
    if not receipt_ids:
        return
    placeholders = ",".join("?" * len(receipt_ids))
    await db.execute(
        f"UPDATE receipts SET is_shipped = 1 WHERE receipt_id IN ({placeholders})",
        receipt_ids,
    )
