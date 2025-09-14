from re import findall 
from math import floor
from time import time
from os import path as ospath
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, rename as aiorename
from shlex import split as ssplit
from asyncio import sleep as asleep, gather, create_subprocess_shell, create_task
from asyncio.subprocess import PIPE
import datetime
from bot import Var, bot_loop, ffpids_cache, LOGS
from .func_utils import mediainfo, convertBytes, convertTime, sendMessage, editMessage
from .reporter import rep
from .text_utils import TextEditor
from bot.core.database import db

ffargs = {
    'HDRi': Var.FFCODE_HDRi,
    '1080': Var.FFCODE_1080,
    '720': Var.FFCODE_720,
    '480': Var.FFCODE_480,
    '360': Var.FFCODE_360,
    '240': Var.FFCODE_240,
    '144': Var.FFCODE_144,
}

quality_settings = {
    '1080': {'crf_diff': 0, 'audio_bitrate': None},
    '720': {'crf_diff': 1, 'audio_bitrate': '72k'},
    '480': {'crf_diff': 2, 'audio_bitrate': '54k'},
    '360': {'crf_diff': 3, 'audio_bitrate': '35k'},
    '240': {'crf_diff': 4, 'audio_bitrate': '25k'},
    '144': {'crf_diff': 4, 'audio_bitrate': '20k'}
}

