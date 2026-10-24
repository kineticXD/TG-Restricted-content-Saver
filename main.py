import os
import shutil
import psutil
import asyncio
from time import time

from pyleaves import Leaves
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.errors import PeerIdInvalid, BadRequest, FloodWait
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from helpers.utils import (
    processMediaGroup,
    progressArgs,
    send_media,
)

from helpers.forward import check_forward_permission, resolve_forward_chat_id

from helpers.files import (
    get_download_path,
    fileSizeLimit,
    get_readable_file_size,
    get_readable_time,
    cleanup_download,
    cleanup_downloads_root,
)

from helpers.msg import (
    getChatMsgID,
    get_file_name,
    get_raw_text,
)

from config import PyroConf
from logger import LOGGER

MODE_SINGLE = "single"
MODE_BATCH = "batch"

# Initialize the bot client
bot = Client(
    "media_bot",
    api_id=PyroConf.API_ID,
    api_hash=PyroConf.API_HASH,
    bot_token=PyroConf.BOT_TOKEN,
    workers=100,
    parse_mode=ParseMode.MARKDOWN,
    max_concurrent_transmissions=1,
    sleep_threshold=30,
)

# Client for user session
user = Client(
    "user_session",
    workers=100,
    session_string=PyroConf.SESSION_STRING,
    max_concurrent_transmissions=1,
    sleep_threshold=30,
)

RUNNING_TASKS = set()
USER_INPUT_MODE = {}
download_semaphore = None
forward_chat_id = None


def get_main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Download One Post", callback_data="ui:single"),
                InlineKeyboardButton("Batch Download", callback_data="ui:batch"),
            ],
            [
                InlineKeyboardButton("Examples", callback_data="ui:examples"),
                InlineKeyboardButton("How It Works", callback_data="ui:help"),
            ],
            [
                InlineKeyboardButton("Stats", callback_data="ui:stats"),
                InlineKeyboardButton("Cleanup", callback_data="ui:cleanup"),
            ],
            [
                InlineKeyboardButton("Logs", callback_data="ui:logs"),
                InlineKeyboardButton("Stop Active Jobs", callback_data="ui:killall"),
            ],
        ]
    )


def get_context_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Download One Post", callback_data="ui:single"),
                InlineKeyboardButton("Batch Download", callback_data="ui:batch"),
            ],
            [
                InlineKeyboardButton("Main Menu", callback_data="ui:home"),
            ],
        ]
    )


def get_quick_actions_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Download Again", callback_data="ui:single"),
                InlineKeyboardButton("Batch", callback_data="ui:batch"),
            ],
            [
                InlineKeyboardButton("Examples", callback_data="ui:examples"),
                InlineKeyboardButton("Main Menu", callback_data="ui:home"),
            ],
        ]
    )


def get_input_mode_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Cancel Input", callback_data="ui:cancel"),
                InlineKeyboardButton("Main Menu", callback_data="ui:home"),
            ]
        ]
    )


def get_cleanup_confirmation_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Yes, Cleanup", callback_data="ui:cleanup_confirm"),
                InlineKeyboardButton("No, Go Back", callback_data="ui:home"),
            ],
            [InlineKeyboardButton("Main Menu", callback_data="ui:home")],
        ]
    )


def get_killall_confirmation_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Yes, Stop Jobs", callback_data="ui:killall_confirm"),
                InlineKeyboardButton("No, Go Back", callback_data="ui:home"),
            ],
            [InlineKeyboardButton("Main Menu", callback_data="ui:home")],
        ]
    )


def get_welcome_text() -> str:
    return (
        "✨ **Welcome to Restricted Content Downloader**\n\n"
        "A clean, guided Telegram experience for downloading protected content.\n"
        "Everything is button-driven, with commands available as optional fallback.\n\n"
        "**Core Features**\n"
        "• Single post downloads (photo, video, audio, document)\n"
        "• Batch ranges with progress handling\n"
        "• Text/caption extraction from posts\n"
        "• Optional auto-forward to your configured target chat\n\n"
        "Tap **Download One Post** to start."
    )


