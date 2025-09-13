from asyncio import gather, create_task, sleep as asleep, Event
from asyncio.subprocess import PIPE
from os import path as ospath, system, remove
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove
from traceback import format_exc
from base64 import urlsafe_b64encode
from time import time
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import UserAlreadyParticipant, ChannelInvalid, PeerIdInvalid
import re
from bot import bot, bot_loop, Var, ani_cache, ffQueue, ffLock, ff_queued
from .tordownload import TorDownloader
from .database import db
from .func_utils import getfeed, encode, editMessage, sendMessage, convertBytes
from .text_utils import TextEditor, MangaLister
from .ffencoder import FFEncoder
from .tguploader import TgUploader
from .text_utils import get_manga_filename, parse_manga_title, get_manga_caption
from .reporter import rep
import datetime
import asyncio
from pyrogram.errors import FloodWait
import requests
import os
import feedparser
from fpdf import FPDF
import httpx
import subprocess
from PIL import Image
import shutil
import time
import hashlib

MAX_ABOUT_LEN = 255

btn_formatter = {
    'HDRi':'Hᴅʀɪᴘ',
    '1080':'1080ᴘ', 
    '720':'720ᴘ',
    '480':'480ᴘ',
    '360':'360ᴘ',
    '240':'240ᴘ',
    '144':'144ᴘ'
}

#RAW_BTN = "𝗥𝗔𝗪"
RAW_BTN = "Hᴅʀɪᴘ"
MANGA_BTN = "Rᴇᴀᴅ ɴᴏᴡ"
MANGA_READ_BUTTON = "Rᴇᴀᴅ ɴᴏᴡ"
MANGA_CHNL_BUTTON = "Jᴏɪɴ ᴄʜᴀɴɴᴇʟ"
DOWNLOAD_BTN = "Dᴏᴡɴʟᴏᴀᴅ"
DOWNLOAD_ANIME_BTN = "Dᴏᴡɴʟᴏᴀᴅ"
DOWNLAOD_CHNL_BTN = "Jᴏɪɴ ᴄʜᴀɴɴᴇʟ "

import hashlib
import time
import os
import shutil

def generate_unique_dir(name, torrent_url):
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
    safe_name = safe_name[:40]
    url_hash = hashlib.md5(torrent_url.encode()).hexdigest()[:8]
    timestamp = int(time.time())
    return f"./downloads/{safe_name}_{url_hash}_{timestamp}"

def find_video_files(folder):
    video_exts = ('.mp4', '.mkv', '.avi', '.webm', '.wmv')
    files = []
    for root, dirs, filenames in os.walk(folder):
        for f in filenames:
            if f.lower().endswith(video_exts):
                files.append(os.path.join(root, f))
    return sorted(files)

def patch_caption_episode(caption, episode_count):
    try:
        episode_count = int(episode_count)
    except Exception:
        episode_count = 1
    return re.sub(
        r"(❍\s*𝗘𝗽𝗶𝘀𝗼𝗱𝗲:\s*<i>)[^<]+(</i>)",
        f"\\1{episode_count}\\2",
        caption
    )

