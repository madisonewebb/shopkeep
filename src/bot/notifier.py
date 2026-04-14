"""
Discord embed formatter for new Etsy order notifications.
Works with rows returned from the receipts DB table (snake_case column names).
"""

from datetime import datetime, timezone

import discord


def build_welcome_embed(guild_name: str, setup_url: str) -> discord.Embed:
    """Build the welcome DM embed sent to a guild owner when the bot joins."""
    embed = discord.Embed(
        title="Welcome to Shopkeep!",
        description=(
            "Shopkeep connects your Etsy shop to Discord so you never miss a sale. "
            "Get real-time order notifications posted directly to your server."
        ),
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="Get started",
        value=f"[Connect your Etsy shop]({setup_url}) to authorize Shopkeep.",
        inline=False,
    )
    embed.add_field(
        name="Then in {guild_name}".format(guild_name=guild_name),
        value="Run `/setchannel` to choose which channel receives order notifications.",
        inline=False,
    )
    embed.add_field(
        name="Need help?",
        value="Run `/help` in your server to see all available commands.",
        inline=False,
    )
    return embed


def build_shop_embed(shop: dict) -> discord.Embed:
    """Build a Discord embed for shop info from an API shop dict."""
    name = shop.get("shop_name", "Shop")
    url = shop.get("url")

    embed = discord.Embed(
        title=name,
        url=url,
        color=discord.Color.blurple(),
    )

    if announcement := shop.get("announcement"):
        embed.description = announcement[:500]

    if shop.get("is_vacation"):
        embed.add_field(name="Status", value="On Vacation", inline=True)

    active = shop.get("listing_active_count")
    if active is not None:
        embed.add_field(name="Active Listings", value=str(active), inline=True)

    digital = shop.get("digital_listing_count")
    if digital is not None:
        embed.add_field(name="Digital Listings", value=str(digital), inline=True)

    favorers = shop.get("num_favorers")
    if favorers is not None:
        embed.add_field(name="Favorites", value=str(favorers), inline=True)

    if currency := shop.get("currency_code"):
        embed.add_field(name="Currency", value=currency, inline=True)

    return embed


def build_connected_embed(shop_name: str, no_channel: bool = False) -> discord.Embed:
    """Build the embed posted when an Etsy shop is first connected.

    If no_channel is True, the embed is sent as a DM to the guild owner and includes
    a prompt to run /setchannel.
    """
    if no_channel:
        description = (
            f"**{shop_name}** is now linked to your server. "
            "Run `/setchannel` in the channel where you'd like order notifications posted."
        )
    else:
        description = (
            f"**{shop_name}** is now linked to this server. "
            "New order notifications will be posted in this channel.\n\n"
            "Use `/setchannel` to change the notification channel, or `/shop` to see your shop info."
        )
    embed = discord.Embed(
        title="Etsy Shop Connected",
        description=description,
        color=discord.Color.green(),
    )
    return embed


def build_disconnect_embed(shop_name: str) -> discord.Embed:
    """Build the confirmation embed shown after a successful /disconnect."""
    embed = discord.Embed(
        title="Etsy Shop Disconnected",
        description=(
            f"**{shop_name}** has been unlinked from this server. "
            "Order notifications have been stopped and your tokens have been removed.\n\n"
            "To reconnect, run `/status` to get a new setup link."
        ),
        color=discord.Color.greyple(),
    )
    return embed


def build_status_change_embed(
    receipt: dict,
    shop_name: str,
    change_type: str,
) -> discord.Embed:
    """
    Build a Discord embed for an order status change notification.

    Args:
        receipt: Raw API receipt dict (snake_case).
        shop_name: Human-readable shop name shown in the footer.
        change_type: "shipped" or "canceled".
    """
    receipt_id = receipt.get("receipt_id", "?")
    buyer = receipt.get("name") or "Unknown"
    grandtotal = receipt.get("grandtotal", {})
    amount = grandtotal.get("amount", 0)
    divisor = grandtotal.get("divisor") or 100
    currency = grandtotal.get("currency_code", "USD")
    total = f"${amount / divisor:.2f} {currency}"
    receipt_url = f"https://www.etsy.com/your_account/orders/{receipt_id}"

    if change_type == "shipped":
        title = f"Order #{receipt_id} Shipped"
        color = discord.Color.green()
    else:
        title = f"Order #{receipt_id} Canceled"
        color = discord.Color.red()

    embed = discord.Embed(
        title=title,
        url=receipt_url,
        description=f"**{buyer}** — {total}",
        color=color,
    )

    transactions = receipt.get("transactions", [])
    if transactions:
        titles = [t["title"] for t in transactions if t.get("title")]
        if titles:
            embed.add_field(name="Items", value="\n".join(f"• {t}" for t in titles), inline=False)
        first_image = transactions[0].get("listing_image") or {}
        thumbnail_url = first_image.get("url_75x75") or first_image.get("url_170x135")
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

    create_timestamp = receipt.get("create_timestamp")
    if create_timestamp:
        embed.timestamp = datetime.fromtimestamp(create_timestamp, tz=timezone.utc)

    embed.set_footer(text=shop_name)
    return embed