def get_help_text() -> str:
    return (
        "🧭 **How It Works**\n\n"
        "1. Tap **Download One Post** and send one post URL.\n"
        "2. Tap **Batch Download** and send start + end URLs in one line.\n"
        "3. Use **Stats**, **Logs**, and **Cleanup** from the menu whenever needed.\n\n"
        "**Access Notes**\n"
        "• Your user session must already be able to view the source chat.\n"
        "• Private/restricted chats require proper membership and permissions.\n\n"
        "**Command Fallback (optional)**\n"
        "`/dl <link>`\n"
        "`/bdl <start_link> <end_link>`\n"
        "`/stats` `/logs` `/cleanup` `/killall`"
    )


def get_examples_text() -> str:
    return (
        "🧪 **General Examples**\n\n"
        "Paste these directly in chat.\n\n"
        "**Single Post**\n"
        "• `https://t.me/username/547`\n"
        "• `https://t.me/c/123456789/10`\n"
        "• `https://t.me/c/123456789/120/122`\n\n"
        "**Batch Range (same message)**\n"
        "• `https://t.me/username/100 https://t.me/username/120`\n"
        "• `https://t.me/c/123456789/300 https://t.me/c/123456789/360`\n\n"
        "Tip: in batch mode, keep start and end links separated by one space."
    )


def get_single_prompt_text() -> str:
    return (
        "📎 **Send a single Telegram post URL**\n\n"
        "Example:\n"
        "`https://t.me/username/547`"
    )


def get_batch_prompt_text() -> str:
    return (
        "📦 **Send two Telegram post URLs in one message**\n"
        "Format: `start_link end_link`\n\n"
        "Example:\n"
        "`https://t.me/username/100 https://t.me/username/120`"
    )


def get_user_key(message: Message) -> int:
    if message.from_user:
        return message.from_user.id
    return message.chat.id


def clear_user_mode(user_id: int) -> None:
    USER_INPUT_MODE.pop(user_id, None)


def extract_tme_urls(text: str) -> list[str]:
    if not text:
        return []
    return [
        token.strip()
        for token in text.replace("\n", " ").split()
        if token.strip().startswith("https://t.me/")
    ]


def track_task(coro):
    task = asyncio.create_task(coro)
    RUNNING_TASKS.add(task)

    def _remove(_):
        RUNNING_TASKS.discard(task)

    task.add_done_callback(_remove)
    return task


async def send_help_panel(message: Message):
    await message.reply(
        get_help_text(),
        reply_markup=get_context_menu_markup(),
        
    )


async def send_examples_panel(message: Message):
    await message.reply(
        get_examples_text(),
        reply_markup=get_context_menu_markup(),
        
    )


async def send_stats_panel(message: Message):
    current_time = get_readable_time(time() - PyroConf.BOT_START_TIME)
    total, used, free = shutil.disk_usage(".")

    stats_text = (
        "📊 **Live Bot Stats**\n\n"
        f"• **Uptime:** `{current_time}`\n"
        f"• **Total Disk:** `{get_readable_file_size(total)}`\n"
        f"• **Used Disk:** `{get_readable_file_size(used)}`\n"
        f"• **Free Disk:** `{get_readable_file_size(free)}`\n"
        f"• **Memory Used (Process):** `{round(psutil.Process(os.getpid()).memory_info()[0] / 1024**2)} MiB`\n\n"
        f"• **Network Upload:** `{get_readable_file_size(psutil.net_io_counters().bytes_sent)}`\n"
        f"• **Network Download:** `{get_readable_file_size(psutil.net_io_counters().bytes_recv)}`\n\n"
        f"• **CPU:** `{psutil.cpu_percent(interval=0.5)}%`\n"
        f"• **RAM:** `{psutil.virtual_memory().percent}%`\n"
        f"• **Disk Usage:** `{psutil.disk_usage('.').percent}%`"
    )

    await message.reply(stats_text, reply_markup=get_quick_actions_markup())