async def detect_audio_type(video_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=language", "-of", "csv=p=0", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        audio_langs = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        unique_langs = set(audio_langs)
        if len(unique_langs) > 2:
            return "Multi"
        elif len(unique_langs) == 2:
            return "Dual"
        elif len(unique_langs) == 1:
            return "Dub" if "eng" in unique_langs else "Sub"
        else:
            return "Sub"
    except Exception as e:
        print(f"Audio detection failed: {e}")
        return "Sub"

async def process_batch_anime(anime_name, torrent_url, audio):
    import re
    import time
    import os
    import shutil
    from os import path as ospath
    import asyncio
    
    cleaned_name = clean_anime_title(anime_name)
    safe_title = re.sub(r'[\\/*?:"<>|\'\n\r\t]', '_', cleaned_name)
    unique_dir = f"./downloads/{safe_title}"
    os.makedirs(unique_dir, exist_ok=True)

    aniInfo = TextEditor(cleaned_name)
    await aniInfo.load_info()
    all_banners = await db.list_anime_banners()
    banner_url = None
    for banner_key, url in all_banners:
        if banner_key.lower() in anime_name.lower():
            banner_url = url
            break
    if banner_url:
        poster_url = banner_url
    elif hasattr(Var, 'ANIME') and Var.ANIME in anime_name:
        poster_url = Var.CUSTOM_BANNER
    else:
        poster_url = aniInfo.adata.get("poster_url", "https://envs.sh/E7p.png?isziC=1")

    channel_to_use = await get_or_create_anime_channel(anime_name, aniInfo)

    channel_valid = False
    for attempt in range(3):
        if await validate_channel_id(channel_to_use):
            channel_valid = True
            break
        await asyncio.sleep(2)
    if not channel_valid:
        await rep.report(f"Final channel {channel_to_use} is invalid after retries, using main channel", "error")
        channel_to_use = Var.MAIN_CHANNEL

    dl_path = await TorDownloader(unique_dir).download(torrent_url)
    if not dl_path or not ospath.exists(dl_path):
        await rep.report(f"Batch download failed for {anime_name}", "error")
        return

    batch_dir = dl_path if ospath.isdir(dl_path) else unique_dir
    video_files = find_video_files(batch_dir)
    episode_count = len(video_files)
    if not video_files:
        await rep.report(f"No video files found in batch for {anime_name}", "error")
        return

    aniInfo.pdata["audio_type"] = audio
    caption = await aniInfo.get_caption()

    caption = re.sub(
        r"(❍\s*𝗘𝗽𝗶𝘀𝗼𝗱𝗲:\s*<i>)[^<]+(</i>)",
        lambda m: f"{m.group(1)}1-{episode_count}{m.group(2)}",
        caption
    )

    try:
        post_msg = await bot.send_photo(
            channel_to_use,
            photo=poster_url,
            caption=caption
        )
    except Exception as e:
        await rep.report(f"Failed to send batch poster: {e}", "error")
        post_msg = None

    await mirror_to_main_channel(
        post_msg=post_msg,
        photo_url=poster_url,
        caption=caption,
        channel_to_use=channel_to_use
    )

    await asleep(1.5)
    await rep.report(f"Using channel: {channel_to_use} for anime: {cleaned_name}", "info")
    await asleep(1.5)

    stat_msg = await bot.send_message(
        chat_id=channel_to_use,
        text=f"<blockquote>‣ <b>Anime Name :</b> <b><i>{anime_name}</i></b></blockquote>\n\n<pre><i>Downloading...</i></pre>"
    )

    await asleep(Var.STICKER_INTERVAL)
    await send_sticker_to_channel(channel_to_use, Var.STICKER_ID)

    batch_buttons = []
    for qual in Var.QUALS:
        qual_msg_ids = []
        os.makedirs("encode", exist_ok=True)
        for idx, vfile in enumerate(video_files, 1):
            ep_num = str(idx).zfill(2)
            aniInfo.pdata["episode_number"] = ep_num
            ep_upname = await aniInfo.get_upname(qual)
            out_path = f"encode/{ep_upname}"

            encoded_path = await FFEncoder(stat_msg, vfile, ep_upname, qual).start_encode()
            if not encoded_path or not ospath.exists(encoded_path):
                await rep.report(f"Encoding failed for {vfile} ({qual}p)", "error")
                continue

            msg = await TgUploader(stat_msg).upload(encoded_path, qual)
            if msg:
                qual_msg_ids.append(msg.id)
            try:
                if ospath.exists(encoded_path):
                    os.remove(encoded_path)
            except Exception:
                pass

        if qual_msg_ids:
            first_id = min(qual_msg_ids)
            last_id = max(qual_msg_ids)
            batch_string = f"get-{first_id * abs(Var.FILE_STORE)}-{last_id * abs(Var.FILE_STORE)}"
            batch_link = f"https://t.me/{Var.BOT_USERNAME}?start={await encode(batch_string)}"
            btn_text = f"{btn_formatter.get(qual, qual+'p')}"
            batch_buttons.append(InlineKeyboardButton(btn_text, url=batch_link))
            if post_msg and batch_buttons:
                btns = [batch_buttons[i:i+2] for i in range(0, len(batch_buttons), 2)]
                await editMessage(post_msg, caption, InlineKeyboardMarkup(btns))

    await stat_msg.delete()
    shutil.rmtree(batch_dir, ignore_errors=True)
    await rep.report(f"Batch processing done and cleaned for {anime_name}", "info")

async def fetch_hentai():
    await rep.report("Fetching Hentai Started !!!", "info")
    processed_urls = set()
    while True:
        await asleep(15)
        if len(processed_urls) > 1000:
            processed_urls.clear()
        mode = await db.get_mode()
        if ani_cache.get('global_pause') and not ani_cache.get('manual_task'):
            continue
        if mode == "hentai":
            try:
                feed = feedparser.parse(getattr(Var, "HENTAI_RSS", "https://sukebei.nyaa.si/?page=rss&c=1_1&f=0"))
                for entry in feed.entries:
                    if entry.link in processed_urls:
                        continue
                    if "[Batch]" in entry.title:
                        continue
                    processed_urls.add(entry.link)
                    await process_hentai(entry.title, entry.link)
                    break
                    await asleep(2)
            except Exception as e:
                await rep.report(f"Hentai RSS fetch error: {e}", "error")
        await asleep(10)

async def process_hentai(title, torrent_url, force=False):
    try:
        aniInfo = TextEditor(title)
        await aniInfo.load_info()
        hentai_id = torrent_url
        ep_no = "1"

        ani_data = await db.getAnime(hentai_id)
        if ani_data and ani_data.get(ep_no, {}).get("failed"):
            await rep.report(f"[DEBUG] Skipping previously failed hentai: {title}", "info")
            return

        if not force and await db.getAnime(hentai_id):
            await rep.report(f"[DEBUG] Skipping duplicate hentai: {title}", "info")
            return

        cleaned_name = clean_anime_title(title)
        channel_to_use = await get_or_create_anime_channel(title, aniInfo)

        all_banners = await db.list_anime_banners()
        banner_url = None
        for banner_key, url in all_banners:
            if banner_key.lower() in title.lower():
                banner_url = url
                break
        photo_url = banner_url or "https://envs.sh/E7p.png?isziC=1"

        if not aniInfo.adata or not aniInfo.adata.get("title"):
            aniInfo.adata = {
                "id": title,
                "title": {"romaji": cleaned_name, "english": cleaned_name, "native": cleaned_name},
                "format": "Hentai",
                "genres": ["Hentai"],
                "averageScore": None,
                "status": None,
                "episodes": None,
                "description": None,
                "siteUrl": None,
                "startDate": None,
                "endDate": None,
                "duration": None,
                "poster_url": photo_url
            }
        async def fallback_caption():
            return (
            f"<blockquote><b>✦<i> {title} </i>✦</b></blockquote>\n"
            f"<b>╔━━━━━━━━━━━━━━━━━━━━━╗</b>\n"
            f"<blockquote><b>⌲ 𝗧𝘆𝗽𝗲: <i>Hentai</i></b>\n"
            f"<b>❍ 𝗘𝗽𝗶𝘀𝗼𝗱𝗲: <i>N/A</i></b></blockquote>\n"
            f"<blockquote><b>〄 𝗔𝘂𝗱𝗶𝗼: <i>Japanese</i></b>\n"
            f"<b>❐ 𝗦𝘁𝗮𝘁𝘂𝘀: <i>N/A</i></b></blockquote>\n"
            f"<blockquote><b>◎ 𝗧𝗼𝘁𝗮𝗹 𝗘𝗽𝗶𝘀𝗼𝗱𝗲𝘀: <i>N/A</i></b>\n"
            f"<b>♡ 𝗚𝗲𝗻𝗿𝗲𝘀: <i>Hentai</i></blockquote></b>\n"
            f"<b>╚━━━━━━━━━━━━━━━━━━━━━╝</b>"
        )
        aniInfo.get_caption = fallback_caption

        channel_valid = False
        for attempt in range(3):
            if await validate_channel_id(channel_to_use):
                channel_valid = True
                break
            await asyncio.sleep(2)

        if not channel_valid:
            await rep.report(f"Final channel {channel_to_use} is invalid after retries, using main channel", "error")
            channel_to_use = Var.MAIN_CHANNEL

        try:
            post_msg = await bot.send_photo(
                channel_to_use,
                photo=photo_url,
                caption=await aniInfo.get_caption()
            )
        except Exception as e:
            await rep.report(f"Failed to send initial hentai post: {e}", "error")
            return

        await mirror_to_main_channel(
            post_msg=post_msg,
            photo_url=photo_url,
            caption=post_msg.caption.html if post_msg.caption else "",
            channel_to_use=channel_to_use
        )

        await asleep(1.5)
        await rep.report(f"Using channel: {channel_to_use} for hentai: {cleaned_name}", "info")
        await asleep(1.5)

        stat_msg = await bot.send_message(
            chat_id=channel_to_use, 
            text=f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Downloading...</i></pre>"
        )

        await asleep(Var.STICKER_INTERVAL)
        await send_sticker_to_channel(channel_to_use, Var.STICKER_ID)

        dl_path = await download_torrent(torrent_url)
        if not dl_path or not ospath.exists(dl_path):
            await rep.report(f"File Download Incomplete, Try Again", "error")
            await db.saveAnime(hentai_id, ep_no, "status", "failed")
            await stat_msg.delete()
            return

        video_files = []
        if ospath.isdir(dl_path):
            for root, dirs, files in os.walk(dl_path):
                for file in files:
                    if file.lower().endswith(('.mp4', '.mkv', '.avi', '.webm', '.wmv')):
                        file_path = os.path.join(root, file)
                        if ospath.getsize(file_path) <= 1.2 * 1024 * 1024 * 1024:
                            video_files.append(file_path)
                        else:
                            await db.saveAnime(hentai_id, ep_no, "status", "failed")
                            await rep.report(f"File too large (>1.2GB): {file_path}", "error")
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
        else:
            if dl_path.lower().endswith(('.mp4', '.mkv', '.avi', '.webm', '.wmv')):
                if ospath.getsize(dl_path) <= 1.2 * 1024 * 1024 * 1024:
                    video_files.append(dl_path)
                else:
                    await db.saveAnime(hentai_id, ep_no, "status", "failed")
                    await rep.report(f"File too large (>1.2GB): {dl_path}", "error")
                    try:
                        os.remove(dl_path)
                    except Exception:
                        pass

        if not video_files:
            await rep.report(f"No video files under 1.2GB found in {title}", "info")
            await db.saveAnime(hentai_id, ep_no, "status", "failed")
            await stat_msg.delete()
            if dl_path and ospath.exists(dl_path):
                try:
                    os.remove(dl_path)
                except Exception:
                    pass
            return

        file_store_links = {}
        btns = []
        post_id = post_msg.id

        upload_mode = await db.get_upload_mode()
        encoding_enabled = await db.get_encoding()
        rename_enabled = getattr(Var, 'LOW_END_RENAME', False)


        ffEvent = Event()
        ff_queued[post_id] = ffEvent
        try:
            if ffLock.locked():
                await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Queued to Encode...</i></pre>")
                await rep.report("Added Task to Queue...", "info")
            await ffQueue.put(post_id)
            await ffEvent.wait()
            await ffLock.acquire()
            try:
                for vfile in video_files:
                    if upload_mode == "high_end":
                        if encoding_enabled:
                            qual_btns = []
                            for qual in Var.QUALS:
                                filename = safe_filename(f"{cleaned_name}_{qual}p{ospath.splitext(vfile)[1]}")
                                out_path = f"encode/{filename}"
                                await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Encoding {qual}p...</i></pre>")
                                ffmpeg_var = getattr(Var, f"FFMPEG_{qual}", None)
                                if not ffmpeg_var:
                                    await rep.report(f"No FFMPEG config for {qual}p", "error")
                                    continue
                                ffmpeg_cmd = ffmpeg_var.format(
                                    vfile, cleaned_name, cleaned_name, cleaned_name, cleaned_name, out_path
                                )
                                proc = await asyncio.create_subprocess_shell(ffmpeg_cmd)
                                await proc.communicate()
                                if not ospath.exists(out_path):
                                    await rep.report(f"Failed to encode {qual}p with FFMPEG_{qual}", "error")
                                    await db.saveAnime(hentai_id, ep_no, "status", "failed")
                                    continue
                                await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Uploading {qual}p...</i></pre>")
                                uploader = TgUploader(stat_msg)
                                try:
                                    msg = await uploader.upload(out_path, qual)
                                except Exception as e:
                                    await rep.report(f"Upload failed: {e}", "error")
                                    await db.saveAnime(hentai_id, ep_no, "status", "failed")
                                    try:
                                        if ospath.exists(out_path):
                                            os.remove(out_path)
                                    except Exception:
                                        pass
                                    continue
                                if msg:
                                    file_store_links[qual] = msg.id
                                    await db.saveAnime(hentai_id, ep_no, qual, msg.id)
                                    encoded = await encode('get-' + str(msg.id * abs(Var.FILE_STORE)))
                                    qual_btns.append(InlineKeyboardButton(f"{btn_formatter.get(qual, qual+'p')}", url=f"https://t.me/{Var.BOT_USERNAME}?start={encoded}"))
                                    try:
                                        if ospath.exists(out_path):
                                            os.remove(out_path)
                                    except Exception:
                                        pass
                                else:
                                    await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Failed to upload {qual}p</i></pre>")
                                    await db.saveAnime(hentai_id, ep_no, "status", "failed")
                            if qual_btns:
                                btns.extend([qual_btns[i:i+2] for i in range(0, len(qual_btns), 2)])
                        else:
                            await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Uploading...</i></pre>")
                            uploader = TgUploader(stat_msg)
                            try:
                                msg = await uploader.upload(vfile, None)
                            except Exception as e:
                                await rep.report(f"Upload failed: {e}", "error")
                                await db.saveAnime(hentai_id, ep_no, "status", "failed")
                                continue
                            if msg:
                                file_store_links["raw"] = msg.id
                                await db.saveAnime(hentai_id, ep_no, "raw", msg.id)
                                encoded = await encode('get-' + str(msg.id * abs(Var.FILE_STORE)))
                                btns.append([InlineKeyboardButton(f"{RAW_BTN}", url=f"https://t.me/{Var.BOT_USERNAME}?start={encoded}")])
                            else:
                                await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Failed to upload</i></pre>")
                                await db.saveAnime(hentai_id, ep_no, "status", "failed")
                    else:
                        if rename_enabled:
                            filename = safe_filename(f"{cleaned_name}{ospath.splitext(vfile)[1]}")
                            out_path = f"encode/{filename}"
                            await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Renaming...</i></pre>")
                            ffmpeg_cmd = Var.HENTAI_FFMPEG.format(
                                vfile, cleaned_name, cleaned_name, cleaned_name, cleaned_name, out_path
                            )
                            proc = await asyncio.create_subprocess_shell(ffmpeg_cmd)
                            await proc.communicate()
                            if not ospath.exists(out_path):
                                await rep.report(f"Failed to rename/process with hentai-ffmpeg", "error")
                                await db.saveAnime(hentai_id, ep_no, "status", "failed")
                                continue
                            upload_path = out_path
                        else:
                            upload_path = vfile
                        await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Uploading...</i></pre>")
                        uploader = TgUploader(stat_msg)
                        try:
                            msg = await uploader.upload(upload_path, None)
                        except Exception as e:
                            await rep.report(f"Upload failed: {e}", "error")
                            await db.saveAnime(hentai_id, ep_no, "status", "failed")
                            continue
                        if msg:
                            file_store_links["raw"] = msg.id
                            await db.saveAnime(hentai_id, ep_no, "raw", msg.id)
                            encoded = await encode('get-' + str(msg.id * abs(Var.FILE_STORE)))
                            btns.append([InlineKeyboardButton(f"{RAW_BTN}", url=f"https://t.me/{Var.BOT_USERNAME}?start={encoded}")])
                        else:
                            await editMessage(stat_msg, f"<blockquote>‣ <b>Hentai Name :</b> <b><i>{title}</i></b></blockquote>\n\n<pre><i>Failed to upload</i></pre>")
                            await db.saveAnime(hentai_id, ep_no, "status", "failed")
            finally:
                ffLock.release()
        except Exception as e:
            if ffLock.locked():
                ffLock.release()
            await rep.report(f"process_hentai error: {e}", "error")
            return

        if btns and post_msg:
            flat_btns = []
            for b in btns:
                if isinstance(b, list):
                    flat_btns.extend(b)
                else:
                    flat_btns.append(b)
            grouped_btns = [flat_btns[i:i+2] for i in range(0, len(flat_btns), 2)]
            await editMessage(post_msg, post_msg.caption.html if post_msg.caption else "", InlineKeyboardMarkup(grouped_btns))

        await stat_msg.delete()
        await rep.report(f"Successfully uploaded hentai: {title}", "info")
        await db.saveAnime(hentai_id, ep_no, "completed", True)

    except Exception as e:
        await rep.report(f"Hentai processing error: {str(e)}", "error")

async def hentai_ffmpeg_rename(vfile):
    base, ext = ospath.splitext(vfile)
    out_path = f"{base}_hentai{ext}"
    ffmpeg_cmd = Var.HENTAI_FFMPEG.format(vfile, out_path)
    proc = await asyncio.create_subprocess_shell(ffmpeg_cmd)
    await proc.communicate()
    return out_path if ospath.exists(out_path) else vfile

def download_image(url, filename):
    try:
        if not url:
            print("No URL provided for image download.")
            return None
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            with open(filename, "wb") as f:
                f.write(r.content)
            print(f"Image downloaded: {filename}")
            return filename
        else:
            print(f"Failed to download image. Status code: {r.status_code}")
    except Exception as e:
        print(f"Exception during image download: {e}")
    return None

async def get_anilist_titles_from_cleaned(name: str):
    cleaned_name = extract_base_anime_name(name)
    query = '''
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title {
          romaji
          english
          native
        }
        synonyms
      }
    }
    '''
    variables = {"search": cleaned_name}
    url = "https://graphql.anilist.co"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"query": query, "variables": variables})
            resp.raise_for_status()
            data = resp.json()
            
            media = data.get("data", {}).get("Media", None)
            if not media:
                return []

            titles = set()
            for key in ["romaji", "english", "native"]:
                val = media.get("title", {}).get(key)
                if val:
                    titles.add(val)
            
            for syn in media.get("synonyms", []):
                titles.add(syn)

            return [normalize_anime_name_for_search(t) for t in titles if t]
    
    except Exception as e:
        print(f"Error in get_anilist_titles_from_cleaned: {e}")
        return []

