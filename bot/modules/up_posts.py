#──────────────────────
#────────ᴊᴇғғʏ ᴅᴇᴠ─────────
#──────────────────────

from json import loads as jloads
from os import path as ospath, execl
from sys import executable
from bot import bot
from aiohttp import ClientSession
from bot import Var, bot, ffQueue
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler
from pyrogram import filters
from bot.core.text_utils import TextEditor
from bot.core.reporter import rep
from bot.core.func_utils import decode, is_fsubbed, get_fsubs, editMessage, sendMessage, new_task, convertTime, getfeed
from asyncio import sleep as asleep, gather
from pyrogram.filters import command, private, user
from pyrogram import filters
import time
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.types import Message
from pyrogram.types import Message
import subprocess
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified
from bot.core.database import db
from bot import bot, bot_loop, Var, ani_cache
import datetime
import asyncio
from pyrogram.enums import ParseMode

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
    start = time.time()
    await db.command("ping")
    end = time.time()
    return round((end - start) * 1000, 2)

async def get_ping(bot: bot) -> float:
    start = time.time()
    await bot.get_me()
    end = time.time()
    return round((end - start) * 1000, 2)  

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

@bot.on_message(filters.command("ongoing"))
@new_task
async def ongoing_animes(client, message):
    if not getattr(Var, "SEND_SCHEDULE", True):
        await message.reply_text("<blockquote><b>Ongoing schedule feature is disabled.</blockquote></b>")
        return
    try:
        async with ClientSession() as ses:
            res = await ses.get("https://subsplease.org/api/?f=schedule&h=true&tz=Asia/Kolkata")
            if res.status != 200:
                await message.reply_text("<blockquote><b>Failed to fetch schedule from SubsPlease.</blockquote></b>")
                return
            data = await res.text()
            aniContent = jloads(data).get("schedule", [])
        if not aniContent:
            await message.reply_text("<blockquote><b>No anime schedule found for today.</blockquote></b>")
            return
        text = "<blockquote><b>Today's Anime Releases Schedule [IST]</b></blockquote>\n\n"
        for i in aniContent:
            aname = TextEditor(i["title"])
            await aname.load_anilist()
            title = aname.adata.get('title', {}).get('english') or i['title']
            text += (
                f'<blockquote> <a href="https://subsplease.org/shows/{i["page"]}">'
                f'{title}</a>\n    • <b>Time</b> : {i["time"]} hrs</blockquote>'
            )
        await message.reply_text(text)
    except Exception as err:
        await message.reply_text(f"Error: {str(err)}")

async def update_shdr(name, link):
    if TD_SCHR is not None:
        TD_lines = TD_SCHR.text.split('\n')
        for i, line in enumerate(TD_lines):
            if line.startswith(f"📌 {name}"):
                TD_lines[i+2] = f"    • <b>Status :</b> ✅ __Uploaded__\n    • <b>Link :</b> {link}"
        await TD_SCHR.edit("\n".join(TD_lines))



async def upcoming_animes():
    if Var.SEND_SCHEDULE:
        try:
            async with ClientSession() as ses:
                res = await ses.get("https://subsplease.org/api/?f=schedule&h=true&tz=Asia/Kolkata")
                aniContent = jloads(await res.text())["schedule"]

            text = "────────────────────\n<b>〄 Tᴏᴅᴀʏ's ᴀɴɪᴍᴇ ʀᴇʟᴇᴀsᴇs sᴄʜᴇᴅᴜʟᴇ [ɪsᴛ]</b>\n────────────────────\n"
            for i in aniContent:
                aname = TextEditor(i["title"])
                await aname.load_anilist()
                text += f'''›› <a href="https://subsplease.org/shows/{i['page']}">{aname.adata.get('title', {}).get('english') or i['title']}</a>\n• <b>Tɪᴍᴇ</b> : {i["time"]} ʜʀs\n──\n'''

            # 1. Send image + text together
            TD_SCHR = await bot.send_photo(
                Var.MAIN_CHANNEL,
                photo="https://telegra.ph/HgBotz-09-14-4",   # Replace with your image
                caption=text,
                parse_mode=ParseMode.HTML
            )

            # Pin & auto-delete pin message
            await (await TD_SCHR.pin()).delete()

            # 2. Delay before sticker
            await asyncio.sleep(2)

            # 3. Send sticker
            await bot.send_sticker(
                Var.MAIN_CHANNEL,
                sticker="CAACAgUAAxkBAAEPXv5oxogTeaN34oLKszLqCTudHhv73wACahcAAoNhMFZ3tCnYZNM56TYE"  # Replace with your sticker file_id
            )

        except Exception as err:
            await rep.report(str(err), "error")

    if not ffQueue.empty():
        await ffQueue.join()
    await rep.report("Auto Restarting..!!", "info")
    execl(executable, executable, "-m", "bot")


async def update_shdr(name, link):
    if TD_SCHR is not None:
        TD_lines = TD_SCHR.text.split('\n')
        for i, line in enumerate(TD_lines):
            if line.startswith(f"📌 {name}"):
                TD_lines[i+2] = f"    • <b>Status :</b> ✅ __Uploaded__\n    • <b>Link :</b> {link}"
        await TD_SCHR.edit("\n".join(TD_lines))