async def run_cleanup_and_notify(message: Message):
    try:
        files_removed, bytes_freed = cleanup_downloads_root()
        if files_removed == 0:
            await message.reply(
                "🧹 **Cleanup complete:** no local downloads found.",
                reply_markup=get_quick_actions_markup(),
            )
            return

        await message.reply(
            f"🧹 **Cleanup complete:** removed `{files_removed}` file(s), "
            f"freed `{get_readable_file_size(bytes_freed)}`.",
            reply_markup=get_quick_actions_markup(),
        )
    except Exception as e:
        LOGGER(__name__).error(f"Cleanup failed: {e}")
        await message.reply(
            "❌ **Cleanup failed.** Check logs for details.",
            reply_markup=get_quick_actions_markup(),
        )


async def send_logs_panel(message: Message):
    if os.path.exists("logs.txt"):
        await message.reply_document(document="logs.txt", caption="📄 **Latest Logs**")
        await message.reply(
            "Logs are ready. Select your next action:",
            reply_markup=get_quick_actions_markup(),
        )
    else:
        await message.reply(
            "📄 **No logs file found yet.**",
            reply_markup=get_quick_actions_markup(),
        )


async def send_cleanup_confirmation(message: Message):
    await message.reply(
        "⚠️ **Confirm Cleanup**\n\n"
        "This will permanently remove local downloads and temporary files from disk.\n"
        "Do you want to continue?",
        reply_markup=get_cleanup_confirmation_markup(),
    )


async def send_killall_confirmation(message: Message):
    await message.reply(
        "⚠️ **Confirm Stop Active Jobs**\n\n"
        "This will cancel all running download/upload tasks right now.\n"
        "Do you want to continue?",
        reply_markup=get_killall_confirmation_markup(),
    )


async def cancel_all_running_tasks(message: Message):
    cancelled = 0
    for task in list(RUNNING_TASKS):
        if not task.done():
            task.cancel()
            cancelled += 1

    await message.reply(
        f"🛑 **Stopped `{cancelled}` running task(s).**",
        reply_markup=get_quick_actions_markup(),
    )