def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|\'\n\r\t]', '_', name)

def clean_anime_title(title: str) -> str:
    cleaned_title = re.sub(r'^\[.*?\]\s*', '', title)
    cleaned_title = re.sub(r'\s*-\s*\d+\s*\(.*?\)', '', cleaned_title)
    cleaned_title = re.sub(r'\[.*?\]', '', cleaned_title)
    cleaned_title = cleaned_title.replace('.mkv', '').strip()
    return cleaned_title

def extract_base_anime_name(name: str) -> str:
    cleaned = name
    cleaned = re.sub(r'^\[[^\]]+\]\s*', '', cleaned)
    cleaned = re.sub(r'\s*-\s*\d+\s*(\([^\)]*\))?', '', cleaned)
    cleaned = re.sub(r'\s*S\d{1,2}E\d{1,3}', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*Season\s*\d+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*Ep(isode)?\s*\d+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(HEVC|x265|x264|AAC|WEB[- ]?DL|WEB[- ]?Rip|BluRay|HDTV|MultiSub|Multi-Subs|CR|RAW|SUB|Dub|Dual[- ]?Audio|Dual[- ]?Subs|VOSTFR|AMZN|NF|BILI|WeTV|iQ|AVC|EAC3|DDP2\.0|DDP5\.1|H\.?264|H\.?265|10bit|8bit|OV|REPACK|weekly|English Audio|VARYG|YURASUKA|Tsundere-Raws|Aniplus|YT|Disney\+|Opus|CA|Hero|Finals Arc|Uncensored|Remastered|A Multi-Language Release|Dual Audio|Dual Subs|Multi-Audio|Multi Subs|Dual|Eng|Jap|EN|JP)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(\d{3,4}p)\b', '', cleaned)
    cleaned = re.sub(r'\.(mkv|mp4|avi|webm|wmv|mov|flv|ts)$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[[A-Fa-f0-9]{6,}\]', '', cleaned)
    cleaned = re.sub(r'\([^)]+\)', '', cleaned)
    cleaned = re.sub(r'\[[^\]]+\]', '', cleaned)
    cleaned = re.sub(r'[._\-:,/]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def normalize_anime_name_for_search(name: str) -> str:
    base_name = extract_base_anime_name(name)
    normalized = re.sub(r'\s+', ' ', base_name.lower().strip())
    return normalized

async def get_all_possible_anime_names(name: str):
    base_name = extract_base_anime_name(name)
    anilist_titles = await get_anilist_titles_from_cleaned(base_name)
    if not anilist_titles:
        return [base_name]
    all_names = set([normalize_anime_name_for_search(base_name)] + anilist_titles)
    return list(all_names)

def is_manga_entry(title: str) -> bool:
    title_lower = title.lower()
    manga_keywords = [
        "ch.", "chapter", "ch ", "vol.", "vol ", "volume",
        " ch:", " chapter:", " vol:", " volume:"
    ]
    return any(keyword in title_lower for keyword in manga_keywords)

async def is_valid_torrent_url(url):
    try:
        if not url or not url.startswith(('http://', 'https://', 'magnet:')):
            return False
        
        if url.startswith('magnet:'):
            return True
        
        if url.endswith('.torrent'):
            return True

        async with httpx.AsyncClient() as client:
            try:
                response = await client.head(url, timeout=10)
                content_type = response.headers.get('content-type', '').lower()
                return 'torrent' in content_type or 'bittorrent' in content_type
            except:
                return False
                
    except Exception:
        return False

async def find_existing_anime_channel(anime_name: str):
    normalized_input = normalize_anime_name_for_search(anime_name)
    all_channels = await db.get_all_anime_channels()

    if normalized_input in all_channels:
        return all_channels[normalized_input]
        
    for stored_name, channel_id in all_channels.items():
        if normalized_input in stored_name or stored_name in normalized_input:
            return channel_id
    return None

async def send_sticker_to_channel(channel, sticker_id):
    if Var.SEND_STICKER and sticker_id:
        try:
            await bot.send_sticker(channel, sticker_id)
        except Exception as e:
            print(f"Failed to send sticker: {e}")

async def validate_channel_id(channel_id):
    if not channel_id:
        return None
        
    try:
        await asleep(1)
        chat_info = await bot.get_chat(channel_id)
        return chat_info
    except (ChannelInvalid, PeerIdInvalid) as e:
        await rep.report(f"Channel validation failed for {channel_id}: {e}", "error")
        return None
    except Exception as e:
        await rep.report(f"Unexpected error validating channel {channel_id}: {e}", "error")
        return None

async def mirror_to_main_channel(post_msg, photo_url, caption, channel_to_use):
    try:
        if channel_to_use == Var.MAIN_CHANNEL:
            return

        chat_info = await validate_channel_id(channel_to_use)
        if not chat_info:
            await rep.report(f"Cannot mirror to invalid channel: {channel_to_use}", "error")
            return

        if chat_info.username:
            post_link = f"https://t.me/{chat_info.username}/{post_msg.id}"
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"{DOWNLOAD_BTN}", url=post_link)
                ]
            ])
        else:
            try:
                invite_link = chat_info.invite_link or await bot.export_chat_invite_link(channel_to_use)
                raw_channel_id = str(chat_info.id).replace("-100", "")
                post_link = f"https://t.me/c/{raw_channel_id}/{post_msg.id}"
                buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"{DOWNLOAD_ANIME_BTN}", url=post_link),
                        InlineKeyboardButton(f"{DOWNLAOD_CHNL_BTN}", url=invite_link)
                    ]
                ])
            except Exception as e:
                await rep.report(f"Failed to get invite link for {channel_to_use}: {e}", "error")
                return

        main_chat_info = await validate_channel_id(Var.MAIN_CHANNEL)
        if not main_chat_info:
            await rep.report(f"Main channel {Var.MAIN_CHANNEL} is invalid", "error")
            return

        await bot.send_photo(
            Var.MAIN_CHANNEL,
            photo=post_msg.photo.file_id if post_msg.photo else photo_url,
            caption=caption,
            reply_markup=buttons
        )

        await asleep(Var.STICKER_INTERVAL)
        await send_sticker_to_channel(Var.MAIN_CHANNEL, Var.STICKER_ID)

    except Exception as e:
        await rep.report(f"Mirror Error: {e}", "error")