def build_order_embed(
    receipt: dict,
    shop_name: str,
    new: bool = False,
    transactions: list | None = None,
    returning: bool = False,
) -> discord.Embed:
    """
    Build a Discord embed for an order notification.

    Args:
        receipt: A dict of receipt DB columns (snake_case).
        shop_name: Human-readable shop name shown in the footer.
        new: If True, prefixes the title with "New Order"; otherwise "Order".
        transactions: Raw transaction list from the Etsy API receipt, used to
            show listing titles and thumbnail.
    """
    receipt_id = receipt.get("receipt_id", "?")
    status = (receipt.get("status") or "Unknown").capitalize()
    is_paid = receipt.get("is_paid")
    is_shipped = receipt.get("is_shipped")

    if status.lower() == "canceled":
        color = discord.Color.red()
    elif new:
        color = discord.Color.gold()
    elif is_paid and not is_shipped:
        color = discord.Color.orange()
    else:
        color = discord.Color.blurple()

    amount = receipt.get("grandtotal_amount", 0)
    divisor = receipt.get("grandtotal_divisor") or 100
    currency = receipt.get("grandtotal_currency", "USD")
    total = f"${amount / divisor:.2f} {currency}"
    buyer = receipt.get("name") or "Unknown"

    city = receipt.get("city")
    country = receipt.get("country_iso")
    location = ", ".join(filter(None, [city, country])) if (city or country) else None

    receipt_url = f"https://www.etsy.com/your_account/orders/{receipt_id}"
    if new:
        title = "🎉 New Sale!"
        buyer_line = f"**{buyer}** ordered [#{receipt_id}]({receipt_url}) — **{total}**"
        location_line = f"\n📍 {location}" if location else ""
        returning_line = "\n🔁 Returning customer!" if returning else ""
        description = f"{buyer_line}{location_line}{returning_line}"
    else:
        title = f"Order #{receipt_id}"
        description = f"**{buyer}** — {total}"

    embed = discord.Embed(
        title=title,
        url=receipt_url if not new else None,
        description=description,
        color=color,
    )

    if transactions:
        item_lines = []
        for t in transactions:
            if not t.get("title"):
                continue
            qty = t.get("quantity", 1)
            line = f"• {t['title']}" + (f" ×{qty}" if qty > 1 else "")
            variations = t.get("selected_variations") or []
            if variations:
                var_str = ", ".join(
                    f"{v['formatted_name']}: {v['formatted_value']}"
                    for v in variations
                    if v.get("formatted_name") and v.get("formatted_value")
                )
                if var_str:
                    line += f"\n  *{var_str}*"
            item_lines.append(line)
        if item_lines:
            embed.add_field(name="Items", value="\n".join(item_lines), inline=False)

        first_image = transactions[0].get("listing_image") or {}
        thumbnail_url = first_image.get("url_75x75") or first_image.get("url_170x135")
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

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


def build_review_embed(review: dict, shop_name: str) -> discord.Embed:
    """
    Build a Discord embed for a new shop review notification.

    Args:
        review: A dict of review DB columns (snake_case).
        shop_name: Human-readable shop name shown in the footer.
    """
    rating = review.get("rating", 0)
    stars = "⭐" * rating + f" ({rating}/5)"
    review_text = review.get("review", "").strip()

    embed = discord.Embed(
        title=f"New Review: {stars}",
        description=f'"{review_text}"' if review_text else None,
        color=discord.Color.gold(),
    )

    if image_url := review.get("image_url"):
        embed.set_thumbnail(url=image_url)

    create_timestamp = review.get("create_timestamp")
    if create_timestamp:
        embed.timestamp = datetime.fromtimestamp(create_timestamp, tz=timezone.utc)

    embed.set_footer(text=shop_name)
    return embed


def build_shipping_reminder_embed(
    receipt: dict,
    shop_name: str,
    days_before: int,
) -> discord.Embed:
    """
    Build a Discord embed for a shipping deadline reminder.

    Args:
        receipt: A dict of receipt DB columns (snake_case).
        shop_name: Human-readable shop name shown in the footer.
        days_before: Days until expected ship date (0=today, 1=tomorrow, etc.).
    """
    receipt_id = receipt.get("receipt_id", "?")
    buyer = receipt.get("name") or "Unknown"
    amount = receipt.get("grandtotal_amount", 0)
    divisor = receipt.get("grandtotal_divisor") or 100
    currency = receipt.get("grandtotal_currency", "USD")
    total = f"${amount / divisor:.2f} {currency}"
    receipt_url = f"https://www.etsy.com/your_account/orders/{receipt_id}"

    if days_before == 0:
        urgency = "Ship Today"
        color = discord.Color.red()
        deadline_line = "This order is due to ship **today**."
    elif days_before == 1:
        urgency = "Ship Tomorrow"
        color = discord.Color.orange()
        deadline_line = "This order is due to ship **tomorrow**."
    else:
        urgency = f"Ship in {days_before} Days"
        color = discord.Color.yellow()
        deadline_line = f"This order is due to ship in **{days_before} days**."

    embed = discord.Embed(
        title=f"Shipping Reminder — {urgency}",
        url=receipt_url,
        description=f"**{buyer}** — Order [#{receipt_id}]({receipt_url}) — {total}\n{deadline_line}",
        color=color,
    )

    expected_ship_date = receipt.get("expected_ship_date")
    if expected_ship_date:
        embed.add_field(
            name="Expected Ship Date",
            value=f"<t:{expected_ship_date}:D>",
            inline=True,
        )

    create_timestamp = receipt.get("create_timestamp")
    if create_timestamp:
        embed.timestamp = datetime.fromtimestamp(create_timestamp, tz=timezone.utc)

    embed.set_footer(text=shop_name)
    return embed
