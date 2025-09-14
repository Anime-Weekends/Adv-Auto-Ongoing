from asyncio import sleep as asleep, gather
from pyrogram.filters import command, private, user
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler
from pyrogram import filters
from pyrogram.types import Message
import subprocess
from bot import bot, bot_loop, Var, ani_cache
from bot.core.auto_animes import get_animes, process_manga_chapter, process_batch_anime
from bot.core.database import db
from bot.core.func_utils import decode, is_fsubbed, get_fsubs, editMessage, sendMessage, new_task, convertTime, getfeed
from bot.core.auto_animes import get_animes
from bot.core.reporter import rep
import time
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient
import datetime
import os
from pyrogram.enums import ParseMode
from bot import ani_cache
import sys
import psutil
import asyncio
from aiofiles import open as aiopen
from functools import wraps
from typing import Callable, Any
import os
import time
import psutil
import asyncio
from datetime import datetime
from functools import wraps
from aiofiles import open as aiopen
from typing import Callable, Any
import asyncio
from bot.core.auto_animes import get_all_possible_anime_names

def rate_limit(seconds: int) -> Callable:
    def decorator(func: Callable) -> Callable:
        last_time: dict = {}
        
        @wraps(func)
        async def wrapper(client: Any, message: Message, *args: Any, **kwargs: Any) -> Any:
            user_id = message.from_user.id
            current_time = time.time()
            
            if user_id in last_time and current_time - last_time[user_id] < seconds:
                remaining = round(seconds - (current_time - last_time[user_id]), 1)
                await message.reply(f"<blockquote><b>Please wait {remaining}s before using this command again.</b></blockquote>")
                return None
                
            last_time[user_id] = current_time
            return await func(client, message, *args, **kwargs)
            
        return wrapper
    return decorator

DB_URI = Var.MONGO_URI

def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time

async def get_db_response_time() -> float:
    try:
        start = time.time()
        await db._MongoDB__client.admin.command('ping')
        end = time.time()
        return round((end - start) * 1000, 2)
    except Exception as e:
        await rep.report(f"DB ping error: {str(e)}", "error")
        return 0

async def get_ping(bot_client) -> float:
    start = time.time()
    await bot_client.get_me()
    end = time.time()
    return round((end - start) * 1000, 2)

async def update_fsub_chats_var():
    Var.FSUB_CHATS = await db.list_fsubs()

@bot.on_message(filters.command("delallmangas") & filters.user(Var.ADMINS))
@new_task
async def del_all_manga_cmd(client, message: Message):
    try:
        await db.delete_all_manga_mappings()
        await message.reply("<blockquote><b>All manga mappings deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("delallmangabanners") & filters.user(Var.ADMINS))
@new_task
async def del_all_manga_banner_cmd(client, message: Message):
    try:
        await db.delete_all_manga_banners()
        await message.reply("<blockquote><b>All manga banners deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("listadmins") & filters.user(Var.ADMINS))
@new_task
async def list_admins_cmd(client, message: Message):
    try:
        admins = await db.get_admins()
        if not admins:
            return await message.reply("<blockquote><b>No admins set.</b></blockquote>")
        msg = "<blockquote><b>Admin IDs:</b></blockquote>\n"
        for admin_id in admins:
            msg += f"<code>{admin_id}</code>\n"
        await message.reply(msg)
    except Exception as e:
        await message.reply(f"<blockquote><b>Error: {str(e)}</b></blockquote>")

@bot.on_message(filters.command("deladmin") & filters.user(Var.ADMINS))
@new_task
async def del_admin_cmd(client, message: Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return await message.reply("<blockquote><b>Usage:</b> <code>/deladmin &lt;user_id&gt;</code></blockquote>")
        user_id = int(args[1].strip())
        await db.remove_admin(user_id)
        if user_id in Var.ADMINS:
            Var.ADMINS.remove(user_id)
        await message.reply(f"<blockquote><b>Admin removed:</b> <code>{user_id}</code></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error: {str(e)}</b></blockquote>")

@bot.on_message(filters.command("addadmin") & filters.user(Var.ADMINS))
@new_task
async def add_admin_cmd(client, message: Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return await message.reply("<blockquote><b>Usage:</b> <code>/addadmin &lt;user_id or username&gt;</code></blockquote>")
        user = args[1].strip()
        if user.startswith("@"):
            try:
                user_obj = await client.get_users(user)
                user_id = user_obj.id
            except Exception:
                return await message.reply("<blockquote><b>Invalid username or user not found.</b></blockquote>")
        else:
            try:
                user_id = int(user)
            except Exception:
                return await message.reply("<blockquote><b>Invalid user ID.</b></blockquote>")
        await db.add_admin(user_id)
        if user_id not in Var.ADMINS:
            Var.ADMINS.append(user_id)
        await message.reply(f"<blockquote><b>Admin added:</b> <code>{user_id}</code></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")


@bot.on_message(filters.command("setffmpeg") & filters.user(Var.ADMINS))
@new_task
async def set_ffmpeg_cmd(client, message: Message):
    help_text = """
<b>Usage:</b> 
<code>/setffmpeg "Anime Name" - RESOLUTION_CONFIG ||| HDRIP_CONFIG</code>

<b>For resolution encoding, use these placeholders:</b>
• <code>{}</code> - Input file
• <code>{}</code> - Progress file
• <code>{}</code> - Resolution (will be auto-set)
• <code>{}</code> - Output file

<b>For HDRip, use these placeholders:</b>
• <code>{}</code> - Input file
• <code>{}</code> - Progress file
• <code>{}</code> - Output file

<b>Example with both configs:</b>
<code>/setffmpeg "Jujutsu Kaisen" - ffmpeg -i "{}" -progress "{}" -map 0:v -map 0:a -map 0:s -c:v libx264 -crf 24 -c:s copy -pix_fmt yuv420p -s {} -c:a libopus -preset veryfast -metadata title="YourTitle" "{}" -y ||| ffmpeg -i "{}" -progress "{}" -c copy -map 0:v -map 0:a -map 0:s -metadata title="YourTitle" "{}" -y</code>

<b>Note:</b> Use ||| to separate resolution and HDRip configs
"""

    try:
        text = message.text[len("/setffmpeg"):].strip()
        if " - " not in text:
            return await message.reply(help_text)

        anime_name, ffmpeg_configs = text.split(" - ", 1)
        anime_name = anime_name.strip()

        if "|||" in ffmpeg_configs:
            resolution_config, hdrip_config = ffmpeg_configs.split("|||", 1)
            resolution_config = resolution_config.strip()
            hdrip_config = hdrip_config.strip()

            if resolution_config.count("{}") != 4:
                return await message.reply("<b>Resolution config must have 4 placeholders {}</b>")
            if hdrip_config.count("{}") != 3:
                return await message.reply("<b>HDRip config must have 3 placeholders {}</b>")

            combined_config = f"{resolution_config} ||| {hdrip_config}"
        else:
            if ffmpeg_configs.count("{}") not in [3, 4]:
                return await message.reply("<b>Config must have 3 (HDRip) or 4 (Resolution) placeholders {}</b>")
            combined_config = ffmpeg_configs.strip()

        possible_names = await get_all_possible_anime_names(anime_name)
        for name in possible_names:
            await db.set_anime_ffmpeg(name, combined_config)
        await message.reply(
            f"<b>FFmpeg config set for:</b> <code>{anime_name}</code>\n"
            f"<b>Mapped variants:</b> <code>{', '.join(possible_names)}</code>\n"
            f"<b>Config:</b>\n<code>{combined_config}</code>"
        )
    except Exception as e:
        await message.reply(f"<b>Error:</b> {str(e)}")

@bot.on_message(filters.command("getffmpeg") & filters.user(Var.ADMINS))
@new_task
async def get_ffmpeg_cmd(client, message: Message):
    try:
        anime_name = message.text[len("/getffmpeg"):].strip()
        if not anime_name:
            return await message.reply(
                "<blockquote><b>Usage:</b>\n<code>/getffmpeg Anime Name</code></blockquote>"
            )

        possible_names = await get_all_possible_anime_names(anime_name)
        found = False
        reply_text = ""
        for name in possible_names:
            config = await db.get_anime_ffmpeg(name)
            if config:
                found = True
                reply_text += (
                    f"<blockquote><b>FFmpeg config for:</b> <code>{name}</code>\n\n"
                    f"<b>Config:</b>\n<code>{config}</code></blockquote>\n\n"
                )
        if not found:
            return await message.reply(
                f"<blockquote><b>No FFmpeg config found for:</b> <code>{anime_name}</code></blockquote>\n"
                f"<blockquote><b>Tried variants:</b> <code>{', '.join(possible_names)}</code></blockquote>"
            )
        reply_text += f"<blockquote><b>Tried variants:</b> <code>{', '.join(possible_names)}</code></blockquote>"
        await message.reply(reply_text)
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("delffmpeg") & filters.user(Var.ADMINS))
@new_task
async def del_ffmpeg_cmd(client, message: Message):
    try:
        anime_name = message.text[len("/delffmpeg"):].strip()
        if not anime_name:
            return await message.reply(
                "<blockquote><b>Usage:</b>\n<code>/delffmpeg Anime Name</code></blockquote>"
            )

        possible_names = await get_all_possible_anime_names(anime_name)
        deleted = []
        for name in possible_names:
            result = await db.del_anime_ffmpeg(name)
            if result:
                deleted.append(name)
        if deleted:
            await message.reply(
                f"<blockquote><b>Deleted FFmpeg config for:</b> <code>{anime_name}</code></blockquote>\n"
                f"<blockquote><b>Mapped variants:</b> <code>{', '.join(deleted)}</code></blockquote>"
            )
        else:
            await message.reply(
                f"<blockquote><b>No FFmpeg config found for:</b> <code>{anime_name}</code></blockquote>\n"
                f"<blockquote><b>Tried variants:</b> <code>{', '.join(possible_names)}</code></blockquote>"
            )
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("listffmpeg") & filters.user(Var.ADMINS))
@new_task
async def list_ffmpeg_cmd(client, message: Message):
    try:
        configs = await db.list_anime_ffmpeg()
        if not configs:
            return await message.reply(
                "<blockquote><b>No custom FFmpeg configs found.</b></blockquote>"
            )

        msg = "<blockquote><b>Custom FFmpeg Configs:</b></blockquote>\n\n"
        for name, config in configs:
            msg += f"<blockquote>• <b>{name}</b>\n<code>{config}</code></blockquote>\n\n"

        await message.reply(msg)

    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("setmangabanner") & filters.user(Var.ADMINS))
@new_task
async def set_manga_banner_cmd(client, message: Message):
    try:
        if message.reply_to_message and message.reply_to_message.photo:
            manga_name = message.text[len("/setmangabanner"):].strip()
            if not manga_name:
                return await message.reply("<blockquote><b>Usage when replying to photo:</b>\n<code>/setmangabanner Manga Name</code></blockquote>")

            banner_url = message.reply_to_message.photo.file_id
            
        else:
            text = message.text[len("/setmangabanner"):].strip()
            if " - " not in text:
                return await message.reply("<blockquote><b>Usage with URL:</b>\n<code>/setmangabanner Manga Name - Banner URL</code>\n\nOr reply to a photo with:\n<code>/setmangabanner Manga Name</code></blockquote>")

            manga_name, banner_url = text.split(" - ", 1)
            manga_name = manga_name.strip()
            banner_url = banner_url.strip()

        if not manga_name or not banner_url:
            return await message.reply("<blockquote><b>Please provide both the manga name and banner (URL or photo).</b></blockquote>")

        await db.set_manga_banner(manga_name, banner_url)

        if message.reply_to_message and message.reply_to_message.photo:
            await message.reply(f"<blockquote><b>Set banner for manga from replied photo:</b>\n<code>{manga_name}</code></blockquote>")
        else:
            await message.reply(f"<blockquote><b>Set banner for manga from URL:</b>\n<code>{manga_name}</code>\n\n<code>{banner_url}</code></blockquote>")
        
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("viewmangabanner") & filters.user(Var.ADMINS))
@new_task
async def view_manga_banner_cmd(client, message: Message):
    try:
        manga_name = message.text[len("/viewmangabanner"):].strip()
        if not manga_name:
            return await message.reply("<blockquote><b>Usage: /viewmangabanner Manga Name</b></blockquote>")

        banner_url = await db.get_manga_banner(manga_name)
        if not banner_url:
            return await message.reply(f"<blockquote><b>No banner set for manga:</b> <code>{manga_name}</code></blockquote>")

        await message.reply_photo(
            photo=banner_url,
            caption=f"<blockquote><b>Banner for manga:</b> <code>{manga_name}</code></blockquote>"
        )
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("delmangabanner") & filters.user(Var.ADMINS))
@new_task
async def del_manga_banner_cmd(client, message: Message):
    try:
        manga_name = message.text[len("/delmangabanner"):].strip()
        if not manga_name:
            return await message.reply("<blockquote><b>Usage: /delmangabanner Manga Name</b></blockquote>")

        await db.del_manga_banner(manga_name)
        await message.reply(f"<blockquote><b>Banner deleted for manga:</b> <code>{manga_name}</code></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("listmangabanners") & filters.user(Var.ADMINS))
@new_task
async def list_manga_banners_cmd(client, message: Message):
    try:
        banners = await db.list_manga_banners()
        if not banners:
            return await message.reply("<blockquote><b>No manga banners set.</b></blockquote>")

        msg = "<blockquote><b>Manga Banners:</b></blockquote>\n\n"
        for name, url in banners:
            msg += f"<blockquote>• <b>{name}</b>\n<code>{url}</code></blockquote>\n"

        await message.reply(msg, disable_web_page_preview=True)
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("setmanga") & filters.user(Var.ADMINS))
@new_task
async def set_manga_channel(client, message: Message):
    try:
        text = message.text[len("/setmanga"):].strip()
        if " - " not in text:
            return await message.reply("<blockquote><b>Usage: /setmanga <manga name> - <channel username or ID></b></blockquote>")

        manga_name, channel = text.split(" - ", 1)
        manga_name = manga_name.strip()
        channel = channel.strip()

        if not manga_name or not channel:
            return await message.reply("<blockquote><b>Please provide both the manga name and channel ID.</b></blockquote>")

        if channel.startswith("@"):
            final_channel = channel
        else:
            final_channel = int(channel)

        await db.add_manga_channel_mapping(manga_name, final_channel)
        await message.reply(f"<blockquote><b>Set channel for manga '{manga_name}' to '{channel}'</b></blockquote>")
        
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("delmanga") & filters.user(Var.ADMINS))
@new_task
async def remove_manga_channel_cmd(client, message: Message):
    try:
        cmd_text = message.text.strip()
        if " - " in cmd_text:
            _, rest = cmd_text.split(maxsplit=1)
            manga_name, channel = map(str.strip, rest.split(" - ", 1))
        else:
            manga_name = cmd_text[len("/delmanga"):].strip()
            channel = None
        if not manga_name:
            return await message.reply("<blockquote><b>Usage: /delmanga manga name [- channel]</b></blockquote>")
        await db.remove_manga_channel_mapping(manga_name, channel)
        await message.reply(f"<blockquote><b>Removed mapping for manga '{manga_name}'{f' from {channel}' if channel else ''}</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("listmangas") & filters.user(Var.ADMINS))
@new_task
async def list_manga_channels(client, message: Message):
    try:
        manga_channels = await db.get_all_manga_channels()

        if not manga_channels:
            return await message.reply("<blockquote><b>No manga channels have been added yet.</blockquote></b>")

        response_text = "<blockquote><b>List of Manga Channels:</b></blockquote>\n\n"
        for manga, channel in manga_channels.items():
            response_text += f"<blockquote>• <b>{manga}</b> - <code>{channel}</code></blockquote>\n"

        await message.reply_text(response_text)

    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("settings") & filters.user(Var.ADMINS))
