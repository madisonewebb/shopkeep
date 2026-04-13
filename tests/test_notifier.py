"""Basic tests for Discord embed builders."""

import discord

from src.bot.notifier import build_order_embed, build_review_embed, build_shop_embed


def test_shop_embed_title():
    embed = build_shop_embed({"shop_name": "My Shop", "url": "https://etsy.com/shop/test"})
    assert embed.title == "My Shop"
    assert embed.url == "https://etsy.com/shop/test"


def test_shop_embed_vacation_field():
    embed = build_shop_embed({"is_vacation": True})
    assert any(f.name == "Status" and f.value == "On Vacation" for f in embed.fields)


def test_order_embed_new_title():
    receipt = {
        "receipt_id": 1,
        "status": "open",
        "grandtotal_amount": 2500,
        "grandtotal_divisor": 100,
        "grandtotal_currency": "USD",
    }
    embed = build_order_embed(receipt, "My Shop", new=True)
    assert embed.title == "🎉 New Sale!"
    assert embed.colour == discord.Color.gold()
    assert "#1" in embed.description


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
    # non-new embeds link via embed.url; new embeds embed the link in the description
    embed = build_order_embed(receipt, "My Shop")
    assert embed.url == "https://www.etsy.com/your_account/orders/42"
    new_embed = build_order_embed(receipt, "My Shop", new=True)
    assert "https://www.etsy.com/your_account/orders/42" in new_embed.description


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


def test_review_embed_title_contains_stars():
    review = {"transaction_id": 1, "rating": 5, "review": "Loved it!", "create_timestamp": 1700000000}
    embed = build_review_embed(review, "My Shop")
    assert "⭐⭐⭐⭐⭐" in embed.title
    assert "(5/5)" in embed.title


def test_review_embed_description_is_quoted_text():
    review = {"transaction_id": 2, "rating": 4, "review": "Really nice.", "create_timestamp": 1700000000}
    embed = build_review_embed(review, "My Shop")
    assert embed.description == '"Really nice."'


def test_review_embed_no_description_when_no_text():
    review = {"transaction_id": 3, "rating": 3, "create_timestamp": 1700000000}
    embed = build_review_embed(review, "My Shop")
    assert embed.description is None


def test_review_embed_footer_is_shop_name():
    review = {"transaction_id": 4, "rating": 5, "create_timestamp": 1700000000}
    embed = build_review_embed(review, "Acme Crafts")
    assert embed.footer.text == "Acme Crafts"


def test_review_embed_thumbnail_from_image_url():
    review = {"transaction_id": 5, "rating": 5, "image_url": "https://example.com/img.jpg", "create_timestamp": 1700000000}
    embed = build_review_embed(review, "My Shop")
    assert embed.thumbnail.url == "https://example.com/img.jpg"
