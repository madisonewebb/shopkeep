import asyncio
import datetime
import os
import secrets
import time
import zoneinfo

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from src.bot import db
from src.bot.notifier import build_backlog_embed, build_bestsellers_embed, build_connected_embed, build_digest_embed, build_disconnect_embed, build_goal_milestone_embed, build_label_dm_embed, build_label_public_embed, build_order_embed, build_out_of_stock_embed, build_review_embed, build_shipping_reminder_embed, build_shop_embed, build_status_change_embed, build_welcome_embed
from src.etsy.client import EtsyClient
from src.usps.client import USPSAddressVerificationError, USPSClient

load_dotenv()

ETSY_API_KEY = os.environ["ETSY_API_KEY"]
ETSY_SHARED_SECRET = os.environ["ETSY_SHARED_SECRET"]
POLL_INTERVAL_SECS = int(os.getenv("POLL_INTERVAL_SECS", "60"))
DB_PATH_ENV = os.getenv("DB_PATH", "./shopkeep.db")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "")

_usps_client: USPSClient | None = None
if os.getenv("USPS_CLIENT_ID") and os.getenv("USPS_CLIENT_SECRET"):
    _usps_client = USPSClient(os.environ["USPS_CLIENT_ID"], os.environ["USPS_CLIENT_SECRET"])

SETUP_TOKEN_TTL = 86400  # 24 hours


_ORDERS_PAGE_SIZE = 5

_PACKAGE_TYPES: list[tuple[str, str]] = [
    ("PACKAGE", "Package (custom box/envelope)"),
    ("LARGE_ENVELOPE", "Large Envelope"),
    ("FLAT_RATE_ENVELOPE", "Flat Rate Envelope"),
    ("FLAT_RATE_PADDED_ENVELOPE", "Flat Rate Padded Envelope"),
    ("SMALL_FLAT_RATE_BOX", "Small Flat Rate Box"),
    ("MEDIUM_FLAT_RATE_BOX", "Medium Flat Rate Box"),
    ("LARGE_FLAT_RATE_BOX", "Large Flat Rate Box"),
    ("REGIONAL_RATE_BOX_A", "Regional Rate Box A"),
    ("REGIONAL_RATE_BOX_B", "Regional Rate Box B"),
]


class OrdersView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0
        self.message: discord.Message | None = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current == 0
        self.next_button.disabled = self.current == len(self.pages) - 1

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)


