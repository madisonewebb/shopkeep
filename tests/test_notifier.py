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