@new_task
async def settings_cmd(client, message: Message):
    user_session = getattr(Var, "USER_SESSION", None)
    encoding = await db.get_encoding()
    low_end_rename = await db.get_low_end_rename()
    Var.LOW_END_RENAME = low_end_rename
    channel_creation = await db.get_channel_creation()
    mode = await db.get_mode()
    upload_mode = await db.get_upload_mode()
    low_end_rename = getattr(Var, "LOW_END_RENAME", False)
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Cʜᴀɴɴᴇʟ Cʀᴇᴀᴛɪᴏɴ {'Oɴ ✓' if channel_creation else 'Oғғ ✘'}",
                callback_data="toggle_channel_creation"
            ),
            InlineKeyboardButton(
                f"Eɴᴄᴏᴅɪɴɢ Sʏsᴛᴇᴍ {'Oɴ ✓' if encoding else 'Oғғ ✘'}",
                callback_data="toggle_encoding"
            )
        ],
        [
            InlineKeyboardButton(
                f"Lᴏᴡ-Eɴᴅ Rᴇɴᴀᴍᴇ {'Oɴ ✓' if low_end_rename else 'Oғғ ✘'}",
                callback_data="toggle_low_end_rename"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Uᴘʟᴏᴀᴅ Mᴏᴅᴇ: {upload_mode.replace('_', ' ').title()}",
                callback_data="change_upload_mode"
            ),
            InlineKeyboardButton(
                f"Mᴏᴅᴇ: {mode.capitalize()}",
                callback_data="change_mode"
            )
        ],
    ])
    text = "<blockquote><b>Settings Panel</blockquote>\n<blockquote>Toggle features below:</b></blockquote>"
    if not user_session:
        text += "<blockquote><b>\n⚠️ <b>USER_SESSION not found!</b>\nPlease enter the user session in <code>config.env</code> to enable this option.</b></blockquote>"
    await message.reply(
        text,
        reply_markup=btns
    )
    
@bot.on_callback_query(filters.regex(r"^ffmpeg_configs$"))
async def ffmpeg_configs_cb(client, callback_query):
    config_keys = [
        "HENTAI_FFMPEG", "LOW_END_FFMPEG", "FFCODE_HDRi", "FFCODE_1080",
        "FFCODE_720", "FFCODE_480", "FFCODE_360", "FFCODE_240", "FFCODE_144"
    ]
    
    msg = "<blockquote><b>Current FFmpeg Configs:</b></blockquote>\n\n"
    for key in config_keys:
        db_val = await db.get_anime_ffmpeg(key)
        val = db_val if db_val else getattr(Var, key, "Not Set")
        msg += f"<b>{key}:</b>\n<code>{val}</code>\n\n"

    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("HENTAI", callback_data="ffmpeg_edit_HENTAI_FFMPEG"),
            InlineKeyboardButton("LOW END", callback_data="ffmpeg_edit_LOW_END_FFMPEG"), 
        ],
        [
            InlineKeyboardButton("144p", callback_data="ffmpeg_edit_FFCODE_144"),
            InlineKeyboardButton("240p", callback_data="ffmpeg_edit_FFCODE_240"),
            InlineKeyboardButton("360p", callback_data="ffmpeg_edit_FFCODE_360"),
        ],
        [
            InlineKeyboardButton("480p", callback_data="ffmpeg_edit_FFCODE_480"),
            InlineKeyboardButton("720p", callback_data="ffmpeg_edit_FFCODE_720"),
            InlineKeyboardButton("1080p", callback_data="ffmpeg_edit_FFCODE_1080"),
            InlineKeyboardButton("HDRi", callback_data="ffmpeg_edit_FFCODE_HDRi"),
        ],
        [InlineKeyboardButton("« Back", callback_data="settings_back")]
    ])
    
    await callback_query.edit_message_text(msg, reply_markup=btns)

@bot.on_callback_query(filters.regex(r"^ffmpeg_edit_(.+)$")) 
async def ffmpeg_edit_cb(client, callback_query):
    config_key = callback_query.data.split("_", 2)[2]
    
    db_val = await db.get_anime_ffmpeg(config_key) 
    current_val = db_val if db_val else getattr(Var, config_key, "")
    user_id = callback_query.from_user.id
    
    await callback_query.edit_message_text(
        f"<blockquote><b>Send new FFmpeg config for <code>{config_key}</code>:</b></blockquote>\n\n"
        f"<code>{current_val}</code>"
    )

    try:
        response = await client.listen(
            chat_id=callback_query.message.chat.id,
            filters=filters.text & filters.user(user_id),
            timeout=60
        )

        if response:
            new_config = response.text.strip()
            
            await db.set_anime_ffmpeg(config_key, new_config)
            setattr(Var, config_key, new_config)
            
            await client.send_message(
                chat_id=callback_query.message.chat.id,
                text=f"<blockquote><b>FFmpeg config for <code>{config_key}</code> updated!</b></blockquote>",
                reply_to_message_id=response.id
            )

            await ffmpeg_configs_cb(client, callback_query)

    except TimeoutError:
        await client.send_message(
            chat_id=callback_query.message.chat.id,
            text=f"<blockquote><b>FFmpeg config edit for <code>{config_key}</code> cancelled (timeout).</b></blockquote>"
        )


