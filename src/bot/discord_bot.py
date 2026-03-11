import asyncio
import os
import secrets
import time

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from src.bot import db
from src.bot.notifier import build_order_embed, build_shop_embed
from src.etsy.client import EtsyClient

load_dotenv()

ETSY_API_KEY = os.environ["ETSY_API_KEY"]
ETSY_SHARED_SECRET = os.environ["ETSY_SHARED_SECRET"]
POLL_INTERVAL_SECS = int(os.getenv("POLL_INTERVAL_SECS", "60"))
DB_PATH_ENV = os.getenv("DB_PATH", "./shopkeep.db")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "")

SETUP_TOKEN_TTL = 86400  # 24 hours


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
                    await guild.owner.send(
                        f"Hi! Shopkeep needs to be connected to your Etsy shop for **{guild.name}**.\n\n"
                        f"Complete setup here:\n"
                        f"{WEB_BASE_URL}/connect/{setup_token}\n\n"
                        f"After connecting, use `/setchannel` to choose where order notifications go."
                    )
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
                await guild.owner.send(
                    f"Thanks for adding Shopkeep to **{guild.name}**!\n\n"
                    f"Connect your Etsy shop to start receiving order notifications:\n"
                    f"{WEB_BASE_URL}/connect/{setup_token}\n\n"
                    f"After connecting, use `!setchannel` in any channel to choose "
                    f"where order notifications are posted. Use `/setchannel` in any channel to set it."
                )
            except discord.Forbidden:
                pass  # Owner has DMs disabled

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    async def _bootstrap_guild(self, guild_id: int, shop_id: int) -> None:
        etsy = self.etsy_clients.get(guild_id)
        if not etsy:
            return

        print(f"[bootstrap] guild={guild_id} shop={shop_id}")
        loop = asyncio.get_running_loop()

        shop_data = await loop.run_in_executor(None, lambda: etsy.get_shop(shop_id))
        listings_resp = await loop.run_in_executor(
            None, lambda: etsy.get_shop_listings(shop_id, limit=100)
        )
        receipts_resp = await loop.run_in_executor(
            None, lambda: etsy.get_shop_receipts(shop_id, limit=100)
        )

        listings = listings_resp.get("results", [])
        receipts = receipts_resp.get("results", [])

        async with db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)
            await db.upsert_listings(conn, listings)
            for receipt in receipts:
                receipt.setdefault("shop_id", shop_id)
                await db.upsert_receipt(conn, receipt, already_seen=True)
            await conn.commit()

        print(
            f"[bootstrap] Done — '{shop_data.get('shop_name')}', "
            f"{len(listings)} listing(s), {len(receipts)} existing receipt(s) marked seen."
        )

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
                    await self._bootstrap_guild(guild_id, row["etsy_shop_id"])
                    self._bootstrapped_guilds.add(guild_id)
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
        channel = self.get_channel(channel_id)
        shop_name = shop_data.get("shop_name", "My Shop")

        async with db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)
            for receipt in receipts:
                receipt.setdefault("shop_id", shop_id)
                await db.upsert_receipt(conn, receipt)
            await conn.commit()

            unnotified = await db.get_unnotified_receipts(conn, shop_id)
            for row in unnotified:
                if channel:
                    embed = build_order_embed(dict(row), shop_name=shop_name, new=True)
                    await channel.send(embed=embed)
                await db.mark_receipt_notified(conn, row["receipt_id"])
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

        @tree.command(name="orders", description="Show open orders from the last 30 days")
        async def orders(interaction: discord.Interaction):
            await self._cmd_orders(interaction)

    async def _cmd_help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "**Shopkeep Commands**\n"
            "`/help` — List all commands\n"
            "`/status` — Show Etsy connection and notification channel\n"
            "`/setchannel` — Set this channel for order notifications\n"
            "`/shop` — Show your Etsy shop info\n"
            "`/orders` — Show open orders from the last 30 days"
        )

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
            f"Order notifications will be posted in <#{interaction.channel_id}>."
        )

    async def _cmd_status(self, interaction: discord.Interaction) -> None:
        async with db.get_db() as conn:
            guild_row = await db.get_guild(conn, interaction.guild_id)

        if not guild_row:
            await interaction.response.send_message(
                "This server hasn't been set up yet. Add Shopkeep via the website."
            )
            return

        shop_id = guild_row["etsy_shop_id"]
        channel_id = guild_row["order_channel_id"]
        etsy_status = f"Connected (shop ID: {shop_id})" if shop_id else "Not connected"
        channel_status = f"<#{channel_id}>" if channel_id else "Not set — use `/setchannel`"

        connect_link = ""
        if WEB_BASE_URL and not shop_id:
            token = guild_row["setup_token"]
            exp = guild_row["setup_token_exp"] or 0
            if not token or exp < int(time.time()):
                token = secrets.token_urlsafe(16)
                exp = int(time.time()) + SETUP_TOKEN_TTL
                async with db.get_db() as conn:
                    await db.refresh_setup_token(conn, guild_row["guild_id"], token, exp)
                    await conn.commit()
            connect_link = f"\nConnect your shop: {WEB_BASE_URL}/connect/{token}"

        await interaction.response.send_message(
            f"**Shopkeep Status**\n"
            f"Etsy: {etsy_status}\n"
            f"Notifications: {channel_status}"
            f"{connect_link}"
        )

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

    async def _cmd_orders(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        etsy, shop_id = await self._get_etsy_client(interaction)
        if not etsy:
            return
        loop = asyncio.get_running_loop()
        min_created = int(time.time()) - 30 * 24 * 3600
        try:
            shop_data = await loop.run_in_executor(None, lambda: etsy.get_shop(shop_id))
            response = await loop.run_in_executor(
                None, lambda: etsy.get_shop_receipts(shop_id, limit=50, min_created=min_created)
            )
        except Exception as exc:
            await interaction.followup.send(f"Failed to fetch orders: {exc}")
            return
        receipts = [
            r for r in response.get("results", [])
            if (r.get("status") or "").lower() != "completed"
        ]
        shop_name = shop_data.get("shop_name", "My Shop")

        if not receipts:
            await interaction.followup.send("No open orders in the last 30 days.")
            return

        for receipt in receipts:
            gt = receipt.get("grandtotal", {})
            normalized = {
                "receipt_id": receipt.get("receipt_id"),
                "name": receipt.get("name"),
                "status": receipt.get("status"),
                "is_paid": receipt.get("is_paid"),
                "is_shipped": receipt.get("is_shipped"),
                "gift_message": receipt.get("gift_message"),
                "create_timestamp": receipt.get("create_timestamp"),
                "grandtotal_amount": gt.get("amount", 0),
                "grandtotal_divisor": gt.get("divisor", 100),
                "grandtotal_currency": gt.get("currency_code", "USD"),
            }
            await interaction.followup.send(embed=build_order_embed(normalized, shop_name=shop_name))

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