async def process_batch_download(bot: Client, message: Message, start_link: str, end_link: str):
    if not (start_link.startswith("https://t.me/") and end_link.startswith("https://t.me/")):
        await message.reply(
            "❌ Please provide valid Telegram post links.",
            reply_markup=get_input_mode_markup(),
            
        )
        return

    try:
        start_chat, start_id = getChatMsgID(start_link)
        end_chat, end_id = getChatMsgID(end_link)
    except Exception as e:
        await message.reply(
            f"❌ **Error parsing links:** `{e}`",
            reply_markup=get_input_mode_markup(),
            
        )
        return

    if start_chat != end_chat:
        await message.reply(
            "❌ Both links must be from the same channel/chat.",
            reply_markup=get_input_mode_markup(),
        )
        return

    if start_id > end_id:
        await message.reply(
            "❌ Invalid range: start ID cannot be greater than end ID.",
            reply_markup=get_input_mode_markup(),
        )
        return

    try:
        await user.get_chat(start_chat)
    except Exception:
        pass

    prefix = start_link.rsplit("/", 1)[0]
    loading = await message.reply(f"📥 **Batch started:** posts `{start_id}` to `{end_id}`")

    downloaded = 0
    skipped = 0
    failed = 0
    processed_media_groups = set()
    batch_tasks = []
    batch_size = PyroConf.BATCH_SIZE

    for msg_id in range(start_id, end_id + 1):
        url = f"{prefix}/{msg_id}"
        try:
            chat_msg = await user.get_messages(chat_id=start_chat, message_ids=msg_id)
            if not chat_msg:
                skipped += 1
                continue

            if chat_msg.media_group_id:
                if chat_msg.media_group_id in processed_media_groups:
                    skipped += 1
                    continue
                processed_media_groups.add(chat_msg.media_group_id)

            has_media = bool(chat_msg.media_group_id or chat_msg.media)
            has_text = bool(chat_msg.text or chat_msg.caption)
            if not (has_media or has_text):
                skipped += 1
                continue

            task = track_task(handle_download(bot, message, url, show_actions=False))
            batch_tasks.append(task)

            if len(batch_tasks) >= batch_size:
                results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, asyncio.CancelledError):
                        await loading.delete()
                        await message.reply(
                            f"❌ **Batch canceled** after `{downloaded}` successful post(s).",
                            reply_markup=get_quick_actions_markup(),
                        )
                        return
                    if isinstance(result, Exception):
                        failed += 1
                        LOGGER(__name__).error(f"Batch error: {result}")
                        continue
                    if result is True:
                        downloaded += 1
                    else:
                        failed += 1

                batch_tasks.clear()
                await asyncio.sleep(PyroConf.FLOOD_WAIT_DELAY)

        except Exception as e:
            failed += 1
            LOGGER(__name__).error(f"Error at {url}: {e}")

    if batch_tasks:
        results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                failed += 1
            elif result is True:
                downloaded += 1
            else:
                failed += 1

    await loading.delete()
    await message.reply(
        "✅ **Batch Complete**\n"
        "--------------------\n"
        f"📥 **Downloaded:** `{downloaded}`\n"
        f"⏭️ **Skipped:** `{skipped}`\n"
        f"❌ **Failed:** `{failed}`",
        reply_markup=get_quick_actions_markup(),
    )