@bot.on_callback_query(filters.regex(r"^change_upload_mode$"))
async def change_upload_mode_cb(client, callback_query):
    upload_mode = await db.get_upload_mode()
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Hɪɢʜ Eɴᴅ" + (" ✓" if upload_mode == "high_end" else ""),
                callback_data="set_upload_high"
            ),
            InlineKeyboardButton(
                "Lᴏᴡ Eɴᴅ" + (" ✓" if upload_mode == "low_end" else ""),
                callback_data="set_upload_low"
            )
        ],
        [InlineKeyboardButton("« Bᴀᴄᴋ", callback_data="settings_back")]
    ])
    await callback_query.edit_message_text(
        "<blockquote><b>Select Upload Mode:</b></blockquote>\n\n"
        "<blockquote><b>High End:</b> Normal encoding process\n"
        "<b>Low End:</b> Multiple quality downloads without encoding</blockquote>",
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^toggle_low_end_rename$"))
async def toggle_low_end_rename_cb(client, callback_query):
    current = await db.get_low_end_rename()
    new_value = not current
    await db.set_low_end_rename(new_value)
    Var.LOW_END_RENAME = new_value

    encoding = await db.get_encoding()
    channel_creation = await db.get_channel_creation()
    mode = await db.get_mode()
    upload_mode = await db.get_upload_mode()
    user_session = getattr(Var, "USER_SESSION", None)
    
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Cʜᴀɴɴᴇʟ Cʀᴇᴀᴛɪᴏɴ {'Oɴ ✓' if channel_creation else 'Oғғ ✘'}",
                callback_data="toggle_channel_creation"
            ),
            InlineKeyboardButton(
                f"Eɴᴄᴏᴅɪɴɢ Sʏsᴛᴇᴍ {'Oɴ ✓' if encoding else 'Oғғ ✘'}",
                callback_data="toggle_encoding"
            )
        ],
        [
            InlineKeyboardButton(
                f"Lᴏᴡ-Eɴᴅ Rᴇɴᴀᴍᴇ {'Oɴ ✓' if new_value else 'Oғғ ✘'}",
                callback_data="toggle_low_end_rename"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Uᴘʟᴏᴀᴅ Mᴏᴅᴇ: {upload_mode.replace('_', ' ').title()}",
                callback_data="change_upload_mode"
            ),
            InlineKeyboardButton(
                f"Mᴏᴅᴇ: {mode.capitalize()}",
                callback_data="change_mode"
            )
        ],
    ])
    
    text = "<blockquote><b>Settings Panel</blockquote>\n<blockquote>Toggle features below:</b></blockquote>"
    if not user_session:
        text += "<blockquote><b>\n⚠️ <b>USER_SESSION not found!</b>\nPlease enter the user session in <code>config.env</code> to enable this option.</b></blockquote>"

    await callback_query.edit_message_text(
        text,
        reply_markup=btns
    )
    
    await callback_query.answer(
        f"Low-End Rename {'enabled' if new_value else 'disabled'}",
        show_alert=True
    )

@bot.on_callback_query(filters.regex(r"^set_upload_(high|low)$")) 
async def set_upload_mode_cb(client, callback_query):
    mode = callback_query.data.split("_")[-1]
    mode = f"{mode}_end"
    await db.set_upload_mode(mode)
    await callback_query.answer(f"Upload mode set to {mode.replace('_', ' ').title()}", show_alert=True)
    await settings_back_cb(client, callback_query)

@bot.on_callback_query(filters.regex(r"^toggle_encoding$"))
async def toggle_encoding_cb(client, callback_query):
    current = await db.get_encoding()
    new_value = not current
    await db.set_encoding(new_value)
    encoding = new_value
    user_session = getattr(Var, "USER_SESSION", None)
    encoding = await db.get_encoding()
    low_end_rename = await db.get_low_end_rename()
    Var.LOW_END_RENAME = low_end_rename
    channel_creation = await db.get_channel_creation()
    mode = await db.get_mode()
    upload_mode = await db.get_upload_mode()
    low_end_rename = getattr(Var, "LOW_END_RENAME", False)
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Cʜᴀɴɴᴇʟ Cʀᴇᴀᴛɪᴏɴ {'Oɴ ✓' if channel_creation else 'Oғғ ✘'}",
                callback_data="toggle_channel_creation"
            ),
            InlineKeyboardButton(
                f"Eɴᴄᴏᴅɪɴɢ Sʏsᴛᴇᴍ {'Oɴ ✓' if encoding else 'Oғғ ✘'}",
                callback_data="toggle_encoding"
            )
        ],
        [
            InlineKeyboardButton(
                f"Lᴏᴡ-Eɴᴅ Rᴇɴᴀᴍᴇ {'Oɴ ✓' if low_end_rename else 'Oғғ ✘'}",
                callback_data="toggle_low_end_rename"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Uᴘʟᴏᴀᴅ Mᴏᴅᴇ: {upload_mode.replace('_', ' ').title()}",
                callback_data="change_upload_mode"
            ),
            InlineKeyboardButton(
                f"Mᴏᴅᴇ: {mode.capitalize()}",
                callback_data="change_mode"
            )
        ],
    ])
    text = "<blockquote><b>Settings Panel</blockquote>\n<blockquote>Toggle features below:</b></blockquote>"
    user_session = getattr(Var, "USER_SESSION", None)
    if not user_session:
        text += "<blockquote><b>\n⚠️ <b>USER_SESSION not found!</b>\nPlease enter the user session in <code>config.env</code> to enable this option.</b></blockquote>"
    await callback_query.edit_message_text(
        text,
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^change_mode$"))
async def change_mode_cb(client, callback_query):
    mode = await db.get_mode()
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("Aɴɪᴍᴇ" + (" ✓" if mode == "anime" else ""), callback_data="set_mode_anime"),
        InlineKeyboardButton("Mᴀɴɢᴀ" + (" ✓" if mode == "manga" else ""), callback_data="set_mode_manga")],
        [InlineKeyboardButton("Hᴇɴᴛᴀɪ (sᴏᴏɴ)" + (" ✓" if mode == "hentai" else ""), callback_data="set_mode_hentai")],
        [InlineKeyboardButton("Bᴀᴄᴋ", callback_data="settings_back")]
    ])
    await callback_query.edit_message_text(
        "<b>Select Mode:</b>",
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^set_mode_(anime|manga|hentai)$"))
async def set_mode_cb(client, callback_query):
    mode = callback_query.data.split("_")[-1]
    await db.set_mode(mode)
    user_session = getattr(Var, "USER_SESSION", None)
    encoding = await db.get_encoding()
    low_end_rename = await db.get_low_end_rename()
    Var.LOW_END_RENAME = low_end_rename
    channel_creation = await db.get_channel_creation()
    mode = await db.get_mode()
    upload_mode = await db.get_upload_mode()
    low_end_rename = getattr(Var, "LOW_END_RENAME", False)
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Cʜᴀɴɴᴇʟ Cʀᴇᴀᴛɪᴏɴ {'Oɴ ✓' if channel_creation else 'Oғғ ✘'}",
                callback_data="toggle_channel_creation"
            ),
            InlineKeyboardButton(
                f"Eɴᴄᴏᴅɪɴɢ Sʏsᴛᴇᴍ {'Oɴ ✓' if encoding else 'Oғғ ✘'}",
                callback_data="toggle_encoding"
            )
        ],
        [
            InlineKeyboardButton(
                f"Lᴏᴡ-Eɴᴅ Rᴇɴᴀᴍᴇ {'Oɴ ✓' if low_end_rename else 'Oғғ ✘'}",
                callback_data="toggle_low_end_rename"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Uᴘʟᴏᴀᴅ Mᴏᴅᴇ: {upload_mode.replace('_', ' ').title()}",
                callback_data="change_upload_mode"
            ),
            InlineKeyboardButton(
                f"Mᴏᴅᴇ: {mode.capitalize()}",
                callback_data="change_mode"
            )
        ],
    ])
    text = "<blockquote><b>Settings Panel</blockquote>\n<blockquote>Toggle features below:</b></blockquote>"
    await callback_query.edit_message_text(
        text,
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^settings_back$"))
async def settings_back_cb(client, callback_query):
    user_session = getattr(Var, "USER_SESSION", None)
    encoding = await db.get_encoding()
    low_end_rename = await db.get_low_end_rename()
    Var.LOW_END_RENAME = low_end_rename
    channel_creation = await db.get_channel_creation()
    mode = await db.get_mode()
    upload_mode = await db.get_upload_mode()
    low_end_rename = getattr(Var, "LOW_END_RENAME", False)
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Cʜᴀɴɴᴇʟ Cʀᴇᴀᴛɪᴏɴ {'Oɴ ✓' if channel_creation else 'Oғғ ✘'}",
                callback_data="toggle_channel_creation"
            ),
            InlineKeyboardButton(
                f"Eɴᴄᴏᴅɪɴɢ Sʏsᴛᴇᴍ {'Oɴ ✓' if encoding else 'Oғғ ✘'}",
                callback_data="toggle_encoding"
            )
        ],
        [
            InlineKeyboardButton(
                f"Lᴏᴡ-Eɴᴅ Rᴇɴᴀᴍᴇ {'Oɴ ✓' if low_end_rename else 'Oғғ ✘'}",
                callback_data="toggle_low_end_rename"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Uᴘʟᴏᴀᴅ Mᴏᴅᴇ: {upload_mode.replace('_', ' ').title()}",
                callback_data="change_upload_mode"
            ),
            InlineKeyboardButton(
                f"Mᴏᴅᴇ: {mode.capitalize()}",
                callback_data="change_mode"
            )
        ],
    ])
    text = "<blockquote><b>Settings Panel</blockquote>\n<blockquote>Toggle features below:</b></blockquote>"
    user_session = getattr(Var, "USER_SESSION", None)
    if not user_session:
        text += "<blockquote><b>\n⚠️ <b>USER_SESSION not found!</b>\nPlease enter the user session in <code>config.env</code> to enable this option.</b></blockquote>"
    await callback_query.edit_message_text(text, reply_markup=btns)