async def fetch_manga():
    await rep.report("Fetching Manga Started !!!", "info")
    processed_urls = set()
    manga_queue = []
    last_checked = set()

    while True:
        await asleep(10)
        if len(processed_urls) > 1000:
            processed_urls.clear()
        mode = await db.get_mode()
        if ani_cache.get('global_pause') and not ani_cache.get('manual_task'):
            continue
        if mode == "manga" and ani_cache['fetch_manga']:
            for rss_url in Var.RSS_ITEMS_MANGA:
                try:
                    feed = feedparser.parse(rss_url)
                    for entry in feed.entries:
                        title = entry.title
                        link = entry.link
                        if link in processed_urls or link in last_checked:
                            continue
                        if not is_manga_entry(title):
                            continue
                        if await db.getAnime(link):
                            continue
                        manga_queue.append((title, link))
                        last_checked.add(link)
                except Exception as e:
                    await rep.report(f"Error in fetch_manga: {e}", "error")
            while manga_queue:
                title, url = manga_queue.pop(0)
                try:
                    await process_manga_chapter(title, url)
                    processed_urls.add(url)
                except Exception as e:
                    await rep.report(f"Error processing manga: {e}", "error")
                await asleep(2)

async def get_or_create_manga_channel(name: str, manga_info):
    try:
        manga_name = name.split(":")[0].strip()
        normalized_name = manga_name.lower()
        
        await rep.report(f"Searching for existing manga channel for: {manga_name}", "info")
        await asleep(1.5)
        custom_channel = await db.get_manga_channel(normalized_name)
        if custom_channel:
            await rep.report(f"Found custom manga channel mapping: {custom_channel}", "info")
            return custom_channel

        channel_creation = await db.get_channel_creation()
        if not channel_creation or not Var.USER_SESSION:
            await rep.report("Channel creation disabled or no user session, using main channel", "info")
            return Var.MAIN_CHANNEL

        await rep.report(f"Creating new channel for manga: {manga_name}", "info")
        new_channel = await create_manga_channel(name, manga_info)
        
        if new_channel:
            await db.add_manga_channel_mapping(normalized_name, new_channel)
            await rep.report(f"Successfully created and saved manga channel mapping for {manga_name}", "info")
            return new_channel
        else:
            await rep.report("Failed to create manga channel, using main channel", "error")
            return Var.MAIN_CHANNEL
            
    except Exception as e:
        await rep.report(f"Error in get_or_create_manga_channel: {e}", "error")
        return Var.MAIN_CHANNEL

async def create_manga_channel(name: str, manga_info):
    try:
        if not Var.USER_SESSION:
            await rep.report("User session not available for channel creation", "error")
            return None
            
        from pyrogram import Client
        user_client = Client("user_session", session_string=Var.USER_SESSION, 
                           api_id=Var.API_ID, api_hash=Var.API_HASH)
        
        await user_client.start()

        manga_name = name.split(":")[0].strip()
        channel_name = manga_name
        description = f"Manga Channel | Created by AutoAnime @{Var.BOT_USERNAME}"

        created_chat = await user_client.create_channel(channel_name, description)
        channel_id = created_chat.id

        poster_url = (manga_info.get("coverImage", {}).get("large") or 
                     manga_info.get("coverImage", {}).get("medium") or 
                     "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSvJiVgwS6MM3Gv0riNlqmCsxqHu5Y9_ScrFQ&s")
        
        if poster_url:
            filename = f"/tmp/{channel_id}_logo.jpg"
            filename = download_image(poster_url, filename)
            if filename:
                try:
                    await user_client.set_chat_photo(channel_id, photo=filename)
                    remove(filename)
                except Exception as e:
                    await rep.report(f"Failed to set manga channel photo: {e}", "warning")

        try:
            from pyrogram.types import ChatPrivileges
            await user_client.promote_chat_member(
                channel_id,
                Var.CREATION_USERNAME,
                privileges=ChatPrivileges(
                    can_post_messages=True,
                    can_edit_messages=True,
                    can_delete_messages=True,
                    can_invite_users=True,
                    can_pin_messages=True,
                    can_manage_chat=True
                )
            )
        except Exception as e:
            await rep.report(f"Failed to add/promote bot in manga channel: {e}", "error")

        await user_client.stop()
        return channel_id
        
    except Exception as e:
        await rep.report(f"Failed to create manga channel: {e}", "error")
        return None

