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
    """
    Handles sentiment requests from both commands and buttons.
    Sends a "digging" message and then edits it with the results for a better UX.
    """
    project_name: Optional[str] = None
    query = update.callback_query

    # Determine the chat_id and how to respond (edit vs. send)
    if query:
        await query.answer()  # Acknowledge button press
        project_name = query.data.split('_')[1]
        # Edit the menu message to show the bot is working
        status_message = await query.message.edit_text(
            text=f"<i>⛏️ Digging for {project_name.capitalize()} sentiment...</i>",
            parse_mode=ParseMode.HTML
        )
    elif context.args:
        project_name = context.args[0]
        # Send a new message since this was a typed command
        status_message = await update.message.reply_text(
            text=f"<i>⛏️ Digging for {project_name.capitalize()} sentiment...</i>",
            parse_mode=ParseMode.HTML
        )
    else:
        # This case handles a user typing /sentiment without args
        if update.message:
            await update.message.reply_text(
                "Please specify a project. Usage: `/sentiment Solana`",
                reply_markup=get_sentiment_keyboard()
            )
        return

    # If project_name is still None, something went wrong.
    if not project_name:
        await status_message.edit_text(
            "⚠️ Could not determine the project. Please try again.",
            reply_markup=get_sentiment_keyboard()
        )
        return

    try:
        async with httpx.AsyncClient() as client:
            # Render's free tier can be slow to wake up, so a long timeout is essential.
            response = await client.get(f"{API_URL}{project_name.capitalize()}", timeout=180.0)

        response.raise_for_status()  # Raise an error for bad responses (404, 502, etc.)
        data = response.json()
        score = data.get('sentiment_score', 0)
        tweets = data.get('analyzed_tweet_count', 0)
        top_tweet = data.get('top_tweet') # Safely get the top_tweet object

        mood = "🟢 Bullish" if score >= 70 else "🟡 Neutral" if score >= 50 else "🔴 Bearish"

        # --- Build the Reply Message ---
        reply_parts = [
            f"<b>📈 Sentiment for {project_name.upper()}</b>\n",
            f"<b>Overall Mood:</b> {mood}",
            f"<b>Sentiment Score:</b> <code>{score:.2f}%</code>",
            f"<b>Based on:</b> <i>{tweets} recent tweets</i>"
        ]

        # Add the top tweet section if it exists
        if top_tweet and isinstance(top_tweet, dict):
            tweet_text = top_tweet.get('text', 'N/A')
            tweet_author = top_tweet.get('author_username', 'N/A')
            reply_parts.append(
                f"\n<b>🔝 Top Tweet driving the score:</b>\n"
                f"<i>\"{tweet_text}\"</i>\n"
                f"- <b>Author:</b> @{tweet_author}"
            )

        reply = "\n".join(reply_parts)

        await status_message.edit_text(
            text=reply,
            reply_markup=get_sentiment_keyboard(project_name=project_name),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

        # After sending the main message, check for and send the photo if it exists
        if top_tweet and isinstance(top_tweet, dict) and top_tweet.get('media_url'):
            media_url = top_tweet['media_url']
            await context.bot.send_photo(chat_id=status_message.chat_id, photo=media_url)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            reply = f"⚠️ No data found for <b>{project_name.upper()}</b>. The tracker may not have this token yet."
        else:
            reply = f"❌ Server error: Could not retrieve data ({e.response.status_code}). Please try again."
        await status_message.edit_text(
            text=reply,
            reply_markup=get_sentiment_keyboard(project_name=project_name),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await status_message.edit_text(
            text=reply,
            reply_markup=get_sentiment_keyboard(project_name=project_name),
            parse_mode=ParseMode.HTML
        )


def create_bar(score: float, length: int = 10) -> str:
    """Creates a text-based progress bar for sentiment scores (0-100)."""
    score = max(0, min(100, score))  # Clamp score between 0 and 100
    filled_len = int(length * score / 100)
    return '█' * filled_len + '░' * (length - filled_len)


async def sentiment_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the 7-day sentiment history for a project."""
    query = update.callback_query
    await query.answer()

    project_name = query.data.split('_')[1]

    status_message = await query.message.edit_text(
        f"<i>Fetching 7-day history for {project_name.capitalize()}...</i>",
        parse_mode=ParseMode.HTML
    )

    try:
        async with httpx.AsyncClient() as client:
            api_url_history = f"https://dugtrio-backend.onrender.com/api/history/{project_name.capitalize()}"
            response = await client.get(api_url_history, timeout=60.0)

        response.raise_for_status()
        history_data = response.json()

        if not history_data:
            reply = f"😕 No historical data found for <b>{project_name.upper()}</b>."
        else:
            reply_parts = [f"<b>📈 7-Day Sentiment History for {project_name.upper()}</b>\n"]
            # Sort data by date just in case it's not sorted
            history_data.sort(key=lambda x: x.get('date', ''))
            for entry in history_data:
                date_obj = datetime.strptime(entry.get('date'), '%Y-%m-%d')
                day_name = date_obj.strftime('%a')
                score = entry.get('average_sentiment_score', 0)
                bar = create_bar(score)
                reply_parts.append(f"<code>{day_name}: {bar} {score:.0f}%</code>")
            reply = "\n".join(reply_parts)

        await status_message.edit_text(
            reply,
            reply_markup=get_sentiment_keyboard(project_name=project_name),
            parse_mode=ParseMode.HTML
        )

    except httpx.HTTPStatusError as e:
        reply = f"❌ Server error while fetching history ({e.response.status_code})."
        await status_message.edit_text(reply, reply_markup=get_sentiment_keyboard(project_name=project_name), parse_mode=ParseMode.HTML)
    except Exception as e:
        reply = f"❌ An unexpected error occurred while fetching history: {e}"
        await status_message.edit_text(reply, reply_markup=get_sentiment_keyboard(project_name=project_name), parse_mode=ParseMode.HTML)


# --- "Demo Magic" Handlers (for impressive, simulated features) ---


async def analyze_pnl_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompts the user to enter a project name for PNL data."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.edit_text(
            "<b>📸 PNL Card Viewer</b>\n\n"
            "Please enter the project name to view its PNL cards. "
            "Usage:\n<code>/pnl [project_name]</code>\n\n"
            "Example: <code>/pnl Solana</code>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )


async def analyze_pnl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays PNL cards for a given project."""
    if not context.args:
        await update.message.reply_text(
            "Please specify a project. Usage: `/pnl Solana`"
        )
        return

    project_name = context.args[0]
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
                # Assuming the API returns a list of objects with a 'url' field
                card_url = card.get('url')
                if card_url:
                    reply_parts.append(f"{i}. <a href='{card_url}'>PNL Card #{i}</a>")
            reply = "\n".join(reply_parts)

        await status_message.edit_text(
            reply,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False # Ensure links are clickable
        )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            reply = f"⚠️ No data found for <b>{project_name.upper()}</b>."
        else:
            reply = f"❌ Server error: Could not retrieve data ({e.response.status_code})."
        await status_message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await status_message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)


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
    """Fetches and displays the top trending projects from the backend."""
    query = update.callback_query
    if query:
        await query.answer()
        status_message = await query.message.edit_text(
            "<i>🔥 Fetching top trending projects...</i>",
            parse_mode=ParseMode.HTML
        )
    else:
        status_message = await update.message.reply_text(
            "<i>🔥 Fetching top trending projects...</i>",
            parse_mode=ParseMode.HTML
        )

    try:
        async with httpx.AsyncClient() as client:
            # Note the change in the URL structure, pointing to the new endpoint
            response = await client.get("https://dugtrio-backend.onrender.com/api/trending", timeout=60.0)

        response.raise_for_status()
        projects = response.json()

        if not projects:
            reply = "😕 No trending projects found at the moment."
        else:
            reply_parts = ["<b>🔥 Top Trending Projects</b>\n"]
            for i, project in enumerate(projects, 1):
                # Assuming the API returns a list of strings
                reply_parts.append(f"{i}. ${project.upper()}")
            reply = "\n".join(reply_parts)

        await status_message.edit_text(
            reply,
            reply_markup=get_main_menu_keyboard(),
            parse_mode=ParseMode.HTML
        )

    except httpx.HTTPStatusError as e:
        reply = f"❌ Server error: Could not retrieve data ({e.response.status_code}). Please try again."
        await status_message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)
    except Exception as e:
        reply = f"❌ An unexpected error occurred: {e}"
        await status_message.edit_text(reply, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.HTML)




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
    # This is now re-purposed for the text-based command, so we can remove the photo handler
    # application.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r'/pnl'), analyze_pnl_command))

    # Register handlers for main menu button presses, using their callback_data
    application.add_handler(CallbackQueryHandler(start_command, pattern=r'^menu_start$'))
    application.add_handler(CallbackQueryHandler(sentiment_menu, pattern=r'^menu_sentiment$'))
    application.add_handler(CallbackQueryHandler(analyze_pnl_prompt, pattern=r'^menu_analyze_pnl$'))
    application.add_handler(CallbackQueryHandler(track_wallet_prompt, pattern=r'^menu_track_wallet$'))
    application.add_handler(CallbackQueryHandler(subscribe_command, pattern=r'^menu_subscribe$'))
    application.add_handler(CallbackQueryHandler(top_projects_command, pattern=r'^menu_topprojects$'))

    # This handler catches all specific sentiment buttons (e.g., 'sentiment_Solana')
    application.add_handler(CallbackQueryHandler(sentiment_command, pattern=r'^sentiment_'))
    # This handler catches the history button press
    application.add_handler(CallbackQueryHandler(sentiment_history_command, pattern=r'^history_'))

    # Start the bot and wait for user input
    application.run_polling()


if __name__ == "__main__":
    main()