@bot.on_callback_query(filters.regex(r"^change_mode$"))
async def change_mode_cb(client, callback_query):
    mode = await db.get_mode()
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("Aɴɪᴍᴇ" + (" ✓" if mode == "anime" else ""), callback_data="set_mode_anime"),
         InlineKeyboardButton("Mᴀɴɢᴀ" + (" ✓" if mode == "manga" else ""), callback_data="set_mode_manga")],
        [InlineKeyboardButton("Hᴇɴᴛᴀɪ (sᴏᴏɴ)" + (" ✓" if mode == "hentai" else ""), callback_data="set_mode_hentai")],
        [InlineKeyboardButton("« Bᴀᴄᴋ", callback_data="settings_back")]
    ])
    await callback_query.edit_message_text(
        "<blockquote><b>Select Mode:</b></blockquote>",
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^toggle_channel_creation$"))
async def toggle_channel_creation_cb(client, callback_query):
    user_session = getattr(Var, "USER_SESSION", None)
    if not user_session:
        await callback_query.answer(
            "USER_SESSION not found! Please enter the user session in config.env to enable this option.",
            show_alert=True
        )
        return
    current = await db.get_channel_creation()
    await db.set_channel_creation(not current)
    channel_creation = not current
    user_session = getattr(Var, "USER_SESSION", None)
    encoding = await db.get_encoding()
    low_end_rename = await db.get_low_end_rename()
    Var.LOW_END_RENAME = low_end_rename
    mode = await db.get_mode()
    upload_mode = await db.get_upload_mode()
    low_end_rename = getattr(Var, "LOW_END_RENAME", False)
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Cʜᴀɴɴᴇʟ Cʀᴇᴀᴛɪᴏɴ {'Oɴ ✓' if channel_creation else 'Oғғ ✘'}",
                callback_data="toggle_channel_creation"
            ),
            InlineKeyboardButton(
                f"Eɴᴄᴏᴅɪɴɢ Sʏsᴛᴇᴍ {'Oɴ ✓' if encoding else 'Oғғ ✘'}",
                callback_data="toggle_encoding"
            )
        ],
        [
            InlineKeyboardButton(
                f"Lᴏᴡ-Eɴᴅ Rᴇɴᴀᴍᴇ {'Oɴ ✓' if low_end_rename else 'Oғғ ✘'}",
                callback_data="toggle_low_end_rename"
            ),
        ],
        [
            InlineKeyboardButton(
                f"Uᴘʟᴏᴀᴅ Mᴏᴅᴇ: {upload_mode.replace('_', ' ').title()}",
                callback_data="change_upload_mode"
            ),
            InlineKeyboardButton(
                f"Mᴏᴅᴇ: {mode.capitalize()}",
                callback_data="change_mode"
            )
        ],
    ])
    text = "<blockquote><b>Settings Panel</blockquote>\n<blockquote>Toggle features below:</b></blockquote>"
    if not user_session:
        text += "<blockquote><b>\n⚠️ <b>USER_SESSION not found!</b>\nPlease enter the user session in <code>config.env</code> to enable this option.</b></blockquote>"
    await callback_query.edit_message_text(
        text,
        reply_markup=btns
    )