async def process_manga_chapter(title, chapter_url, manual=False):
    try:
        if ani_cache.get('global_pause') and not manual:
            return

        if await db.getAnime(chapter_url):
            await rep.report(f"[DEBUG] Skipping duplicate manga: {title}", "info")
            return

        safe_title = safe_filename(title)
        manga_dir = os.path.join(os.getcwd(), "downloads", "manga")
        os.makedirs(manga_dir, exist_ok=True)

        status_msg = await bot.send_message(
            Var.MAIN_CHANNEL,
            f"<blockquote><b>‣ Manga Name:</b> <i>{title}</i></blockquote>\n\n<pre>Processing...</pre>"
        )

        manga_name = title.split(":")[0].strip()
        try:
            manga_lister = MangaLister(manga_name, datetime.datetime.now().year)
            manga_info = await manga_lister.get_mangadata() or {}
        except Exception as e:
            await rep.report(f"Failed to get manga metadata: {e}", "warning")
            manga_info = {}

        file_store_msg = None
        try:
            await status_msg.edit_text(
                f"<blockquote><b>‣ Manga Name :</b> <i>{title}</i></blockquote>\n\n<pre>Downloading images...</pre>"
            )
            images = await get_mangadex_images(chapter_url)
            if not isinstance(images, list) or not images or not all(isinstance(i, str) and i.strip() for i in images):
                await rep.report(f"Upload failed: No images found or bad image data for {title}", "error")
                await status_msg.edit_text(
                    f"<blockquote><b>‣ Manga Name :</b> <i>{title}</i></blockquote>\n\n<pre>No images found. Skipping.</pre>"
                )
                return

            await status_msg.edit_text(
                f"<blockquote><b>‣ Manga Name :</b> <i>{title}</i></blockquote>\n\n<pre>Creating PDF...</pre>"
            )

            pdf_path = await images_to_pdf(safe_title, images, manga_dir)
            if not pdf_path or not ospath.exists(pdf_path):
                await rep.report(f"PDF creation failed for {title}", "error")
                await status_msg.edit_text(
                    f"<blockquote><b>‣ Manga Name :</b> <i>{title}</i></blockquote>\n\n<pre>PDF creation failed.</pre>"
                )
                return

            await status_msg.edit_text(
                f"<blockquote><b>‣ Manga Name :</b> <i>{title}</i></blockquote>\n\n<pre>Uploading...</pre>"
            )

            file_caption = get_manga_filename(title, Var.BRAND_UNAME)
            if not isinstance(file_caption, str) or not file_caption.strip():
                file_caption = "<b>Manga</b>"
            else:
                file_caption = f"<b>{file_caption}</b>"

            thumb_path = "thumb.jpg" if os.path.exists("thumb.jpg") else None
            if thumb_path is not None and not isinstance(thumb_path, str):
                thumb_path = None

            debug_msg = (
                f"[DEBUG] Manga upload vars: pdf_path={pdf_path!r} (exists={ospath.exists(pdf_path) if isinstance(pdf_path, str) else 'N/A'}), "
                f"file_caption={file_caption!r} (type={type(file_caption)}), thumb_path={thumb_path!r} (type={type(thumb_path)})"
            )
            await rep.report(debug_msg, "info")

            if not isinstance(pdf_path, str) or not ospath.exists(pdf_path):
                await rep.report(f"Upload failed: pdf_path is not a valid string or file does not exist: {pdf_path}", "error")
                return

            if not isinstance(file_caption, str) or not file_caption.strip():
                await rep.report(f"Upload failed: file_caption is not a valid string: {file_caption}", "error")
                file_caption = "<b>Manga</b>"

            if thumb_path is not None and not isinstance(thumb_path, str):
                await rep.report(f"Upload warning: thumb_path is not a string: {thumb_path}", "warning")
                thumb_path = None

            file_store_msg = await bot.send_document(
                Var.FILE_STORE,
                pdf_path,
                caption=file_caption,
                thumb=thumb_path,
                force_document=True
            )

            bot_link = f"https://telegram.me/{Var.BOT_USERNAME}?start={await encode('get-'+str(file_store_msg.id * abs(Var.FILE_STORE)))}"

            manga_banner = await db.get_manga_banner(manga_name)
            poster_url = (manga_banner or 
                        manga_info.get("coverImage", {}).get("large") or 
                        manga_info.get("coverImage", {}).get("medium") or 
                        "https://envs.sh/E7p.png?isziC=1")

            main_buttons = [[InlineKeyboardButton(f"{MANGA_BTN}", url=bot_link)]]

            channel_creation = await db.get_channel_creation()
            if channel_creation:
                custom_channel = await get_or_create_manga_channel(title, manga_info)
                if custom_channel and custom_channel != Var.FILE_STORE:
                    await status_msg.edit_text(
                        f"<blockquote><b>‣ Manga Name :</b> <i>{title}</i></blockquote>\n\n<pre>Mirroring to custom channel...</pre>"
                    )

                    custom_msg = await bot.send_document(
                        custom_channel,
                        pdf_path,
                        caption=file_caption,
                        thumb="thumb.jpg" if os.path.exists("thumb.jpg") else None,
                        force_document=True
                    )
                    

                    chat_info = await bot.get_chat(custom_channel)
                    if chat_info.username:
                        custom_link = f"https://t.me/{chat_info.username}/{custom_msg.id}"
                        main_buttons = [[InlineKeyboardButton(f"{MANGA_BUTTON}", url=custom_link)]]
                    else:
                        try:
                            invite_link = await bot.export_chat_invite_link(custom_channel)
                            raw_channel_id = str(custom_channel).replace("-100", "")
                            post_link = f"https://t.me/c/{raw_channel_id}/{custom_msg.id}"
                            main_buttons = [
                                [InlineKeyboardButton(f"{MANGA_READ_BUTTON}", url=post_link),
                                InlineKeyboardButton(f"{MANGA_CHNL_BUTTON}", url=invite_link)]
                            ]
                        except Exception as e:
                            await rep.report(f"Failed to create custom channel links: {e}", "warning")

            await status_msg.edit_text(
                f"<blockquote><b>‣ Manga Name:</b> <i>{title}</i></blockquote>\n\n<pre>Sending main post...</pre>"
            )

            caption = await get_manga_caption(manga_info, title)
            main_post = await bot.send_photo(
                Var.MAIN_CHANNEL,
                photo=poster_url,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(main_buttons)
            )

            await asleep(Var.STICKER_INTERVAL)
            await send_sticker_to_channel(Var.MAIN_CHANNEL, Var.STICKER_ID)

            if os.path.exists(pdf_path):
                os.remove(pdf_path)

            await db.saveAnime(chapter_url, "1", "pdf", file_store_msg.id)

            if status_msg:
                await status_msg.delete()

            await rep.report(f"Successfully uploaded manga: {title}", "info")

        except Exception as e:
            raise Exception(f"Upload failed: {e}")

    except Exception as e:
        await rep.report(f"Error processing manga: {e}", "error")
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            os.remove(pdf_path)
        if 'status_msg' in locals() and status_msg:
            await status_msg.delete()

async def get_mangadex_images(chapter_url):
    try:
        import re
        match = re.search(r'/chapter/([a-f0-9\-]+)', chapter_url)
        if not match:
            return []
        chapter_id = match.group(1)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.mangadex.org/at-home/server/{chapter_id}")
            if resp.status_code != 200:
                return []
            data = resp.json()
            base_url = data["baseUrl"]
            chapter = data["chapter"]
            hash_ = chapter["hash"]
            images = chapter["data"]
 
            return [f"{base_url}/data/{hash_}/{img}" for img in images]
    except Exception as e:
        await rep.report(f"Failed to fetch MangaDx images: {e}", "error")
        return []

async def images_to_pdf(title, images, manga_dir):
    try:
        if not isinstance(title, str):
            await rep.report(f"PDF creation failed: title is not a string: {title}", "error")
            return None
        if not isinstance(images, list) or not all(isinstance(img, str) for img in images):
            await rep.report(f"PDF creation failed: images list contains non-string items: {images}", "error")
            return None

            
        pdf = FPDF()
        img_paths = []
        error_count = 0
        max_errors = 3

        async with httpx.AsyncClient(timeout=30) as client:
            tasks = []
            for idx, img_url in enumerate(images):
                if not isinstance(img_url, str):
                    await rep.report(f"Skipping non-string image URL: {img_url}", "warning")
                    error_count += 1
                    continue
                img_path = os.path.join(manga_dir, f"{title}_{idx}.jpg")
                tasks.append(download_image_async(client, img_url, img_path))
                img_paths.append(img_path)
            
            await asyncio.gather(*tasks)

        for img_path in img_paths:
            if not ospath.exists(img_path):
                error_count += 1
                if error_count > max_errors:
                    await rep.report(f"Too many image failures for {title}, aborting", "error")
                    break
                continue
                
            try:
                with Image.open(img_path) as im:
                    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
                        bg = Image.new('RGB', im.size, (255, 255, 255))
                        if im.mode == 'RGBA':
                            bg.paste(im, mask=im.split()[3])
                        elif im.mode == 'LA':
                            bg.paste(im, mask=im.split()[1])
                        else:
                            bg.paste(im)
                        im = bg
                    elif im.mode != 'RGB':
                        im = im.convert('RGB')

                    im.save(img_path, "JPEG", quality=75)

                width, height = Image.open(img_path).size
                pdf_width = 210
                pdf_height = height * (pdf_width / width)
                
                pdf.add_page(orientation='P' if width <= height else 'L')
                pdf.image(img_path, x=0, y=0, w=pdf_width)
            
            except Exception as e:
                error_count += 1
                await rep.report(f"Failed to process image {img_path}: {e}", "warning")
                if error_count > max_errors:
                    await rep.report(f"Too many image failures for {title}, aborting", "error")
                    break
            finally:
                try:
                    if ospath.exists(img_path):
                        os.remove(img_path)
                except Exception:
                    pass

        if error_count > max_errors:
            return None

        pdf_path = os.path.join(manga_dir, f"{title}.pdf")
        pdf.output(pdf_path)
        
        if not ospath.exists(pdf_path) or ospath.getsize(pdf_path) < 1024:
            await rep.report(f"Generated PDF appears invalid for {title}", "error")
            return None
            
        return pdf_path
        
    except Exception as e:
        await rep.report(f"PDF creation failed: {e}", "error")
        return None
    finally:
        for img_path in img_paths:
            try:
                if ospath.exists(img_path):
                    os.remove(img_path)
            except Exception:
                pass
async def download_image_async(client, url, filename):
    try:
        resp = await client.get(url, timeout=30)
        if resp.status_code == 200:
            with open(filename, "wb") as f:
                f.write(resp.content)
    except Exception as e:
        print(f"Failed to download {url}: {e}")

def normalize_title_for_comparison(title):
    patterns = [
        r'\[.*?\]',
        r'\(.*?\)',
        r'- \d+.*$',
        r'\d{3,4}p',
        r'CR WEBRip.*$',
        r'MultiSub.*$',
        r'HEVC.*$',
        r'AAC.*$',
        r'^\[.*?\]\s*',
        r'\s+',
    ]
    
    clean_title = title
    for pattern in patterns:
        clean_title = re.sub(pattern, ' ', clean_title)
    return clean_title.strip().lower()

