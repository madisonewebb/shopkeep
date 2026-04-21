
Shopkeep - Planned Features


WHAT'S ALREADY BUILT (updated 4/19/26)

The following are fully functional:

OAuth 2.0 onboarding: Guild owners run /connect; bot DMs a setup link; owner authorizes with Etsy (PKCE flow)
Order notifications: Bot polls Etsy every 60 seconds and posts a notification for every new order
Celebratory new sale embed: New order notifications show a 🎉 "New Sale!" title in gold with buyer name, order total, buyer location (city + country), item list with variations, and listing thumbnail
Order status change notifications: Posts a green "Order Shipped" embed when an order is marked shipped; posts a red "Order Canceled" embed when an order is canceled
Welcome message on bot join: DMs the guild owner a setup link and onboarding instructions when the bot joins a new server
Connect/disconnect confirmation embeds: Posts a confirmation to the order channel when a shop is linked or unlinked; falls back to a DM to the guild owner if no channel is set
/help - Lists all available commands
/status - Shows the connected Etsy shop and the configured notification channel
/setchannel - Sets which channel order notifications are posted to (requires Manage Channels)
/shop - Displays shop name, active listing count, favorites, vacation status, and more
/orders [days] [status] - Paginated order list, filterable by status (open / completed / canceled / all), defaults to last 30 days
/disconnect - Unlinks the Etsy shop from the server; clears OAuth tokens and stops notifications (requires Manage Server)
/revenue [period] - Revenue summary for today, this week, or this month; shows total revenue, order count, and average order value
/listings - Paginated browse of active Etsy listings; shows title, price, and quantity in stock (5 per page)
/reminders - Configurable shipping deadline reminders; on by default with 1-day notice; supports multiple thresholds (e.g. /reminders set 1 2); disable with /reminders off
/preset - Save reusable shipping package configurations (weight, dimensions, carrier, mail class) per server; supports add, list, and remove subcommands
Review notifications: Posts a notification when a new review is left; shows star rating and review text; existing reviews are marked seen on connect to avoid spam
Repeat customer callout: New sale embeds show a 🔁 "Returning customer!" note when the buyer has ordered before; works from locally stored receipt history, no extra API calls
Out-of-stock notifications: Posts a notification when a listing's quantity drops to zero; listing quantities are synced every poll cycle; notification shows title, link, and thumbnail
Order backlog warning: Posts a one-time warning when open unshipped orders exceed a configurable threshold; resets when backlog clears; configure with /backlog set <n> or /backlog off
Daily digest: Posts a morning summary of 24hr orders + revenue, open order count, and upcoming ship deadlines; timezone-aware; configure with /digest on, /digest time, /digest off
Revenue goal tracking: Set a monthly revenue target with /goal set; bot notifies at 25/50/75/100% milestones; progress shown in daily digest; resets automatically each month
/bestsellers: Shows top 5 listings by units sold or revenue; supports this month / this year / all time; computed from stored transaction data
/label [receipt_ids] [preset]: Purchase a shipping label for one or more orders; omit receipt IDs to pick from an interactive list; supports comma-separated batch IDs; autocompletes both orders and presets; uses saved /preset configurations


STRETCH GOALS


S1. Etsy Conversations + Busy Hours (/busyhours)

What: Surface incoming buyer messages from Etsy into Discord, allow the owner to reply from Discord, and automatically send a customizable away message to buyers who write in during configured busy hours.


Details:

Conversations in Discord:
- Polls for new buyer messages alongside receipts each cycle
- When a new inbound message arrives, posts it to the notification channel with the buyer name, message snippet, and a link to the full conversation on Etsy
- Owner replies using /reply - bot sends the reply back through the Etsy Conversations API

Busy hours auto-reply:
- If a new message arrives during configured busy hours, automatically sends a customizable away message to the buyer
- Fires once per conversation per busy window. It never spams a buyer who sends multiple messages
- Off by default; opt-in via /busyhours

Configuration:
    /busyhours set 22 8                                                  # busy from 10 PM to 8 AM
    /busyhours message "We'll reply by morning!"        # set custom away message
    /busyhours off                                                          # disable
    /busyhours                                                               # show current settings

Example - new message notification:
    New Message from Buyer
    HappyBuyer42: "Hi! Do you do custom orders?"
    View on Etsy

Example - auto-reply sent during busy hours:
    Auto-reply sent to HappyBuyer42
    "Thanks for reaching out! We're resting up and will get back to you first thing in the morning."


SUMMARY

Done:
- OAuth onboarding + polling
- Welcome message on bot join
- Celebratory new sale embeds (buyer location, item variations, thumbnail)
- Connect/disconnect confirmation embeds
- Order status change notifications (shipped = green, canceled = red)
- Shipping deadline reminders (/reminders)
- Review notifications (star rating, quoted review text, bootstrap deduplication)
- /help, /status, /setchannel, /shop, /orders, /disconnect, /revenue, /listings, /preset, /label

Stretch:
S1. Etsy Conversations + busy hours (/busyhours) ✓ DONE