class ConfirmDisconnectView(discord.ui.View):
    def __init__(self, bot: "ShopkeepBot", guild_id: int, shop_name: str, channel_id: int | None):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.shop_name = shop_name
        self.channel_id = channel_id

    @discord.ui.button(label="Disconnect", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup_token = secrets.token_urlsafe(16)
        setup_token_exp = int(time.time()) + SETUP_TOKEN_TTL
        async with db.get_db() as conn:
            await db.disconnect_guild(conn, self.guild_id, setup_token, setup_token_exp)
            await conn.commit()

        self.bot.etsy_clients.pop(self.guild_id, None)
        self.bot._bootstrapped_guilds.discard(self.guild_id)
        self.bot._last_polled.pop(self.guild_id, None)

        self.stop()
        await interaction.response.edit_message(
            embed=build_disconnect_embed(self.shop_name), view=None
        )

        if self.channel_id and self.channel_id != interaction.channel_id:
            channel = self.bot.get_channel(self.channel_id)
            if channel:
                await channel.send(embed=build_disconnect_embed(self.shop_name))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Disconnect canceled.", embed=None, view=None)


class LabelModal(discord.ui.Modal):
    weight = discord.ui.TextInput(
        label="Weight",
        placeholder="e.g. 4oz or 0.3lb",
        required=True,
        max_length=20,
    )
    dims = discord.ui.TextInput(
        label="Dimensions (LxWxH in inches)",
        placeholder="e.g. 6x4x2",
        required=True,
        max_length=30,
    )
    carrier = discord.ui.TextInput(
        label="Carrier",
        placeholder="USPS or UPS",
        required=True,
        max_length=10,
        default="USPS",
    )
    mail_class = discord.ui.TextInput(
        label="Mail Class",
        placeholder="e.g. First Class, Priority Mail, Ground",
        required=True,
        max_length=50,
    )

    def __init__(self, bot: "ShopkeepBot", receipt_ids: str):
        super().__init__(title="Shipping Label Details")
        self.bot = bot
        self.receipt_ids_str = receipt_ids

    async def on_submit(self, interaction: discord.Interaction) -> None:
        weight_oz = _parse_weight_oz(self.weight.value)
        if weight_oz is None or weight_oz <= 0:
            await interaction.response.send_message(
                "Invalid weight. Use a format like `4oz`, `0.3lb`, or `5` (oz).", ephemeral=True
            )
            return
        parsed_dims = _parse_dims(self.dims.value)
        if parsed_dims is None:
            await interaction.response.send_message(
                "Invalid dimensions. Use `LxWxH` in inches, e.g. `6x4x2`.", ephemeral=True
            )
            return
        length_in, width_in, height_in = parsed_dims
        await interaction.response.defer(ephemeral=True)
        await self.bot._process_label_purchases(
            interaction,
            receipt_ids_str=self.receipt_ids_str,
            carrier=self.carrier.value.strip().upper(),
            mail_class=self.mail_class.value.strip(),
            weight_oz=weight_oz,
            length_in=length_in,
            width_in=width_in,
            height_in=height_in,
        )


class LabelWeightModal(discord.ui.Modal):
    weight = discord.ui.TextInput(
        label="Weight",
        placeholder="e.g. 4oz or 0.3lb",
        required=True,
        max_length=20,
    )

    def __init__(self, bot: "ShopkeepBot", receipt_ids_str: str, preset_row):
        super().__init__(title="Confirm Weight")
        self.bot = bot
        self.receipt_ids_str = receipt_ids_str
        self.preset_row = preset_row
        self.weight.default = f"{preset_row['weight_oz']:g}oz"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        weight_oz = _parse_weight_oz(self.weight.value)
        if weight_oz is None or weight_oz <= 0:
            await interaction.response.send_message(
                "Invalid weight. Use a format like `4oz`, `0.3lb`, or `5` (oz).", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await self.bot._process_label_purchases(
            interaction,
            receipt_ids_str=self.receipt_ids_str,
            carrier=self.preset_row["carrier"],
            mail_class=self.preset_row["mail_class"],
            weight_oz=weight_oz,
            length_in=self.preset_row["length_in"],
            width_in=self.preset_row["width_in"],
            height_in=self.preset_row["height_in"],
            package_type=self.preset_row["package_type"] or "",
        )


class LabelPresetView(discord.ui.View):
    def __init__(self, bot: "ShopkeepBot", receipt_ids_str: str, presets: list):
        super().__init__(timeout=120)
        self.bot = bot
        self.receipt_ids_str = receipt_ids_str
        self.presets = {p["name"]: p for p in presets}
        self.selected_name: str | None = None

        options = [discord.SelectOption(label=p["name"], value=p["name"]) for p in presets]
        self.select = discord.ui.Select(
            placeholder="Choose a preset…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        self.selected_name = self.select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Use Preset", style=discord.ButtonStyle.primary)
    async def use_preset(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.selected_name:
            await interaction.response.send_message("Select a preset first.", ephemeral=True)
            return
        self.stop()
        await interaction.response.send_modal(
            LabelWeightModal(self.bot, self.receipt_ids_str, self.presets[self.selected_name])
        )

    @discord.ui.button(label="Enter Manually", style=discord.ButtonStyle.secondary)
    async def enter_manually(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.send_modal(LabelModal(self.bot, self.receipt_ids_str))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class LabelSelectView(discord.ui.View):
    def __init__(self, bot: "ShopkeepBot", receipts: list, preset_row: dict | None):
        super().__init__(timeout=120)
        self.bot = bot
        self.preset_row = preset_row
        self.selected_ids: list[str] = []

        options = [
            discord.SelectOption(
                label=f"{r['name'] or 'Unknown buyer'} — {r['items'] or 'Unknown items'}"[:100],
                value=str(r["receipt_id"]),
            )
            for r in receipts
        ]
        self.select = discord.ui.Select(
            placeholder="Pick orders to label…",
            min_values=1,
            max_values=min(len(options), 25),
            options=options,
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        self.selected_ids = self.select.values
        await interaction.response.defer()

    @discord.ui.button(label="Buy Labels", style=discord.ButtonStyle.primary)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.selected_ids:
            await interaction.response.send_message(
                "Select at least one order first.", ephemeral=True
            )
            return
        self.stop()
        receipt_ids_str = ",".join(self.selected_ids)
        if self.preset_row:
            await interaction.response.send_modal(
                LabelWeightModal(self.bot, receipt_ids_str, self.preset_row)
            )
        else:
            async with db.get_db() as conn:
                presets = await db.list_presets(conn, interaction.guild_id)
            if presets:
                await interaction.response.edit_message(
                    content="Choose a preset or enter shipping details manually:",
                    view=LabelPresetView(self.bot, receipt_ids_str, presets),
                )
            else:
                await interaction.response.send_modal(LabelModal(self.bot, receipt_ids_str))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Canceled.", view=None)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


def _ship_deadline_str(expected_ship_date: int | None) -> str | None:
    if not expected_ship_date:
        return None
    now = int(time.time())
    days = (expected_ship_date - now) / 86400
    if days < -0.5:
        overdue = int(-days + 0.5)
        return f"⚠️ Overdue by {overdue}d"
    elif days < 0.5:
        return "🚨 Ships today"
    elif days < 1.5:
        return "📦 Ships tomorrow"
    else:
        return f"📦 Ships in {int(days + 0.5)}d"


def _build_orders_pages(receipts: list[dict], shop_name: str, revenue_str: str = "") -> list[discord.Embed]:
    total = len(receipts)
    total_pages = (total + _ORDERS_PAGE_SIZE - 1) // _ORDERS_PAGE_SIZE
    pages = []
    description = f"{total} order{'s' if total != 1 else ''}"
    if revenue_str:
        description += f" · {revenue_str} total"
    for page_num, i in enumerate(range(0, total, _ORDERS_PAGE_SIZE), start=1):
        chunk = receipts[i:i + _ORDERS_PAGE_SIZE]
        embed = discord.Embed(
            title="Orders",
            description=description,
            color=discord.Color.orange(),
        )
        for r in chunk:
            gt = r.get("grandtotal") or {}
            amount = gt.get("amount", 0)
            divisor = gt.get("divisor") or 100
            currency = gt.get("currency_code", "USD")
            total_str = f"${amount / divisor:.2f} {currency}"
            status = (r.get("status") or "Unknown").capitalize()
            shipped = "Shipped" if r.get("is_shipped") else "Not shipped"
            buyer = r.get("name") or "Unknown"

            lines = [f"{total_str} · {status} · {shipped}"]

            txns = r.get("transactions") or []
            ship_ts = r.get("expected_ship_date") or max(
                (t.get("expected_ship_date") for t in txns if t.get("expected_ship_date")),
                default=None,
            )
            deadline = _ship_deadline_str(ship_ts)
            if deadline and not r.get("is_shipped"):
                lines.append(deadline)

            item_blocks = []
            for t in txns:
                if not t.get("title"):
                    continue
                qty = t.get("quantity", 1)
                item_lines = [f"**{t['title']}" + (f" ×{qty}**" if qty > 1 else "**")]
                variations = t.get("selected_variations") or t.get("variations") or []
                for v in variations:
                    if v.get("formatted_name") and v.get("formatted_value"):
                        item_lines.append(f"  {v['formatted_name']}: {v['formatted_value']}")
                if msg := t.get("personalization_msg"):
                    item_lines.append(f"  📝 {msg}")
                item_blocks.append("\n".join(item_lines))

            if item_blocks:
                lines.append("")
                lines.extend(item_blocks)

            embed.add_field(
                name=buyer,
                value="\n".join(lines),
                inline=False,
            )
        footer = shop_name if total_pages == 1 else f"Page {page_num} of {total_pages} · {shop_name}"
        embed.set_footer(text=footer)
        pages.append(embed)
    return pages


_LISTINGS_PAGE_SIZE = 5


def _build_listings_pages(rows: list, shop_name: str) -> list[discord.Embed]:
    total = len(rows)
    total_pages = (total + _LISTINGS_PAGE_SIZE - 1) // _LISTINGS_PAGE_SIZE
    pages = []
    for page_num, i in enumerate(range(0, total, _LISTINGS_PAGE_SIZE), start=1):
        chunk = rows[i:i + _LISTINGS_PAGE_SIZE]
        embed = discord.Embed(
            title="Active Listings",
            description=f"{total} listing{'s' if total != 1 else ''}",
            color=discord.Color.blurple(),
        )
        for r in chunk:
            price = r["price_amount"] / (r["price_divisor"] or 100)
            currency = r["price_currency_code"] or "USD"
            qty = r["quantity"]
            stock = f"{qty} in stock" if qty > 0 else "Out of stock"
            title = r["title"]
            url = r["url"]
            name = f"[{title}]({url})" if url else title
            embed.add_field(
                name=name,
                value=f"${price:.2f} {currency} · {stock}",
                inline=False,
            )
        footer = shop_name if total_pages == 1 else f"Page {page_num} of {total_pages} · {shop_name}"
        embed.set_footer(text=footer)
        pages.append(embed)
    return pages


def _parse_weight_oz(weight_str: str) -> float | None:
    """Parse a weight string like '0.3lb', '4.8oz', or '5' (assumed oz). Returns oz or None."""
    s = weight_str.strip().lower()
    if s.endswith("lbs") or s.endswith("lb"):
        num_str = s.rstrip("slb")
        try:
            return float(num_str) * 16
        except ValueError:
            return None
    elif s.endswith("oz"):
        try:
            return float(s[:-2])
        except ValueError:
            return None
    else:
        try:
            return float(s)
        except ValueError:
            return None


def _parse_dims(dims_str: str) -> tuple[float, float, float] | None:
    """Parse a dims string like '4x3x1' (LxWxH in inches). Returns (l, w, h) or None."""
    parts = dims_str.strip().lower().split("x")
    if len(parts) != 3:
        return None
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None


class ShopkeepBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        # guild_id -> EtsyClient, populated on startup and when new guilds connect
        self.etsy_clients: dict[int, EtsyClient] = {}
        self._bootstrapped_guilds: set[int] = set()
        self._bootstrapped = False
        self._last_polled: dict[int, int] = {}
        self._poll_tick: int = 0

    async def setup_hook(self):
        db.DB_PATH = DB_PATH_ENV
        await db.init_db()

        loop = asyncio.get_running_loop()
        async with db.get_db() as conn:
            guilds = await db.get_connected_guilds(conn)
            for guild_row in guilds:
                tokens = await db.get_guild_tokens(conn, guild_row["guild_id"])
                if tokens:
                    self._register_client(
                        loop,
                        guild_row["guild_id"],
                        tokens["access_token"],
                        tokens["refresh_token"],
                        tokens["expires_at"],
                    )

        self._setup_slash_commands()
        await self.tree.sync()

    def _register_client(
        self,
        loop: asyncio.AbstractEventLoop,
        guild_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: int,
    ) -> EtsyClient:
        client = EtsyClient(
            api_key=ETSY_API_KEY,
            shared_secret=ETSY_SHARED_SECRET,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            on_token_refresh=self._make_refresh_callback(loop, guild_id),
        )
        self.etsy_clients[guild_id] = client
        return client

    def _make_refresh_callback(self, loop: asyncio.AbstractEventLoop, guild_id: int):
        def callback(access_token: str, refresh_token: str, expires_at: int):
            asyncio.run_coroutine_threadsafe(
                self._save_guild_tokens(guild_id, access_token, refresh_token, expires_at),
                loop,
            )
        return callback

    async def _save_guild_tokens(
        self, guild_id: int, access_token: str, refresh_token: str, expires_at: int
    ) -> None:
        async with db.get_db() as conn:
            await db.save_guild_tokens(conn, guild_id, access_token, refresh_token, expires_at)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def on_ready(self):
        print(f"Logged in as {self.user} | {len(self.etsy_clients)} shop(s) connected")
        # Sync commands to each guild immediately (guild sync is instant vs. up to 1h for global)
        for guild in self.guilds:
            await self.tree.sync(guild=guild)
        if not self._bootstrapped:
            self._bootstrapped = True
            await self._register_existing_guilds()
            async with db.get_db() as conn:
                guild_rows = await db.get_connected_guilds(conn)
            for row in guild_rows:
                try:
                    await self._bootstrap_guild(row["guild_id"], row["etsy_shop_id"])
                except Exception as exc:
                    print(f"[bootstrap] guild={row['guild_id']} {exc}")
                finally:
                    self._bootstrapped_guilds.add(row["guild_id"])
            self.poll_orders.start()

    async def _register_existing_guilds(self) -> None:
        """Create guild rows for any Discord servers the bot is already in but hasn't seen before.
        This handles guilds that were joined before multi-tenant support, or while the bot was offline.
        """
        for guild in self.guilds:
            async with db.get_db() as conn:
                existing = await db.get_guild(conn, guild.id)
                if existing:
                    continue
                setup_token = secrets.token_urlsafe(16)
                setup_token_exp = int(time.time()) + SETUP_TOKEN_TTL
                await db.create_guild(conn, guild.id, guild.name, setup_token, setup_token_exp)
                await conn.commit()

            print(f"[register] New guild found: '{guild.name}' ({guild.id})")
            if WEB_BASE_URL and guild.owner:
                try:
                    setup_url = f"{WEB_BASE_URL}/connect/{setup_token}"
                    embed = build_welcome_embed(guild.name, setup_url)
                    await guild.owner.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def on_guild_join(self, guild: discord.Guild):
        setup_token = secrets.token_urlsafe(16)
        setup_token_exp = int(time.time()) + SETUP_TOKEN_TTL

        async with db.get_db() as conn:
            await db.create_guild(conn, guild.id, guild.name, setup_token, setup_token_exp)
            await conn.commit()

        print(f"[guild_join] Joined '{guild.name}' ({guild.id})")

        if WEB_BASE_URL and guild.owner:
            try:
                setup_url = f"{WEB_BASE_URL}/connect/{setup_token}"
                embed = build_welcome_embed(guild.name, setup_url)
                await guild.owner.send(embed=embed)
            except discord.Forbidden:
                pass  # Owner has DMs disabled

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    async def _bootstrap_guild(self, guild_id: int, shop_id: int) -> str:
        etsy = self.etsy_clients.get(guild_id)
        if not etsy:
            return ""

        print(f"[bootstrap] guild={guild_id} shop={shop_id}")
        loop = asyncio.get_running_loop()

        shop_data = await loop.run_in_executor(None, lambda: etsy.get_shop(shop_id))
        listings_resp = await loop.run_in_executor(
            None, lambda: etsy.get_shop_listings(shop_id, limit=100)
        )
        receipts_resp = await loop.run_in_executor(
            None, lambda: etsy.get_shop_receipts(shop_id, limit=100)
        )
        reviews_resp = await loop.run_in_executor(
            None, lambda: etsy.get_shop_reviews(shop_id, limit=100)
        )

        listings = listings_resp.get("results", [])
        receipts = receipts_resp.get("results", [])
        reviews = reviews_resp.get("results", [])

        async with db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)
            await db.upsert_listings(conn, listings)
            for receipt in receipts:
                receipt.setdefault("shop_id", shop_id)
                await db.upsert_receipt(conn, receipt, already_seen=True)
                await db.upsert_transactions(
                    conn, receipt["receipt_id"], shop_id, receipt.get("transactions", [])
                )
            for review in reviews:
                review["shop_id"] = shop_id
                await db.upsert_review(conn, review, already_seen=True)
            await conn.commit()

        shop_name = shop_data.get("shop_name", "")
        print(
            f"[bootstrap] Done — '{shop_name}', "
            f"{len(listings)} listing(s), {len(receipts)} existing receipt(s) marked seen, "
            f"{len(reviews)} existing review(s) marked seen."
        )
        return shop_name

    # ── Poll loop ─────────────────────────────────────────────────────────────

    @tasks.loop(seconds=POLL_INTERVAL_SECS)
    async def poll_orders(self):
        loop = asyncio.get_running_loop()
        async with db.get_db() as conn:
            guild_rows = await db.get_connected_guilds(conn)
            for row in guild_rows:
                guild_id = row["guild_id"]
                tokens = await db.get_guild_tokens(conn, guild_id)
                if not tokens:
                    continue
                existing = self.etsy_clients.get(guild_id)
                if existing is None or existing.access_token != tokens["access_token"]:
                    self._register_client(
                        loop, guild_id,
                        tokens["access_token"], tokens["refresh_token"], tokens["expires_at"],
                    )

        for row in guild_rows:
            guild_id = row["guild_id"]
            if guild_id in self.etsy_clients and guild_id not in self._bootstrapped_guilds:
                try:
                    shop_name = await self._bootstrap_guild(guild_id, row["etsy_shop_id"])
                    if shop_name:
                        if row["order_channel_id"]:
                            channel = self.get_channel(row["order_channel_id"])
                            if channel:
                                await channel.send(embed=build_connected_embed(shop_name))
                        else:
                            guild = self.get_guild(guild_id)
                            if guild and guild.owner:
                                try:
                                    await guild.owner.send(embed=build_connected_embed(shop_name, no_channel=True))
                                except discord.Forbidden:
                                    pass
                except Exception as exc:
                    print(f"[poller] bootstrap guild={guild_id} {exc}")
                finally:
                    self._bootstrapped_guilds.add(guild_id)

        self._poll_tick += 1

        await asyncio.gather(*(
            self._safe_poll_guild(row["guild_id"], row["etsy_shop_id"], row["order_channel_id"])
            for row in guild_rows
        ))

    async def _safe_poll_guild(self, guild_id: int, shop_id: int, channel_id: int) -> None:
        try:
            await self._poll_guild(guild_id, shop_id, channel_id)
        except Exception as exc:
            print(f"[poller] guild={guild_id} {exc}")

    @poll_orders.before_loop
    async def before_poll(self):
        await self.wait_until_ready()

    async def _poll_guild(self, guild_id: int, shop_id: int, channel_id: int) -> None:
        etsy = self.etsy_clients.get(guild_id)
        if not etsy:
            return

        loop = asyncio.get_running_loop()
        shop_data = await loop.run_in_executor(None, lambda: etsy.get_shop(shop_id))
        response = await loop.run_in_executor(
            None, lambda: etsy.get_shop_receipts(shop_id, limit=50)
        )
        listings_resp = await loop.run_in_executor(
            None, lambda: etsy.get_shop_listings(shop_id, limit=100)
        )
        receipts = response.get("results", [])
        listings = listings_resp.get("results", [])
        raw_by_id = {r["receipt_id"]: r for r in receipts}
        channel = self.get_channel(channel_id)
        shop_name = shop_data.get("shop_name", "My Shop")

        async with db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)

            # Snapshot listing quantities before upsert to detect zero-crossings
            listing_ids = [l["listing_id"] for l in listings]
            qty_snapshot = await db.get_listing_quantity_snapshot(conn, listing_ids)
            await db.upsert_listings(conn, listings)
            await conn.commit()

            if channel:
                for listing in listings:
                    lid = listing["listing_id"]
                    old_qty = qty_snapshot.get(lid)
                    new_qty = listing.get("quantity", 0)
                    # Only fire if listing was previously known (old_qty is not None),
                    # had stock, and now has none
                    if old_qty is not None and old_qty > 0 and new_qty == 0:
                        first_image = (listing.get("images") or [{}])[0]
                        listing_row = {
                            "listing_id": lid,
                            "title": listing.get("title", ""),
                            "url": listing.get("url"),
                            "image_url": first_image.get("url_75x75") or first_image.get("url_170x135"),
                        }
                        await channel.send(embed=build_out_of_stock_embed(listing_row, shop_name))

            # Snapshot status before upserting so we can detect changes
            receipt_ids = [r["receipt_id"] for r in receipts]
            old_snapshot = await db.get_receipts_status_snapshot(conn, receipt_ids)

            for receipt in receipts:
                receipt.setdefault("shop_id", shop_id)
                await db.upsert_receipt(conn, receipt)
                await db.upsert_transactions(
                    conn, receipt["receipt_id"], shop_id, receipt.get("transactions", [])
                )
            await conn.commit()

            # Post status change notifications for already-seen receipts
            if channel:
                for receipt in receipts:
                    rid = receipt["receipt_id"]
                    old = old_snapshot.get(rid)
                    if old is None:
                        continue  # New receipt — handled by unnotified flow below
                    new_shipped = 1 if receipt.get("is_shipped") else 0
                    new_status = receipt.get("status", "")
                    if not old["is_shipped"] and new_shipped:
                        await channel.send(embed=build_status_change_embed(receipt, shop_name, "shipped"))
                    elif old["status"] != "canceled" and new_status == "canceled":
                        await channel.send(embed=build_status_change_embed(receipt, shop_name, "canceled"))

            unnotified = await db.get_unnotified_receipts(conn, shop_id)
            for row in unnotified:
                if channel:
                    raw = raw_by_id.get(row["receipt_id"], {})
                    returning = await db.is_returning_buyer(
                        conn, shop_id, row["buyer_user_id"], row["receipt_id"]
                    )
                    embed = build_order_embed(
                        dict(row),
                        shop_name=shop_name,
                        new=True,
                        transactions=raw.get("transactions", []),
                        returning=returning,
                    )
                    await channel.send(embed=embed)
                    await db.mark_receipt_notified(conn, row["receipt_id"])
                    await conn.commit()

            await self._check_backlog(conn, guild_id, shop_id, channel, shop_name)
            await self._check_goal_milestones(conn, guild_id, shop_id, channel, shop_name)
            await self._check_digest(conn, guild_id, shop_id, channel, shop_name)
            await self._check_shipping_reminders(conn, guild_id, shop_id, channel, shop_name)
            await self._check_new_reviews(conn, guild_id, shop_id, channel, shop_name)

        self._last_polled[guild_id] = int(time.time())

    async def _check_digest(
        self,
        conn,
        guild_id: int,
        shop_id: int,
        channel,
        shop_name: str,
    ) -> None:
        """Post the daily digest at the configured time, at most once per day."""
        config = await db.get_digest_config(conn, guild_id)
        if not config or channel is None:
            return

        try:
            tz = zoneinfo.ZoneInfo(config["tz"])
        except zoneinfo.ZoneInfoNotFoundError:
            tz = datetime.timezone.utc

        now_local = datetime.datetime.now(tz)
        h, m = map(int, config["time"].split(":"))
        target = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now_local - target).total_seconds())
        if diff > POLL_INTERVAL_SECS / 2:
            return

        # Don't send more than once per day (23h cooldown)
        last_sent = config["last_sent"]
        now_ts = int(time.time())
        if last_sent and (now_ts - last_sent) < 23 * 3600:
            return

        # Gather digest data
        since_24h = now_ts - 86400
        receipts_24h = await db.get_receipts_since(conn, shop_id, since_24h)
        order_count = len(receipts_24h)
        revenue = sum(
            r["grandtotal_amount"] / (r["grandtotal_divisor"] or 100)
            for r in receipts_24h
        )
        currency = (
            receipts_24h[0]["grandtotal_currency"]
            if receipts_24h
            else await db.get_shop_currency(conn, shop_id)
        )
        open_count = await db.get_open_order_count(conn, shop_id)
        due_soon = await db.get_receipts_due_within(conn, shop_id, within_seconds=2 * 86400, now=now_ts)

        # Include goal progress if configured
        goal_amount = goal_current = goal_pct = None
        goal_config = await db.get_goal_config(conn, guild_id)
        if goal_config:
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            month_start = datetime.datetime(now_dt.year, now_dt.month, 1, tzinfo=datetime.timezone.utc)
            month_receipts = await db.get_receipts_since(conn, shop_id, int(month_start.timestamp()))
            goal_current = sum(r["grandtotal_amount"] / (r["grandtotal_divisor"] or 100) for r in month_receipts)
            goal_amount = goal_config["amount_cents"] / 100
            goal_pct = int(goal_current / goal_amount * 100) if goal_amount > 0 else 0

        await channel.send(
            embed=build_digest_embed(
                orders_24h=order_count,
                revenue_24h=revenue,
                currency=currency,
                open_count=open_count,
                due_soon=[dict(r) for r in due_soon],
                shop_name=shop_name,
                goal_amount=goal_amount,
                goal_current=goal_current,
                goal_pct=goal_pct,
            )
        )
        await db.mark_digest_sent(conn, guild_id, now_ts)
        await conn.commit()

    async def _check_goal_milestones(
        self,
        conn,
        guild_id: int,
        shop_id: int,
        channel,
        shop_name: str,
    ) -> None:
        """Fire milestone notifications when monthly revenue crosses 25/50/75/100% of the goal."""
        config = await db.get_goal_config(conn, guild_id)
        if not config or channel is None:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        current_month = now.strftime("%Y-%m")

        # Reset milestones at the start of a new month
        milestones_sent = config["milestones_sent"]
        if config["month"] != current_month:
            milestones_sent = []

        # Monthly revenue: sum receipts from the first of this month
        month_start = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc)
        receipts = await db.get_receipts_since(conn, shop_id, int(month_start.timestamp()))
        if not receipts:
            if config["month"] != current_month:
                await db.update_goal_milestones(conn, guild_id, [], current_month)
                await conn.commit()
            return

        revenue = sum(r["grandtotal_amount"] / (r["grandtotal_divisor"] or 100) for r in receipts)
        currency = receipts[0]["grandtotal_currency"]
        goal_dollars = config["amount_cents"] / 100
        pct = int(revenue / goal_dollars * 100) if goal_dollars > 0 else 0

        # Days left in month
        import calendar
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        days_left = days_in_month - now.day

        month_name = now.strftime("%B")

        newly_sent = list(milestones_sent)
        for milestone in [25, 50, 75, 100]:
            if pct >= milestone and milestone not in milestones_sent:
                await channel.send(
                    embed=build_goal_milestone_embed(
                        milestone_pct=milestone,
                        current=revenue,
                        goal=goal_dollars,
                        currency=currency,
                        month_name=month_name,
                        days_left=days_left,
                        shop_name=shop_name,
                    )
                )
                newly_sent.append(milestone)

        if newly_sent != milestones_sent or config["month"] != current_month:
            await db.update_goal_milestones(conn, guild_id, newly_sent, current_month)
            await conn.commit()

    async def _check_backlog(
        self,
        conn,
        guild_id: int,
        shop_id: int,
        channel,
        shop_name: str,
    ) -> None:
        """Post a one-time warning when open unshipped orders exceed the configured threshold."""
        config = await db.get_backlog_config(conn, guild_id)
        if not config or channel is None:
            return

        threshold = config["threshold"]
        warned = config["warned"]
        count = await db.get_open_order_count(conn, shop_id)

        if count >= threshold and not warned:
            await channel.send(embed=build_backlog_embed(count, threshold, shop_name))
            await db.set_backlog_warned(conn, guild_id, True)
            await conn.commit()
        elif count < threshold and warned:
            # Backlog cleared — reset so warning can fire again next time
            await db.set_backlog_warned(conn, guild_id, False)
            await conn.commit()

    async def _check_shipping_reminders(
        self,
        conn,
        guild_id: int,
        shop_id: int,
        channel,
        shop_name: str,
    ) -> None:
        """Post shipping deadline reminders for open orders approaching their ship date."""
        config = await db.get_guild_reminder_config(conn, guild_id)
        if not config or channel is None:
            return

        # If a time-of-day is configured, only fire during the poll window that contains it
        if config["time"] and config["tz"]:
            try:
                tz = zoneinfo.ZoneInfo(config["tz"])
            except zoneinfo.ZoneInfoNotFoundError:
                tz = datetime.timezone.utc
            now_local = datetime.datetime.now(tz)
            h, m = map(int, config["time"].split(":"))
            target = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
            diff = abs((now_local - target).total_seconds())
            if diff > POLL_INTERVAL_SECS / 2:
                return

        reminder_days = config["days"]
        try:
            reminder_tz = zoneinfo.ZoneInfo(config.get("tz") or "UTC")
        except zoneinfo.ZoneInfoNotFoundError:
            reminder_tz = datetime.timezone.utc
        today_local = datetime.datetime.now(reminder_tz).date()
        for days_before in reminder_days:
            target_date = today_local + datetime.timedelta(days=days_before)
            day_start = datetime.datetime(target_date.year, target_date.month, target_date.day, tzinfo=reminder_tz)
            day_end = day_start + datetime.timedelta(days=1)
            lower = int(day_start.timestamp())
            upper = int(day_end.timestamp())
            pending = await db.get_pending_reminders(conn, shop_id, days_before, lower, upper)
            for row in pending:
                txns = await db.get_receipt_transactions(conn, row["receipt_id"])
                embed = build_shipping_reminder_embed(dict(row), shop_name, days_before, transactions=txns)
                await channel.send(embed=embed)
                await db.mark_reminder_sent(conn, row["receipt_id"], days_before)
                await conn.commit()

    async def _check_new_reviews(
        self,
        conn,
        guild_id: int,
        shop_id: int,
        channel,
        shop_name: str,
    ) -> None:
        """Fetch recent reviews, store any new ones, and post notifications.

        The API call is only made every 5th poll cycle (~5 minutes) to conserve
        API budget. Unnotified rows accumulated in the interim are still flushed
        every cycle.
        """
        etsy = self.etsy_clients.get(guild_id)
        if not etsy or channel is None:
            return
        loop = asyncio.get_running_loop()

        if self._poll_tick % 5 == 0:
            try:
                response = await loop.run_in_executor(
                    None, lambda: etsy.get_shop_reviews(shop_id, limit=25)
                )
            except Exception as exc:
                print(f"[poller] reviews guild={guild_id} {exc}")
                return
            reviews = response.get("results", [])
            for review in reviews:
                review["shop_id"] = shop_id
                await db.upsert_review(conn, review)
            await conn.commit()

        unnotified = await db.get_unnotified_reviews(conn, shop_id)
        for row in unnotified:
            embed = build_review_embed(
                dict(row), shop_name=shop_name, listing_title=row["listing_title"]
            )
            await channel.send(embed=embed)
            await db.mark_review_notified(conn, row["transaction_id"])
            await conn.commit()

    # ── Commands ──────────────────────────────────────────────────────────────

    def _setup_slash_commands(self) -> None:
        tree = self.tree

        @tree.command(name="help", description="List all Shopkeep commands")
        async def help_cmd(interaction: discord.Interaction):
            await self._cmd_help(interaction)

        @tree.command(name="status", description="Show Etsy connection and notification channel")
        async def status(interaction: discord.Interaction):
            await self._cmd_status(interaction)

        @tree.command(name="setchannel", description="Set this channel for order notifications")
        async def setchannel(interaction: discord.Interaction):
            await self._cmd_setchannel(interaction)

        @tree.command(name="shop", description="Show your Etsy shop info")
        async def shop(interaction: discord.Interaction):
            await self._cmd_shop(interaction)

        @tree.command(name="orders", description="Show orders from your Etsy shop")
        @discord.app_commands.describe(
            days="Number of days to look back (default: 30)",
            status="Which orders to show (default: open only)",
        )
        @discord.app_commands.choices(status=[
            discord.app_commands.Choice(name="Unpaid/Unshipped (default)", value="open"),
            discord.app_commands.Choice(name="All", value="all"),
            discord.app_commands.Choice(name="Completed", value="completed"),
            discord.app_commands.Choice(name="Canceled", value="canceled"),
        ])
        async def orders(interaction: discord.Interaction, days: int = 30, status: str = "open"):
            await self._cmd_orders(interaction, days=days, status_filter=status)

        @tree.command(name="disconnect", description="Unlink your Etsy shop from this server")
        async def disconnect(interaction: discord.Interaction):
            await self._cmd_disconnect(interaction)

        @tree.command(name="listings", description="Browse your active Etsy listings")
        async def listings(interaction: discord.Interaction):
            await self._cmd_listings(interaction)

        @tree.command(name="revenue", description="Show revenue summary for a time period")
        @discord.app_commands.describe(period="Time period to summarize (default: this month)")
        @discord.app_commands.choices(period=[
            discord.app_commands.Choice(name="Today", value="today"),
            discord.app_commands.Choice(name="This week", value="this_week"),
            discord.app_commands.Choice(name="This month", value="this_month"),
        ])
        async def revenue(interaction: discord.Interaction, period: str = "this_month"):
            await self._cmd_revenue(interaction, period=period)

        preset_group = discord.app_commands.Group(name="preset", description="Manage shipping presets")

        @preset_group.command(name="add", description="Save a new shipping preset")
        @discord.app_commands.describe(
            name="Preset name (e.g. small-jewelry)",
            carrier="Shipping carrier",
            mail_class="Shipping service (e.g. 'Priority Mail', 'First Class', 'Ground')",
            weight="Package weight (e.g. 0.3lb or 4.8oz)",
            dims="Package dimensions LxWxH in inches (e.g. 4x3x1)",
            package_type="Package type (optional, e.g. PACKAGE, FLAT_RATE_ENVELOPE)",
        )
        @discord.app_commands.choices(carrier=[
            discord.app_commands.Choice(name="USPS", value="USPS"),
            discord.app_commands.Choice(name="UPS", value="UPS"),
            discord.app_commands.Choice(name="FedEx", value="FedEx"),
        ])
        @discord.app_commands.choices(package_type=[
            discord.app_commands.Choice(name=label, value=value)
            for value, label in _PACKAGE_TYPES
        ])
        async def preset_add(
            interaction: discord.Interaction,
            name: str,
            carrier: str,
            mail_class: str,
            weight: str,
            dims: str,
            package_type: str = "",
        ):
            await self._cmd_preset_add(
                interaction, name=name, carrier=carrier, mail_class=mail_class,
                weight=weight, dims=dims, package_type=package_type,
            )

        @preset_group.command(name="list", description="List all saved shipping presets")
        async def preset_list(interaction: discord.Interaction):
            await self._cmd_preset_list(interaction)

        @preset_group.command(name="remove", description="Delete a saved shipping preset")
        @discord.app_commands.describe(name="Name of the preset to remove")
        async def preset_remove(interaction: discord.Interaction, name: str):
            await self._cmd_preset_remove(interaction, name=name)

        tree.add_command(preset_group)

        reminders_group = discord.app_commands.Group(
            name="reminders",
            description="Set reminders for when orders are due to ship",
        )

        @reminders_group.command(
            name="set",
            description="Enable shipping reminders for orders approaching their ship date",
        )
        @discord.app_commands.describe(
            days='Days before shipping deadline to remind you (0=today, 1=tomorrow). E.g. "0,1,2"',
        )
        async def reminders_set(interaction: discord.Interaction, days: str):
            await self._cmd_reminders_set(interaction, days=days)

        @reminders_group.command(
            name="time",
            description="Set the time of day reminders fire (default: any poll cycle)",
        )
        @discord.app_commands.describe(
            time="Time in HH:MM format (24-hour), e.g. 09:00",
            timezone="Timezone name (e.g. America/New_York). Use autocomplete to find yours.",
        )
        @discord.app_commands.autocomplete(timezone=self._autocomplete_timezone)
        async def reminders_time(interaction: discord.Interaction, time: str, timezone: str):
            await self._cmd_reminders_time(interaction, time=time, timezone=timezone)

        @reminders_group.command(
            name="off",
            description="Disable all shipping deadline reminders for this server",
        )
        async def reminders_disable(interaction: discord.Interaction):
            await self._cmd_reminders_disable(interaction)

        @reminders_group.command(
            name="status",
            description="Show the current shipping reminder configuration for this server",
        )
        async def reminders_status(interaction: discord.Interaction):
            await self._cmd_reminders_status(interaction)

        tree.add_command(reminders_group)

        backlog_group = discord.app_commands.Group(
            name="backlog",
            description="Configure the order backlog warning",
        )

        @backlog_group.command(name="set", description="Warn when open orders exceed a threshold")
        @discord.app_commands.describe(threshold="Number of open orders that triggers a warning")
        async def backlog_set(interaction: discord.Interaction, threshold: int):
            await self._cmd_backlog_set(interaction, threshold=threshold)

        @backlog_group.command(name="off", description="Disable the order backlog warning")
        async def backlog_off(interaction: discord.Interaction):
            await self._cmd_backlog_off(interaction)

        @backlog_group.command(name="status", description="Show the current backlog warning configuration")
        async def backlog_status(interaction: discord.Interaction):
            await self._cmd_backlog_status(interaction)

        tree.add_command(backlog_group)

        digest_group = discord.app_commands.Group(
            name="digest",
            description="Configure the daily order digest",
        )

        @digest_group.command(name="on", description="Enable the daily digest (default: 9:00 AM UTC)")
        async def digest_on(interaction: discord.Interaction):
            await self._cmd_digest_on(interaction)

        @digest_group.command(name="time", description="Set the time the daily digest is posted")
        @discord.app_commands.describe(
            time="Delivery time in HH:MM format (24-hour), e.g. 09:00",
            timezone="Timezone name (e.g. America/New_York). Use autocomplete to find yours.",
        )
        @discord.app_commands.autocomplete(timezone=self._autocomplete_timezone)
        async def digest_time(interaction: discord.Interaction, time: str, timezone: str):
            await self._cmd_digest_time(interaction, time=time, timezone=timezone)

        @digest_group.command(name="off", description="Disable the daily digest")
        async def digest_off(interaction: discord.Interaction):
            await self._cmd_digest_off(interaction)

        @digest_group.command(name="status", description="Show the current daily digest configuration")
        async def digest_status(interaction: discord.Interaction):
            await self._cmd_digest_status(interaction)

        tree.add_command(digest_group)

        goal_group = discord.app_commands.Group(
            name="goal",
            description="Set and track a monthly revenue goal",
        )

        @goal_group.command(name="set", description="Set a monthly revenue goal")
        @discord.app_commands.describe(amount="Target revenue in dollars (e.g. 500)")
        async def goal_set(interaction: discord.Interaction, amount: int):
            await self._cmd_goal_set(interaction, amount=amount)

        @goal_group.command(name="status", description="Show current progress toward your monthly goal")
        async def goal_status(interaction: discord.Interaction):
            await self._cmd_goal_status(interaction)

        @goal_group.command(name="off", description="Remove the monthly revenue goal")
        async def goal_off(interaction: discord.Interaction):
            await self._cmd_goal_off(interaction)

        tree.add_command(goal_group)

        @tree.command(name="bestsellers", description="Show top listings by units or revenue (this month / year / all-time)")
        @discord.app_commands.describe(
            period="Time period (default: this month)",
            ranked_by="Rank by units sold or revenue (default: units)",
        )
        @discord.app_commands.choices(
            period=[
                discord.app_commands.Choice(name="This month", value="this_month"),
                discord.app_commands.Choice(name="This year", value="this_year"),
                discord.app_commands.Choice(name="All time", value="all_time"),
            ],
            ranked_by=[
                discord.app_commands.Choice(name="Units sold", value="units"),
                discord.app_commands.Choice(name="Revenue", value="revenue"),
            ],
        )
        async def bestsellers(
            interaction: discord.Interaction,
            period: str = "this_month",
            ranked_by: str = "units",
        ):
            await self._cmd_bestsellers(interaction, period=period, ranked_by=ranked_by)

        @tree.command(name="label", description="Buy a shipping label for one or more orders")
        @discord.app_commands.describe(
            receipt_ids="Order receipt ID(s) — omit to pick from a list, or comma-separate for batch",
            preset="Shipping preset to use — skips manual entry",
        )
        @discord.app_commands.autocomplete(
            receipt_ids=self._autocomplete_labelable_receipt,
            preset=self._autocomplete_preset,
        )
        async def label(
            interaction: discord.Interaction,
            receipt_ids: str = "",
            preset: str = "",
        ):
            await self._cmd_label(interaction, receipt_ids=receipt_ids, preset=preset)

    async def _autocomplete_labelable_receipt(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            if not guild_row or not guild_row["etsy_shop_id"]:
                return []
            rows = await db.get_labelable_receipts(conn, guild_row["etsy_shop_id"])

        current = current.strip()
        # Support comma-separated input: autocomplete only the last segment
        prefix, _, stem = current.rpartition(",")
        stem = stem.strip()

        choices = []
        for row in rows:
            rid = str(row["receipt_id"])
            buyer = row["name"] or "Unknown buyer"
            display = f"#{rid} — {buyer}"
            if stem and stem not in rid and stem.lower() not in buyer.lower():
                continue
            value = f"{prefix},{rid}".lstrip(",") if prefix else rid
            choices.append(discord.app_commands.Choice(name=display[:100], value=value))
        return choices[:25]

    async def _autocomplete_preset(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        async with db.get_db() as conn:
            presets = await db.list_presets(conn, interaction.guild_id)
        current_lower = current.lower()
        return [
            discord.app_commands.Choice(name=p["name"], value=p["name"])
            for p in presets
            if current_lower in p["name"].lower()
        ][:25]

    async def _cmd_help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Shopkeep Commands", color=discord.Color.blurple())
        sections = [
            ("/help", "List all commands"),
            ("/status", "Show Etsy connection and notification channel"),
            ("/setchannel", "Set this channel for order notifications"),
            ("/shop", "Show your Etsy shop info"),
            ("/orders [days] [status]", "Show orders (default: last 30 days, unpaid/unshipped only)"),
            ("/disconnect", "Unlink your Etsy shop from this server"),
            ("/revenue [period]", "Show revenue summary (default: this month)"),
            ("/listings", "Browse your active Etsy listings"),
            ("/bestsellers [period] [ranked_by]", "Top listings by units or revenue (this month / year / all-time)"),
            ("/label [receipt_ids] [preset]", "Buy shipping labels — omit receipt IDs to pick from a list"),
            ("/preset add/list/remove", "Manage shipping presets — save carrier, mail class, weight, and dimensions for reuse with `/label`"),
            ("/reminders set/time/off/status", "Configure shipping deadline reminders"),
            ("/backlog set/off/status", "Alert when open unshipped orders exceed a threshold"),
            ("/digest on/time/off/status", "Configure the daily order digest"),
            ("/goal set/status/off", "Set and track a monthly revenue goal"),
        ]
        for name, desc in sections:
            embed.add_field(name=name, value=desc, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _cmd_setchannel(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "You need the **Manage Channels** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.update_guild_channel(conn, interaction.guild_id, interaction.channel_id)
            await conn.commit()

        await interaction.response.send_message(
            f"Order notifications will be posted in <#{interaction.channel_id}>.",
            ephemeral=True,
        )

    async def _cmd_status(self, interaction: discord.Interaction) -> None:
        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            shop_row = None
            if guild_row and guild_row["etsy_shop_id"]:
                cursor = await conn.execute(
                    "SELECT shop_name, url FROM shops WHERE shop_id = ?",
                    (guild_row["etsy_shop_id"],),
                )
                shop_row = await cursor.fetchone()
            reminder_config = await db.get_guild_reminder_config(conn, interaction.guild_id)
            backlog_config = await db.get_backlog_config(conn, interaction.guild_id)
            digest_config = await db.get_digest_config(conn, interaction.guild_id)
            goal_config = await db.get_goal_config(conn, interaction.guild_id)

        if not guild_row:
            await interaction.response.send_message(
                "This server hasn't been set up yet. Add Shopkeep via the website.",
                ephemeral=True,
            )
            return

        shop_id = guild_row["etsy_shop_id"]
        channel_id = guild_row["order_channel_id"]

        embed = discord.Embed(title="Shopkeep Status", color=discord.Color.blurple())

        if shop_id and shop_row:
            shop_name = shop_row["shop_name"]
            shop_url = shop_row["url"]
            etsy_value = f"[{shop_name}]({shop_url})" if shop_url else shop_name
        elif shop_id:
            etsy_value = f"Connected (shop ID: {shop_id})"
        else:
            etsy_value = "Not connected"
        embed.add_field(name="Etsy Shop", value=etsy_value, inline=True)

        embed.add_field(
            name="Notifications",
            value=f"<#{channel_id}>" if channel_id else "Not set — use `/setchannel`",
            inline=True,
        )

        last_poll = self._last_polled.get(interaction.guild_id)
        if last_poll:
            embed.add_field(name="Last Poll", value=f"<t:{last_poll}:R>", inline=True)

        if WEB_BASE_URL and not shop_id:
            token = guild_row["setup_token"]
            exp = guild_row["setup_token_exp"] or 0
            if not token or exp < int(time.time()):
                token = secrets.token_urlsafe(16)
                exp = int(time.time()) + SETUP_TOKEN_TTL
                async with db.get_db() as conn:
                    await db.refresh_setup_token(conn, guild_row["guild_id"], token, exp)
                    await conn.commit()
            embed.add_field(
                name="Setup",
                value=f"[Connect your Etsy shop]({WEB_BASE_URL}/connect/{token})",
                inline=False,
            )

        feature_lines = []
        if reminder_config:
            threshold_labels = {0: "today", 1: "tomorrow"}
            day_labels = [threshold_labels.get(d, f"{d}d out") for d in reminder_config["days"]]
            feature_lines.append(f"Reminders: {', '.join(day_labels)}")
        else:
            feature_lines.append("Reminders: off")
        if backlog_config:
            feature_lines.append(f"Backlog warning: ≥{backlog_config['threshold']} orders")
        else:
            feature_lines.append("Backlog warning: off")
        if digest_config:
            feature_lines.append(f"Daily digest: {digest_config['time']} {digest_config['tz']}")
        else:
            feature_lines.append("Daily digest: off")
        if goal_config:
            feature_lines.append(f"Monthly goal: ${goal_config['amount_cents'] // 100:,}")
        else:
            feature_lines.append("Monthly goal: off")
        embed.add_field(name="Features", value="\n".join(feature_lines), inline=False)

        await interaction.response.send_message(embed=embed)

    async def _cmd_shop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        etsy, shop_id = await self._get_etsy_client(interaction)
        if not etsy:
            return
        loop = asyncio.get_running_loop()
        try:
            shop_data = await loop.run_in_executor(None, lambda: etsy.get_shop(shop_id))
        except Exception as exc:
            print(f"[shop] guild={interaction.guild_id} {exc}")
            await interaction.followup.send(
                "Couldn't reach Etsy right now. Try again in a moment — if it keeps failing, run `/status` to check your connection.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(embed=build_shop_embed(shop_data))

    async def _cmd_orders(
        self, interaction: discord.Interaction, days: int = 30, status_filter: str = "open"
    ) -> None:
        await interaction.response.defer()
        etsy, shop_id = await self._get_etsy_client(interaction)
        if not etsy:
            return
        loop = asyncio.get_running_loop()
        min_created = int(time.time()) - days * 24 * 3600
        try:
            shop_data = await loop.run_in_executor(None, lambda: etsy.get_shop(shop_id))
            response = await loop.run_in_executor(
                None, lambda: etsy.get_shop_receipts(shop_id, limit=50, min_created=min_created)
            )
        except Exception as exc:
            print(f"[orders] guild={interaction.guild_id} {exc}")
            await interaction.followup.send(
                "Couldn't reach Etsy right now. Try again in a moment — if it keeps failing, run `/status` to check your connection.",
                ephemeral=True,
            )
            return

        all_receipts = response.get("results", [])
        if status_filter == "open":
            receipts = [r for r in all_receipts if (r.get("status") or "").lower() not in ("completed", "canceled")]
        elif status_filter == "completed":
            receipts = [r for r in all_receipts if (r.get("status") or "").lower() == "completed"]
        elif status_filter == "canceled":
            receipts = [r for r in all_receipts if (r.get("status") or "").lower() == "canceled"]
        else:
            receipts = all_receipts

        shop_name = shop_data.get("shop_name", "My Shop")

        if not receipts:
            label = f"{status_filter} " if status_filter != "all" else ""
            await interaction.followup.send(f"No {label}orders in the last {days} days.", ephemeral=True)
            return

        total_cents = sum((r.get("grandtotal") or {}).get("amount", 0) for r in receipts)
        divisor = (receipts[0].get("grandtotal") or {}).get("divisor") or 100
        currency = (receipts[0].get("grandtotal") or {}).get("currency_code", "USD")
        revenue_str = f"${total_cents / divisor:.2f} {currency}"

        pages = _build_orders_pages(receipts, shop_name, revenue_str=revenue_str)
        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            view = OrdersView(pages)
            msg = await interaction.followup.send(embed=pages[0], view=view)
            view.message = msg

    async def _cmd_disconnect(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)

        if not guild_row or not guild_row["etsy_shop_id"]:
            await interaction.response.send_message(
                "No Etsy shop is connected to this server.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            cursor = await conn.execute(
                "SELECT shop_name FROM shops WHERE shop_id = ?", (guild_row["etsy_shop_id"],)
            )
            shop_row = await cursor.fetchone()
        shop_name = shop_row["shop_name"] if shop_row else f"shop #{guild_row['etsy_shop_id']}"

        embed = discord.Embed(
            title="Disconnect Etsy Shop?",
            description=(
                f"This will unlink **{shop_name}** from this server, stop all order notifications, "
                "and delete your stored OAuth tokens.\n\n"
                "You can reconnect at any time using `/status`."
            ),
            color=discord.Color.red(),
        )
        view = ConfirmDisconnectView(self, interaction.guild_id, shop_name, guild_row["order_channel_id"])
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _cmd_listings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)

        if not guild_row or not guild_row["etsy_shop_id"]:
            await interaction.followup.send("No Etsy shop connected.")
            return

        async with db.get_db() as conn:
            rows = await db.get_active_listings(conn, guild_row["etsy_shop_id"])
            cursor = await conn.execute(
                "SELECT shop_name FROM shops WHERE shop_id = ?", (guild_row["etsy_shop_id"],)
            )
            shop_row = await cursor.fetchone()

        shop_name = shop_row["shop_name"] if shop_row else "My Shop"

        if not rows:
            await interaction.followup.send(
                "No active listings found. Make sure you have active listings on Etsy — data syncs every 60 seconds."
            )
            return

        pages = _build_listings_pages(rows, shop_name)
        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            await interaction.followup.send(embed=pages[0], view=OrdersView(pages))

    async def _cmd_revenue(self, interaction: discord.Interaction, period: str = "this_month") -> None:
        await interaction.response.defer(ephemeral=True)

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)

        if not guild_row or not guild_row["etsy_shop_id"]:
            await interaction.followup.send("No Etsy shop connected.")
            return

        shop_id = guild_row["etsy_shop_id"]

        now = datetime.datetime.now(datetime.timezone.utc)
        if period == "today":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
            label = f"Today · {now.strftime('%B %d, %Y')}"
        elif period == "this_week":
            since = (now - datetime.timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            label = f"This Week · {since.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
        else:
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            label = f"This Month · {now.strftime('%B %Y')}"

        async with db.get_db() as conn:
            rows = await db.get_receipts_since(conn, shop_id, int(since.timestamp()))

        order_count = len(rows)
        if order_count == 0:
            await interaction.followup.send(f"No orders found for {label}.")
            return

        total_amount = sum(r["grandtotal_amount"] for r in rows)
        divisor = rows[0]["grandtotal_divisor"] or 100
        currency = rows[0]["grandtotal_currency"] or "USD"
        total = total_amount / divisor
        avg = total / order_count

        embed = discord.Embed(title="Revenue", description=label, color=discord.Color.green())
        embed.add_field(name="Total Revenue", value=f"${total:,.2f} {currency}", inline=True)
        embed.add_field(name="Orders", value=str(order_count), inline=True)
        embed.add_field(name="Avg Order Value", value=f"${avg:,.2f} {currency}", inline=True)
        await interaction.followup.send(embed=embed)

    async def _cmd_preset_add(
        self,
        interaction: discord.Interaction,
        name: str,
        carrier: str,
        mail_class: str,
        weight: str,
        dims: str,
        package_type: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        weight_oz = _parse_weight_oz(weight)
        if weight_oz is None or weight_oz <= 0:
            await interaction.followup.send(
                "Invalid weight. Use a format like `0.3lb`, `4.8oz`, or `5` (oz).", ephemeral=True
            )
            return

        parsed_dims = _parse_dims(dims)
        if parsed_dims is None:
            await interaction.followup.send(
                "Invalid dimensions. Use `LxWxH` in inches, e.g. `4x3x1`.", ephemeral=True
            )
            return
        length_in, width_in, height_in = parsed_dims

        async with db.get_db() as conn:
            inserted = await db.add_preset(
                conn, interaction.guild_id, name, carrier, mail_class,
                weight_oz, length_in, width_in, height_in,
                package_type=package_type,
            )
            await conn.commit()

        if not inserted:
            await interaction.followup.send(
                f"A preset named **{name}** already exists. Remove it first with `/preset remove`.",
                ephemeral=True,
            )
            return

        weight_lb = weight_oz / 16
        dims_str = f"{length_in:g}×{width_in:g}×{height_in:g} in"
        embed = discord.Embed(title="Preset Saved", color=discord.Color.green())
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Carrier", value=carrier, inline=True)
        embed.add_field(name="Mail Class", value=mail_class, inline=True)
        if package_type:
            embed.add_field(name="Package Type", value=package_type, inline=True)
        embed.add_field(name="Weight", value=f"{weight_lb:.2f} lb", inline=True)
        embed.add_field(name="Dimensions", value=dims_str, inline=True)
        await interaction.followup.send(embed=embed)

    async def _cmd_preset_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with db.get_db() as conn:
            presets = await db.list_presets(conn, interaction.guild_id)

        if not presets:
            await interaction.followup.send(
                "No presets saved yet. Use `/preset add` to create one.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Shipping Presets",
            description=f"{len(presets)} preset{'s' if len(presets) != 1 else ''}",
            color=discord.Color.blurple(),
        )
        for p in presets:
            weight_lb = p["weight_oz"] / 16
            dims_str = f"{p['length_in']:g}×{p['width_in']:g}×{p['height_in']:g} in"
            parts = [p["carrier"], p["mail_class"]]
            if p["package_type"]:
                parts.append(p["package_type"])
            parts += [f"{weight_lb:.2f} lb", dims_str]
            embed.add_field(
                name=p["name"],
                value=" · ".join(parts),
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    async def _cmd_preset_remove(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)

        async with db.get_db() as conn:
            deleted = await db.delete_preset(conn, interaction.guild_id, name)
            await conn.commit()

        if not deleted:
            await interaction.followup.send(
                f"No preset named **{name}** found. Use `/preset list` to see all presets.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(f"Preset **{name}** removed.", ephemeral=True)

    async def _cmd_reminders_set(self, interaction: discord.Interaction, days: str) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        parsed = []
        for part in days.split(","):
            part = part.strip()
            if not part.isdigit():
                await interaction.response.send_message(
                    f'`{part}` is not a valid number. Use comma-separated integers where 0=today, 1=tomorrow, etc. E.g. `"0,1,2"`.',
                    ephemeral=True,
                )
                return
            val = int(part)
            if val < 0 or val > 7:
                await interaction.response.send_message(
                    f"Day value `{val}` is out of range. Use values between 0 and 7.", ephemeral=True
                )
                return
            parsed.append(val)

        parsed = sorted(set(parsed))

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            if not guild_row or not guild_row["etsy_shop_id"]:
                await interaction.response.send_message(
                    "No Etsy shop connected. Connect a shop first.", ephemeral=True
                )
                return
            await db.set_guild_reminder_days(conn, interaction.guild_id, parsed)
            await conn.commit()
            reminder_config = await db.get_guild_reminder_config(conn, interaction.guild_id)

        threshold_labels = {0: "Today", 1: "Tomorrow"}
        labels = [threshold_labels.get(d, f"{d} days out") for d in parsed]
        embed = discord.Embed(
            title="Shipping Reminders Configured",
            description=f"You'll be notified when unshipped orders are due: **{', '.join(labels)}**.",
            color=discord.Color.green(),
        )
        if reminder_config and reminder_config["time"] and reminder_config["tz"]:
            try:
                tz = zoneinfo.ZoneInfo(reminder_config["tz"])
                abbr = datetime.datetime.now(tz).strftime("%Z")
                embed.add_field(
                    name="Fire time",
                    value=f"{reminder_config['time']} {abbr} (`{reminder_config['tz']}`)",
                    inline=False,
                )
            except Exception:
                pass
        else:
            embed.add_field(name="Fire time", value="Any poll cycle — use `/reminders time` to pin a specific time.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _autocomplete_timezone(
        self, interaction: discord.Interaction, current: str
    ) -> list[discord.app_commands.Choice[str]]:
        current_lower = current.lower()
        matches = [
            tz for tz in sorted(zoneinfo.available_timezones())
            if current_lower in tz.lower()
        ]
        # Prioritise common US/Canada zones at the top when query is empty or short
        priority = [
            "America/New_York", "America/Chicago", "America/Denver",
            "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu",
            "America/Toronto", "America/Vancouver", "Europe/London",
            "Europe/Paris", "Australia/Sydney",
        ]
        ordered = [tz for tz in priority if current_lower in tz.lower()] + \
                  [tz for tz in matches if tz not in priority]
        return [
            discord.app_commands.Choice(name=tz, value=tz)
            for tz in ordered[:25]
        ]

    async def _cmd_reminders_time(
        self, interaction: discord.Interaction, time: str, timezone: str
    ) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        # Validate time format
        try:
            h, m = time.split(":")
            if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                raise ValueError
            time_str = f"{int(h):02d}:{int(m):02d}"
        except (ValueError, AttributeError):
            await interaction.response.send_message(
                "Invalid time. Use HH:MM format, e.g. `09:00` or `14:30`.", ephemeral=True
            )
            return

        # Validate timezone
        try:
            tz = zoneinfo.ZoneInfo(timezone)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            await interaction.response.send_message(
                f"Unknown timezone `{timezone}`. Use the autocomplete to find a valid name (e.g. `America/New_York`, `Europe/London`).",
                ephemeral=True,
            )
            return

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            if not guild_row or not guild_row["etsy_shop_id"]:
                await interaction.response.send_message(
                    "No Etsy shop connected. Connect a shop first.", ephemeral=True
                )
                return
            await db.set_guild_reminder_time(conn, interaction.guild_id, time_str, timezone)
            await conn.commit()

        now_local = datetime.datetime.now(tz).strftime("%Z")
        embed = discord.Embed(
            title="Reminder Time Set",
            description=f"Shipping reminders will fire at **{time_str} {now_local}** (`{timezone}`).",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _cmd_reminders_disable(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.disable_guild_reminders(conn, interaction.guild_id)
            await conn.commit()

        await interaction.response.send_message(
            "Shipping deadline reminders have been disabled.", ephemeral=True
        )

    async def _cmd_reminders_status(self, interaction: discord.Interaction) -> None:
        async with db.get_db() as conn:
            config = await db.get_guild_reminder_config(conn, interaction.guild_id)

        if not config:
            await interaction.response.send_message(
                "Shipping reminders are **disabled**. Use `/reminders set` to enable them.",
                ephemeral=True,
            )
            return

        threshold_labels = {0: "Today", 1: "Tomorrow"}
        day_labels = [threshold_labels.get(d, f"{d} days out") for d in config["days"]]

        if config["time"] and config["tz"]:
            try:
                tz = zoneinfo.ZoneInfo(config["tz"])
                abbr = datetime.datetime.now(tz).strftime("%Z")
                time_str = f"**{config['time']} {abbr}** (`{config['tz']}`)"
            except Exception:
                time_str = f"**{config['time']}** (`{config['tz']}`)"
        else:
            time_str = "any poll cycle (no specific time set)"

        embed = discord.Embed(
            title="Shipping Reminder Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Status", value="Enabled", inline=False)
        embed.add_field(name="Remind me", value=", ".join(day_labels), inline=False)
        embed.add_field(name="Fire time", value=time_str, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _cmd_backlog_set(self, interaction: discord.Interaction, threshold: int) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return
        if threshold < 1:
            await interaction.response.send_message(
                "Threshold must be at least 1.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.set_backlog_threshold(conn, interaction.guild_id, threshold)
            guild_row = await db.get_guild(conn, interaction.guild_id)
            await conn.commit()

        channel_id = guild_row["order_channel_id"] if guild_row else None
        channel_mention = f"<#{channel_id}>" if channel_id else "your notification channel"
        await interaction.response.send_message(
            f"Backlog warning enabled. You'll be notified in {channel_mention} when you have **{threshold} or more** open orders waiting to ship.",
            ephemeral=True,
        )

    async def _cmd_backlog_off(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.set_backlog_threshold(conn, interaction.guild_id, None)
            await conn.commit()

        await interaction.response.send_message(
            "Backlog warning has been disabled.", ephemeral=True
        )

    async def _cmd_backlog_status(self, interaction: discord.Interaction) -> None:
        async with db.get_db() as conn:
            config = await db.get_backlog_config(conn, interaction.guild_id)

        if not config:
            await interaction.response.send_message(
                "Backlog warning is **disabled**. Use `/backlog set` to enable it.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="Backlog Warning Status", color=discord.Color.blurple())
        embed.add_field(name="Status", value="Enabled", inline=False)
        embed.add_field(name="Threshold", value=f"{config['threshold']} open orders", inline=False)
        embed.add_field(name="Currently warned", value="Yes" if config["warned"] else "No", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _cmd_digest_on(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.set_digest_config(conn, interaction.guild_id, "09:00", "UTC")
            await conn.commit()

        await interaction.response.send_message(
            "Daily digest enabled. I'll post a summary every day at **9:00 AM UTC**.\n"
            "Use `/digest time` to set a different time and timezone.",
            ephemeral=True,
        )

    async def _cmd_digest_time(
        self, interaction: discord.Interaction, time: str, timezone: str
    ) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        try:
            h, m = map(int, time.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Invalid time format. Use HH:MM (24-hour), e.g. `09:00` or `14:30`.",
                ephemeral=True,
            )
            return

        try:
            zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError:
            await interaction.response.send_message(
                f"Unknown timezone `{timezone}`. Use the autocomplete to find a valid name (e.g. `America/New_York`, `Europe/London`).",
                ephemeral=True,
            )
            return

        time_str = f"{h:02d}:{m:02d}"
        async with db.get_db() as conn:
            await db.set_digest_config(conn, interaction.guild_id, time_str, timezone)
            await conn.commit()

        await interaction.response.send_message(
            f"Daily digest will be posted at **{time_str}** ({timezone}).",
            ephemeral=True,
        )

    async def _cmd_digest_off(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.disable_digest(conn, interaction.guild_id)
            await conn.commit()

        await interaction.response.send_message(
            "Daily digest has been disabled.", ephemeral=True
        )

    async def _cmd_digest_status(self, interaction: discord.Interaction) -> None:
        async with db.get_db() as conn:
            config = await db.get_digest_config(conn, interaction.guild_id)

        if not config:
            await interaction.response.send_message(
                "Daily digest is **disabled**. Use `/digest on` to enable it.",
                ephemeral=True,
            )
            return

        try:
            tz = zoneinfo.ZoneInfo(config["tz"])
            abbr = datetime.datetime.now(tz).strftime("%Z")
            time_str = f"**{config['time']} {abbr}** (`{config['tz']}`)"
        except Exception:
            time_str = f"**{config['time']}** (`{config['tz']}`)"

        embed = discord.Embed(title="Daily Digest Status", color=discord.Color.blurple())
        embed.add_field(name="Status", value="Enabled", inline=False)
        embed.add_field(name="Posts at", value=time_str, inline=False)
        if config["last_sent"]:
            embed.add_field(name="Last sent", value=f"<t:{config['last_sent']}:R>", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _cmd_goal_set(self, interaction: discord.Interaction, amount: int) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return
        if amount < 1:
            await interaction.response.send_message("Goal must be at least $1.", ephemeral=True)
            return

        async with db.get_db() as conn:
            await db.set_goal_amount(conn, interaction.guild_id, amount * 100)
            await conn.commit()

        await interaction.response.send_message(
            f"Monthly revenue goal set to **${amount:,}**. "
            "You'll be notified at 25%, 50%, 75%, and 100%.",
            ephemeral=True,
        )

    async def _cmd_goal_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            if not guild_row or not guild_row["etsy_shop_id"]:
                await interaction.followup.send("No Etsy shop connected.", ephemeral=True)
                return
            goal_config = await db.get_goal_config(conn, interaction.guild_id)
            if not goal_config:
                await interaction.followup.send(
                    "No goal set. Use `/goal set <amount>` to set one.", ephemeral=True
                )
                return
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            month_start = datetime.datetime(now_dt.year, now_dt.month, 1, tzinfo=datetime.timezone.utc)
            month_receipts = await db.get_receipts_since(
                conn, guild_row["etsy_shop_id"], int(month_start.timestamp())
            )

        revenue = sum(r["grandtotal_amount"] / (r["grandtotal_divisor"] or 100) for r in month_receipts)
        currency = month_receipts[0]["grandtotal_currency"] if month_receipts else "USD"
        goal_dollars = goal_config["amount_cents"] / 100
        pct = int(revenue / goal_dollars * 100) if goal_dollars > 0 else 0

        import calendar
        days_in_month = calendar.monthrange(now_dt.year, now_dt.month)[1]
        days_left = days_in_month - now_dt.day
        month_name = now_dt.strftime("%B")

        embed = discord.Embed(
            title=f"{month_name} Revenue Goal",
            description=(
                f"**${revenue:.2f}** of **${goal_dollars:.2f}** {currency} — **{pct}%**\n"
                f"{days_left} day{'s' if days_left != 1 else ''} remaining in {month_name}."
            ),
            color=discord.Color.gold() if pct >= 100 else discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _cmd_goal_off(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to use this.", ephemeral=True
            )
            return

        async with db.get_db() as conn:
            await db.disable_goal(conn, interaction.guild_id)
            await conn.commit()

        await interaction.response.send_message("Monthly revenue goal removed.", ephemeral=True)

    async def _cmd_bestsellers(
        self, interaction: discord.Interaction, period: str, ranked_by: str
    ) -> None:
        await interaction.response.defer()
        now = datetime.datetime.now(datetime.timezone.utc)

        if period == "this_month":
            since = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc)
            period_label = now.strftime("%B %Y")
        elif period == "this_year":
            since = datetime.datetime(now.year, 1, 1, tzinfo=datetime.timezone.utc)
            period_label = str(now.year)
        else:
            since = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
            period_label = "All Time"

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            if not guild_row or not guild_row["etsy_shop_id"]:
                await interaction.followup.send("No Etsy shop connected. Run `/status` to get started.")
                return
            shop_id = guild_row["etsy_shop_id"]
            shop_row = await conn.execute("SELECT shop_name FROM shops WHERE shop_id = ?", (shop_id,))
            shop_row = await shop_row.fetchone()
            shop_name = shop_row["shop_name"] if shop_row else "My Shop"
            rows = await db.get_bestsellers(conn, shop_id, int(since.timestamp()), ranked_by=ranked_by)

        embed = build_bestsellers_embed(
            [dict(r) for r in rows],
            period_label=period_label,
            ranked_by=ranked_by,
            shop_name=shop_name,
        )
        await interaction.followup.send(embed=embed)

    async def _cmd_label(
        self,
        interaction: discord.Interaction,
        receipt_ids: str = "",
        preset: str = "",
    ) -> None:
        preset_row = None
        if preset:
            async with db.get_db() as conn:
                preset_row = await db.get_preset_by_name(conn, interaction.guild_id, preset)
            if not preset_row:
                await interaction.response.send_message(
                    f"No preset named **{preset}** found. Use `/preset list` to see all presets.",
                    ephemeral=True,
                )
                return

        if not receipt_ids:
            # Show multi-select picker
            etsy, shop_id = await self._get_etsy_client_silent(interaction)
            if not etsy:
                await interaction.response.send_message(
                    "No Etsy shop connected. Run `/status` to get started.", ephemeral=True
                )
                return
            async with db.get_db() as conn:
                receipts = await db.get_labelable_receipts(conn, shop_id)
            if not receipts:
                await interaction.response.send_message(
                    "No paid, unshipped orders found.", ephemeral=True
                )
                return
            view = LabelSelectView(self, receipts, preset_row)
            await interaction.response.send_message(
                "Select the orders you want to label:", view=view, ephemeral=True
            )
            return

        if preset_row:
            await interaction.response.defer(ephemeral=True)
            await self._process_label_purchases(
                interaction,
                receipt_ids_str=receipt_ids,
                carrier=preset_row["carrier"],
                mail_class=preset_row["mail_class"],
                weight_oz=preset_row["weight_oz"],
                length_in=preset_row["length_in"],
                width_in=preset_row["width_in"],
                height_in=preset_row["height_in"],
                package_type=preset_row["package_type"] or "",
            )
        else:
            await interaction.response.send_modal(LabelModal(self, receipt_ids))

    async def _process_label_purchases(
        self,
        interaction: discord.Interaction,
        receipt_ids_str: str,
        carrier: str,
        mail_class: str,
        weight_oz: float,
        length_in: float,
        width_in: float,
        height_in: float,
        package_type: str = "",
    ) -> None:
        etsy, shop_id = await self._get_etsy_client(interaction)
        if not etsy:
            return

        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
            shop_row = await conn.execute("SELECT shop_name FROM shops WHERE shop_id = ?", (shop_id,))
            shop_row = await shop_row.fetchone()
        shop_name = shop_row["shop_name"] if shop_row else "My Shop"

        raw_ids = [part.strip() for part in receipt_ids_str.split(",") if part.strip()]
        receipt_ids: list[int] = []
        for raw in raw_ids:
            if not raw.isdigit():
                await interaction.followup.send(
                    f"`{raw}` is not a valid receipt ID.", ephemeral=True
                )
                return
            receipt_ids.append(int(raw))

        if not receipt_ids:
            await interaction.followup.send("No receipt IDs provided.", ephemeral=True)
            return

        # Validate eligibility before purchasing any labels
        receipt_rows: dict[int, any] = {}
        async with db.get_db() as conn:
            ineligible = []
            for rid in receipt_ids:
                cursor = await conn.execute(
                    """
                    SELECT receipt_id, is_paid, is_shipped,
                           first_line, city, state, zip, country_iso
                    FROM receipts WHERE receipt_id = ? AND shop_id = ?
                    """,
                    (rid, shop_id),
                )
                row = await cursor.fetchone()
                if not row:
                    ineligible.append(f"#{rid}: not found")
                elif not row["is_paid"]:
                    ineligible.append(f"#{rid}: not paid")
                elif row["is_shipped"]:
                    ineligible.append(f"#{rid}: already shipped")
                else:
                    receipt_rows[rid] = row
            if ineligible:
                await interaction.followup.send(
                    "The following orders are not eligible for a label:\n" +
                    "\n".join(f"- {msg}" for msg in ineligible),
                    ephemeral=True,
                )
                return

        # USPS address verification — warn but do not block
        address_warnings: list[str] = []
        if _usps_client:
            loop = asyncio.get_running_loop()
            for rid, row in receipt_rows.items():
                city = row["city"] or ""
                state = row["state"] or ""
                zip_code = row["zip"] or ""
                street = row["first_line"] or ""
                if not (street and city and state and zip_code):
                    address_warnings.append(f"#{rid}: address incomplete, could not verify with USPS")
                    continue
                try:
                    await loop.run_in_executor(
                        None,
                        lambda r=row: _usps_client.verify_address(
                            street_address=r["first_line"] or "",
                            city=r["city"] or "",
                            state=r["state"] or "",
                            zip_code=r["zip"] or "",
                        ),
                    )
                except USPSAddressVerificationError as exc:
                    address_warnings.append(f"#{rid}: {exc}")
                except Exception as exc:
                    print(f"[label] USPS verification failed for receipt {rid}: {exc}")
                    # Don't warn on transient USPS API errors

        if address_warnings:
            warning_text = (
                "**Address verification warning** — USPS could not confirm the following:\n" +
                "\n".join(f"- {w}" for w in address_warnings) +
                "\n\nYou can still proceed, but the label may be undeliverable."
            )
            await interaction.followup.send(warning_text, ephemeral=True)

        loop = asyncio.get_running_loop()
        results: list[dict] = []
        errors: list[str] = []

        for rid in receipt_ids:
            try:
                data = await loop.run_in_executor(
                    None,
                    lambda r=rid: etsy.create_shipping_label(
                        shop_id, r, carrier, mail_class,
                        weight_oz, length_in, width_in, height_in,
                        package_type=package_type,
                    ),
                )
                data["receipt_id"] = rid
                results.append(data)
            except Exception as exc:
                err_str = str(exc)
                print(f"[label] create_shipping_label error for receipt {rid}: {exc!r}")
                # Try to extract Etsy's JSON error body for a friendlier message
                etsy_msg = err_str
                if hasattr(exc, "response") and exc.response is not None:
                    try:
                        body = exc.response.json()
                        etsy_msg = body.get("error_description") or body.get("message") or err_str
                    except Exception:
                        pass
                is_scope_error = (
                    "scope" in etsy_msg.lower()
                    or "permission" in etsy_msg.lower()
                    or "transactions_w" in etsy_msg.lower()
                )
                if is_scope_error:
                    await interaction.followup.send(
                        "Missing required scope. Run `/status` to re-authorize with label permissions.",
                        ephemeral=True,
                    )
                    return
                errors.append(f"#{rid}: {etsy_msg}")

        if results:
            channel_id = guild_row["order_channel_id"] if guild_row else None
            channel = self.get_channel(channel_id) if channel_id else interaction.channel
            if channel:
                await channel.send(embed=build_label_public_embed(results, shop_name))
            try:
                await interaction.user.send(embed=build_label_dm_embed(results, shop_name))
            except discord.Forbidden:
                await interaction.followup.send(
                    "Labels purchased, but your DMs are closed — check your Etsy account for PDF links.",
                    ephemeral=True,
                )
                return
            msg = f"Label{'s' if len(results) != 1 else ''} purchased. Check your DMs for PDF links."
            if errors:
                msg += "\n\nFailed:\n" + "\n".join(f"- {e}" for e in errors)
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.followup.send(
                "All label purchases failed:\n" + "\n".join(f"- {e}" for e in errors),
                ephemeral=True,
            )

    async def _get_etsy_client_silent(
        self, interaction: discord.Interaction
    ) -> tuple[EtsyClient | None, int | None]:
        """Return (EtsyClient, shop_id) without sending any response — caller handles errors."""
        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)
        if not guild_row or not guild_row["etsy_shop_id"]:
            return None, None
        etsy = self.etsy_clients.get(interaction.guild_id)
        if not etsy:
            return None, None
        return etsy, guild_row["etsy_shop_id"]

    async def _get_etsy_client(
        self, interaction: discord.Interaction
    ) -> tuple[EtsyClient | None, int | None]:
        """Return (EtsyClient, shop_id) for the guild, or send an error via followup and return (None, None)."""
        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)

        if not guild_row or not guild_row["etsy_shop_id"]:
            link = f" {WEB_BASE_URL}/connect/{guild_row['setup_token']}" if (
                guild_row and guild_row["setup_token"] and WEB_BASE_URL
            ) else ""
            await interaction.followup.send(f"No Etsy shop connected.{link}")
            return None, None

        etsy = self.etsy_clients.get(interaction.guild_id)
        if not etsy:
            await interaction.followup.send(
                "Bot connection error — try again in a moment. If this persists, contact an admin.",
                ephemeral=True,
            )
            return None, None

        return etsy, guild_row["etsy_shop_id"]


token = os.getenv("DISCORD_BOT_TOKEN")
if not token:
    print("ERROR: DISCORD_BOT_TOKEN not set")
    exit(1)

client = ShopkeepBot()
client.run(token)
