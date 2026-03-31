
Shopkeep - Planned Features


WHAT'S ALREADY BUILT (updated 3/31/26)

The following are fully functional:

OAuth 2.0 onboarding: Guild owners run /connect; bot DMs a setup link; owner authorizes with Etsy (PKCE flow)
Order notifications: Bot polls Etsy every 60 seconds and posts a notification for every new order
/help - Lists all available commands
/status - Shows the connected Etsy shop and the configured notification channel
/setchannel - Sets which channel order notifications are posted to (requires Manage Channels)
/shop - Displays shop name, active listing count, favorites, vacation status, and more
/orders [days] [status] - Paginated order list, filterable by status (open / completed / canceled / all), defaults to last 30 days
/disconnect - Unlinks the Etsy shop from the server; clears OAuth tokens and stops notifications (requires Manage Server)
/revenue [period] - Revenue summary for today, this week, or this month; shows total revenue, order count, and average order value


PLANNED FEATURES

1. Welcome Message on Bot Join

What: When Shopkeep is added to a new Discord server, automatically send a welcome message to the server owner

Details:
- Triggered when the bot joins a new server
- DM includes a brief description of what Shopkeep does, how to run /connect to get started, and a link to the
- Acts as a built-in onboarding guide so new users aren't left wondering what to do next


2. Richer Order Notification Embeds

What: Improve the existing new-order notification to show what was actually purchased.

Details:
- Add the listing title(s) from the order's transactions
- Add a direct link back to the receipt on Etsy
- Add the item thumbnail image


3. Order Status Change Notifications

What: Post a follow-up notification when an existing order is marked as shipped or canceled.

Details:
- When an order is marked shipped, post a green "Order Shipped" notification
- When an order is canceled, post a red "Order Canceled" notification
- Requires changing the database upsert logic to detect what changed on each poll

4. Review Notifications

What: Post a notification whenever a new review is left on the shop.

Details:
- Polls for new reviews alongside receipts each cycle
- Stores seen review IDs to avoid duplicate notifications
- Notification shows star rating, reviewer name, and review snippet

Example:
    New Review: 5 stars
    "Absolutely love my order! Shipped fast and beautifully packaged."
    - HappyBuyer42


5. Repeat Customer Callout

What: When a new order comes in from a buyer who has ordered before, flag them as a returning customer in the n

Details:
- On each new order notification, check stored order history for prior orders from the same buyer
- If a match is found, add a "Returning customer!" note to the notification
- No extra API calls;  works entirely from data already stored locally


6. Shipping Deadline Reminders (/reminders)

What: Post a reminder when an open order is approaching its expected ship date, with a configurable advance not

Details:
- Each Etsy receipt includes an expected ship date; the bot checks open orders against the current date each cy
- On by default with a 1-day notice — no setup required after connecting
- Per-order tracking prevents the same reminder from firing twice

Configuration:
    /reminders                 # show current settings
    /reminders set 1        # notify 1 day before ship date (default)
    /reminders set 1 2     # notify at both 2 days and 1 day before
    /reminders off            # disable shipping reminders

Example:
    Ship by Tomorrow: Order #12345
    Buyer: Jane Smith - $34.00
    Expected ship date: March 27, 2026


7. Out-of-Stock Notifications

What: Post a notification when a listing's quantity drops to zero.

Details:
- The bot already syncs listing quantities on each poll
- Compares new quantity against the previously stored value; if it crosses zero, posts a notification
- Notification shows listing title, thumbnail, and a direct link to the listing on Etsy

Example:
    Out of Stock: "Hand-painted Ceramic Mug"
    Your listing has sold out. Visit Etsy to restock or deactivate it.


8. Order Backlog Warning

What: Post a warning when the number of open, unshipped orders exceeds a configurable threshold.

Details:
- Checked each poll cycle — no new API calls needed
- Default threshold: 5 open orders; configurable per server
- Warning fires once when the threshold is crossed, not on every poll, to avoid spam

9. Daily Digest (/digest)

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


10. Revenue Goal Tracking (/goal)

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


11. /bestsellers - Top Listings by Sales

What: Show the shop's top-performing listings by units sold or revenue over a time period.

Details:
- Computed from stored order data — no extra API calls
- Options: this month, this year, all time
- Shows listing title, units sold, and total revenue per item

Example:
    /bestsellers period:this_month
    Top 5 listings ranked by units sold in March


12. /listings - Browse Active Listings

What: A slash command to browse the shop's active listings from within Discord.

Details:
- Paginated (5 listings per page) with Previous / Next buttons
- Each listing shows title, price, quantity in stock, and thumbnail
- Data comes from the listings table, which is already synced every poll


STRETCH GOALS

S1. Shipping Presets (/preset)

What: Allow shop owners to save reusable package configurations (weight, dimensions, carrier) so that printing

Details:
- Presets are stored per server in the database
- Each preset has a name, weight, dimensions, carrier, and mail class
- Used as the foundation for the label printing feature below

Configuration:
    /preset add "small-jewelry" carrier:USPS class:first_class weight:0.3lb dims:4x3x1
    /preset list
    /preset remove "small-jewelry"


S2. Shipping Label Printing (/printlabel)

What: Create a shipping label for an order directly from Discord using a saved preset.

Details:
- Uses the Etsy API's shipping label endpoint
- Owner selects an open order and a saved preset; the bot submits the label creation request
- Etsy returns a label PDF URL which is posted back as a Discord message
- Requires shipping presets (S1) — entering dimensions manually per label would be too cumbersome

Example:
    /printlabel order:12345 preset:small-jewelry
    Label created! Download: [PDF link] · Tracking: 9400111899223397522056

Why it's a stretch goal: Label creation involves payment (charged to the Etsy account) and the shipping label A


S3. Etsy Conversations + Busy Hours (/busyhours)

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
- /help, /status, /setchannel, /shop, /orders, /disconnect, /revenue

Planned:
1.  Welcome message on bot join
2.  Richer order notification embeds
3.  Order status change notifications
4.  Review notifications
5.  Repeat customer callout
6.  Shipping deadline reminders (/reminders)
7.  Out-of-stock notifications
8.  Order backlog warning
9.  Daily digest (/digest)
10. Revenue goal tracking (/goal)
11. /bestsellers
12. /listings

Stretch:
S1. Shipping presets (/preset)
S2. Shipping label printing (/printlabel)
S3. Etsy Conversations + busy hours (/busyhours)


