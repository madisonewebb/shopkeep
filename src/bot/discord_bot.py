import asyncio
import os

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from src.bot import db
from src.bot.notifier import build_order_embed, build_shop_embed
from src.etsy.client import MockEtsyClient

load_dotenv()

ETSY_API_URL = os.getenv("ETSY_API_URL", "http://localhost:5000")
ETSY_SHOP_ID = int(os.getenv("ETSY_SHOP_ID", "12345678"))
ORDER_CHANNEL_ID = int(os.getenv("ORDER_CHANNEL_ID", "0"))
POLL_INTERVAL_SECS = int(os.getenv("POLL_INTERVAL_SECS", "60"))
DB_PATH_ENV = os.getenv("DB_PATH", "./shopkeep.db")


class ShopkeepBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.etsy = MockEtsyClient(base_url=ETSY_API_URL)
        self._etsy_authed = False
        self._bootstrapped = False

    async def setup_hook(self):
        """Called by discord.py before login; event loop is already running."""
        db.DB_PATH = DB_PATH_ENV
        await db.init_db()
        self.poll_orders.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} | Polling shop {ETSY_SHOP_ID} every {POLL_INTERVAL_SECS}s")
        if not self._bootstrapped:
            self._bootstrapped = True
            try:
                await self._bootstrap()
            except Exception as exc:
                print(f"[bootstrap] {exc}")

    async def _ensure_etsy_auth(self):
        if not self._etsy_authed:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.etsy.get_access_token)
            self._etsy_authed = True

    async def _bootstrap(self):
        """Seed the DB with current shop state on first connect.

        Upserts the shop, all active listings, and all existing receipts.
        Receipts are marked already_seen=True so the poll loop only notifies
        for orders that arrive after the bot starts.
        """
        print(f"[bootstrap] Seeding shop {ETSY_SHOP_ID}…")
        loop = asyncio.get_running_loop()

        await self._ensure_etsy_auth()

        shop_data = await loop.run_in_executor(None, lambda: self.etsy.get_shop(ETSY_SHOP_ID))
        listings_resp = await loop.run_in_executor(
            None, lambda: self.etsy.get_shop_listings(ETSY_SHOP_ID, limit=100)
        )
        receipts_resp = await loop.run_in_executor(
            None, lambda: self.etsy.get_shop_receipts(ETSY_SHOP_ID, limit=100)
        )

        listings = listings_resp.get("results", [])
        receipts = receipts_resp.get("results", [])

        async with await db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)
            await db.upsert_listings(conn, listings)
            for receipt in receipts:
                receipt.setdefault("shop_id", ETSY_SHOP_ID)
                await db.upsert_receipt(conn, receipt, already_seen=True)
            await conn.commit()

        print(
            f"[bootstrap] Done — shop '{shop_data.get('shop_name')}', "
            f"{len(listings)} listing(s), {len(receipts)} existing receipt(s) marked seen."
        )

    @tasks.loop(seconds=POLL_INTERVAL_SECS)
    async def poll_orders(self):
        try:
            await self._ensure_etsy_auth()
            await self._do_poll()
        except Exception as exc:
            print(f"[poller] {exc}")

    @poll_orders.before_loop
    async def before_poll(self):
        await self.wait_until_ready()

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        cmd = message.content.strip().lower()

        if cmd == "!shop":
            await self._ensure_etsy_auth()
            loop = asyncio.get_running_loop()
            shop_data = await loop.run_in_executor(None, lambda: self.etsy.get_shop(ETSY_SHOP_ID))
            embed = build_shop_embed(shop_data)
            await message.channel.send(embed=embed)
            return

        if cmd != "!orders":
            return

        await self._ensure_etsy_auth()
        loop = asyncio.get_running_loop()
        shop_data = await loop.run_in_executor(None, lambda: self.etsy.get_shop(ETSY_SHOP_ID))
        response = await loop.run_in_executor(
            None, lambda: self.etsy.get_shop_receipts(ETSY_SHOP_ID, limit=50)
        )
        receipts = response.get("results", [])
        shop_name = shop_data.get("shop_name", "My Shop")

        if not receipts:
            await message.channel.send("No orders found.")
            return

        for receipt in receipts:
            # Map API fields (snake_case) to the keys build_order_embed expects
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
            embed = build_order_embed(normalized, shop_name=shop_name)
            await message.channel.send(embed=embed)

    async def _do_poll(self):
        loop = asyncio.get_running_loop()

        # Fetch shop info so we can upsert it (satisfies FK constraint) and get shop name
        shop_data = await loop.run_in_executor(
            None, lambda: self.etsy.get_shop(ETSY_SHOP_ID)
        )
        response = await loop.run_in_executor(
            None, lambda: self.etsy.get_shop_receipts(ETSY_SHOP_ID, limit=50)
        )
        receipts = response.get("results", [])
        channel = self.get_channel(ORDER_CHANNEL_ID)
        shop_name = shop_data.get("shop_name", "My Shop")

        async with await db.get_db() as conn:
            await db.upsert_shop(conn, shop_data)
            for receipt in receipts:
                # Ensure shop_id is present (real API includes it; inject as fallback)
                receipt.setdefault("shop_id", ETSY_SHOP_ID)
                await db.upsert_receipt(conn, receipt)
            await conn.commit()

            unnotified = await db.get_unnotified_receipts(conn, ETSY_SHOP_ID)
            for row in unnotified:
                if channel:
                    embed = build_order_embed(dict(row), shop_name=shop_name)
                    await channel.send(embed=embed)
                await db.mark_receipt_notified(conn, row["receipt_id"])
                await conn.commit()  # commit after each to avoid re-notifying on crash


token = os.getenv("DISCORD_BOT_TOKEN")
if not token:
    print("ERROR: DISCORD_BOT_TOKEN not found in environment variables")
    print("Make sure your .env file exists and contains: DISCORD_BOT_TOKEN=your_token")
    exit(1)

client = ShopkeepBot()
client.run(token)
