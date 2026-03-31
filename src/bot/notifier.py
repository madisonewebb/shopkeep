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