class FFEncoder:
    def __init__(self, message, path, name, qual, is_movie=False):
        self.__proc = None
        self.is_cancelled = False
        self.message = message
        self.__name = name
        self.__qual = qual
        self.resolution_map = {
            '1080': '1920x1080',
            '720': '1280x720',
            '480': '854x480',
            '360': '640x360',
            '240': '320x240',
            '144': '256x144'
        }
        self.dl_path = path
        self.__total_time = None
        self.out_path = ospath.join("encode", name)
        self.__prog_file = 'prog.txt'
        self.__start_time = time()
        self.editor = TextEditor(name)
        self.pdata = self.editor.pdata
        self.is_movie = is_movie

    async def progress(self):
        self.__total_time = await mediainfo(self.dl_path, get_duration=True)
        if isinstance(self.__total_time, str):
            self.__total_time = 1.0
        while not (self.__proc is None or self.is_cancelled):
            async with aiopen(self.__prog_file, 'r+') as p:
                text = await p.read()
            if text:
                time_done = floor(int(t[-1]) / 1000000) if (t := findall("out_time_ms=(\d+)", text)) else 1
                ensize = int(s[-1]) if (s := findall(r"total_size=(\d+)", text)) else 0
                
                diff = time() - self.__start_time
                speed = ensize / diff
                percent = round((time_done/self.__total_time)*100, 2)
                tsize = ensize / (max(percent, 0.01)/100)
                eta = (tsize-ensize)/max(speed, 0.01)
    
                bar = floor(percent/8)*"█" + (12 - floor(percent/8))*"▒"
                
                progress_str = f"""<blockquote>‣ <b>Anime Name :</b> <b><i>{self.__name}</i></b></blockquote>
─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<blockquote>‣ <b>Status :</b> <i>Encoding</i>
    <code>[{bar}]</code> {percent}%</blockquote> 
─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<blockquote>   ‣ <b>Size :</b> {convertBytes(ensize)} out of ~ {convertBytes(tsize)}
    ‣ <b>Speed :</b> {convertBytes(speed)}/s
    ‣ <b>Time Took :</b> {convertTime(diff)}
    ‣ <b>Time Left :</b> {convertTime(eta)}
    ‣ <b>Quality:</b> {self.__qual}p</blockquote>
─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<blockquote>‣ <b>File(s) Encoded:</b> <code>{Var.QUALS.index(self.__qual)} / {len(Var.QUALS)}</code></blockquote>"""
            
                await editMessage(self.message, progress_str)
                if (prog := findall(r"progress=(\w+)", text)) and prog[-1] == 'end':
                    break
            await asleep(8)

    async def get_ffmpeg_command(self, dl_npath, out_npath):
        try:
            anime_name = self.pdata.get('title', '').strip() if self.pdata else None
            if not anime_name:
                match = findall(r'\] (.+?) [-–] \d+', self.dl_path)
                if match:
                    anime_name = match[0].strip()

            if anime_name:
                LOGS.info(f"Checking FFmpeg config for anime: {anime_name}")
                await rep.report(f"Checking FFmpeg config for anime: {anime_name}", "info")
                custom_config = await db.get_anime_ffmpeg(anime_name)

                if custom_config:
                    LOGS.info(f"Found custom FFmpeg config for: {anime_name}")
                    await rep.report(f"Found custom FFmpeg config for: {anime_name}", "info")

                    if "|||" in custom_config:
                        resolution_config, hdrip_config = custom_config.split("|||", 1)
                        resolution_config = resolution_config.strip()
                        hdrip_config = hdrip_config.strip()

                        if self.__qual == 'HDRi':
                            LOGS.info("Using HDRip config")
                            return hdrip_config.format(dl_npath, self.__prog_file, out_npath)

                        base_crf_match = findall(r'-crf\s+(\d+)', resolution_config)
                        base_crf = int(base_crf_match[0]) if base_crf_match else 23

                        quality_adjust = quality_settings.get(self.__qual, {'crf_diff': 0, 'audio_bitrate': None})
                        new_crf = base_crf + quality_adjust['crf_diff']

                        modified_config = resolution_config
 
                        if quality_adjust['audio_bitrate']:
                            audio_matches = findall(r'-b:a\s+\w+k', modified_config)
                            if audio_matches:
                                modified_config = modified_config.replace(
                                    audio_matches[0],
                                    f"-b:a {quality_adjust['audio_bitrate']}"
                                )

                        modified_config = modified_config.replace(
                            f"-crf {base_crf}",
                            f"-crf {new_crf}"
                        )


                        resolution = self.resolution_map.get(self.__qual, '1920x1080')
                        LOGS.info(f"Using modified config with CRF {new_crf} and resolution {resolution}")
                        await rep.report(f"Using modified config with CRF {new_crf} and resolution {resolution}", "info")
                        return modified_config.format(dl_npath, self.__prog_file, resolution, out_npath)
                
                    else:
                        if self.__qual == 'HDRi':
                            return custom_config.format(dl_npath, self.__prog_file, out_npath)
                        else:
                            resolution = self.resolution_map.get(self.__qual, '1920x1080')
                            return custom_config.format(dl_npath, self.__prog_file, resolution, out_npath)

            LOGS.info(f"No custom config found, using default {self.__qual} config")
            return ffargs[self.__qual].format(dl_npath, self.__prog_file, out_npath)

        except Exception as e:
            LOGS.error(f"Error getting FFmpeg command: {e}")
            await rep.report(f"Error getting FFmpeg command: {e}", "warning")
            return ffargs['1080'].format(dl_npath, self.__prog_file, out_npath)

    async def start_encode(self):
        encoding_enabled = await db.get_encoding()
        if not encoding_enabled:
            if self.__qual != 'HDRi':
                LOGS.info("Skipping non-HDRi encode when encoding is disabled")
                return self.dl_path
            else:
                LOGS.info("Processing HDRi encode even though encoding is disabled")
                await rep.report("Processing HDRi encode...", "info")

        if ospath.exists(self.__prog_file):
            await aioremove(self.__prog_file)
        async with aiopen(self.__prog_file, 'w+'):
            LOGS.info("Progress Temp Generated !")
            pass

        dl_npath = ospath.join("encode", "ffanimeadvin.mkv")
        out_npath = ospath.join("encode", "ffanimeadvout.mkv")
        await aiorename(self.dl_path, dl_npath)

        ffcode = await self.get_ffmpeg_command(dl_npath, out_npath)
        LOGS.info(f'Using FFmpeg command: {ffcode}')

        self.__proc = await create_subprocess_shell(ffcode, stdout=PIPE, stderr=PIPE)
        proc_pid = self.__proc.pid
        ffpids_cache.append(proc_pid)

        _, return_code = await gather(create_task(self.progress()), self.__proc.wait())
        ffpids_cache.remove(proc_pid)
        await aiorename(dl_npath, self.dl_path)
    
        if self.is_cancelled:
            LOGS.info("Encoding was cancelled.")
            await rep.report("Encoding was cancelled.", "warning")
            return None
    
        if return_code == 0:
            if ospath.exists(out_npath):
                await aiorename(out_npath, self.out_path)
            LOGS.info(f"Encoding successful! Output file: {self.out_path}")
            return self.out_path
        else:
            error_message = (await self.__proc.stderr.read()).decode().strip()
            LOGS.error(f"Encoding failed with error: {error_message}")
            await rep.report(f"Encoding failed: {error_message[:200]}...", "error")
            return None
    
    async def cancel_encode(self):
        self.is_cancelled = True
        if self.__proc is not None:
            try:
                self.__proc.kill()
            except:
                pass
