import os
import httpx
import asyncio
from datetime import datetime
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
            InlineKeyboardButton("🔥 Top Projects", callback_data='menu_topprojects')
        ],
        [
            InlineKeyboardButton("📸 PNL Viewer", callback_data='menu_analyze_pnl'),
            InlineKeyboardButton("🧠 Track Wallet (Premium)", callback_data='menu_track_wallet')
        ],
        [
            InlineKeyboardButton("👑 Subscribe", callback_data='menu_subscribe')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_sentiment_keyboard(project_name: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    Returns the secondary menu for sentiment checks.
    If a project_name is provided, it adds a button to view 7-day history.
    """
    keyboard = [
        [
            InlineKeyboardButton("SOL", callback_data='sentiment_Solana'),
            InlineKeyboardButton("JUP", callback_data='sentiment_Jupiter')
        ],
        [
            InlineKeyboardButton("PYTH", callback_data='sentiment_Pyth'),
            InlineKeyboardButton("BONK", callback_data='sentiment_Bonk')
        ]
    ]
    if project_name:
        keyboard.append([
            InlineKeyboardButton(f"📈 7-Day History", callback_data=f'history_{project_name}')
        ])

    keyboard.append([InlineKeyboardButton("« Back to Main Menu", callback_data='menu_start')])
    return InlineKeyboardMarkup(keyboard)

# Helper utilities to avoid edit_text
async def send_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, disable_web_page_preview: Optional[bool] = None):
    if not update.effective_chat:
        return None
    chat_id = update.effective_chat.id
    return await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=disable_web_page_preview
    )

async def safe_delete_message(message):
    try:
        await message.delete()
    except Exception:
        pass

# --- Core Command & Callback Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and 'Back to Main Menu' button presses."""
    welcome_message = (
        "<b>⛏️ DugTrio is Online. Ready to Unearth Alpha! 🚀</b>\n\n"
        "<i>Your AI-powered analytics system for the Solana ecosystem is live.</i>\n\n"
        "Use the buttons below to navigate or type a command like <code>/sentiment Solana</code>."
    )
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.message:
            await safe_delete_message(query.message)
        await send_new_message(update, context, welcome_message, reply_markup=get_main_menu_keyboard())
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
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.message:
            await safe_delete_message(query.message)
        await send_new_message(update, context, message, reply_markup=get_sentiment_keyboard())


async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles sentiment requests from both commands and buttons.
    Sends a "digging" message and then sends results as a new message.
    """
    project_name: Optional[str] = None
    status_message = None
    query = update.callback_query

    if query:
        await query.answer()
        try:
            if query.data:
                project_name = query.data.split('_', 1)[1]
        except Exception:
            project_name = None
        if query.message:
            await safe_delete_message(query.message)
        status_message = await send_new_message(
            update, context, f"<i>⛏️ Digging for {project_name.capitalize() if project_name else 'project'} sentiment...</i>"
        )
    elif context.args and update.message:
        project_name = context.args[0]
        status_message = await update.message.reply_text(
            text=f"<i>⛏️ Digging for {project_name.capitalize()} sentiment...</i>",
            parse_mode=ParseMode.HTML
        )
    else:
        if update.message:
            await update.message.reply_text(
                "Please specify a project. Usage: `/sentiment Solana`",
                reply_markup=get_sentiment_keyboard()
            )
        return

    if not project_name:
        await send_new_message(update, context, "⚠️ Could not determine the project. Please try again.", reply_markup=get_sentiment_keyboard())
        if status_message:
            await safe_delete_message(status_message)
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}{project_name.capitalize()}", timeout=180.0)
        response.raise_for_status()
        data = response.json()
        score = data.get('sentiment_score', 0)
        tweets = data.get('analyzed_tweet_count', 0)
        top_tweet = data.get('top_tweet')

        mood = "🟢 Bullish" if score >= 70 else "🟡 Neutral" if score >= 50 else "🔴 Bearish"

        reply_parts = [
            f"<b>📈 Sentiment for {project_name.upper()}</b>\n",
            f"<b>Overall Mood:</b> {mood}",
            f"<b>Sentiment Score:</b> <code>{score:.2f}%</code>",
            f"<b>Based on:</b> <i>{tweets} recent tweets</i>"
        ]
        if top_tweet and isinstance(top_tweet, dict):
            tweet_text = top_tweet.get('text', 'N/A')
            tweet_author = top_tweet.get('author_username', 'N/A')
            reply_parts.append(
                f"\n<b>🔝 Top Tweet driving the score:</b>\n"
                f"<i>\"{tweet_text}\"</i>\n"
                f"- <b>Author:</b> @{tweet_author}"
            )
        reply = "\n".join(reply_parts)

        await send_new_message(
            update,
            context,
            reply,
            reply_markup=get_sentiment_keyboard(project_name=project_name),
            disable_web_page_preview=True
        )

        if top_tweet and isinstance(top_tweet, dict) and top_tweet.get('media_url') and update.effective_chat:
            media_url = top_tweet['media_url']
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=media_url)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            reply = f"⚠️ No data found for <b>{project_name.upper()}</b>. The tracker may not have this token yet."
        else:
            reply = f"❌ Server error: Could not retrieve data ({e.response.status_code}). Please try again."
        await send_new_message(update, context, reply, reply_markup=get_sentiment_keyboard(project_name=project_name))
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await send_new_message(update, context, reply, reply_markup=get_sentiment_keyboard(project_name=project_name))
    finally:
        if status_message:
            await safe_delete_message(status_message)


def create_bar(score: float, length: int = 10) -> str:
    """Creates a text-based progress bar for sentiment scores (0-100)."""
    score = max(0, min(100, score))  # Clamp score between 0 and 100
    filled_len = int(length * score / 100)
    return '█' * filled_len + '░' * (length - filled_len)


async def sentiment_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the 7-day sentiment history for a project."""
    query = update.callback_query
    if query:
        await query.answer()

    project_name = query.data.split('_', 1)[1] if query and query.data else None

    if query and query.message:
        await safe_delete_message(query.message)

    status_message = await send_new_message(
        update, context, f"<i>Fetching 7-day history for {project_name.capitalize() if project_name else 'project'}...</i>"
    )

    try:
        async with httpx.AsyncClient() as client:
            api_url_history = f"https://dugtrio-backend.onrender.com/api/history/{(project_name or '').capitalize()}"
            response = await client.get(api_url_history, timeout=60.0)

        response.raise_for_status()
        history_data = response.json()

        if not history_data:
            reply = f"😕 No historical data found for <b>{(project_name or 'PROJECT').upper()}</b>."
        else:
            reply_parts = [f"<b>📈 7-Day Sentiment History for {(project_name or 'PROJECT').upper()}</b>\n"]
            history_data.sort(key=lambda x: x.get('date', ''))
            for entry in history_data:
                date_obj = datetime.strptime(entry.get('date'), '%Y-%m-%d')
                day_name = date_obj.strftime('%a')
                score = entry.get('average_sentiment_score', 0)
                bar = create_bar(score)
                reply_parts.append(f"<code>{day_name}: {bar} {score:.0f}%</code>")
            reply = "\n".join(reply_parts)

        await send_new_message(
            update, context, reply, reply_markup=get_sentiment_keyboard(project_name=project_name)
        )

    except httpx.HTTPStatusError as e:
        reply = f"❌ Server error while fetching history ({e.response.status_code})."
        await send_new_message(update, context, reply, reply_markup=get_sentiment_keyboard(project_name=project_name))
    except Exception as e:
        reply = f"❌ An unexpected error occurred while fetching history: {e}"
        await send_new_message(update, context, reply, reply_markup=get_sentiment_keyboard(project_name=project_name))
    finally:
        if status_message:
            await safe_delete_message(status_message)


# --- "Demo Magic" Handlers (for impressive, simulated features) ---

async def analyze_pnl_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user to enter a project name for PNL data."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.message:
            await safe_delete_message(query.message)
        await send_new_message(
            update, context,
            "<b>📸 PNL Card Viewer</b>\n\n"
            "Please enter the project name to view its PNL cards. "
            "Usage:\n<code>/pnl [project_name]</code>\n\n"
            "Example: <code>/pnl Solana</code>",
            reply_markup=get_main_menu_keyboard()
        )


async def analyze_pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays PNL cards for a given project."""
    if not context.args:
        if update.message:
            await update.message.reply_text(
                "Please specify a project. Usage: `/pnl Solana`"
            )
        return

    project_name = context.args[0]
    status_message = None
    if update.message:
        status_message = await update.message.reply_text(
            f"<i>Fetching PNL cards for {project_name.capitalize()}...</i>",
            parse_mode=ParseMode.HTML
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://dugtrio-backend.onrender.com/api/pnl/{project_name.capitalize()}", timeout=60.0)

        response.raise_for_status()
        pnl_cards = response.json()

        if not pnl_cards:
            reply = f"😕 No PNL cards found for <b>{project_name.upper()}</b>."
        else:
            reply_parts = [f"<b>📸 PNL Cards for {project_name.upper()}</b>\n"]
            for i, card in enumerate(pnl_cards, 1):
                card_url = card.get('url')
                if card_url:
                    reply_parts.append(f"{i}. <a href='{card_url}'>PNL Card #{i}</a>")
            reply = "\n".join(reply_parts)

        await send_new_message(
            update, context, reply, reply_markup=get_main_menu_keyboard(), disable_web_page_preview=False
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            reply = f"⚠️ No data found for <b>{project_name.upper()}</b>."
        else:
            reply = f"❌ Server error: Could not retrieve data ({e.response.status_code})."
        await send_new_message(update, context, reply, reply_markup=get_main_menu_keyboard())
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await send_new_message(update, context, reply, reply_markup=get_main_menu_keyboard())
    finally:
        if status_message:
            await safe_delete_message(status_message)


async def track_wallet_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query and query.message:
        await query.answer()
        await safe_delete_message(query.message)
        await send_new_message(
            update, context,
            "<b>🧠 Smart Wallet Tracker (Premium Demo)</b>\n\nPlease send the command:\n<code>/trackwallet [address]</code>",
            reply_markup=get_main_menu_keyboard()
        )

async def track_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if context.args:
        wallet_address = context.args[0]
        reply = (
            "<b>🧠 Smart Wallet Tracker (Premium)</b>\n\n"
            f"Now tracking wallet: <code>{wallet_address}</code>\n"
            "Status: 🟢 <b>Active</b>\n\n"
            "<i>You will receive alerts on this wallet's significant trades.</i>"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Usage: `/trackwallet <address>`")
        await update.message.reply_text("Usage: `/trackwallet <address>`")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = (
        "<b>👑 Unlock DugTrio Premium</b>\n\n"
        "1. Send <b>0.5 SOL</b> to:\n<code>YourSolanaWalletAddress.sol</code>\n\n"
        "2. DM <b>@YourUsername</b> with your transaction ID.\n\n"
        "<i>Thanks for supporting the alpha!</i>"
    )
    if update.callback_query and update.callback_query.message:
        await update.callback_query.answer()
        await safe_delete_message(update.callback_query.message)
        await send_new_message(update, context, reply, reply_markup=get_main_menu_keyboard())


async def top_projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the top trending projects from the backend."""
    query = update.callback_query
    if query and query.message:
        await query.answer()
        await safe_delete_message(query.message)
        status_message = await send_new_message(update, context, "<i>🔥 Fetching top trending projects...</i>")
    elif update.message:
        status_message = await update.message.reply_text(
            "<i>🔥 Fetching top trending projects...</i>",
            parse_mode=ParseMode.HTML
        )
    else:
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://dugtrio-backend.onrender.com/api/trending", timeout=60.0)

        response.raise_for_status()
        projects = response.json()

        if not projects:
            reply = "😕 No trending projects found at the moment."
        else:
            reply_parts = ["<b>🔥 Top Trending Projects</b>\n"]
            for i, project in enumerate(projects, 1):
                reply_parts.append(f"{i}. ${project.upper()}")
            reply = "\n".join(reply_parts)

        await send_new_message(update, context, reply, reply_markup=get_main_menu_keyboard())
    except httpx.HTTPStatusError as e:
        reply = f"❌ Server error: Could not retrieve data ({e.response.status_code}). Please try again."
        await send_new_message(update, context, reply, reply_markup=get_main_menu_keyboard())
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await send_new_message(update, context, reply, reply_markup=get_main_menu_keyboard())
    finally:
        if status_message:
            await safe_delete_message(status_message)


# --- Main Bot Logic ---

def main() -> None:
    """Starts the bot and registers all the different ways a user can interact."""
    assert TELEGRAM_BOT_TOKEN is not None  # Type narrowing for type checker
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    print("✅ DugTrio Alpha Hunter is online...")

    # Register handlers for simple text commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("sentiment", sentiment_command))
    application.add_handler(CommandHandler("trackwallet", track_wallet_command))
    application.add_handler(CommandHandler("pnl", analyze_pnl_command))

    # Register handlers for main menu button presses, using their callback_data
    application.add_handler(CallbackQueryHandler(start_command, pattern=r'^menu_start$'))
    application.add_handler(CallbackQueryHandler(sentiment_menu, pattern=r'^menu_sentiment$'))
    application.add_handler(CallbackQueryHandler(analyze_pnl_prompt, pattern=r'^menu_analyze_pnl$'))
    application.add_handler(CallbackQueryHandler(track_wallet_prompt, pattern=r'^menu_track_wallet$'))
    application.add_handler(CallbackQueryHandler(subscribe_command, pattern=r'^menu_subscribe$'))
    application.add_handler(CallbackQueryHandler(top_projects_command, pattern=r'^menu_topprojects$'))

    # Sentiment actions
    application.add_handler(CallbackQueryHandler(sentiment_command, pattern=r'^sentiment_'))
    application.add_handler(CallbackQueryHandler(sentiment_history_command, pattern=r'^history_'))

    application.run_polling()


if __name__ == "__main__":
    main()