async def handle_download(bot: Client, message: Message, post_url: str, show_actions: bool = True) -> bool:
    global forward_chat_id

    async def reply_status(text: str):
        if show_actions:
            return await message.reply(
                text,
                reply_markup=get_quick_actions_markup(),
                
            )
        return await message.reply(text, disable_web_page_preview=True)

    async with download_semaphore:
        if "?" in post_url:
            post_url = post_url.split("?", 1)[0]

        try:
            effective_forward_chat_id = None
            if forward_chat_id:
                ok, err_msg = await check_forward_permission(bot, forward_chat_id)
                if not ok:
                    await reply_status(
                        f"⚠️ **Forward chat issue:** {err_msg}\n\n"
                        "Output will be sent only to this chat."
                    )
                else:
                    effective_forward_chat_id = forward_chat_id

            chat_id, message_id = getChatMsgID(post_url)
            chat_message = await user.get_messages(chat_id=chat_id, message_ids=message_id)

            if not chat_message:
                await reply_status("❌ Could not fetch this message. Verify the link and your chat access.")
                return False

            LOGGER(__name__).info(f"Downloading media from URL: {post_url}")

            if chat_message.document or chat_message.video or chat_message.audio:
                file_size = (
                    chat_message.document.file_size
                    if chat_message.document
                    else chat_message.video.file_size
                    if chat_message.video
                    else chat_message.audio.file_size
                )

                if not await fileSizeLimit(
                    file_size, message, "download", user.me.is_premium
                ):
                    if show_actions:
                        await message.reply(
                            "Try another post link or use batch mode.",
                            reply_markup=get_quick_actions_markup(),
                        )
                    return False

            raw_caption, raw_caption_entities = get_raw_text(
                chat_message.caption, chat_message.caption_entities
            )
            raw_text, raw_text_entities = get_raw_text(
                chat_message.text, chat_message.entities
            )

            if chat_message.media_group_id:
                ok = await processMediaGroup(
                    chat_message,
                    bot,
                    message,
                    forward_chat_id=effective_forward_chat_id,
                )
                if ok and show_actions:
                    await message.reply(
                        "✅ Media group completed successfully.",
                        reply_markup=get_quick_actions_markup(),
                    )
                elif not ok and show_actions:
                    await message.reply(
                        "❌ Could not extract valid media from this group.",
                        reply_markup=get_quick_actions_markup(),
                    )
                return bool(ok)

            has_downloadable_media = (
                chat_message.photo
                or chat_message.video
                or chat_message.audio
                or chat_message.document
                or chat_message.voice
                or chat_message.video_note
                or chat_message.animation
                or chat_message.sticker
            )

            if has_downloadable_media:
                start_time = time()
                progress_message = await message.reply("**📥 Downloading Progress...**")

                filename = get_file_name(message_id, chat_message)
                download_path = get_download_path(message.id, filename)

                media_path = None
                for attempt in range(2):
                    try:
                        media_path = await chat_message.download(
                            file_name=download_path,
                            progress=Leaves.progress_for_pyrogram,
                            progress_args=progressArgs(
                                "📥 Downloading Progress", progress_message, start_time
                            ),
                        )
                        break
                    except FloodWait as e:
                        wait_s = int(getattr(e, "value", 0) or 0)
                        LOGGER(__name__).warning(f"FloodWait while downloading media: {wait_s}s")
                        if wait_s > 0 and attempt == 0:
                            await asyncio.sleep(wait_s + 1)
                            continue
                        raise

                if not media_path or not os.path.exists(media_path):
                    await progress_message.edit("**❌ Download failed: file not saved properly**")
                    if show_actions:
                        await message.reply(
                            "Try another link.",
                            reply_markup=get_quick_actions_markup(),
                        )
                    return False

                file_size = os.path.getsize(media_path)
                if file_size == 0:
                    await progress_message.edit("**❌ Download failed: file is empty**")
                    cleanup_download(media_path)
                    if show_actions:
                        await message.reply(
                            "Try another link.",
                            reply_markup=get_quick_actions_markup(),
                        )
                    return False

                LOGGER(__name__).info(f"Downloaded media: {media_path} (Size: {file_size} bytes)")

                media_type = (
                    "photo"
                    if chat_message.photo
                    else "video"
                    if chat_message.video
                    else "audio"
                    if chat_message.audio
                    else "document"
                )

                await send_media(
                    bot,
                    message,
                    media_path,
                    media_type,
                    raw_caption,
                    raw_caption_entities,
                    progress_message,
                    start_time,
                    forward_chat_id=effective_forward_chat_id,
                )

                cleanup_download(media_path)
                await progress_message.delete()

                if show_actions:
                    await message.reply(
                        "✅ Download finished. Choose your next action:",
                        reply_markup=get_quick_actions_markup(),
                    )
                return True

            if chat_message.poll:
                await reply_status("❌ This post contains a poll and cannot be downloaded.")
                return False

            if chat_message.text or chat_message.caption:
                txt = raw_text or raw_caption
                ents = raw_text_entities if raw_text else raw_caption_entities
                sent_text = None

                try:
                    sent_text = await message.reply(txt, entities=ents or None)
                except BadRequest as e:
                    if "ENTITY_TEXT_INVALID" in str(e):
                        LOGGER(__name__).warning(
                            f"ENTITY_TEXT_INVALID in text reply, retrying without entities: {e}"
                        )
                        sent_text = await message.reply(txt)
                    else:
                        raise

                if effective_forward_chat_id and sent_text:
                    try:
                        await bot.copy_message(
                            chat_id=effective_forward_chat_id,
                            from_chat_id=sent_text.chat.id,
                            message_id=sent_text.id,
                        )
                        LOGGER(__name__).info(
                            f"Copied text message to chat: {effective_forward_chat_id}"
                        )
                    except Exception as e:
                        LOGGER(__name__).error(
                            f"Failed to copy text message to {effective_forward_chat_id}: {e}"
                        )

                if show_actions:
                    await message.reply(
                        "✅ Text copied successfully.",
                        reply_markup=get_quick_actions_markup(),
                    )
                return True

            await reply_status("❌ No media or text found in this post.")
            return False

        except FloodWait as e:
            wait_s = int(getattr(e, "value", 0) or 0)
            LOGGER(__name__).warning(f"FloodWait in handle_download: {wait_s}s")
            if wait_s > 0:
                await asyncio.sleep(wait_s + 1)
            if show_actions:
                await message.reply(
                    f"⏳ Telegram requested a cooldown of `{wait_s}` seconds. Please try again.",
                    reply_markup=get_quick_actions_markup(),
                )
            return False

        except PeerIdInvalid as e:
            LOGGER(__name__).error(f"PeerIdInvalid for {post_url}: {e}")
            await reply_status(
                "❌ **Access denied**\n\n"
                "The user session cannot access this chat/message.\n"
                f"**Details:** `{e}`"
            )
            return False

        except BadRequest as e:
            LOGGER(__name__).error(f"BadRequest for {post_url}: {e}")
            await reply_status(
                "❌ **Bad request**\n\n"
                f"Telegram returned: `{e}`\n\n"
                "This can happen for invalid message IDs or inaccessible chats."
            )
            return False

        except (KeyError, ValueError) as e:
            LOGGER(__name__).error(f"URL parse error for {post_url}: {e}")
            await reply_status(f"❌ **Invalid post URL:** `{e}`")
            return False

        except Exception as e:
            LOGGER(__name__).error(f"Unexpected error for {post_url}: {e}")
            await reply_status(f"❌ **Unexpected error:** `{e}`")
            return False


