
Shopkeep - Planned Features


WHAT'S ALREADY BUILT (updated 4/13/26)

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


PLANNED FEATURES

3. Repeat Customer Callout

What: When a new order comes in from a buyer who has ordered before, flag them as a returning customer in the n

Details:
- On each new order notification, check stored order history for prior orders from the same buyer
- If a match is found, add a "Returning customer!" note to the notification
- No extra API calls;  works entirely from data already stored locally


4. Out-of-Stock Notifications

What: Post a notification when a listing's quantity drops to zero.

Details:
- The bot already syncs listing quantities on each poll
- Compares new quantity against the previously stored value; if it crosses zero, posts a notification
- Notification shows listing title, thumbnail, and a direct link to the listing on Etsy

Example:
    Out of Stock: "Hand-painted Ceramic Mug"
    Your listing has sold out. Visit Etsy to restock or deactivate it.


5. Order Backlog Warning

What: Post a warning when the number of open, unshipped orders exceeds a configurable threshold.

Details:
- Checked each poll cycle — no new API calls needed
- Default threshold: 5 open orders; configurable per server
- Warning fires once when the threshold is crossed, not on every poll, to avoid spam

6. Daily Digest (/digest)

What: Every morning at a configured time, the bot automatically posts a summary to the notification channel — n

Details:
- Orders received in the past 24 hours and their total revenue
- Number of open orders currently waiting to ship
- Any orders whose ship deadline is today or tomorrow
- Configurable delivery time (default: 9:00 AM, timezone-aware)

Configuration:
    /digest on                 # enable with default time (9:00 AM)
    /digest time 8:00      # set delivery time
    /digest off                 # disable


7. Revenue Goal Tracking (/goal)

What: Set a monthly revenue target and receive milestone notifications as progress is made.

Details:
- Bot posts a notification when the shop hits 25%, 50%, 75%, and 100% of the monthly goal
- Current progress also shown in the daily digest
- Goal resets automatically at the start of each month

Configuration:
    /goal set 500      # set a $500 monthly revenue goal
    /goal                   # show current progress
    /goal off              # remove the goal

Example:
    Goal Milestone: 50%
    You've made $250.00 of your $500.00 March goal with 18 days to go.


8. /bestsellers - Top Listings by Sales

What: Show the shop's top-performing listings by units sold or revenue over a time period.

Details:
- Computed from stored order data — no extra API calls
- Options: this month, this year, all time
- Shows listing title, units sold, and total revenue per item

Example:
    /bestsellers period:this_month
    Top 5 listings ranked by units sold in March


STRETCH GOALS

S1. Shipping Label Printing (/printlabel)

What: Create a shipping label for an order directly from Discord using a saved preset.

Details:
- Uses the Etsy API's shipping label endpoint
- Owner selects an open order and a saved preset; the bot submits the label creation request
- Etsy returns a label PDF URL which is posted back as a Discord message
- Requires shipping presets (/preset) — entering dimensions manually per label would be too cumbersome

Example:
    /printlabel order:12345 preset:small-jewelry
    Label created! Download: [PDF link] · Tracking: 9400111899223397522056

Why it's a stretch goal: Label creation involves payment (charged to the Etsy account) and the shipping label A


S2. Etsy Conversations + Busy Hours (/busyhours)

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
- /help, /status, /setchannel, /shop, /orders, /disconnect, /revenue, /listings, /preset

Planned:
1.  Repeat customer callout
2.  Out-of-stock notifications
3.  Order backlog warning
4.  Daily digest (/digest)
5.  Revenue goal tracking (/goal)
6.  /bestsellers

Stretch:
S1. Shipping label printing (/printlabel)
S2. Etsy Conversations + busy hours (/busyhours)


