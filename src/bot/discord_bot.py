import asyncio
import datetime
import os
import secrets
import time

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from src.bot import db
from src.bot.notifier import build_connected_embed, build_disconnect_embed, build_order_embed, build_review_embed, build_shipping_reminder_embed, build_shop_embed, build_status_change_embed, build_welcome_embed
from src.etsy.client import EtsyClient

load_dotenv()

ETSY_API_KEY = os.environ["ETSY_API_KEY"]
ETSY_SHARED_SECRET = os.environ["ETSY_SHARED_SECRET"]
POLL_INTERVAL_SECS = int(os.getenv("POLL_INTERVAL_SECS", "60"))
DB_PATH_ENV = os.getenv("DB_PATH", "./shopkeep.db")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "")

SETUP_TOKEN_TTL = 86400  # 24 hours


_ORDERS_PAGE_SIZE = 5


class OrdersView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current == 0
        self.next_button.disabled = self.current == len(self.pages) - 1

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
            embed.add_field(
                name=f"Order #{r.get('receipt_id')} — {buyer}",
                value=f"{total_str} · {status} · {shipped}",
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
                    self._bootstrapped_guilds.add(row["guild_id"])
                except Exception as exc:
                    print(f"[bootstrap] guild={row['guild_id']} {exc}")
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
                if guild_id not in self.etsy_clients:
                    tokens = await db.get_guild_tokens(conn, guild_id)
                    if tokens:
                        self._register_client(
                            loop, guild_id,
                            tokens["access_token"], tokens["refresh_token"], tokens["expires_at"],
                        )

        for row in guild_rows:
            guild_id = row["guild_id"]
            if guild_id in self.etsy_clients and guild_id not in self._bootstrapped_guilds:
                try:
                    shop_name = await self._bootstrap_guild(guild_id, row["etsy_shop_id"])
                    self._bootstrapped_guilds.add(guild_id)
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
        receipts = response.get("results", [])
        raw_by_id = {r["receipt_id"]: r for r in receipts}
        channel = self.get_channel(channel_id)
        shop_name = shop_data.get("shop_name", "My Shop")

        async with db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)

            # Snapshot status before upserting so we can detect changes
            receipt_ids = [r["receipt_id"] for r in receipts]
            old_snapshot = await db.get_receipts_status_snapshot(conn, receipt_ids)

            for receipt in receipts:
                receipt.setdefault("shop_id", shop_id)
                await db.upsert_receipt(conn, receipt)
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
                    embed = build_order_embed(
                        dict(row),
                        shop_name=shop_name,
                        new=True,
                        transactions=raw.get("transactions", []),
                    )
                    await channel.send(embed=embed)
                    await db.mark_receipt_notified(conn, row["receipt_id"])
                    await conn.commit()

            await self._check_shipping_reminders(conn, guild_id, shop_id, channel, shop_name)
            await self._check_new_reviews(conn, guild_id, shop_id, channel, shop_name)

        self._last_polled[guild_id] = int(time.time())

    async def _check_shipping_reminders(
        self,
        conn,
        guild_id: int,
        shop_id: int,
        channel,
        shop_name: str,
    ) -> None:
        """Post shipping deadline reminders for open orders approaching their ship date."""
        reminder_days = await db.get_guild_reminder_days(conn, guild_id)
        if not reminder_days or channel is None:
            return
        now = int(time.time())
        for days_before in reminder_days:
            pending = await db.get_pending_reminders(conn, shop_id, days_before, now)
            for row in pending:
                embed = build_shipping_reminder_embed(dict(row), shop_name, days_before)
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
        """Fetch recent reviews, store any new ones, and post notifications."""
        etsy = self.etsy_clients.get(guild_id)
        if not etsy or channel is None:
            return
        loop = asyncio.get_running_loop()
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
            embed = build_review_embed(dict(row), shop_name=shop_name)
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
            discord.app_commands.Choice(name="Open (default)", value="open"),
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
            mail_class="Mail class or service level (e.g. first_class, priority)",
            weight="Package weight (e.g. 0.3lb or 4.8oz)",
            dims="Package dimensions LxWxH in inches (e.g. 4x3x1)",
        )
        @discord.app_commands.choices(carrier=[
            discord.app_commands.Choice(name="USPS", value="USPS"),
            discord.app_commands.Choice(name="UPS", value="UPS"),
            discord.app_commands.Choice(name="FedEx", value="FedEx"),
        ])
        async def preset_add(
            interaction: discord.Interaction,
            name: str,
            carrier: str,
            mail_class: str,
            weight: str,
            dims: str,
        ):
            await self._cmd_preset_add(interaction, name=name, carrier=carrier, mail_class=mail_class, weight=weight, dims=dims)

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
            description="Configure shipping deadline reminders",
        )

        @reminders_group.command(
            name="set",
            description="Enable shipping reminders for specific day thresholds",
        )
        @discord.app_commands.describe(
            days='Day thresholds as comma-separated integers: 0=today, 1=tomorrow, 2=in 2 days (e.g. "0,1,2")',
        )
        async def reminders_set(interaction: discord.Interaction, days: str):
            await self._cmd_reminders_set(interaction, days=days)

        @reminders_group.command(
            name="disable",
            description="Disable all shipping deadline reminders for this server",
        )
        async def reminders_disable(interaction: discord.Interaction):
            await self._cmd_reminders_disable(interaction)

        tree.add_command(reminders_group)

    async def _cmd_help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Shopkeep Commands", color=discord.Color.blurple())
        commands = [
            ("/help", "List all commands"),
            ("/status", "Show Etsy connection and notification channel"),
            ("/setchannel", "Set this channel for order notifications"),
            ("/shop", "Show your Etsy shop info"),
            ("/orders [days] [status]", "Show orders (default: last 30 days, open only)"),
            ("/disconnect", "Unlink your Etsy shop from this server"),
            ("/revenue [period]", "Show revenue summary (today / this week / this month)"),
            ("/listings", "Browse your active Etsy listings"),
            ("/preset add", "Save a new shipping preset (carrier, mail class, weight, dims)"),
            ("/preset list", "List all saved shipping presets"),
            ("/preset remove", "Delete a saved shipping preset"),
            ("/reminders set", "Enable shipping deadline reminders (0=today, 1=tomorrow, etc.)"),
            ("/reminders disable", "Disable all shipping deadline reminders"),
        ]
        for name, desc in commands:
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
            await interaction.followup.send(f"Failed to fetch shop info: {exc}")
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
            await interaction.followup.send(f"Failed to fetch orders: {exc}")
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
            await interaction.followup.send(f"No {label}orders in the last {days} days.")
            return

        total_cents = sum((r.get("grandtotal") or {}).get("amount", 0) for r in receipts)
        divisor = (receipts[0].get("grandtotal") or {}).get("divisor") or 100
        currency = (receipts[0].get("grandtotal") or {}).get("currency_code", "USD")
        revenue_str = f"${total_cents / divisor:.2f} {currency}"

        pages = _build_orders_pages(receipts, shop_name, revenue_str=revenue_str)
        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            await interaction.followup.send(embed=pages[0], view=OrdersView(pages))

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
            await interaction.followup.send("No active listings found. Data syncs every 60 seconds — try again shortly.")
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
            embed.add_field(
                name=p["name"],
                value=f"{p['carrier']} · {p['mail_class']} · {weight_lb:.2f} lb · {dims_str}",
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
                    f'Invalid value `{part}`. Use integers only, e.g. `"0,1,2"`.', ephemeral=True
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

        threshold_labels = {0: "Today", 1: "Tomorrow"}
        labels = [threshold_labels.get(d, f"{d} days out") for d in parsed]
        embed = discord.Embed(
            title="Shipping Reminders Configured",
            description=f"You'll be notified when unshipped orders are due: **{', '.join(labels)}**.",
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
            await interaction.followup.send("Etsy client not loaded. Try restarting the bot.")
            return None, None

        return etsy, guild_row["etsy_shop_id"]


token = os.getenv("DISCORD_BOT_TOKEN")
if not token:
    print("ERROR: DISCORD_BOT_TOKEN not set")
    exit(1)

client = ShopkeepBot()
client.run(token)
