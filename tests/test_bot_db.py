"""Basic tests for the async SQLite layer."""

import time

import pytest

import src.bot.db as botdb
from src.bot.db import create_guild, get_guild, get_unnotified_receipts, init_db, upsert_receipt, upsert_shop


@pytest.fixture(autouse=True)
def patch_db_path(tmp_path, monkeypatch):
    monkeypatch.setattr(botdb, "DB_PATH", str(tmp_path / "test.db"))


@pytest.fixture()
async def db():
    await init_db()
    async with botdb.get_db() as conn:
        yield conn


async def test_create_and_get_guild(db):
    await create_guild(db, 1, "My Server", "tok", int(time.time()) + 3600)
    await db.commit()
    row = await get_guild(db, 1)
    assert row["guild_name"] == "My Server"


async def test_upsert_receipt_new_returns_true(db):
    await upsert_shop(db, {"shop_id": 1, "shop_name": "Shop", "user_id": 9})
    await db.commit()
    receipt = {
        "receipt_id": 100,
        "shop_id": 1,
        "seller_user_id": 9,
        "status": "open",
        "grandtotal": {"amount": 500, "divisor": 100, "currency_code": "USD"},
        "create_timestamp": int(time.time()),
    }
    assert await upsert_receipt(db, receipt) is True


async def test_upsert_receipt_duplicate_returns_false(db):
    await upsert_shop(db, {"shop_id": 1, "shop_name": "Shop", "user_id": 9})
    await db.commit()
    receipt = {
        "receipt_id": 101,
        "shop_id": 1,
        "seller_user_id": 9,
        "status": "open",
        "grandtotal": {"amount": 0, "divisor": 100, "currency_code": "USD"},
        "create_timestamp": int(time.time()),
    }
    await upsert_receipt(db, receipt)
    await db.commit()
    assert await upsert_receipt(db, receipt) is False


async def test_get_unnotified_receipts(db):
    await upsert_shop(db, {"shop_id": 1, "shop_name": "Shop", "user_id": 9})
    await db.commit()
    base = {"shop_id": 1, "seller_user_id": 9, "status": "open",
            "grandtotal": {"amount": 0, "divisor": 100, "currency_code": "USD"},
            "create_timestamp": int(time.time())}
    await upsert_receipt(db, {**base, "receipt_id": 1})
    await upsert_receipt(db, {**base, "receipt_id": 2}, already_seen=True)
    await db.commit()

    rows = await get_unnotified_receipts(db, shop_id=1)
    assert [r["receipt_id"] for r in rows] == [1]
