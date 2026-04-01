import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot settings - CHANGE THESE
BOT_TOKEN = ""  # Token from @BotFather
CHANNEL_ID = "@simmerliq"  # Channel ID or username (e.g. @TradCast or -1001234567890)

ADMIN_IDS = []  # 👈 Your admin Telegram IDs here

# ── Rate-limit config ──────────────────────────────────────────────────────
MENU_RATE_LIMIT        = 3    # max times the menu can be triggered per user
MENU_RATE_WINDOW_SEC   = 60   # within this many seconds
 
# ── Conversation states ────────────────────────────────────────────────────
WAITING_FOR_EMAIL  = 1
WAITING_FOR_TICKET = 2
 
 
# ── In-memory rate-limit tracker ──────────────────────────────────────────
# { user_id: [timestamp, timestamp, ...] }
_menu_trigger_log: dict[int, list[datetime]] = defaultdict(list)
 
 
def _is_menu_rate_limited(user_id: int) -> bool:
    """
    Returns True (blocked) if the user has triggered the menu
    MENU_RATE_LIMIT or more times in the last MENU_RATE_WINDOW_SEC seconds.
    Cleans up old timestamps on every call.
    """
    now    = datetime.now()
    cutoff = now - timedelta(seconds=MENU_RATE_WINDOW_SEC)
 
    # Drop timestamps outside the window
    _menu_trigger_log[user_id] = [
        t for t in _menu_trigger_log[user_id] if t > cutoff
    ]
 
    if len(_menu_trigger_log[user_id]) >= MENU_RATE_LIMIT:
        return True  # blocked
 
    # Record this trigger
    _menu_trigger_log[user_id].append(now)
    return False  # allowed
 
 
# ── DB helpers ─────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('invite_tracker.db')
    c = conn.cursor()
 
    c.execute('''CREATE TABLE IF NOT EXISTS invites
                 (user_id INTEGER,
                  username TEXT,
                  invite_link TEXT,
                  created_at TEXT,
                  total_invites INTEGER DEFAULT 0)''')
 
    c.execute('''CREATE TABLE IF NOT EXISTS invited_users
                 (inviter_id INTEGER,
                  invited_user_id INTEGER,
                  invited_at TEXT)''')
 
    c.execute('''CREATE TABLE IF NOT EXISTS tickets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  email TEXT,
                  message TEXT,
                  status TEXT DEFAULT 'open',
                  created_at TEXT)''')
 
    conn.commit()
    conn.close()
 
 
def check_ticket_limits(user_id: int) -> tuple[bool, str]:
    conn = sqlite3.connect('invite_tracker.db')
    c = conn.cursor()
 
    now          = datetime.now()
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    one_day_ago  = (now - timedelta(days=1)).isoformat()
 
    c.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ? AND created_at >= ?",
              (user_id, one_hour_ago))
    hourly_count = c.fetchone()[0]
 
    c.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ? AND created_at >= ?",
              (user_id, one_day_ago))
    daily_count = c.fetchone()[0]
 
    conn.close()
 
    if hourly_count >= 5:
        return False, "⏳ You've reached the 5 ticket/hour limit.\nPlease wait a bit before submitting another ticket."
    if daily_count >= 10:
        return False, "🚫 You've reached the 10 ticket/day limit.\nYou can submit more tickets tomorrow."
 
    return True, ""
 
 
