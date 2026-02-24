"""
Example: Integrating Mock Etsy API with Discord Bot
This demonstrates how to use the mock Etsy API in your Discord bot
"""

import discord
from discord.ext import commands
from mock_etsy_client import MockEtsyClient
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize Etsy client
# For development: use mock API
etsy_client = MockEtsyClient(
    api_key="mock-api-key",
    base_url="http://localhost:5000"
)

# When your real API key is ready, switch to:
# etsy_client = MockEtsyClient(
#     api_key=os.getenv("ETSY_API_KEY"),
#     base_url="https://api.etsy.com"
# )

# Sample shop ID (use your real shop ID when ready)
SHOP_ID = 12345678


@bot.event
async def on_ready():
    """Bot startup event"""
    print(f'{bot.user} has connected to Discord!')
    
    # Get OAuth token on startup
    try:
        token_response = etsy_client.get_access_token()
        print(f'✓ Etsy API authenticated')
    except Exception as e:
        print(f'✗ Failed to authenticate with Etsy API: {e}')


@bot.command(name='shop')
async def shop_info(ctx):
    """Get shop information"""
    try:
        shop = etsy_client.get_shop(SHOP_ID)
        
        embed = discord.Embed(
            title=f"🛍️ {shop['shop_name']}",
            description=shop.get('announcement', 'No announcement'),
            color=discord.Color.blue(),
            url=shop['url']
        )
        
        embed.add_field(name="Active Listings", value=shop['listing_active_count'], inline=True)
        embed.add_field(name="Favorites", value=shop['num_favorers'], inline=True)
        embed.add_field(name="Currency", value=shop['currency_code'], inline=True)
        
        if shop.get('is_vacation'):
            embed.add_field(name="⚠️ Status", value="On Vacation", inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching shop info: {e}")


@bot.command(name='orders')
async def recent_orders(ctx, limit: int = 5):
    """Get recent orders (receipts)"""
    try:
        receipts = etsy_client.get_shop_receipts(SHOP_ID, limit=min(limit, 10))
        
        if receipts['count'] == 0:
            await ctx.send("No orders found.")
            return
        
        embed = discord.Embed(
            title=f"📦 Recent Orders ({receipts['count']} total)",
            color=discord.Color.green()
        )
        
        for receipt in receipts['results'][:limit]:
            status_emoji = "✅" if receipt['is_shipped'] else "📦"
            amount = receipt['grandtotal']['amount'] / receipt['grandtotal']['divisor']
            currency = receipt['grandtotal']['currency_code']
            
            value = f"**Amount:** {currency} ${amount:.2f}\n"
            value += f"**Status:** {receipt['status']}\n"
            value += f"**Shipped:** {'Yes' if receipt['is_shipped'] else 'No'}\n"
            value += f"**Buyer:** {receipt['name']}"
            
            embed.add_field(
                name=f"{status_emoji} Order #{receipt['receipt_id']}",
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching orders: {e}")


@bot.command(name='listings')
async def active_listings(ctx, limit: int = 5):
    """Get active listings"""
    try:
        listings = etsy_client.get_shop_listings(SHOP_ID, limit=min(limit, 10), state='active')
        
        if listings['count'] == 0:
            await ctx.send("No active listings found.")
            return
        
        embed = discord.Embed(
            title=f"🏷️ Active Listings ({listings['count']} total)",
            color=discord.Color.purple()
        )
        
        for listing in listings['results'][:limit]:
            price = listing['price']['amount'] / listing['price']['divisor']
            currency = listing['price']['currency_code']
            
            value = f"**Price:** {currency} ${price:.2f}\n"
            value += f"**Quantity:** {listing['quantity']}\n"
            value += f"**Views:** {listing.get('views', 'N/A')}\n"
            value += f"**Favorites:** {listing.get('num_favorers', 0)}"
            
            embed.add_field(
                name=listing['title'],
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching listings: {e}")


@bot.command(name='neworders')
async def new_orders(ctx):
    """Get unpaid or unshipped orders"""
    try:
        # Get unshipped orders
        receipts = etsy_client.get_shop_receipts(
            SHOP_ID, 
            limit=25,
            was_shipped=False
        )
        
        if receipts['count'] == 0:
            await ctx.send("✅ All orders have been shipped!")
            return
        
        embed = discord.Embed(
            title=f"⚠️ Unshipped Orders ({receipts['count']})",
            description="Orders that need attention",
            color=discord.Color.orange()
        )
        
        for receipt in receipts['results'][:10]:
            amount = receipt['grandtotal']['amount'] / receipt['grandtotal']['divisor']
            currency = receipt['grandtotal']['currency_code']
            
            value = f"**Amount:** {currency} ${amount:.2f}\n"
            value += f"**Buyer:** {receipt['name']}\n"
            value += f"**Status:** {receipt['status']}"
            
            if receipt.get('message_from_buyer'):
                value += f"\n**Note:** {receipt['message_from_buyer'][:50]}..."
            
            embed.add_field(
                name=f"Order #{receipt['receipt_id']}",
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching new orders: {e}")


@bot.command(name='stats')
async def shop_stats(ctx):
    """Get shop statistics"""
    try:
        shop = etsy_client.get_shop(SHOP_ID)
        receipts = etsy_client.get_shop_receipts(SHOP_ID, limit=100)
        listings = etsy_client.get_shop_listings(SHOP_ID, limit=100)
        
        # Calculate stats
        total_revenue = sum(
            r['grandtotal']['amount'] / r['grandtotal']['divisor'] 
            for r in receipts['results']
        )
        
        shipped_count = sum(1 for r in receipts['results'] if r['is_shipped'])
        unshipped_count = receipts['count'] - shipped_count
        
        embed = discord.Embed(
            title=f"📊 Shop Statistics - {shop['shop_name']}",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="Active Listings", value=shop['listing_active_count'], inline=True)
        embed.add_field(name="Total Orders", value=receipts['count'], inline=True)
        embed.add_field(name="Shop Favorites", value=shop['num_favorers'], inline=True)
        
        embed.add_field(name="Shipped Orders", value=shipped_count, inline=True)
        embed.add_field(name="Pending Shipment", value=unshipped_count, inline=True)
        embed.add_field(name="Total Revenue", value=f"${total_revenue:.2f}", inline=True)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error fetching stats: {e}")


if __name__ == '__main__':
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not found in environment variables")
        print("Make sure your .env file exists and contains: DISCORD_BOT_TOKEN=your_token")
        exit(1)
    
    print("=" * 60)
    print("Discord Bot with Mock Etsy API Integration")
    print("=" * 60)
    print("\nAvailable Commands:")
    print("  !shop       - Get shop information")
    print("  !orders     - Get recent orders")
    print("  !listings   - Get active listings")
    print("  !neworders  - Get unshipped orders")
    print("  !stats      - Get shop statistics")
    print("\nMake sure the mock Etsy API server is running:")
    print("  python mock_etsy_api.py")
    print("=" * 60)
    print()
    
    bot.run(token)