@bot.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
    clear_user_mode(get_user_key(message))
    await message.reply(
        get_welcome_text(),
        reply_markup=get_main_menu_markup(),
        
    )


@bot.on_message(filters.command("help") & filters.private)
async def help_command(_, message: Message):
    await send_help_panel(message)


@bot.on_message(filters.command("examples") & filters.private)
async def examples_command(_, message: Message):
    await send_examples_panel(message)


@bot.on_callback_query(filters.regex(r"^ui:"))
async def callback_router(bot: Client, query: CallbackQuery):
    if not query.message:
        await query.answer()
        return

    action = query.data.split(":", 1)[1] if query.data else ""
    user_id = query.from_user.id if query.from_user else query.message.chat.id

    try:
        if action == "home":
            clear_user_mode(user_id)
            await query.message.reply(
                get_welcome_text(),
                reply_markup=get_main_menu_markup(),
                
            )

        elif action == "single":
            USER_INPUT_MODE[user_id] = MODE_SINGLE
            await query.message.reply(
                get_single_prompt_text(),
                reply_markup=get_input_mode_markup(),
                
            )

        elif action == "batch":
            USER_INPUT_MODE[user_id] = MODE_BATCH
            await query.message.reply(
                get_batch_prompt_text(),
                reply_markup=get_input_mode_markup(),
                
            )

        elif action == "help":
            await send_help_panel(query.message)

        elif action == "examples":
            await send_examples_panel(query.message)

        elif action == "stats":
            await send_stats_panel(query.message)

        elif action == "cleanup":
            await send_cleanup_confirmation(query.message)

        elif action == "cleanup_confirm":
            await run_cleanup_and_notify(query.message)

        elif action == "logs":
            await send_logs_panel(query.message)

        elif action == "killall":
            await send_killall_confirmation(query.message)

        elif action == "killall_confirm":
            await cancel_all_running_tasks(query.message)

        elif action == "cancel":
            clear_user_mode(user_id)
            await query.message.reply(
                "✅ Input mode canceled.",
                reply_markup=get_main_menu_markup(),
            )

        else:
            await query.answer("Unknown action.")
            return

        await query.answer()

    except Exception as e:
        LOGGER(__name__).error(f"Callback action failed ({action}): {e}")
        await query.answer("Action failed. Please try again.", show_alert=True)


