import os
import httpx
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest # Import specific errors
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from typing import Optional

# --- Load Environment Variables & Constants ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = "https://dugtrio-backend.onrender.com/api/project/"

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("FATAL ERROR: TELEGRAM_BOT_TOKEN not found in .env file.")

# --- UI Keyboards ---

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📊 Check Sentiment", callback_data='menu_sentiment')],
        [InlineKeyboardButton("💧 New Pools (Demo)", callback_data='menu_new_pools')],
        [InlineKeyboardButton("📸 Analyze PNL (Demo)", callback_data='menu_analyze_pnl')],
        [InlineKeyboardButton("🧠 Track Wallet (Premium)", callback_data='menu_track_wallet')],
        [InlineKeyboardButton("👑 Subscribe", callback_data='menu_subscribe')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sentiment_keyboard(project_name: Optional[str] = None) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("SOL", callback_data='sentiment_Solana'),
            InlineKeyboardButton("JUP", callback_data='sentiment_Jupiter'),
            InlineKeyboardButton("PYTH", callback_data='sentiment_Pyth'),
            InlineKeyboardButton("BONK", callback_data='sentiment_Bonk')
        ],
    ]
    # Dynamically add history button if we have a project context
    if project_name:
         keyboard.append([InlineKeyboardButton(f"📈 7-Day History for {project_name.upper()}", callback_data=f'history_{project_name}')])

    keyboard.append([InlineKeyboardButton("« Back to Main Menu", callback_data='menu_start')])
    return InlineKeyboardMarkup(keyboard)

# --- Utility: Safe Message Editing/Sending ---
async def safe_send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Safely sends or edits a message, handling potential errors."""
    try:
        if update.callback_query and update.callback_query.message:
            await context.bot.edit_message_text(
                chat_id=update.callback_query.message.chat.id,
                message_id=update.callback_query.message.message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        elif update.message:
            await update.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
        elif update.effective_chat: # Fallback if no direct message/query context
             await context.bot.send_message(
                chat_id=update.effective_chat.id, text=text,
                reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
    except BadRequest as e:
        # Ignore "message is not modified" errors, common when clicking buttons quickly
        if "Message is not modified" not in str(e):
            print(f"BadRequest when sending/editing message: {e}")
            # Optionally send a new message if editing failed severely
            if update.effective_chat:
                 await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred displaying the menu.")
    except Forbidden:
        print(f"Bot blocked by user {update.effective_user.id if update.effective_user else 'unknown'}")
    except Exception as e:
        print(f"Unexpected error in safe_send_or_edit: {e}")


# --- Command & Callback Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /start command and 'menu_start' callback."""
    if update.callback_query:
        await update.callback_query.answer() # Answer immediately!
    welcome_message = "<b>⛏️ DugTrio Online!</b>\n\nUse buttons or commands like <code>/sentiment Solana</code>."
    await safe_send_or_edit(update, context, welcome_message, get_main_menu_keyboard())

async def sentiment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the sentiment sub-menu."""
    if not update.callback_query: return
    await update.callback_query.answer() # Answer immediately!
    message = "<b>📊 Sentiment Analysis</b>\n\nChoose below or type <code>/sentiment [project]</code>."
    await safe_send_or_edit(update, context, message, get_sentiment_keyboard())

async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles sentiment requests from commands and buttons."""
    project_name: Optional[str] = None
    chat_id = update.effective_chat.id if update.effective_chat else None
    status_message = None # To hold the "Digging..." message

    if update.callback_query and update.callback_query.data:
        await update.callback_query.answer() # Answer immediately!
        try:
             project_name = update.callback_query.data.split('_', 1)[1]
        except IndexError:
             await safe_send_or_edit(update, context, "Invalid button data.", get_sentiment_keyboard())
             return
    elif context.args:
        project_name = context.args[0]
    else:
        if chat_id is not None:
            await context.bot.send_message(chat_id=chat_id, text="Choose a project or type `/sentiment <name>`.", reply_markup=get_sentiment_keyboard())
        return

    if not project_name: # Should not happen if logic above is correct, but safety check
        if chat_id is not None:
            await context.bot.send_message(chat_id=chat_id, text="Could not identify project.", reply_markup=get_sentiment_keyboard())
        return

    # Send "Digging..." message
    status_message = None
    if chat_id is not None:
        status_message = await context.bot.send_message(chat_id=chat_id, text=f"<i>⛏️ Digging for {project_name.capitalize()} sentiment...</i>", parse_mode=ParseMode.HTML)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}{project_name.capitalize()}", timeout=45.0)
        response.raise_for_status()
        data = response.json()
        score = data.get('sentiment_score', 0)
        tweets = data.get('analyzed_tweet_count', 0)
        mood = "🟢 Bullish" if score >= 70 else "🟡 Neutral" if score >= 50 else "🔴 Bearish"
        reply = (
            f"<b>📈 Sentiment for {project_name.upper()}</b>\n\n"
            f"<b>Mood:</b> {mood}\n<b>Score:</b> <code>{score:.2f}%</code>\n<i>Based on {tweets} tweets.</i>"
        )
        if chat_id is not None:
            if chat_id is not None:
                await context.bot.send_message(chat_id=chat_id, text=reply, reply_markup=get_sentiment_keyboard(project_name), parse_mode=ParseMode.HTML)

    except httpx.HTTPStatusError as e:
        reply = f"⚠️ No data for <b>{project_name.upper()}</b>." if e.response.status_code == 404 else f"❌ Server error ({e.response.status_code})."
        if chat_id is not None:
            await context.bot.send_message(chat_id=chat_id, text=reply, reply_markup=get_sentiment_keyboard(project_name), parse_mode=ParseMode.HTML)
    except Exception as e:
        reply = f"❌ Error: {e}"
        if chat_id is not None:
            await context.bot.send_message(chat_id=chat_id, text=reply, reply_markup=get_sentiment_keyboard(project_name), parse_mode=ParseMode.HTML)
    finally:
        # Clean up the "Digging..." message
        if status_message:
            try:
                await status_message.delete()
            except Exception: pass # Ignore if deletion fails