# ── Bot class ──────────────────────────────────────────────────────────────
class InviteBot:
 
    def __init__(self):
        init_db()
 
    def _main_keyboard(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Get Invite Link", callback_data='get_invite')],
            [InlineKeyboardButton("📊 My Statistics",   callback_data='my_stats')],
            [InlineKeyboardButton("🎫 Create Ticket",   callback_data='create_ticket')],
        ])
 
    WELCOME_TEXT = (
        "👋 Welcome!\n\n"
        "With this bot you can:\n"
        "• Get your personal invite link for the Tradcast channel\n"
        "• View your invite statistics\n"
        "• Submit a support ticket if you have a problem\n\n"
        "Choose an option below 👇"
    )
 
    # ── /start ─────────────────────────────────────────────────────────────
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self.WELCOME_TEXT, reply_markup=self._main_keyboard())
        return ConversationHandler.END
 
    # ── Any plain text → show menu (with rate-limit) ───────────────────────
    async def text_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Triggered by any text message that is NOT inside the ticket conversation.
        Shows the main menu, but silently ignores the message if the user
        is sending too many texts (more than MENU_RATE_LIMIT per MENU_RATE_WINDOW_SEC s).
        """
        user_id = update.effective_user.id
 
        if _is_menu_rate_limited(user_id):
            # Silently drop the message — no reply spam
            logger.info(f"Menu rate-limited for user {user_id}")
            return
 
        await update.message.reply_text(self.WELCOME_TEXT, reply_markup=self._main_keyboard())
 
    # ── Main menu (from inline button) ────────────────────────────────────
    async def show_main_menu(self, query):
        await query.edit_message_text(self.WELCOME_TEXT, reply_markup=self._main_keyboard())
 
    # ── Button router ──────────────────────────────────────────────────────
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
 
        if query.data == 'get_invite':
            await self.create_invite_link(query, context)
        elif query.data == 'my_stats':
            await self.show_stats(query)
        elif query.data == 'main_menu':
            await self.show_main_menu(query)
 
    # ── TICKET FLOW ────────────────────────────────────────────────────────
 
    async def ticket_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
 
        user_id = query.from_user.id
        allowed, reason = check_ticket_limits(user_id)
        if not allowed:
            await query.edit_message_text(
                reason,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Main Menu", callback_data='main_menu')]
                ])
            )
            return ConversationHandler.END
 
        await query.edit_message_text(
            "🎫 <b>New Support Ticket — Step 1/2</b>\n\n"
            "Please enter your <b>email address</b> 📧\n\n"
            "<i>You can cancel anytime with /cancel</i>",
            parse_mode='HTML'
        )
        return WAITING_FOR_EMAIL
 
    async def receive_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        email = update.message.text.strip()
 
        if "@" not in email or "." not in email.split("@")[-1]:
            await update.message.reply_text(
                "❌ That doesn't look like a valid email address.\n"
                "Please enter a valid email (e.g. name@example.com)"
            )
            return WAITING_FOR_EMAIL
 
        context.user_data['ticket_email'] = email
        await update.message.reply_text(
            "✅ Email saved!\n\n"
            "🎫 <b>New Support Ticket — Step 2/2</b>\n\n"
            "Now describe your problem in detail 📝\n\n"
            "<i>You can cancel anytime with /cancel</i>",
            parse_mode='HTML'
        )
        return WAITING_FOR_TICKET
 
    async def receive_ticket(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user     = update.effective_user
        user_id  = user.id
        username = user.username or f"user{user_id}"
        text     = update.message.text.strip()
        email    = context.user_data.get('ticket_email', 'Not provided')
 
        allowed, reason = check_ticket_limits(user_id)
        if not allowed:
            await update.message.reply_text(reason)
            return ConversationHandler.END
 
        conn = sqlite3.connect('invite_tracker.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO tickets (user_id, username, email, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, email, text, datetime.now().isoformat())
        )
        ticket_id = c.lastrowid
        conn.commit()
        conn.close()
 
        context.user_data.pop('ticket_email', None)
 
        await update.message.reply_text(
            f"✅ <b>Ticket #{ticket_id} submitted successfully!</b>\n\n"
            f"Our team will get back to you soon. Thank you!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 Submit Another Ticket", callback_data='create_ticket')],
                [InlineKeyboardButton("🔙 Main Menu",             callback_data='main_menu')],
            ]),
            parse_mode='HTML'
        )
 
        admin_text = (
            f"🎫 <b>New Support Ticket #{ticket_id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Username:</b> @{username}\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"📧 <b>Email:</b> {email}\n"
            f"🕐 <b>Time:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Problem:</b>\n{text}"
        )
 
        failed_admins = []
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_text, parse_mode='HTML')
                logger.info(f"Ticket #{ticket_id} delivered to admin {admin_id}")
            except Exception as e:
                logger.error(
                    f"[TICKET #{ticket_id}] Failed to notify admin {admin_id}. "
                    f"Error type: {type(e).__name__} | Detail: {e} | "
                    f"Hint: make sure the admin has started the bot first."
                )
                failed_admins.append(admin_id)
 
        if failed_admins:
            # Warn the user so the ticket doesn't silently disappear
            await update.message.reply_text(
                "⚠️ Your ticket was saved but we couldn't reach the support team right now.\n"
                "Please also contact support directly if it's urgent."
            )
 
        return ConversationHandler.END
 
    async def cancel_ticket(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.pop('ticket_email', None)
        await update.message.reply_text("❌ Ticket cancelled.", reply_markup=self._main_keyboard())
        return ConversationHandler.END
 
    # ── INVITE LINK ────────────────────────────────────────────────────────
    async def create_invite_link(self, query, context):
        user     = query.from_user
        user_id  = user.id
        username = user.username or f"user{user_id}"
 
        try:
            conn = sqlite3.connect('invite_tracker.db')
            c = conn.cursor()
            c.execute("SELECT invite_link FROM invites WHERE user_id = ?", (user_id,))
            existing = c.fetchone()
 
            if existing:
                invite_link = existing[0]
                message = (
                    f"✅ Your existing invite link:\n\n"
                    f"🔗 {invite_link}\n\n"
                    f"You can share this link with your friends!"
                )
            else:
                link_name   = f"{username}_{user_id}"
                chat_invite = await context.bot.create_chat_invite_link(
                    chat_id=CHANNEL_ID,
                    name=link_name,
                    creates_join_request=False
                )
                invite_link = chat_invite.invite_link
                c.execute(
                    "INSERT INTO invites (user_id, username, invite_link, created_at, total_invites) VALUES (?, ?, ?, ?, 0)",
                    (user_id, username, invite_link, datetime.now().isoformat())
                )
                conn.commit()
                message = (
                    f"🎉 Your invite link has been created!\n\n"
                    f"🔗 {invite_link}\n\n"
                    f"Share it with your friends and track how many people you've invited!"
                )
            conn.close()
 
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 My Statistics", callback_data='my_stats')],
                    [InlineKeyboardButton("🔙 Main Menu",     callback_data='main_menu')],
                ])
            )
        except Exception as e:
            logger.error(f"Invite link creation error: {e}")
            await query.edit_message_text(
                "❌ An error occurred while creating the invite link.\n\n"
                "Please make sure the bot is an admin in the channel and has "
                "'Create Invite Links' permission."
            )
 
    # ── STATS ──────────────────────────────────────────────────────────────
    async def show_stats(self, query):
        user_id = query.from_user.id
        conn = sqlite3.connect('invite_tracker.db')
        c = conn.cursor()
 
        c.execute("SELECT total_invites, invite_link FROM invites WHERE user_id = ?", (user_id,))
        result = c.fetchone()
 
        if result:
            total_invites, invite_link = result
            c.execute(
                "SELECT invited_user_id, invited_at FROM invited_users WHERE inviter_id = ? ORDER BY invited_at DESC LIMIT 5",
                (user_id,)
            )
            recent = c.fetchall()
            stats_text = (
                f"📊 Your Statistics\n\n"
                f"👥 Total Invites: {total_invites}\n"
                f"🔗 Your Invite Link: {invite_link}\n\n"
            )
            if recent:
                stats_text += "Recent Invites:\n"
                for invited_id, invited_at in recent:
                    date = datetime.fromisoformat(invited_at).strftime("%d.%m.%Y %H:%M")
                    stats_text += f"• User ID: {invited_id} — {date}\n"
        else:
            stats_text = (
                "📊 You don't have an invite link yet.\n\n"
                "Click 'Get Invite Link' to create one."
            )
 
        conn.close()
        await query.edit_message_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Get Invite Link", callback_data='get_invite')],
                [InlineKeyboardButton("🔙 Main Menu",       callback_data='main_menu')],
            ])
        )
 
    # ── ADMIN /stats command ───────────────────────────────────────────────
    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
 
        conn = sqlite3.connect('invite_tracker.db')
        c = conn.cursor()
 
        c.execute("SELECT username, user_id, total_invites FROM invites ORDER BY total_invites DESC LIMIT 10")
        top_inviters = c.fetchall()
 
        c.execute("SELECT id, username, email, message, created_at FROM tickets WHERE status = 'open' ORDER BY created_at DESC LIMIT 5")
        open_tickets = c.fetchall()
        conn.close()
 
        text = "📊 <b>GENERAL STATISTICS</b>\n\n🏆 Top Inviters:\n\n"
        for i, (username, uid, invites) in enumerate(top_inviters, 1):
            text += f"{i}. @{username} (ID: {uid}) — {invites} invites\n"
 
        text += "\n\n🎫 <b>Recent Open Tickets:</b>\n\n"
        if open_tickets:
            for tid, uname, email, msg, cat in open_tickets:
                date    = datetime.fromisoformat(cat).strftime("%d.%m.%Y %H:%M")
                preview = msg[:80] + "..." if len(msg) > 80 else msg
                text   += f"#{tid} | @{uname} | {email} | {date}\n{preview}\n\n"
        else:
            text += "No open tickets.\n"
 
        await update.message.reply_text(text, parse_mode='HTML')
 
 
# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    bot = InviteBot()
    application = Application.builder().token(BOT_TOKEN).build()
 
    ticket_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.ticket_prompt, pattern='^create_ticket$')],
        states={
            WAITING_FOR_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.receive_email)
            ],
            WAITING_FOR_TICKET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.receive_ticket)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", bot.cancel_ticket),
        ],
        per_message=False,
    )
 
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("stats", bot.admin_stats))
    application.add_handler(ticket_conv)  # ← must stay before generic handlers
 
    # ✅ Any plain text outside a conversation → show menu (rate-limited)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.text_to_menu)
    )
 
    application.add_handler(CallbackQueryHandler(bot.button_callback))
 
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
 
 
if __name__ == '__main__':
    main()
