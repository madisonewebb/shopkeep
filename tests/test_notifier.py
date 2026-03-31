"""Basic tests for Discord embed builders."""

import discord

from src.bot.notifier import build_order_embed, build_shop_embed


def test_shop_embed_title():
    embed = build_shop_embed({"shop_name": "My Shop", "url": "https://etsy.com/shop/test"})
    assert embed.title == "My Shop"
    assert embed.url == "https://etsy.com/shop/test"


def test_shop_embed_vacation_field():
    embed = build_shop_embed({"is_vacation": True})
    assert any(f.name == "Status" and f.value == "On Vacation" for f in embed.fields)


def test_order_embed_new_prefix():
    receipt = {
        "receipt_id": 1,
        "status": "open",
        "grandtotal_amount": 2500,
        "grandtotal_divisor": 100,
        "grandtotal_currency": "USD",
    }
    embed = build_order_embed(receipt, "My Shop", new=True)
    assert embed.title == "New Order #1"


def test_order_embed_canceled_is_red():
    receipt = {
        "receipt_id": 2,
        "status": "canceled",
        "grandtotal_amount": 0,
        "grandtotal_divisor": 100,
        "grandtotal_currency": "USD",
    }
    embed = build_order_embed(receipt, "My Shop")
    assert embed.colour == discord.Color.red()


def test_order_embed_total_calculation():
    receipt = {
        "receipt_id": 3,
        "status": "open",
        "grandtotal_amount": 1099,
        "grandtotal_divisor": 100,
        "grandtotal_currency": "USD",
        "name": "Buyer",
    }
    embed = build_order_embed(receipt, "My Shop")
    assert "$10.99 USD" in embed.description


def test_order_embed_receipt_url():
    receipt = {"receipt_id": 42, "status": "open", "grandtotal_amount": 0, "grandtotal_divisor": 100, "grandtotal_currency": "USD"}
    embed = build_order_embed(receipt, "My Shop")
    assert embed.url == "https://www.etsy.com/your_account/orders/42"


def test_order_embed_items_field():
    receipt = {"receipt_id": 5, "status": "open", "grandtotal_amount": 0, "grandtotal_divisor": 100, "grandtotal_currency": "USD"}
    transactions = [{"title": "Hand-painted Mug"}, {"title": "Ceramic Bowl"}]
    embed = build_order_embed(receipt, "My Shop", transactions=transactions)
    items_field = next((f for f in embed.fields if f.name == "Items"), None)
    assert items_field is not None
    assert "Hand-painted Mug" in items_field.value
    assert "Ceramic Bowl" in items_field.value


def test_order_embed_thumbnail_from_transaction():
    receipt = {"receipt_id": 6, "status": "open", "grandtotal_amount": 0, "grandtotal_divisor": 100, "grandtotal_currency": "USD"}
    transactions = [{"title": "Mug", "listing_image": {"url_75x75": "https://example.com/thumb.jpg"}}]
    embed = build_order_embed(receipt, "My Shop", transactions=transactions)
    assert embed.thumbnail.url == "https://example.com/thumb.jpg"


def test_order_embed_no_thumbnail_when_missing():
    receipt = {"receipt_id": 7, "status": "open", "grandtotal_amount": 0, "grandtotal_divisor": 100, "grandtotal_currency": "USD"}
    transactions = [{"title": "Mug"}]
    embed = build_order_embed(receipt, "My Shop", transactions=transactions)
    assert embed.thumbnail.url is None