@bot.on_message(filters.command("cleanup") & filters.private)
async def cleanup_storage(_, message: Message):
    await send_cleanup_confirmation(message)


@bot.on_message(filters.command("stats") & filters.private)
async def stats(_, message: Message):
    await send_stats_panel(message)


@bot.on_message(filters.command("logs") & filters.private)
async def logs(_, message: Message):
    await send_logs_panel(message)


@bot.on_message(filters.command("killall") & filters.private)
async def cancel_all_tasks(_, message: Message):
    await send_killall_confirmation(message)


@bot.on_message(filters.command("dl") & filters.private)
async def download_media(bot: Client, message: Message):
    user_id = get_user_key(message)

    if len(message.command) < 2:
        USER_INPUT_MODE[user_id] = MODE_SINGLE
        await message.reply(
            get_single_prompt_text(),
            reply_markup=get_input_mode_markup(),
            
        )
        return

    clear_user_mode(user_id)
    post_url = message.command[1]
    track_task(handle_download(bot, message, post_url))


@bot.on_message(filters.command("bdl") & filters.private)
async def download_range(bot: Client, message: Message):
    user_id = get_user_key(message)
    args = message.text.split()

    if len(args) != 3 or not all(arg.startswith("https://t.me/") for arg in args[1:]):
        USER_INPUT_MODE[user_id] = MODE_BATCH
        await message.reply(
            get_batch_prompt_text(),
            reply_markup=get_input_mode_markup(),
            
        )
        return

    clear_user_mode(user_id)
    await process_batch_download(bot, message, args[1], args[2])


@bot.on_message(filters.private & ~filters.command(["start", "help", "examples", "dl", "bdl", "stats", "logs", "killall", "cleanup"]))
async def handle_any_message(bot: Client, message: Message):
    if not message.text or message.text.startswith("/"):
        return

    user_id = get_user_key(message)
    mode = USER_INPUT_MODE.get(user_id)
    urls = extract_tme_urls(message.text)

    if mode == MODE_SINGLE:
        if not urls:
            await message.reply(
                "❌ I could not find a Telegram post link. Please send one valid link.",
                reply_markup=get_input_mode_markup(),
                
            )
            return

        clear_user_mode(user_id)
        track_task(handle_download(bot, message, urls[0]))
        return

    if mode == MODE_BATCH:
        if len(urls) < 2:
            await message.reply(
                "❌ Please send two Telegram post links: `start_link end_link`.",
                reply_markup=get_input_mode_markup(),
                
            )
            return

        clear_user_mode(user_id)
        await process_batch_download(bot, message, urls[0], urls[1])
        return

    if len(urls) >= 2:
        await process_batch_download(bot, message, urls[0], urls[1])
        return

    if len(urls) == 1:
        track_task(handle_download(bot, message, urls[0]))
        return

    await message.reply(
        "I can work with Telegram post links. Pick an option below to continue.",
        reply_markup=get_main_menu_markup(),
        
    )


async def initialize():
    global download_semaphore, forward_chat_id
    download_semaphore = asyncio.Semaphore(PyroConf.MAX_CONCURRENT_DOWNLOADS)

    if PyroConf.FORWARD_CHAT_ID:
        forward_chat_id = await resolve_forward_chat_id(PyroConf.FORWARD_CHAT_ID)
        LOGGER(__name__).info(f"Auto-forward enabled. Target chat: {forward_chat_id}")


if __name__ == "__main__":
    try:
        LOGGER(__name__).info("Bot Started!")
        asyncio.get_event_loop().run_until_complete(initialize())
        user.start()
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as err:
        LOGGER(__name__).error(err)
    finally:
        LOGGER(__name__).info("Bot Stopped")
