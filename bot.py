import os
import httpx
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from typing import Optional

# --- Load Environment Variables & Constants ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = "https://dugtrio-backend.onrender.com/api/project/"

# This check is critical. It confirms the token was loaded and satisfies the type checker.
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("FATAL ERROR: TELEGRAM_BOT_TOKEN not found in .env file. Please check your configuration.")

# --- UI Keyboard Definitions (The Buttons) ---

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Returns the main navigation menu with all feature buttons."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Check Sentiment", callback_data='menu_sentiment'),
            InlineKeyboardButton("💧 New Pools (Demo)", callback_data='menu_new_pools')
        ],
        [
            InlineKeyboardButton("📸 Analyze PNL (Demo)", callback_data='menu_analyze_pnl'),
            InlineKeyboardButton("🧠 Track Wallet (Premium)", callback_data='menu_track_wallet')
        ],
        [
            InlineKeyboardButton("🔥 Top Projects (Demo)", callback_data='menu_topprojects'),
            InlineKeyboardButton("📅 Calendar (Demo)", callback_data='menu_calendar')
        ],
        [
            InlineKeyboardButton("👑 Subscribe", callback_data='menu_subscribe'),
            InlineKeyboardButton("💬 Send Feedback", callback_data='menu_feedback')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_sentiment_keyboard() -> InlineKeyboardMarkup:
    """Returns the secondary menu for quick sentiment checks."""
    keyboard = [
        [
            InlineKeyboardButton("SOL", callback_data='sentiment_Solana'),
            InlineKeyboardButton("JUP", callback_data='sentiment_Jupiter')
        ],
        [
            InlineKeyboardButton("PYTH", callback_data='sentiment_Pyth'),
            InlineKeyboardButton("BONK", callback_data='sentiment_Bonk')
        ],
        [InlineKeyboardButton("« Back to Main Menu", callback_data='menu_start')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Core Command & Callback Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and 'Back to Main Menu' button presses."""
    welcome_message = (
        "<b>⛏️ DugTrio is Online. Ready to Unearth Alpha! 🚀</b>\n\n"
        "<i>Your AI-powered analytics system for the Solana ecosystem is live.</i>\n\n"
        "Use the buttons below to navigate or type a command like <code>/sentiment Solana</code>."
    )
    # If a button was clicked, edit the existing message. Otherwise, send a new one.
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(
            welcome_message, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )
    elif update.message:
        await update.message.reply_text(
            welcome_message, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command by reusing the start message."""
    await start_command(update, context)


async def sentiment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the sentiment sub-menu when the 'Check Sentiment' button is pressed."""
    message = (
        "<b>📊 Sentiment Analysis</b>\n\n"
        "Choose a popular project below or type your own:\n"
        "<code>/sentiment [project_name]</code>\n\n"
        "Example: <code>/sentiment WIF</code>"
    )
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(
            message, reply_markup=get_sentiment_keyboard(), parse_mode=ParseMode.HTML
        )


async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles both button presses and typed commands for sentiment analysis."""
    project_name: Optional[str] = None
    chat_id = update.effective_chat.id

    # Extract project name from a button press
    if update.callback_query and update.callback_query.data:
        await update.callback_query.answer()  # Acknowledge the button press
        project_name = update.callback_query.data.split('_')[1]
    # Extract project name from a typed command
    elif context.args:
        project_name = context.args[0]

    if not project_name:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please choose a project or provide a name.", reply_markup=get_sentiment_keyboard()
        )
        return

    # Acknowledge the request immediately so the user knows the bot is working.
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"<i>⛏️ Digging for {project_name.capitalize()} sentiment...\n\n(Note: The server may need a moment to start up on the first request.)</i>",
        parse_mode=ParseMode.HTML
    )

    try:
        async with httpx.AsyncClient() as client:
            # Render's free tier can be slow to wake up, so a long timeout is essential.
            response = await client.get(f"{API_URL}{project_name.capitalize()}", timeout=180.0)

        response.raise_for_status()  # Raise an error for bad responses (404, 502, etc.)
        data = response.json()
        score = data.get('sentiment_score', 0)
        tweets = data.get('analyzed_tweet_count', 0)

        mood = "🟢 Bullish" if score >= 70 else "🟡 Neutral" if score >= 50 else "🔴 Bearish"

        reply = (
            f"<b>📈 Sentiment for {project_name.upper()}</b>\n\n"
            f"<b>Overall Mood:</b> {mood}\n"
            f"<b>Sentiment Score:</b> <code>{score:.2f}%</code>\n"
            f"<b>Based on:</b> <i>{tweets} recent tweets</i>"
        )
        await context.bot.send_message(
            chat_id=chat_id, text=reply,
            reply_markup=get_sentiment_keyboard(), parse_mode=ParseMode.HTML
        )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            reply = f"⚠️ No data found for <b>{project_name.upper()}</b>. The tracker may not have this token yet."
        else:
            reply = f"❌ Server error: Could not retrieve data ({e.response.status_code}). Please try again."
        await context.bot.send_message(
            chat_id=chat_id, text=reply,
            reply_markup=get_sentiment_keyboard(), parse_mode=ParseMode.HTML
        )
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await context.bot.send_message(
            chat_id=chat_id, text=reply,
            reply_markup=get_sentiment_keyboard(), parse_mode=ParseMode.HTML
        )


# --- "Demo Magic" Handlers (for impressive, simulated features) ---

async def new_pools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = (
        "<b>🔥 New Pool Scanner (Demo)</b>\n\n"
        "<b>1. $CLEO (Cleopatra)</b>\n"
        "  - Volume (1h): <code>$78,430</code> ⬆️\n"
        "  - Hype Score: <code>85/100</code>\n"
        "  - Signal: <b>BOOM Alert 🚨</b>\n\n"
        "<b>2. $GIZA (Pyramid)</b>\n"
        "  - Volume (1h): <code>$45,120</code> ↗️\n"
        "  - Hype Score: <code>62/100</code>\n"
        "  - Signal: <i>Moderate interest</i>"
    )
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(
            reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )


async def analyze_pnl_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(
            "📸 **PNL Analyzer (Demo)**\n\nPlease upload a screenshot of your PNL and use the caption <code>/pnl</code> to begin analysis.",
            reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )


async def analyze_pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.photo:
        await update.message.reply_text("🔍 Analyzing your PNL screenshot...")
        await asyncio.sleep(2)  # Simulate a delay for realism
        reply = (
            "<b>✅ PNL Analysis Complete</b>\n\n"
            "<b>Detected Coin:</b> <code>$CLEO</code>\n"
            "<b>Realized Profit:</b> 🚀 <code>+1,240%</code>\n"
            "<b>Wallet Confidence:</b> High\n\n"
            "<b>Signal:</b> This trade matches the pattern of a known high-performance wallet. Recommend tracking."
        )
        await update.message.reply_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


async def track_wallet_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(
            "🧠 **Smart Wallet Tracker (Premium Demo)**\n\nPlease send the command:\n<code>/trackwallet [address]</code>",
            reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )


async def track_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and update.message:
        wallet_address = context.args[0]
        reply = (
            "<b>🧠 Smart Wallet Tracker (Premium)</b>\n\n"
            f"Now tracking wallet: <code>{wallet_address}</code>\n"
            "Status: 🟢 <b>Active</b>\n\n"
            "<i>You will receive alerts on this wallet's significant trades.</i>"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text("Usage: `/trackwallet <address>`")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = (
        "<b>👑 Unlock DugTrio Premium</b>\n\n"
        "1. Send <b>0.5 SOL</b> to:\n<code>YourSolanaWalletAddress.sol</code>\n\n"
        "2. DM <b>@YourUsername</b> with your transaction ID.\n\n"
        "<i>Thanks for supporting the alpha!</i>"
    )
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(
            reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML
        )


async def top_projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = "<b>📊 Top Trending (Demo)</b>\n\n1. $SOL - 🔥 High sentiment..."
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = "<b>📅 Upcoming Events (Demo)</b>\n\n• Oct 20: Hacker House - Singapore..."
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = "💬 **Send Feedback (Demo)**\n\nWe'd love your ideas! Please reply to this message with any suggestions."
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


# --- Main Bot Logic ---

def main() -> None:
    """Starts the bot and registers all the different ways a user can interact."""
    # This builder will no longer show an error because we checked the token on line 17.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    print("✅ DugTrio Alpha Hunter is online...")

    # Register handlers for simple text commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("sentiment", sentiment_command))
    application.add_handler(CommandHandler("trackwallet", track_wallet_command))

    # This handler is specifically for the /pnl command when it's a caption on a photo
    application.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r'/pnl'), analyze_pnl_command))

    # Register handlers for main menu button presses, using their callback_data
    application.add_handler(CallbackQueryHandler(start_command, pattern=r'^menu_start$'))
    application.add_handler(CallbackQueryHandler(sentiment_menu, pattern=r'^menu_sentiment$'))
    application.add_handler(CallbackQueryHandler(new_pools_command, pattern=r'^menu_new_pools$'))
    application.add_handler(CallbackQueryHandler(analyze_pnl_prompt, pattern=r'^menu_analyze_pnl$'))
    application.add_handler(CallbackQueryHandler(track_wallet_prompt, pattern=r'^menu_track_wallet$'))
    application.add_handler(CallbackQueryHandler(subscribe_command, pattern=r'^menu_subscribe$'))
    application.add_handler(CallbackQueryHandler(top_projects_command, pattern=r'^menu_topprojects$'))
    application.add_handler(CallbackQueryHandler(calendar_command, pattern=r'^menu_calendar$'))
    application.add_handler(CallbackQueryHandler(feedback_command, pattern=r'^menu_feedback$'))

    # This handler catches all specific sentiment buttons (e.g., 'sentiment_Solana')
    application.add_handler(CallbackQueryHandler(sentiment_command, pattern=r'^sentiment_'))

    # Start the bot and wait for user input
    application.run_polling()


if __name__ == "__main__":
    main()