async def process_low_end(name, torrent_url, force=False):
    try:
        aniInfo = TextEditor(name)
        await aniInfo.load_info()
        ani_id, ep_no = aniInfo.adata.get('id'), aniInfo.pdata.get("episode_number")

        encoding_enabled = await db.get_encoding()
        if ani_id not in ani_cache['ongoing']:
            ani_cache['ongoing'].add(ani_id)
        elif not force:
            return
        if not force and ani_id in ani_cache['completed']:
            return

        if force or (not (ani_data := await db.getAnime(ani_id)) \
            or (ani_data and not (qual_data := ani_data.get(ep_no))) \
            or (ani_data and qual_data and not all(qual for qual in qual_data.values()))):

            if "[Batch]" in name:
                await rep.report(f"Torrent Skipped!\n\n{name}", "warning")
                return

            await rep.report(f"New Anime Torrent Found!\n\n{name}", "info")
            cleaned_name = clean_anime_title(name)
            channel_to_use = await get_or_create_anime_channel(name, aniInfo)

            channel_valid = False
            for attempt in range(3):
                if await validate_channel_id(channel_to_use):
                    channel_valid = True
                    break
                await asyncio.sleep(2)

            if not channel_valid:
                await rep.report(f"Final channel {channel_to_use} is invalid after retries, using main channel", "error")
                channel_to_use = Var.MAIN_CHANNEL

            all_banners = await db.list_anime_banners()
            banner_url = None
            for banner_key, url in all_banners:
                if banner_key.lower() in name.lower():
                    banner_url = url
                    break

            if banner_url:
                photo_url = banner_url
            elif hasattr(Var, 'ANIME') and Var.ANIME in name:
                photo_url = Var.CUSTOM_BANNER
            else:
                photo_url = aniInfo.adata.get("poster_url", "https://envs.sh/E7p.png?isziC=1")

            try:
                post_msg = await bot.send_photo(
                    channel_to_use,
                    photo=photo_url,
                    caption=await aniInfo.get_caption()
                )
            except Exception as e:
                await rep.report(f"Failed to send initial post: {e}", "error")
                return

            await mirror_to_main_channel(
                post_msg=post_msg,
                photo_url=photo_url,
                caption=post_msg.caption.html if post_msg.caption else "",
                channel_to_use=channel_to_use
            )

            await asleep(1.5)
            await rep.report(f"Using channel: {channel_to_use} for anime: {cleaned_name}", "info")
            await asleep(1.5)

            stat_msg = await bot.send_message(
                chat_id=channel_to_use, 
                text=f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Downloading...</i></pre>"
            )

            await asleep(Var.STICKER_INTERVAL)
            await send_sticker_to_channel(channel_to_use, Var.STICKER_ID)

            file_store_links = {}
            buttons = [] 
            for qual in ["480", "720", "1080"]:
                rss_link = Var.RSS_LOW_END.get(qual)
                if not rss_link:
                    continue
                feed = await getfeed(rss_link)
                if not feed or not feed.get("link"):
                    continue

                await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Downloading...</i></pre>")
                dl_path = await download_torrent(feed["link"])
                if not dl_path:
                    await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Failed to download {qual}p</i></pre>")
                    continue

                if Var.LOW_END_RENAME:
                    editor = TextEditor(name)
                    upname = await editor.get_upname(qual)
                    out_path = f"encode/{upname}"
                    os.makedirs("encode", exist_ok=True)
                    progress_path = f"{out_path}.progress"
                    ffmpeg_cmd = Var.LOW_END_FFMPEG.format(
                        dl_path, progress_path, out_path
                    )
                    proc = await asyncio.create_subprocess_shell(
                        ffmpeg_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    await proc.communicate()
                    if os.path.exists(dl_path):
                        try:
                            os.remove(dl_path)
                        except Exception:
                            pass
                    final_path = out_path
                else:
                    final_path = dl_path

                await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Uploading...</i></pre>")
                uploader = TgUploader(stat_msg)
                msg = await uploader.upload(final_path, qual)
                if msg:
                    file_store_links[qual] = msg.id
                    await db.saveAnime(ani_id, ep_no, qual, msg.id)
                    encoded = await encode('get-' + str(msg.id * abs(Var.FILE_STORE)))
                    all_buttons = []
                    for q, mid in file_store_links.items():
                        enc = await encode('get-' + str(mid * abs(Var.FILE_STORE)))
                        all_buttons.append(
                            InlineKeyboardButton(
                                f"{btn_formatter.get(q, q+'p')}",
                                url=f"https://t.me/{Var.BOT_USERNAME}?start={enc}"
                            )
                        )
                    grouped_buttons = [all_buttons[i:i+2] for i in range(0, len(all_buttons), 2)]
                    await editMessage(post_msg, await aniInfo.get_caption(), InlineKeyboardMarkup(grouped_buttons))
                else:
                    await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Failed to upload {qual}p</i></pre>")

            all_buttons = []
            for qual, msg_id in file_store_links.items():
                encoded = await encode('get-' + str(msg_id * abs(Var.FILE_STORE)))
                all_buttons.append(
                    InlineKeyboardButton(
                        f"{btn_formatter.get(qual, qual+'p')}",
                        url=f"https://t.me/{Var.BOT_USERNAME}?start={encoded}"
                    )
                )

            buttons = [all_buttons[i:i+2] for i in range(0, len(all_buttons), 2)]

            final_caption = await aniInfo.get_caption()
            await editMessage(post_msg, final_caption, InlineKeyboardMarkup(buttons))

            if stat_msg:
                await stat_msg.delete()

            #if channel_to_use != Var.MAIN_CHANNEL:
                #try:
                    #await mirror_to_main_channel(post_msg, photo_url, final_caption, channel_to_use)
                #except Exception as e:
                    #await rep.report(f"Mirror error: {e}", "warning")

            if ani_id and ep_no:
                await db.mark_episode_completed(ani_id, ep_no)

    except Exception as e:
        await rep.report(f"Low-end processing error: {str(e)}", "error")

async def fetch_animes():
    await rep.report("Fetching Anime Started !!!", "info")
    processed_urls = set()
    
    while True:
        await asleep(15)
        if len(processed_urls) > 1000:
            processed_urls.clear()
            
        mode = await db.get_mode()
        if ani_cache.get('global_pause') and not ani_cache.get('manual_task'):
            continue
            
        if mode == "anime" and ani_cache['fetch_animes']:
            upload_mode = await db.get_upload_mode()
            print(f"[DEBUG] fetch_animes: mode={mode}, upload_mode={upload_mode}", "info")
            try:
                if upload_mode == "low_end":
                    for qual in ["480", "720", "1080"]:
                        rss_url = Var.RSS_LOW_END.get(qual)
                        print(f"[DEBUG] Checking low_end {qual}p RSS: {rss_url}", "info")
                        if not rss_url:
                            continue
                        feed = await getfeed(rss_url)
                        if feed:
                            print(f"[DEBUG] Low-end {qual}p: {feed.title} | {feed.link}", "info")
                        else:
                            print(f"[DEBUG] Low-end {qual}p: None", "info")
                        if feed and feed.link not in processed_urls:
                            ani_data = await db.getAnime(feed.link)
                            ep_no = None
                            match = re.search(r'[-\s](\d+)\s*\(', feed.title)
                            if match:
                                ep_no = match.group(1)
                            if not ep_no:
                                ep_no = "1"
                            ep_data = ani_data.get(str(ep_no), {}) if ani_data else {}
                            if ep_data.get("completed"):
                                continue
                            processed_urls.add(feed.link)
                            bot_loop.create_task(get_animes(feed.title, feed.link))
                else:
                    for rss_url in Var.RSS_ITEMS_ANIME:
                        print(f"[DEBUG] Checking normal RSS: {rss_url}", "info")
                        feed = await getfeed(rss_url)
                        if feed:
                            print(f"[DEBUG] Normal: {feed.title} | {feed.link}", "info")
                        else:
                            print(f"[DEBUG] Normal: None", "info")
                        if feed and feed.link not in processed_urls:
                            ani_data = await db.getAnime(feed.link)
                            ep_no = None
                            match = re.search(r'[-\s](\d+)\s*\(', feed.title)
                            if match:
                                ep_no = match.group(1)
                            if not ep_no:
                                ep_no = "1"
                            ep_data = ani_data.get(str(ep_no), {}) if ani_data else {}
                            if ep_data.get("completed"):
                                continue
                            processed_urls.add(feed.link)
                            bot_loop.create_task(get_animes(feed.title, feed.link))
            except Exception as e:
                await rep.report(f"Anime fetch error: {str(e)}", "error")

        await asleep(10)

async def get_or_create_anime_channel(name: str, aniInfo):
    try:
        base_anime_name = extract_base_anime_name(name)
        normalized_name = normalize_anime_name_for_search(name)
        
        await rep.report(f"Searching for existing channel for: {base_anime_name}", "info")
        await asleep(1.5)
        custom_channel = await db.get_anime_channel(normalized_name)
        if custom_channel:
            await rep.report(f"Found custom channel mapping: {custom_channel}", "info")
            return custom_channel

        existing_channel = await find_existing_anime_channel(name)
        if existing_channel:
            await rep.report(f"Found existing channel for {base_anime_name}: {existing_channel}", "info")
            await db.add_anime_channel_mapping(normalized_name, existing_channel)
            return existing_channel
        
        channel_creation = await db.get_channel_creation()
        if not channel_creation or not Var.USER_SESSION:
            await rep.report("Channel creation disabled or no user session, using main channel", "info")
            return Var.MAIN_CHANNEL

        await rep.report(f"Creating new channel for: {base_anime_name}", "info")
        new_channel = await create_anime_channel(name, aniInfo)
        
        if new_channel:
            await db.add_anime_channel_mapping(normalized_name, new_channel)
            await rep.report(f"Successfully created and saved channel mapping for {base_anime_name}", "info")
            return new_channel
        else:
            await rep.report("Failed to create channel, using main channel", "error")
            return Var.MAIN_CHANNEL
            
    except Exception as e:
        await rep.report(f"Error in get_or_create_anime_channel: {e}", "error")
        return Var.MAIN_CHANNEL

async def create_anime_channel(name, aniInfo):
    try:
        if not Var.USER_SESSION:
            await rep.report("User session not available for channel creation", "error")
            return None

        from pyrogram import Client
        user_client = Client("user_session", session_string=Var.USER_SESSION, 
                           api_id=Var.API_ID, api_hash=Var.API_HASH)

        await user_client.start()

        anime_format = (aniInfo.adata.get("format", "") or "").lower()
        is_movie = anime_format == "movie" or (
            hasattr(aniInfo, "is_movie_title") and aniInfo.is_movie_title(name)
        )

        titles = aniInfo.adata.get("title", {})
        channel_name = titles.get("english") or titles.get("romaji") or clean_anime_title(name)
        title = channel_name
        status = aniInfo.adata.get("status", "Unknown").capitalize()
        genres = aniInfo.adata.get("genres", [])[:3]
        genres_formatted = ", ".join(genres) if genres else "Unknown"

        if is_movie:
            description = (
                f"• Movie: {title}\n"
                f"• Status: {status}\n"
                f"• Genres: {genres_formatted}\n\n"
                f"Powered by @{Var.BOT_USERNAME}"
            )
        else:
            description = (
                f"• Anime: {title}\n"
                f"• Status: {status}\n"
                f"• Genres: {genres_formatted}\n\n"
                f"Powered by @{Var.BOT_USERNAME}"
            )

        created = await user_client.create_channel(channel_name, description)
        channel_id = created.id

        poster_url = (
            aniInfo.adata.get("coverImage", {}).get("large")
            or aniInfo.adata.get("coverImage", {}).get("medium")
            or aniInfo.adata.get("coverImage", {}).get("small")
        )
        if poster_url:
            filename = f"/tmp/{channel_id}_logo.jpg"
            filename = download_image(poster_url, filename)
            if filename:
                try:
                    await user_client.set_chat_photo(channel_id, photo=filename)
                    print(f"Set channel photo for {channel_id} successfully!")
                    remove(filename)
                except Exception as e:
                    print(f"Failed to set channel photo: {e}")
                    await rep.report(f"Failed to set channel photo: {e}", "warning")
            else:
                print("Image file was not downloaded or does not exist.")
                await rep.report(f"Image file was not downloaded or does not exist.", "warning")
        else:
            print("No poster URL found in AniList data.")
            await rep.report(f"No poster URL found in AniList data.", "warning")

        try:
            from pyrogram.types import ChatPrivileges
            await user_client.promote_chat_member(
                channel_id,
                Var.CREATION_USERNAME,
                privileges=ChatPrivileges(
                    can_post_messages=True,
                    can_edit_messages=True,
                    can_delete_messages=True,
                    can_invite_users=True,
                    can_change_info=True,
                    can_pin_messages=True,
                    can_manage_chat=True,
                    can_manage_video_chats=False,
                    is_anonymous=False
                )
            )
            await rep.report(f"Successfully added and promoted bot in channel", "info")
        except Exception as e:
            await rep.report(f"Failed to add/promote bot in channel: {e}", "error")

        try:
            titles = aniInfo.adata.get("title", {})
            genres = ', '.join(aniInfo.adata.get("genres", [])[:3])
            anime_type = aniInfo.adata.get("format", "Unknown")
            avg_rating = aniInfo.adata.get("averageScore", "N/A")
            status = aniInfo.adata.get("status", "Unknown")
            start_date = aniInfo.adata.get("startDate", {})
            end_date = aniInfo.adata.get("endDate", {})
            runtime = aniInfo.adata.get("duration", "Unknown")
            episodes = aniInfo.adata.get("episodes", "Unknown")
            desc = aniInfo.adata.get("description", "No description available").replace("<br>", "").replace("<i>", "").replace("</i>", "").strip()
            desc = (desc[:200] + "...") if len(desc) > 200 else desc 
            site_url = aniInfo.adata.get("siteUrl", "https://anilist.co")
            media_id = aniInfo.adata.get("id")

            english = titles.get("english", "Unknown")
            romaji = titles.get("romaji", "Unknown")
            display_title = english if english != "Unknown" else romaji

            graphic_poster_url = f"https://img.anili.st/media/{media_id}"

            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.head(graphic_poster_url) as resp:
                    if resp.status != 200:
                        graphic_poster_url = poster_url or "https://imgs.search.brave.com/33oSQBqhBoRB6akjKPud5oFd-PxnMFEm1AjnBTS2ZhE/rs:fit:860:0:0:0/g:ce/aHR0cHM6Ly9pbWcu/ZnJlZXBpay5jb20v/dmVjdG9yLXByZW1p/dW0vaWx1c3RyYWNp/b24tYW5pbWUtZXJy/b3ItNDA0LXBhZ2lu/YS1uby1lbmNvbnRy/YWRhXzE1MDk3Mi0y/NTY0LmpwZw"


            if is_movie:
                caption = f"""<b><blockquote>{display_title}</blockquote>

<blockquote>‣ Genres : {genres}
‣ Type : {anime_type}
‣ Average Rating : {avg_rating}
‣ Status : {status}
‣ Release Date : {start_date.get("year", '')}-{start_date.get("month", '')}-{start_date.get("day", '')}
‣ Duration : {runtime} minutes</blockquote>
<blockquote expandable>‣ Synopsis : <i>{desc}</i></blockquote expandable>
</b>"""
            else:
                caption = f"""<b><blockquote>{display_title}</blockquote>

<blockquote>‣ Genres : {genres}
‣ Type : {anime_type}
‣ Average Rating : {avg_rating}
‣ Status : {status}
‣ First aired : {start_date.get("year", '')}-{start_date.get("month", '')}-{start_date.get("day", '')}
‣ Last aired : {end_date.get("year", '')}-{end_date.get("month", '')}-{end_date.get("day", '')}
‣ Runtime : {runtime} minutes
‣ No of episodes : {episodes}</blockquote>
<blockquote expandable>‣ Synopsis : <i>{desc}</i></blockquote expandable>
</b>"""


            await user_client.send_photo(
                chat_id=channel_id,
                photo=graphic_poster_url,
                caption=caption
            )

            STICKER_ID = "CAACAgUAAxkBAAIERmhruO6M5RpLtZjb2yrvPJxTuw0IAAIzEwACTrLwVSdrhgIPuK1TNgQ"
            await user_client.send_sticker(channel_id, STICKER_ID)

            await rep.report("Intro poster, caption, and sticker sent to channel", "info")

        except Exception as e:
            await rep.report(f"Failed to send intro content: {e}", "warning")

        await db.add_anime_channel_mapping(channel_name, channel_id)

        await asleep(2)

        await user_client.stop()

        await rep.report(f"Successfully created channel: {channel_name} (ID: {channel_id})", "info")
        return channel_id

    except Exception as e:
        await rep.report(f"Failed to create anime channel: {e}", "error")
        return None

async def get_animes(name, torrent, force=False):
    mode = await db.get_mode()
    if mode != "anime":
        await rep.report(f"[DEBUG] Skipping {name} because mode is not anime (current mode: {mode})", "info")
        return

    try:
        upload_mode = await db.get_upload_mode()
        await rep.report(f"[DEBUG] get_animes: upload_mode={upload_mode}", "info")
        if upload_mode == "low_end":
            await rep.report(f"[DEBUG] get_animes: calling process_low_end for {name}", "info")
            await process_low_end(name, torrent)
    except Exception as e:
        await rep.report(f"Error checking upload mode: {str(e)}", "error")
        return

    if not await is_valid_torrent_url(torrent):
        await rep.report(f"Invalid or non-torrent URL for {name}: {torrent}", "error")
        return
    
    try:
        aniInfo = TextEditor(name)
        await aniInfo.load_info()
        ani_id, ep_no = aniInfo.adata.get('id'), aniInfo.pdata.get("episode_number")
        
        encoding_enabled = await db.get_encoding()
        if ani_id not in ani_cache['ongoing']:
            ani_cache['ongoing'].add(ani_id)
        elif not force:
            return
        if not force and ani_id in ani_cache['completed']:
            return
        
        if force or (not (ani_data := await db.getAnime(ani_id)) \
            or (ani_data and not (qual_data := ani_data.get(ep_no))) \
            or (ani_data and qual_data and not all(qual for qual in qual_data.values()))):
            
            if "[Batch]" in name:
                await rep.report(f"Torrent Skipped!\n\n{name}", "warning")
                return
            
            await rep.report(f"New Anime Torrent Found!\n\n{name}", "info")
            cleaned_name = clean_anime_title(name)
            channel_to_use = await get_or_create_anime_channel(name, aniInfo)
            
            channel_valid = False
            for attempt in range(3):
                if await validate_channel_id(channel_to_use):
                    channel_valid = True
                    break
                await asyncio.sleep(2)
            
            if not channel_valid:
                await rep.report(f"Final channel {channel_to_use} is invalid after retries, using main channel", "error")
                channel_to_use = Var.MAIN_CHANNEL
            
            post_msg = None
            photo_path = None
            all_banners = await db.list_anime_banners()
            banner_url = None
            
            for banner_key, url in all_banners:
                if banner_key.lower() in name.lower():
                    banner_url = url
                    break
            
            if banner_url:
                photo_url = banner_url
            elif hasattr(Var, 'ANIME') and Var.ANIME in name:
                photo_url = Var.CUSTOM_BANNER
            else:
                photo_url = aniInfo.adata.get("poster_url", "https://envs.sh/E7p.png?isziC=1")
            
            try:
                if photo_path is not None:
                    with open(photo_path, 'rb') as photo_file:
                        post_msg = await bot.send_photo(
                            channel_to_use,
                            photo=photo_url,
                            caption=await aniInfo.get_caption()
                        )
                else:
                    post_msg = await bot.send_photo(
                        channel_to_use,
                        photo=photo_url,
                        caption=await aniInfo.get_caption()
                    )
            except Exception as e:
                await rep.report(f"Failed to send initial post: {e}", "error")
                return
            
            await mirror_to_main_channel(
                post_msg=post_msg,
                photo_url=photo_url,
                caption=post_msg.caption.html if post_msg.caption else "",
                channel_to_use=channel_to_use
            )
            
            await asleep(1.5)
            print(f"Using channel: {channel_to_use} for anime: {cleaned_name}")
            await rep.report(f"Using channel: {channel_to_use} for anime: {cleaned_name}", "info")
            await asleep(1.5)
            
            stat_msg = await bot.send_message(
                chat_id=channel_to_use, 
                text=f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Downloading...</i></pre>"
            )
            
            await asleep(Var.STICKER_INTERVAL)
            await send_sticker_to_channel(channel_to_use, Var.STICKER_ID)
            
            dl_path = await download_torrent(torrent, name)
            if not dl_path or not ospath.exists(dl_path):
                await rep.report(f"File Download Incomplete for {name}, Try Again", "error")
                await stat_msg.delete()
                return
            
            post_id = post_msg.id
            ffEvent = Event()
            ff_queued[post_id] = ffEvent
            
            if ffLock.locked():
                await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Queued to Encode...</i></pre>")
                await rep.report("Added Task to Queue...", "info")
            
            await ffQueue.put(post_id)
            await ffEvent.wait()
            await ffLock.acquire()
            try:
                btns = []
                if not encoding_enabled:
                    filename = await aniInfo.get_upname("HDRi")
                    await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Uploading...</i></pre>")
                    await asleep(1.5)
                    
                    anime_format = aniInfo.adata.get("format", "").lower()
                    is_movie = anime_format == "movie"
                    
                    out_path = await FFEncoder(stat_msg, dl_path, filename, "HDRi", is_movie=is_movie).start_encode()
                    if out_path and out_path != dl_path:
                        await rep.report("Successfully encoded HDRip version.", "info")
                        msg = await TgUploader(stat_msg).upload(out_path, "HDRi")
                        if os.path.exists(out_path):
                            await aioremove(out_path)
                    else:
                        await rep.report("Uploading original file as HDRip...", "info")
                        msg = await TgUploader(stat_msg).upload(dl, "HDRi")
                    
                    msg_id = msg.id
                    link = f"https://telegram.me/{Var.BOT_USERNAME}?start={{}}".format(await encode('get-'+str(msg_id * abs(Var.FILE_STORE))))
                    btns.append([InlineKeyboardButton(f"{RAW_BTN}", url=link)])
                    if post_msg:
                        await editMessage(post_msg, post_msg.caption.html if post_msg.caption else "", InlineKeyboardMarkup(btns))
                    await db.saveAnime(ani_id, ep_no, "HDRi", post_id)
                    bot_loop.create_task(extra_utils(msg_id, dl))
                else:
                    for qual in Var.QUALS:
                        filename = await aniInfo.get_upname(qual)
                        anime_format = aniInfo.adata.get("format", "").lower()
                        is_movie = anime_format == "movie"
                        await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name :</b> <b><i>{name}</i></b></blockquote>\n\n<pre><i>Ready to Encode...</i></pre>")
                        
                        await asleep(1.5)
                        await rep.report("Starting Encode...", "info")
                        try:
                            out_path = await FFEncoder(stat_msg, dl_path, filename, qual, is_movie=is_movie).start_encode()
                        except Exception as e:
                            await rep.report(f"Error: {e}, Cancelled, Retry Again !", "error")
                            await stat_msg.delete()
                            return
                        await rep.report("Successfully Compressed Now Going To Upload...", "info")
                        
                        await editMessage(stat_msg, f"<blockquote>‣ <b>Anime Name:</b> <b><i>{filename}</i></b></blockquote>\n\n<pre><i>Ready to Upload...</i></pre>")
                        await asleep(1.5)
                        try:
                            msg = await TgUploader(stat_msg).upload(out_path, qual)
                        except Exception as e:
                            await rep.report(f"Error: {e}, Cancelled, Retry Again !", "error")
                            await stat_msg.delete()
                            return
                        await rep.report("Successfully Uploaded File into Channel...", "info")
                        
                        msg_id = msg.id
                        link = f"https://telegram.me/{Var.BOT_USERNAME}?start={{}}".format(await encode('get-'+str(msg_id * abs(Var.FILE_STORE))))
                        if post_msg:
                            if len(btns) != 0 and len(btns[-1]) == 1:
                                btns[-1].insert(1, InlineKeyboardButton(f"{btn_formatter[qual]}", url=link))
                            else:
                                btns.append([InlineKeyboardButton(f"{btn_formatter[qual]}", url=link)])
                            await editMessage(post_msg, post_msg.caption.html if post_msg.caption else "", InlineKeyboardMarkup(btns))
                        await db.saveAnime(ani_id, ep_no, qual, post_id)
                        bot_loop.create_task(extra_utils(msg_id, out_path))
            finally:
                ffLock.release()
            
            await stat_msg.delete()
            if encoding_enabled:
                await aioremove(dl_path)
        ani_cache['completed'].add(ani_id)
    except Exception as error:
        await rep.report(format_exc(), "error")


async def extra_utils(msg_id, out_path):
    try:
        msg = await bot.get_messages(Var.FILE_STORE, message_ids=msg_id)

        if hasattr(Var, 'BACKUP_CHANNEL') and Var.BACKUP_CHANNEL != 0:
            for chat_id in str(Var.BACKUP_CHANNEL).split():
                try:
                    await msg.copy(int(chat_id))
                except Exception as e:
                    await rep.report(f"Failed to backup to {chat_id}: {e}", "error")
    except Exception as e:
        await rep.report(f"Error in extra_utils: {e}", "error")

def safe_dirname(name):
    return re.sub(r'[\\/*?:"<>|\'\n\r\t]', '_', name)

async def download_torrent(torrent_url, name=""):
    try:
        unique_dir = generate_unique_dir(name, torrent_url)
        
        if os.path.exists(unique_dir):
            shutil.rmtree(unique_dir)
        os.makedirs(unique_dir, exist_ok=True)
        
        downloader = TorDownloader(unique_dir)
        dl_path = await downloader.download(torrent_url)
        
        if not dl_path or not os.path.exists(dl_path):
            await rep.report(f"Failed to download torrent: {torrent_url}", "error")
            return None
        
        await rep.report(f"Download directory contents: {os.listdir(unique_dir)}", "info")
        await rep.report(f"Successfully downloaded to: {dl_path}", "info")
        return dl_path
    except Exception as e:
        await rep.report(f"Download error: {str(e)}", "error")
        return None

async def upload_file(file_path, quality):
    try:
        uploader = TgUploader() 
        msg = await uploader.upload(file_path, quality)
        return msg
    except Exception as e:
        await rep.report(f"Upload error: {str(e)}", "error")
        return None