@bot.on_message(filters.command("addfsub") & filters.user(Var.ADMINS))
@new_task
async def add_fsub_cmd(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("<blockquote><b>Usage:</b> <code>/addfsub &lt;channel_id&gt;</code></blockquote>")
    try:
        channel_id = int(args[1])
        await db.add_fsub(channel_id)
        await update_fsub_chats_var()
        await message.reply(f"<blockquote><b>Force-sub channel added:</b> <code>{channel_id}</code></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("delfsub") & filters.user(Var.ADMINS))
@new_task
async def del_fsub_cmd(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("<blockquote><b>Usage:</b> <code>/delfsub &lt;channel_id&gt;</code></blockquote>")
    try:
        channel_id = int(args[1])
        await db.del_fsub(channel_id)
        await update_fsub_chats_var()
        await message.reply(f"<blockquote><b>Force-sub channel removed:</b> <code>{channel_id}</code></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("listfsubs") & filters.user(Var.ADMINS))
@new_task
async def list_fsubs_cmd(client, message: Message):
    try:
        channels = await db.list_fsubs()
        if not channels:
            return await message.reply("<blockquote><b>No force-sub channels set.</b></blockquote>")
        msg = "<blockquote><b>Force-sub Channels:</b></blockquote>\n"
        for ch in channels:
            msg += f"<code>{ch}</code>\n"
        await message.reply(msg)
    except Exception as e:
        await message.reply(f"Error: {e}")


@bot.on_message(filters.command('ping') & user(Var.ADMINS))
@new_task
async def ping_cmd(client, message):
    now = datetime.now()
    try:
        uptime = get_readable_time((now - bot.start_time_helper.start_time).total_seconds())
    except Exception:
        uptime = "N/A"
    ping = await get_ping(bot)
    db_response_time = await get_db_response_time()
    stats_text = (
        f"<b><blockquote>Bot Uptime: {uptime}\n"
        f"Ping: {ping} ms\n"
        f"Database Response Time: {db_response_time} ms</blockquote></b>\n"
    )
    await message.reply(stats_text)


@bot.on_message(filters.command("delallffmpeg") & filters.user(Var.ADMINS))
@new_task
async def del_all_ffmpeg_cmd(client, message: Message):
    try:
        await db.delete_all_ffmpeg_configs()
        await message.reply("<blockquote><b>All FFmpeg configs deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")


@bot.on_message(filters.command("delallanimes") & filters.user(Var.ADMINS))
@new_task
async def del_all_anime_cmd(client, message: Message):
    try:
        await db.delete_all_anime_mappings()
        await message.reply("<blockquote><b>All anime mappings deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")


@bot.on_message(filters.command("delallbanners") & filters.user(Var.ADMINS))
@new_task
async def del_all_banner_cmd(client, message: Message):
    try:
        await db.delete_all_anime_banners()
        await message.reply("<blockquote><b>All anime banners deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")


@bot.on_message(filters.command("viewbanner") & filters.user(Var.ADMINS))
@new_task
async def view_banner_cmd(client, message: Message):
    anime_name = message.text[len("/viewbanner"):].strip()
    if not anime_name:
        return await message.reply("<blockquote><b>Usage: /viewbanner Anime Name</b></blockquote>")
    banner_url = await db.get_anime_banner(anime_name)
    if not banner_url:
        return await message.reply(f"<blockquote><b>No banner set for:</b> <code>{anime_name}</code></blockquote>")
    await message.reply_photo(photo=banner_url, caption=f"<blockquote><b>Banner for:</b> <code>{anime_name}</code></blockquote>")


@bot.on_message(filters.command("broadcast") & filters.user(Var.ADMINS))
@new_task
async def broadcast_cmd(client, message: Message):
    if not message.reply_to_message:
        return await message.reply("<blockquote><b>Reply to a message to broadcast it to all users.</b></blockquote>")
    try:
        users = await db.get_all_users() if hasattr(db, 'get_all_users') else []
        if not users:
            return await message.reply("<blockquote><b>No users found in database.</b></blockquote>")
        sent = 0
        failed = 0
        for user_id in users:
            try:
                await client.copy_message(chat_id=user_id, from_chat_id=message.chat.id, message_id=message.reply_to_message.id)
                sent += 1
            except Exception:
                failed += 1
        await message.reply(f"<blockquote><b>Broadcast finished!\nSent: {sent}\nFailed: {failed}</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("setschedule") & filters.user(Var.ADMINS))
@new_task
async def set_schedule_cmd(client, message: Message):
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    status = "Oɴ" if Var.SEND_SCHEDULE else "Oғғ"
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Oɴ ✓" if Var.SEND_SCHEDULE else "Oɴ", callback_data="schedule_on"),
            InlineKeyboardButton("Oғғ ✘" if not Var.SEND_SCHEDULE else "Oғғ", callback_data="schedule_off"),
        ]
    ])
    await message.reply(
        f"<blockquote><b>Current Schedule Status: <code>{status}</code>\n\nChoose ON or OFF:</b></blockquote>",
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^schedule_(on|off)$"))
async def schedule_callback(client, callback_query):
    if callback_query.data == "schedule_on":
        Var.SEND_SCHEDULE = True
        await db.set_send_schedule(True)
        await callback_query.answer("Schedule set to ON", show_alert=True)
        await callback_query.edit_message_text("<blockquote><b>Schedule is now ON.</b></blockquote>")
    elif callback_query.data == "schedule_off":
        Var.SEND_SCHEDULE = False
        await db.set_send_schedule(False)
        await callback_query.answer("Schedule set to OFF", show_alert=True)
        await callback_query.edit_message_text("<blockquote><b>Schedule is now OFF.</b></blockquote>")

@bot.on_message(filters.command("setstartpic") & filters.user(Var.ADMINS))
@new_task
async def set_start_pic_cmd(client, message: Message):
    try:
        if message.reply_to_message and message.reply_to_message.photo:
            photo = message.reply_to_message.photo
            Var.START_PHOTO = photo.file_id
            if hasattr(db, "set_start_photo"):
                await db.set_start_photo(photo.file_id)
            await message.reply("<blockquote><b>Start photo set from replied photo!</b></blockquote>")
        else:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                return await message.reply("<blockquote><b>Reply to a photo or use:</b> <code>/setstartpic &lt;url&gt;</code></blockquote>")
            Var.START_PHOTO = args[1].strip()
            if hasattr(db, "set_start_photo"):
                await db.set_start_photo(Var.START_PHOTO)
            await message.reply("<blockquote><b>Start photo set from URL!</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("setsticker") & filters.user(Var.ADMINS))
@new_task
async def set_sticker_cmd(client, message: Message):
    try:
        if message.reply_to_message and message.reply_to_message.sticker:
            sticker_id = message.reply_to_message.sticker.file_id
        else:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                return await message.reply("<blockquote><b>Reply to a sticker or use:</b> <code>/setsticker &lt;sticker_id&gt;</code></blockquote>")
            sticker_id = args[1].strip()
        await db.set_sticker_id(sticker_id)
        Var.STICKER_ID = sticker_id
        await message.reply("<blockquote><b>Sticker set successfully!</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("viewsticker") & filters.user(Var.ADMINS))
@new_task
async def view_sticker_cmd(client, message: Message):
    try:
        sticker_id = await db.get_sticker_id()
        if not sticker_id:
            return await message.reply("<blockquote><b>No sticker set.</b></blockquote>")
        await message.reply_sticker(sticker_id)
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("delsticker") & filters.user(Var.ADMINS))
@new_task
async def del_sticker_cmd(client, message: Message):
    try:
        await db.del_sticker_id()
        Var.STICKER_ID = ""
        await message.reply("<blockquote><b>Sticker deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("setthumb") & filters.user(Var.ADMINS))
@new_task
async def set_global_thumb_cmd(client, message: Message):
    try:
        if not message.reply_to_message or not message.reply_to_message.photo:
            return await message.reply("<blockquote><b>Reply to a photo with:</b> <code>/setthumb</code></blockquote>")
        photo = message.reply_to_message.photo
        file_id = photo.file_id
        await db.set_global_thumb(file_id)
        await client.download_media(photo, file_name=os.path.join(os.getcwd(), "thumb.jpg"))
        await message.reply("<blockquote><b>Global thumbnail set!</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("viewthumb") & filters.user(Var.ADMINS))
@new_task
async def view_global_thumb_cmd(client, message: Message):
    try:
        file_id = await db.get_global_thumb()
        if not file_id:
            return await message.reply("<blockquote><b>No global thumbnail set.</b></blockquote>")
        await message.reply_photo(file_id, caption="<b>Current global thumbnail:</b>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("delthumb") & filters.user(Var.ADMINS))
@new_task
async def del_global_thumb_cmd(client, message: Message):
    try:
        await db.del_global_thumb()
        from os import remove
        try:
            remove("thumb.jpg")
        except FileNotFoundError:
            pass
        await message.reply("<blockquote><b>Global thumbnail deleted!</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("setbanner") & filters.user(Var.ADMINS))
@new_task
async def set_anime_banner_cmd(client, message: Message):
    try:
        if message.reply_to_message and message.reply_to_message.photo:
            anime_name = message.text[len("/setbanner"):].strip()
            if not anime_name:
                return await message.reply("<blockquote><b>Usage when replying to photo:</b>\n<code>/setbanner Anime Name</code></blockquote>")

            banner_url = message.reply_to_message.photo.file_id
        else:
            text = message.text[len("/setbanner"):].strip()
            if " - " not in text:
                return await message.reply("<blockquote><b>Usage: /setbanner Anime Name - Banner URL</b></blockquote>")
            anime_name, banner_url = text.split(" - ", 1)
            anime_name = anime_name.strip()
            banner_url = banner_url.strip()

        if not anime_name or not banner_url:
            return await message.reply("<blockquote><b>Please provide both the anime name and banner (URL or photo).</b></blockquote>")
        possible_names = await get_all_possible_anime_names(anime_name)
        for name in possible_names:
            await db.set_anime_banner(name, banner_url)
        if message.reply_to_message and message.reply_to_message.photo:
            await message.reply(f"<blockquote><b>Set banner for anime from replied photo:</b>\n<code>{anime_name}</code></blockquote>\n<blockquote><b>Mapped variants:</b> <code>{', '.join(possible_names)}</code></blockquote>")
        else:
            await message.reply(f"<blockquote><b>Set banner for anime from URL:</b>\n<code>{anime_name}</code>\n\n<code>{banner_url}</code></blockquote>\n<blockquote><b>Mapped variants:</b> <code>{', '.join(possible_names)}</code></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")


@bot.on_message(filters.command("delbanner") & filters.user(Var.ADMINS))
@new_task
async def del_anime_banner_cmd(client, message: Message):
    try:
        text = message.text[len("/delbanner"):].strip()
        if not text:
            return await message.reply("<blockquote><b>Usage:</b> <code>/delbanner Anime Name</code></blockquote>")
        possible_names = await get_all_possible_anime_names(text)
        for name in possible_names:
            await db.del_anime_banner(name)
        await message.reply(f"<blockquote><b>Banner deleted for:</b> <code>{text}</code></blockquote>\n<blockquote><b>Mapped variants:</b> <code>{', '.join(possible_names)}</code></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("listbanners") & filters.user(Var.ADMINS))
@new_task
async def list_anime_banners_cmd(client, message: Message):
    try:
        banners = await db.list_anime_banners()
        if not banners:
            return await message.reply("<blockquote><b>No banners set.</b></blockquote>")
        msg = "<blockquote><b>Custom Banners:</b></blockquote>\n"
        for name, url in banners:
            msg += f"<blockquote><code>{name}</code> - <a href='{url}'>Banner</a></blockquote>\n"
        await message.reply(msg, disable_web_page_preview=True)
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("api") & filters.user(Var.ADMINS))
@new_task
async def api_select(client, message):
    current = await db.get_api_source()
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("AɴɪLɪsᴛ ✓" if current == "anilist" else "AɴɪLɪsᴛ", callback_data="api_anilist"),
            InlineKeyboardButton("Jɪᴋᴀɴ ✓" if current == "jikan" else "Jɪᴋᴀɴ", callback_data="api_jikan"),
        ]
    ])
    await message.reply("<blockquote><b>Current API: <code>{}</b> </code>\n<b>Choose API source:</blockquote></b>".format(current), reply_markup=btns)

@bot.on_callback_query(filters.regex(r"^api_(anilist|jikan)$"))
async def api_callback(client, callback_query):
    if callback_query.data.startswith("api_"):
        api = callback_query.data.split("_", 1)[1]
        await db.set_api_source(api)
        await callback_query.answer(f"API set to {api.capitalize()}", show_alert=True)
        await callback_query.edit_message_text(f"<blockquote><b>API changed to: <code>{api}</code></blockquote></b>")
    
@bot.on_message(filters.command("listanimes") & filters.user(Var.ADMINS))
@new_task
async def list_anime_channels(client, message: Message):
    try:
        anime_channels = await db.get_all_anime_channels()

        if not anime_channels:
            return await message.reply("<blockquote><b>No anime channels have been added yet.</blockquote></b>")

        response_text = "<blockquote><b> List of Anime Channels:</b></blockquote>\n\n"
        for anime, channel in anime_channels.items():
            response_text += f"<blockquote expandable><b>{anime} - {channel}</b></blockquote expandable>\n"

        await message.reply_text(response_text)

    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(filters.command("setdel") & filters.user(Var.ADMINS))
@new_task
async def set_auto_delete_cmd(client, message: Message):
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    status = "Oɴ" if Var.AUTO_DEL else "Oғғ"
    btns = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Oɴ ✓" if Var.AUTO_DEL else "Oɴ", callback_data="autodel_on"),
            InlineKeyboardButton("Oғғ ✘" if not Var.AUTO_DEL else "Oғғ", callback_data="autodel_off"),
        ]
    ])
    await message.reply(
        f"<blockquote><b>Current Auto Delete Status: <code>{status}</code>\n\nChoose ON or OFF:</b></blockquote>",
        reply_markup=btns
    )

@bot.on_callback_query(filters.regex(r"^autodel_(on|off)$"))
async def autodel_callback(client, callback_query):
    if callback_query.data == "autodel_on":
        Var.AUTO_DEL = True
        await db.set_auto_del(True)
        await callback_query.answer("Auto Delete set to ON", show_alert=True)
        await callback_query.edit_message_text("<blockquote><b>Auto Delete is now ON.</b></blockquote>")
    elif callback_query.data == "autodel_off":
        Var.AUTO_DEL = False
        await db.set_auto_del(False)
        await callback_query.answer("Auto Delete set to OFF", show_alert=True)
        await callback_query.edit_message_text("<blockquote><b>Auto Delete is now OFF.</b></blockquote>")

@bot.on_message(filters.command("setdeltimer") & filters.user(Var.ADMINS))
@new_task
async def set_auto_delete_timer_cmd(client, message: Message):
    args = message.text.split(maxsplit=1)
    current_minutes = Var.DEL_TIMER // 60
    if len(args) < 2 or not args[1].isdigit():
        return await message.reply(
            f"<blockquote><b>Usage: <code>/setdeltimer &lt;minutes&gt;</code></b>\n"
            f"<b>Current Auto Delete Timer: <code>{current_minutes} minutes</code></blockquote></b>"
        )
    Var.DEL_TIMER = int(args[1]) * 60
    await db.set_del_timer(Var.DEL_TIMER)
    await message.reply(f"<blockquote><b>Auto Delete Timer set to: <code>{args[1]} minutes</code></blockquote></b>")

@bot.on_message(filters.command("episode_history"))
async def episode_history(client, message: Message):
    try:
        anime_name = message.text.split(" ", 1)[1].strip().lower()

        anime_data = await db.getAnime(anime_name)

        if not anime_data:
            return await message.reply("<blockquote><b>No data found for this anime.</b></blockquote>")

        uploaded_episodes = []
        missing_episodes = []
        current_episode = 1

        while True:
            episode_key = f"ep{current_episode}"
            episode_data = anime_data.get(episode_key, None)

            if episode_data:
                uploaded_episodes.append(
                    f"<blockquote><b>Episode {current_episode}: Uploaded on {episode_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</b></blockquote>")
            else:
                missing_episodes.append(f"<blockquote><b>Episode {current_episode}</b></blockquote>")
            
            current_episode += 1

            if current_episode > 100:
                break

        if uploaded_episodes:
            uploaded_text = "\n".join(uploaded_episodes)
        else:
            uploaded_text = "<blockquote><b>No episodes uploaded yet.</b></blockquote>"

        if missing_episodes:
            missing_text = "\n".join(missing_episodes)
        else:
            missing_text = "<blockquote><b>No episodes are missing.</b></blockquote>"

        reply_text = f"<blockquote><b>Episode History for '{anime_name.capitalize()}':<b></blockquote>\n\n<blockquote><b>Uploaded Episodes:</b>\n{uploaded_text}\n\n<b>Missing Episodes:</b>\n{missing_text}</blockquote>"

        await message.reply_text(reply_text)

    except Exception as e:
        await message.reply_text(f"Error: {str(e)}")
    
@bot.on_message(filters.command("addanime") & filters.user(Var.ADMINS))
@new_task
async def set_anime_channel(client, message: Message):
    try:
        text = message.text[len("/addanime"):].strip()

        if " - " not in text:
            return await message.reply("<blockquote><b>Usage: /addanime <anime name> - <channel username or ID></b></blockquote>")

        anime_name, channel = text.split(" - ", 1)
        anime_name = anime_name.strip()
        channel = channel.strip()

        if not anime_name or not channel:
            return await message.reply("<blockquote><b>Please provide both the anime name and channel ID.</b></blockquote>")

        if channel.startswith("@"):
            final_channel = channel
        else:
            try:
                final_channel = int(channel)
            except ValueError:
                return await message.reply("<blockquote><b>Invalid channel ID. Please provide a valid channel ID or username.</b></blockquote>")

        possible_names = await get_all_possible_anime_names(anime_name)

        if not possible_names:
            await db.add_anime_channel_mapping(anime_name, final_channel)
            return await message.reply(
                f"<blockquote><b>No matching variants found for '{anime_name}'. Added the anime manually to the channel '{channel}'.</b></blockquote>"
            )

        for name in possible_names:
            await db.add_anime_channel_mapping(name, final_channel)

        await message.reply(
            f"<blockquote><b>Set channel for '{anime_name}' to '{channel}'</b></blockquote>\n"
            f"<blockquote><b>Mapped variants:</b> <code>{', '.join(possible_names)}</code></blockquote>"
        )

    except Exception as e:
        print(f"Error occurred while processing the /addanime command: {e}")
        await message.reply(f"<blockquote><b>Error occurred: {e}</b></blockquote>")


@bot.on_message(filters.command("delanime") & filters.user(Var.ADMINS))
@new_task
async def remove_anime_channel_cmd(client, message: Message):
    try:
        cmd_text = message.text.strip()
        if " - " in cmd_text:
            _, rest = cmd_text.split(maxsplit=1)
            anime_name, channel = map(str.strip, rest.split(" - ", 1))
        else:
            anime_name = cmd_text[len("/delanime"):].strip()
            channel = None
        if not anime_name:
            return await message.reply("<blockquote><b>Usage: /delanime anime name [- channel]</b></blockquote>")
        possible_names = await get_all_possible_anime_names(anime_name)
        for name in possible_names:
            await db.remove_anime_channel_mapping(name, channel)
        
        await message.reply(f"<blockquote><b>Removed mapping for '{anime_name}'{f' from {channel}' if channel else ''}</b></blockquote>")
    except Exception as e:
        await message.reply(f"Error: {e}")

@bot.on_message(command('shell') & private & user(Var.ADMINS))
@new_task
async def shell(client, message):
    cmd = message.text.split(" ", 1)
    if len(cmd) == 1:
        message.reply_text("<blockquote>No command to execute was given.</blockquote>")
        return
    cmd = cmd[1]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
    )
    stdout, stderr = process.communicate()
    reply = ""
    stderr = stderr.decode()
    stdout = stdout.decode()
    if stdout:
        reply += f"*ᴘᴀʀᴀᴅᴏx \n stdout*\n`{stdout}`\n"
        LOGGER.info(f"Shell - {cmd} - {stdout}")
    if stderr:
        reply += f"*ᴘᴀʀᴀᴅᴏx \n stdou*\n`{stderr}`\n"
        LOGGER.error(f"Shell - {cmd} - {stderr}")
    if len(reply) > 3000:
        with open("shell_output.txt", "w") as file:
            file.write(reply)
        with open("shell_output.txt", "rb") as doc:
            context.bot.send_document(
                document=doc,
                filename=doc.name,
                reply_to_message_id=message.message_id,
                chat_id=message.chat_id,
            )
    else:
        message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


@bot.on_message(command('start') & private)
@new_task
async def start_msg(client, message):
    uid = message.from_user.id
    from_user = message.from_user
    txtargs = message.text.split()
    try:
        await db.add_user(uid)
    except Exception:
        pass
    temp = await sendMessage(message, "<pre>待って、かわい子ちゃん</pre>")
    if not await is_fsubbed(uid):
        txt, btns = await get_fsubs(uid, txtargs)
        return await editMessage(temp, txt, InlineKeyboardMarkup(btns))
    if len(txtargs) <= 1:
        await temp.delete()
        btns = []
        for elem in Var.START_BUTTONS.split():
            try:
                bt, link = elem.split('|', maxsplit=1)
            except:
                continue
            if len(btns) != 0 and len(btns[-1]) == 1:
                btns[-1].insert(1, InlineKeyboardButton(bt, url=link))
            else:
                btns.append([InlineKeyboardButton(bt, url=link)])
        smsg = Var.START_MSG.format(first_name=from_user.first_name,
                                    last_name=from_user.first_name,
                                    mention=from_user.mention, 
                                    user_id=from_user.id)
        if Var.START_PHOTO:
            await message.reply_photo(
                photo=Var.START_PHOTO, 
                caption=smsg,
                reply_markup=InlineKeyboardMarkup(btns) if len(btns) != 0 else None
            )
        else:
            await sendMessage(message, smsg, InlineKeyboardMarkup(btns) if len(btns) != 0 else None)
        return
    try:
        arg = (await decode(txtargs[1])).split('-')
    except Exception as e:
        await rep.report(f"User : {uid} | Error : {str(e)}", "error")
        await editMessage(temp, "<blockquote><b>Input Link Code Decode Failed !</b></blockquote>")
        return

    def wrap_blockquote(text):
        return "\n".join([f"<blockquote><b>{line}</b></blockquote>" for line in text.splitlines() if line.strip()])

    if len(arg) == 3 and arg[0] == 'get':
        try:
            first = int(int(arg[1]) / abs(int(Var.FILE_STORE)))
            last = int(int(arg[2]) / abs(int(Var.FILE_STORE)))
            if first > last:
                first, last = last, first
            minutes = Var.DEL_TIMER // 60
            sent_msgs = []
            for mid in range(first, last + 1):
                msg = await client.get_messages(Var.FILE_STORE, message_ids=mid)
                if msg.empty:
                    continue
                nmsg = None
                if msg.text:
                    text = msg.text
                    if msg.reply_markup:
                        text = wrap_blockquote(text)
                    nmsg = await client.send_message(
                        chat_id=message.chat.id,
                        text=text,
                        reply_markup=msg.reply_markup if msg.reply_markup else None,
                        parse_mode=ParseMode.HTML
                    )
                elif msg.caption and msg.photo:
                    caption = msg.caption
                    if msg.reply_markup:
                        caption = wrap_blockquote(caption)
                    nmsg = await client.send_photo(
                        chat_id=message.chat.id,
                        photo=msg.photo.file_id,
                        caption=caption,
                        reply_markup=msg.reply_markup if msg.reply_markup else None,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    nmsg = await msg.copy(
                        chat_id=message.chat.id,
                        reply_markup=msg.reply_markup if msg.reply_markup else None
                    )
                if nmsg and Var.AUTO_DEL:
                    sent_msgs.append(nmsg)
            await temp.delete()
            if sent_msgs and Var.AUTO_DEL:
                async def auto_del(msgs, timer):
                    await asleep(timer)
                    for m in msgs:
                        try:
                            await m.delete()
                        except Exception:
                            pass
                await sendMessage(
                    message,
                    f'<blockquote><b>⚠️ Wᴀʀɴɪɴɢ ⚠️\n\nTʜᴇsᴇ Fɪʟᴇs Wɪʟʟ Bᴇ Dᴇʟᴇᴛᴇᴅ Aᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ Iɴ {minutes} Mɪɴ. Fᴏʀᴡᴀʀᴅ Tʜᴇsᴇ Mᴇssᴀɢᴇs...!</b></blockquote>'
                )
                bot_loop.create_task(auto_del(sent_msgs, Var.DEL_TIMER))
            return
        except Exception as e:
            await message.reply(f"Error: {e}")
            await temp.delete()
            return

    if len(arg) == 2 and arg[0] == 'get':
        try:
            fid = int(int(arg[1]) / abs(int(Var.FILE_STORE)))
        except Exception as e:
            await rep.report(f"User : {uid} | Error : {str(e)}", "error")
            await editMessage(temp, "<blockquote><b>Input Link Code is Invalid !</b></blockquote>")
            return
        try:
            msg = await client.get_messages(Var.FILE_STORE, message_ids=fid)
            if msg.empty:
                return await editMessage(temp, "<blockquote><b>File Not Found !</b></blockquote>")
            if msg.text:
                text = msg.text
                if msg.reply_markup:
                    text = wrap_blockquote(text)
                nmsg = await client.send_message(
                    chat_id=message.chat.id,
                    text=text,
                    reply_markup=msg.reply_markup if msg.reply_markup else None,
                    parse_mode=ParseMode.HTML
                )
            elif msg.caption and msg.photo:
                caption = msg.caption
                if msg.reply_markup:
                    caption = wrap_blockquote(caption)
                nmsg = await client.send_photo(
                    chat_id=message.chat.id,
                    photo=msg.photo.file_id,
                    caption=caption,
                    reply_markup=msg.reply_markup if msg.reply_markup else None,
                    parse_mode=ParseMode.HTML
                )
            else:
                nmsg = await msg.copy(
                    message.chat.id,
                    reply_markup=msg.reply_markup if msg.reply_markup else None
                )
            await temp.delete()
            if Var.AUTO_DEL:
                async def auto_del(msg, timer):
                    await asleep(timer)
                    await msg.delete()
                minutes = Var.DEL_TIMER // 60
                await sendMessage(
                    message,
                    f'<blockquote><b>⚠️ Wᴀʀɴɪɴɢ ⚠️\n\nTʜᴇsᴇ Fɪʟᴇs Wɪʟʟ Bᴇ Dᴇʟᴇᴛᴇᴅ Aᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ Iɴ {minutes} Mɪɴ. Fᴏʀᴡᴀʀᴅ Tʜᴇsᴇ Mᴇssᴀɢᴇs...!</b></blockquote>'
                )
                bot_loop.create_task(auto_del(nmsg, Var.DEL_TIMER))
        except Exception as e:
            await rep.report(f"User : {uid} | Error : {str(e)}", "error")
            await editMessage(temp, "<blockquote><b>File Not Found !</b></blockquote>")
    else:
        await editMessage(temp, "<blockquote><b>Input Link is Invalid for Usage !</b></blockquote>")
    
@bot.on_message(command('pause') & private & user(Var.ADMINS))
async def pause_fetch(client, message):
    ani_cache['global_pause'] = True
    await sendMessage(message, "<blockquote><b>Fetching paused for all modes (anime, manga, hentai).</b></blockquote>")

@bot.on_message(command('resume') & private & user(Var.ADMINS))
async def resume_fetch(client, message):
    ani_cache['global_pause'] = False
    await sendMessage(message, "<blockquote><b>Fetching resumed for all modes (anime, manga, hentai).</b></blockquote>")

@bot.on_message(command('log') & private & user(Var.ADMINS))
@new_task
async def _log(client, message):
    await message.reply_document("log.txt", quote=True)

@bot.on_message(filters.command("addlink") & filters.user(Var.ADMINS))
@new_task
async def add_link_cmd(client, message: Message):
    try:
        args = message.text.split()
        if len(args) < 3:
            return await message.reply(
                "<blockquote><b>Usage:\n"
                "/addlink anime [rss_link ...]\n"
                "/addlink manga [rss_link ...]\n"
                "/addlink lowend [quality] [rss_link ...]</b></blockquote>"
            )
        link_type = args[1].lower()
        links_to_save = []
        if link_type == "lowend":
            if len(args) < 4:
                return await message.reply("<blockquote><b>Usage: /addlink lowend [quality] [rss_link ...]</b></blockquote>")
            quality = args[2]
            rss_links = args[3:]
            for rss_link in rss_links:
                if not hasattr(Var, "RSS_LOW_END") or Var.RSS_LOW_END is None:
                    Var.RSS_LOW_END = {}
                if quality not in Var.RSS_LOW_END:
                    links_to_save.append({"type": "lowend", "link": rss_link, "quality": quality})
                    Var.RSS_LOW_END[quality] = rss_link
            if links_to_save:
                await db.save_rss_links_bulk(links_to_save)
                await message.reply(f"<blockquote><b>Low-End RSS link(s) for {quality}p added and saved to database.</b></blockquote>")
            else:
                await message.reply(f"<blockquote><b>Low-End RSS link(s) for {quality}p already exist.</b></blockquote>")
        elif link_type in ("anime", "manga"):
            rss_links = args[2:]
            for rss_link in rss_links:
                if link_type == "anime":
                    if rss_link not in Var.RSS_ITEMS_ANIME:
                        links_to_save.append({"type": link_type, "link": rss_link})
                        Var.RSS_ITEMS_ANIME.append(rss_link)
                elif link_type == "manga":
                    if rss_link not in Var.RSS_ITEMS_MANGA:
                        links_to_save.append({"type": link_type, "link": rss_link})
                        Var.RSS_ITEMS_MANGA.append(rss_link)
            if links_to_save:
                await db.save_rss_links_bulk(links_to_save)
                await message.reply(f"<blockquote><b>{link_type.capitalize()} RSS link(s) added and saved to database.</b></blockquote>")
            else:
                await message.reply(f"<blockquote><b>{link_type.capitalize()} RSS link(s) already exist.</b></blockquote>")
        else:
            await message.reply("<blockquote><b>Unknown link type. Use anime, manga, or lowend.</b></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error: {str(e)}</b></blockquote>")

@bot.on_message(filters.command("listlinks") & filters.user(Var.ADMINS))
@new_task
async def list_links_cmd(client, message: Message):
    try:
        msg = "<blockquote><b>RSS Feed Links:</b></blockquote>\n\n"
        
        if Var.RSS_ITEMS_ANIME:
            msg += "<blockquote><b>Anime RSS:</b></blockquote>\n"
            for i, link in enumerate(Var.RSS_ITEMS_ANIME, 1):
                msg += f"<blockquote>{i}. <code>{link}</code></blockquote>\n"
        else:
            msg += "<blockquote><b>No anime RSS links set.</b></blockquote>\n"
            
        msg += "\n"
        
        if Var.RSS_ITEMS_MANGA:
            msg += "<blockquote><b>Manga RSS:</b></blockquote>\n"
            for i, link in enumerate(Var.RSS_ITEMS_MANGA, 1):
                msg += f"<blockquote>{i}. <code>{link}</code></blockquote>\n"
        else:
            msg += "<blockquote><b>No manga RSS links set.</b></blockquote>\n"

        msg += "\n"

        if hasattr(Var, "RSS_LOW_END") and Var.RSS_LOW_END:
            msg += "<blockquote><b>Low-End RSS:</b></blockquote>\n"
            for qual, link in Var.RSS_LOW_END.items():
                msg += f"<blockquote>{qual}p: <code>{link}</code></blockquote>\n"
        else:
            msg += "<blockquote><b>No low-end RSS links set.</b></blockquote>"

        await message.reply(msg)
        
    except Exception as e:
        await message.reply(f"<blockquote><b>Error:</b> {str(e)}</blockquote>")

@bot.on_message(filters.command("dellink") & filters.user(Var.ADMINS))
@new_task
async def del_link_cmd(client, message: Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3 or args[1] not in ['anime', 'manga']:
            return await message.reply(
                "<blockquote><b>Usage:</b>\n"
                "<code>/dellink anime &lt;rss_link&gt;</code> or\n"
                "<code>/dellink manga &lt;rss_link&gt;</code></blockquote>"
            )
            
        link_type = args[1]
        link = args[2].strip()
        
        if link_type == 'anime':
            if link not in Var.RSS_ITEMS_ANIME:
                return await message.reply("<blockquote><b>This anime RSS link doesn't exist!</b></blockquote>")
            Var.RSS_ITEMS_ANIME.remove(link)
        else:
            if link not in Var.RSS_ITEMS_MANGA:
                return await message.reply("<blockquote><b>This manga RSS link doesn't exist!</b></blockquote>")
            Var.RSS_ITEMS_MANGA.remove(link)
        await db.delete_rss_link(link_type, link)
        await message.reply(f"<blockquote><b>Removed {link_type} RSS link:</b>\n<code>{link}</code></blockquote>")
    except Exception as e:
        await message.reply(f"<blockquote><b>Error: {str(e)}</b></blockquote>")

@bot.on_message(filters.command("addtask") & filters.user(Var.ADMINS))
@new_task
@rate_limit(3)
async def add_custom_task(client, message: Message):
    try:
        text = message.text[len("/addtask"):].strip()
        if not text:
            return await message.reply(
                "<b>Usage:</b> <code>/addtask [hentai|anime|manga] &lt;rss_link&gt; [position]</code>\n"
                "<b>Example:</b> <code>/addtask hentai https://rss.link/feed 3</code>"
            )
        parts = text.split()
        if len(parts) < 2:
            return await message.reply(
                "<b>Usage:</b> <code>/addtask [hentai|anime|manga] &lt;rss_link&gt; [position]</code>"
            )

        if parts[0].lower() in ("hentai", "anime", "manga"):
            mode = parts[0].lower()
            rsslink = parts[1]
            position = int(parts[2]) - 1 if len(parts) > 2 and parts[2].isdigit() else 0
        else:
            rsslink = parts[0]
            position = int(parts[1]) - 1 if len(parts) > 1 and parts[1].isdigit() else 0
            mode = parts[2].lower() if len(parts) > 2 and parts[2].lower() in ("hentai", "anime", "manga") else await db.get_mode()

        status_msg = await message.reply("<blockquote><b>Fetching RSS feed...</b></blockquote>")
        taskInfo = await getfeed(rsslink, position)
        if not taskInfo:
            return await status_msg.edit_text(
                "<blockquote><b><i>Failed to fetch RSS feed\n\n"
                "Possible reasons:\n"
                "• Invalid RSS URL\n"
                "• Feed number out of range\n"
                "• Feed server not responding</b></blockquote>"
            )

        await status_msg.edit_text("<blockquote><b>Checking for duplicates...</b></blockquote>")
        if await db.getAnime(taskInfo.link):
            return await status_msg.edit_text(
                "<blockquote><b>Task already exists or was previously uploaded.</b></blockquote>"
            )

        await status_msg.edit_text(
            f"<blockquote><b><i>Adding Task...</i>\n\n"
            f"<b>    • Task Name :</b> {taskInfo.title}\n"
            f"<b>    • Task Link :</b> {position + 1}\n"
            f"<b>    • Type :</b> {mode.capitalize()}</b></blockquote>"
        )

        if mode == "hentai":
            from bot.core.auto_animes import process_hentai
            bot_loop.create_task(process_hentai(taskInfo.title, taskInfo.link, force=True))
        elif mode == "manga":
            from bot.core.auto_animes import process_manga_chapter
            bot_loop.create_task(process_manga_chapter(taskInfo.title, taskInfo.link, manual=True))
        else:
            from bot.core.auto_animes import get_animes
            bot_loop.create_task(get_animes(taskInfo.title, taskInfo.link, force=True))

        await status_msg.edit_text(
            f"<blockquote><b><i>Task Added Successfully!</i>\n\n"
            f"<b>    • Type :</b> {mode.capitalize()}\n"
            f"<b>    • Task Name :</b> {taskInfo.title}\n"
            f"<b>    • Task Link :</b> {position + 1}</b></blockquote>"
        )

    except Exception as e:
        await message.reply(f"<b><blockquote>Error adding task:</b> {str(e)}</blockquote>")
        await rep.report(f"Task addition error: {str(e)}", "error")

@bot.on_message(filters.command("status") & filters.user(Var.ADMINS))
@new_task
async def status_cmd(client, message: Message):
    try:
        mode = await db.get_mode()
        paused = ani_cache.get('global_pause', False)
        encoding = await db.get_encoding()
        channel_creation = await db.get_channel_creation()
        auto_del = Var.AUTO_DEL
        del_timer = Var.DEL_TIMER // 60
        anime_tasks = len([task for task in ani_cache.get('ongoing', set())])
        api_source = await db.get_api_source()
        
        status_text = (
            "<blockquote><b>Bot Status</b>\n\n"
            f"<b>Mode:</b> {mode.capitalize()}\n"
            f"<b>Status:</b> {'Paused ❚❚' if paused else 'Running ▷'}\n"
            f"<b>Encoding:</b> {'Enabled ✓' if encoding else 'Disabled ✘'}\n"
            f"<b>Channel Creation:</b> {'Enabled ✓' if channel_creation else 'Disabled ✘'}\n"
            f"<b>Auto Delete:</b> {'Enabled ✓' if auto_del else 'Disabled ✘'} ({del_timer} min)\n"
            f"<b>API Source:</b> {api_source.capitalize()}\n"
            f"<b>Active Tasks:</b> {anime_tasks}</blockquote>\n\n"
        )

        try:
            import psutil
            process = psutil.Process()
            memory_use = process.memory_info().rss / 1024 / 1024
            cpu_use = process.cpu_percent()
            status_text += f"<blockquote><b>Memory Usage:</b>\n<b>RAM:</b> {memory_use:.1f} MB\n<b>CPU:</b> {cpu_use}%</blockquote>"
        except ImportError:
            status_text += "<i>psutil not installed</i>"
            
        await message.reply_text(status_text)
        
    except Exception as e:
        await message.reply(f"Error getting status: {str(e)}")

@bot.on_message(filters.command("tasks") & filters.user(Var.ADMINS))
@new_task
async def tasks_cmd(client, message: Message):
    try:
        mode = await db.get_mode()
        active_tasks = ani_cache.get('ongoing', set())
        completed_tasks = ani_cache.get('completed', set())
        
        if not active_tasks and not completed_tasks:
            return await message.reply("<blockquote><b>No active or completed tasks.</b></blockquote>")
        
        status_text = f"<blockquote><b>Task Status ({mode.capitalize()} Mode)</b></blockquote>\n\n"
        
        if active_tasks:
            status_text += "<b>Active Tasks:</b>\n"
            for task_id in active_tasks:
                status_text += f"<blockquote>• <code>{task_id}</code></blockquote>\n"
        
        if completed_tasks:
            status_text += "\n<blockquote><b>Completed Tasks:</b></blockquote>\n"
            for task_id in completed_tasks:
                status_text += f"• <code>{task_id}</code>\n"
                
        await message.reply_text(status_text)
        
    except Exception as e:
        await message.reply(f"Error getting tasks: {str(e)}")

@bot.on_message(filters.command("cleartasks") & filters.user(Var.ADMINS))
@new_task
async def clear_tasks_cmd(client, message: Message):
    try:
        args = message.text.split()
        if len(args) > 1 and args[1] in ['active', 'completed', 'all']:
            task_type = args[1]
        else:
            task_type = 'all'
            
        if task_type in ['active', 'all']:
            ani_cache['ongoing'] = set()
        if task_type in ['completed', 'all']:
            ani_cache['completed'] = set()
            
        await message.reply(f"<blockquote><b>Cleared {task_type} tasks.</b></blockquote>")
        
    except Exception as e:
        await message.reply(f"Error clearing tasks: {str(e)}")

@bot.on_message(filters.command("help") & filters.user(Var.ADMINS))
@new_task
@rate_limit(2)
async def help_cmd(client, message: Message):
    help_text = """
<b><blockquote>Available Commands</blockquote>

<blockquote>Core Commands:
• /start - Start the bot
• /help - Show this help message
• /status - Check bot status
• /settings - Bot settings panel
• /setstartpic - Set start picture
• /setschedule - Set auto-fetch schedule
• /stats - Show bot statistics 
• /broadcast - Broadcast message to all users
• /ping - Check bot response time</blockquote>

<blockquote>Manga Management:
• /setmanga - Map manga to channel
• /delmanga - Remove manga mapping
• /delallmanga - Remove all manga mapping
• /listmangas - List manga channels
• /setmangabanner - Set manga banner
• /viewmangabanner - View manga banner
• /delmangabanner - Remove manga banner
• /delallmangabanner - Remove all manga banner
• /listmangabanners - List all manga banners</blockquote>

<blockquote>Anime Management:
• /addanime - Map anime to channel
• /delanime - Remove anime mapping
• /delallanimes - Remove all anime mapping
• /listanimes - List anime channels
• /setbanner - Set anime banner
• /viewbanner - View anime banner
• /delbanner - Remove anime banner
• /delallbanners - Remove all anime banner
• /listbanners - List anime banners</blockquote>

<blockquote>Channel Management:
• /addfsub - Add force sub channel
• /delfsub - Remove force sub channel
• /listfsubs - List force sub channels</blockquote>

<blockquote>Admin Management:
• /addadmin - Add new admin
• /deladmin - Delete any admin
• /listadmins - List all admins</blockquote>

<blockquote>Task Management:
• /addtask - Add new anime/manga task
• /addbatch - Add batch task 
• /tasks - List active tasks
• /cleartasks - Clear task lists
• /pause - Pause auto-fetching
• /resume - Resume auto-fetching
• /addlink - Add RSS link for Anime and Manga
• /listlinks - List all RSS links
• /dellink - Remove RSS link for Anime and Manga</blockquote>

<blockquote>Content Settings:
• /setthumb - Set global thumbnail
• /delthumb - Remove global thumbnail
• /viewthumb - View global thumbnail
• /setsticker - Set completion sticker
• /delsticker - Remove sticker
• /viewsticker - View completion sticker
• /setdeltimer - Set auto-delete timer
• /setdel - Toggle auto-delete feature
• /setffmpeg - Set FFMPEG config for specific anime
• /delffmpeg - Remove FFMPEG config
• /delallffmpeg - Remove all FFMPEG config
• /listffmpeg - List all FFMPEG configs</blockquote>

<blockquote>System Commands:
• /shell - Execute shell command
• /restart - Restart the bot
• /log - Get bot logs
• /cleanup - Cleanup bot directories
• /api - Change API source</b></blockquote>
"""
    await message.reply(help_text)

@bot.on_message(filters.command("cleanup") & filters.user(Var.ADMINS))
@new_task
@rate_limit(30)
async def cleanup_cmd(client, message: Message):
    try:
        status_msg = await message.reply("<blockquote><b>Starting cleanup...</b></blockquote>")

        cleanup_dirs = [
            "./downloads",
            "./downloads/manga",
            "./encode",
            "./thumbs",
            "./torrents"
        ]
        
        total_files = 0
        total_size = 0
        
        for directory in cleanup_dirs:
            if not os.path.exists(directory):
                continue
                
            await status_msg.edit_text(f"<blockquote><b>Cleaning {directory}...</b></blockquote>")
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        size = os.path.getsize(file_path)
                        os.remove(file_path)
                        total_files += 1
                        total_size += size
                    except Exception as e:
                        await rep.report(f"Failed to delete {file}: {e}", "warning")
        
        if total_size < 1024:
            size_str = f"{total_size} B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size/1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:
            size_str = f"{total_size/(1024*1024):.1f} MB"
        else:
            size_str = f"{total_size/(1024*1024*1024):.1f} GB"
            
        await status_msg.edit_text(
            f"<blockquote><b>Cleanup completed!</b>\n\n"
            f"<b>Files removed:</b> {total_files}\n"
            f"<b>Space freed:</b> {size_str}</blockquote>"
        )
        
    except Exception as e:
        await message.reply(f"<b>Cleanup failed:</b> {str(e)}")
        await rep.report(f"Cleanup error: {str(e)}", "error")

@bot.on_message(filters.command("restart") & filters.user(Var.ADMINS))
@new_task
@rate_limit(15)
async def restart_cmd(client, message: Message):
    try:
        msg = await message.reply("<blockquote><b>Restarting bot...</b></blockquote>")

        async with aiopen(".restart_msg", "w") as f:
            await f.write(f"{msg.chat.id}\n{msg.id}")

        await cleanup_cmd(client, message)

        os.execl(sys.executable, sys.executable, "-m", "bot")
        
    except Exception as e:
        await message.reply(f"<b>Restart failed:</b> {str(e)}")
        await rep.report(f"Restart error: {str(e)}", "error")

@bot.on_message(filters.command(["stats", "statistics"]) & filters.user(Var.ADMINS))
@new_task
@rate_limit(3)
async def stats_cmd(client, message: Message):
    try:
        status_msg = await message.reply("<b>Fetching statistics...</b>")

        total_animes = len(await db.get_all_anime_channels())
        total_fsubs = len(await db.list_fsubs())
        mode = await db.get_mode()
        active_tasks = len(ani_cache.get('ongoing', set()))
        completed_tasks = len(ani_cache.get('completed', set()))
        users_count = await db.get_users_count() if hasattr(db, 'get_users_count') else 0

        import psutil
        process = psutil.Process()

        cpu_usage = process.cpu_percent(interval=0.5)
        ram_usage = process.memory_info().rss / 1024 / 1024

        uptime_str = get_readable_time(
            (datetime.now() - bot.start_time_helper.start_time).total_seconds()
        )
        
        stats = f"""
<b><blockquote>Bot Statistics</blockquote>

<blockquote>System:
• CPU Usage: {cpu_usage:.1f}%
• RAM Usage: {ram_usage:.1f} MB
• Uptime: {uptime_str}</blockquote>

<blockquote>Bot Status:
• Mode: {mode.capitalize()}
• Auto-Fetch: {'Paused' if ani_cache.get('global_pause') else 'Running'}
• Active Tasks: {active_tasks}
• Completed Tasks: {completed_tasks}
• Users: {users_count}</blockquote>

<blockquote>Database:
• Anime Channels: {total_animes}
• Force Sub Channels: {total_fsubs}
• Response Time: {await get_db_response_time()} ms</blockquote>

<blockquote>API:
• Source: {(await db.get_api_source()).capitalize()}
• Bot Ping: {await get_ping(bot)} ms</b></blockquote>
"""
        await status_msg.edit_text(stats)
        
    except Exception as e:
        await status_msg.edit_text(f"<b>✘ Error fetching stats:</b> {str(e)}")
        await rep.report(f"Stats error: {str(e)}", "error")
