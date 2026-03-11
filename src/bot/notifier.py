"""
Discord embed formatter for new Etsy order notifications.
Works with rows returned from the receipts DB table (snake_case column names).
"""

from datetime import datetime, timezone

import discord


def build_shop_embed(shop: dict) -> discord.Embed:
    """Build a Discord embed for shop info from an API shop dict."""
    name = shop.get("shop_name", "Shop")
    url = shop.get("url")

    embed = discord.Embed(
        title=name,
        url=url,
        color=discord.Color.blurple(),
    )

    if location := shop.get("location"):
        embed.add_field(name="Location", value=location, inline=True)

    sales = shop.get("transaction_sold_count")
    if sales is not None:
        embed.add_field(name="Sales", value=str(sales), inline=True)

    review_avg = shop.get("review_average")
    review_count = shop.get("review_count")
    if review_avg is not None:
        value = f"{review_avg:.1f} ★"
        if review_count is not None:
            value += f" ({review_count} reviews)"
        embed.add_field(name="Rating", value=value, inline=True)

    return embed


def build_order_embed(receipt: dict, shop_name: str, new: bool = False) -> discord.Embed:
    """
    Build a Discord embed for an order notification.

    Args:
        receipt: A dict of receipt DB columns (snake_case).
        shop_name: Human-readable shop name shown in the footer.
        new: If True, prefixes the title with "New Order"; otherwise "Order".
    """
    receipt_id = receipt.get("receipt_id", "?")
    status = (receipt.get("status") or "Unknown").capitalize()
    is_paid = receipt.get("is_paid")
    is_shipped = receipt.get("is_shipped")

    if status.lower() == "canceled":
        color = discord.Color.red()
    elif is_paid and not is_shipped:
        color = discord.Color.orange()
    else:
        color = discord.Color.blurple()

    amount = receipt.get("grandtotal_amount", 0)
    divisor = receipt.get("grandtotal_divisor") or 100
    currency = receipt.get("grandtotal_currency", "USD")
    total = f"${amount / divisor:.2f} {currency}"
    buyer = receipt.get("name") or "Unknown"

    title = f"{'New Order' if new else 'Order'} #{receipt_id}"
    embed = discord.Embed(
        title=title,
        description=f"**{buyer}** — {total}",
        color=color,
    )

    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(
        name="Fulfillment",
        value="Shipped" if is_shipped else "Not shipped",
        inline=True,
    )

    if gift_message := receipt.get("gift_message"):
        embed.add_field(name="Gift Message", value=gift_message, inline=False)

    create_timestamp = receipt.get("create_timestamp")
    if create_timestamp:
        embed.timestamp = datetime.fromtimestamp(create_timestamp, tz=timezone.utc)

    embed.set_footer(text=shop_name)

    return embed