async def sentiment_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Demo) Shows fake sentiment history."""
    if not update.callback_query or not update.callback_query.data: return
    await update.callback_query.answer() # Answer immediately!
    project_name = update.callback_query.data.split('_', 1)[1]
    
    # Simulate history data
    fake_history = [
        ("Mon", 65.2), ("Tue", 71.8), ("Wed", 75.1), ("Thu", 68.0),
        ("Fri", 72.5), ("Sat", 80.3), ("Sun", 78.9)
    ]
    reply_parts = [f"<b>📈 7-Day Sentiment History for {project_name.upper()}</b>\n"]
    for day, score in fake_history:
        bar = '█' * int(score / 10) + '░' * (10 - int(score / 10))
        reply_parts.append(f"<code>{day}: {bar} {score:.0f}%</code>")
    reply = "\n".join(reply_parts)
    
    await safe_send_or_edit(update, context, reply, get_sentiment_keyboard(project_name))

# --- "Demo Magic" Handlers ---

async def new_pools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query: return
    await update.callback_query.answer() # Answer immediately!
    reply = "<b>🔥 New Pool Scanner (Demo)</b>\n\n<b>1. $CLEO</b>..." # Your demo text
    await safe_send_or_edit(update, context, reply, get_main_menu_keyboard())

async def analyze_pnl_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query: return
    await update.callback_query.answer() # Answer immediately!
    await safe_send_or_edit(update, context, "📸 **PNL Analyzer (Demo)**\n\nUpload screenshot with caption <code>/pnl</code>.", get_main_menu_keyboard())

async def analyze_pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.photo:
        await update.message.reply_text("🔍 Analyzing PNL...")
        await asyncio.sleep(2)
        reply = "<b>✅ PNL Analysis Complete (Demo)</b>\n\n<b>Coin:</b> <code>$CLEO</code>..." # Your demo text
        await update.message.reply_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)

async def track_wallet_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query: return
    await update.callback_query.answer() # Answer immediately!
    await safe_send_or_edit(update, context, "🧠 **Wallet Tracker (Demo)**\n\nSend command: <code>/trackwallet [address]</code>", get_main_menu_keyboard())

async def track_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and update.message:
        wallet = context.args[0]
        reply = f"<b>🧠 Wallet Tracker (Premium Demo)</b>\n\nTracking <code>{wallet}</code>..." # Your demo text
        await update.message.reply_text(reply, parse_mode=ParseMode.HTML)
    elif update.message:
         await update.message.reply_text("Usage: `/trackwallet <address>`")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query: return
    await update.callback_query.answer() # Answer immediately!
    reply = "<b>👑 Unlock Premium (Demo)</b>\n\n1. Send 0.5 SOL to...\n<code>YourAddress.sol</code>..." # Your demo text
    await safe_send_or_edit(update, context, reply, get_main_menu_keyboard())

# --- Main Bot Logic ---

def main() -> None:
    """Starts the bot and registers all handlers."""
    assert TELEGRAM_BOT_TOKEN is not None, "TELEGRAM_BOT_TOKEN must be set"
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    print("✅ DugTrio Alpha Hunter is online...")

    # Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("sentiment", sentiment_command))
    application.add_handler(CommandHandler("trackwallet", track_wallet_command))
    application.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r'/pnl'), analyze_pnl_command))

    # Callback Query Handlers (Buttons)
    application.add_handler(CallbackQueryHandler(start_command, pattern=r'^menu_start$'))
    application.add_handler(CallbackQueryHandler(sentiment_menu, pattern=r'^menu_sentiment$'))
    application.add_handler(CallbackQueryHandler(new_pools_command, pattern=r'^menu_new_pools$'))
    application.add_handler(CallbackQueryHandler(analyze_pnl_prompt, pattern=r'^menu_analyze_pnl$'))
    application.add_handler(CallbackQueryHandler(track_wallet_prompt, pattern=r'^menu_track_wallet$'))
    application.add_handler(CallbackQueryHandler(subscribe_command, pattern=r'^menu_subscribe$'))
    # Sentiment specific buttons
    application.add_handler(CallbackQueryHandler(sentiment_command, pattern=r'^sentiment_'))
    application.add_handler(CallbackQueryHandler(sentiment_history_command, pattern=r'^history_')) # Example for history button

    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()