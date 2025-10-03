from calendar import month_name
from datetime import datetime
from random import choice
from asyncio import sleep as asleep
from aiohttp import ClientSession
from anitopy import parse
import re
from bot import Var, bot
from .ffargs import ffargs
from .func_utils import handle_logs
from .reporter import rep
from .database import db
import asyncio

_manga_anilist_lock = asyncio.Lock()
_manga_anilist_last_call = 0
_anime_anilist_lock = asyncio.Lock()
_anime_anilist_last_call = 0

MANUAL_ANILIST_NAMES = {
    "Im Living With an Otaku NEET Kunoichi": "I'm Living With an Otaku NEET Kunoichi"
}

CAPTION_FORMAT = """<b><blockquote>❐ {title}</blockquote></b>
─━━━━━━━━━━─
<b>›› Eᴘɪsᴏᴅᴇ : {ep_no}</b>
<b>›› Qᴜᴀʟɪᴛʏ : 480ᴘ | 720ᴘ | 1080ᴘ | Hᴅʀɪᴘ</b>
<b>›› Lᴀɴɢᴜᴀɢᴇ :  Jᴀᴘᴀɴᴇsᴇ | ᴇɴɢ sᴜʙ</b>
─━━━━━━━━━━─
<b><blockquote>≡ ᴜꜱᴇ <a href="https://play.google.com/store/apps/details?id=org.videolan.vlc">ᴠʟᴄ ᴘʟᴀʏᴇʀ</a> ᴏʀ <a href="https://play.google.com/store/apps/details?id=com.mxtech.videoplayer.ad">ᴍx ᴘʟᴀʏᴇʀ</a> ᴛᴏ ᴄʜᴀɴɢᴇ ᴀᴜᴅɪᴏ ᴀɴᴅ ꜱᴜʙᴛɪᴛʟᴇꜱ, ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴏɴ ʜᴏᴡ ᴛᴏ ᴜꜱᴇ ꜰɪʟᴇ ʙᴏᴛ</b></blockquote>
ㅤ"""

MOVIE_CAPTION = """─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<blockquote><b>✦ {title} ✦</b></blockquote>
─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<b>›› Tʏᴘᴇ : Mᴏᴠɪᴇ </b>
<b>›› Eᴘɪsᴏᴅᴇ : {ep_no}</b>
<b>›› Aᴜᴅɪᴏ: {lang}</b>
<b>›› Sᴛᴀᴛᴜs : {status}</b>
<b>›› Dᴜʀᴀᴛɪᴏɴ : {dura}</b>
<b>›› Gᴇɴʀᴇs : {genres}</b>
────────────────────
<b><blockquote>〄 Pᴏᴡᴇʀᴇᴅ ʙʏ : <a href="https://t.me/Eminence_Society">Eᴍɪɴᴇɴᴄᴇ sᴏᴄɪᴇᴛʏ</a></b></blockquote>
<b><blockquote>≡ ᴜꜱᴇ ᴠʟᴄ ᴘʟᴀʏᴇʀ ᴏʀ ᴍx ᴘʟᴀʏᴇʀ ᴛᴏ ᴄʜᴀɴɢᴇ ᴀᴜᴅɪᴏ ᴀɴᴅ ꜱᴜʙᴛɪᴛʟᴇꜱ, ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴏɴ ʜᴏᴡ ᴛᴏ ᴜꜱᴇ ꜰɪʟᴇ ʙᴏᴛ</b></blockquote>"""

MANGA_CAPTION_FORMAT = """─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<blockquote><b>✦ {title} ✦</b></blockquote>
─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ 
<b>›› Tʏᴘᴇ : Mᴀɴɢᴀ</b>
<b>›› Sᴛᴀᴛᴜs : Rᴇʟᴇᴀsɪɴɢ</b>
<b>›› Vᴏʟᴜᴍᴇ : {volume}</b>
<b>›› Cʜᴀᴘᴛᴇʀ : {chapter}</b>
<b>›› Gᴇɴʀᴇs : {genres}</b>
<b>›› Dᴇsᴄʀɪᴘᴛɪᴏɴ :</b> {description}
────────────────────
<b><blockquote>〄 Pᴏᴡᴇʀᴇᴅ ʙʏ : <a href="https://t.me/Eminence_Society">Eᴍɪɴᴇɴᴄᴇ sᴏᴄɪᴇᴛʏ</a></b></blockquote>"""


GENRES_EMOJI = {"Action": "👊", "Adventure": choice(['🪂', '🧗‍♀']), "Comedy": "🤣", "Drama": " 🎭", "Ecchi": choice(['💋', '🥵']), "Fantasy": choice(['🧞', '🧞‍♂', '🧞‍♀','🌗']), "Hentai": "🔞", "Horror": "☠", "Mahou Shoujo": "☯", "Mecha": "🤖", "Music": "🎸", "Mystery": "🔮", "Psychological": "♟", "Romance": "💞", "Sci-Fi": "🛸", "Slice of Life": choice(['☘','🍁']), "Sports": "⚽️", "Supernatural": "🫧", "Thriller": choice(['🥶', '🔪','🤯'])}

# Standard anime query
ANIME_GRAPHQL_QUERY = """
query ($id: Int, $search: String, $seasonYear: Int) {
  Media(id: $id, type: ANIME, format_not_in: [MUSIC, MOVIE, MANGA, NOVEL, ONE_SHOT], search: $search, seasonYear: $seasonYear) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    type
    format
    status(version: 2)
    description(asHtml: false)
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    season
    seasonYear
    episodes
    duration
    chapters
    volumes
    countryOfOrigin
    source
    hashtag
    trailer {
      id
      site
      thumbnail
    }
    updatedAt
    coverImage {
      large
    }
    bannerImage
    genres
    synonyms
    averageScore
    meanScore
    popularity
    trending
    favourites
    studios {
      nodes {
         name
         siteUrl
      }
    }
    isAdult
    nextAiringEpisode {
      airingAt
      timeUntilAiring
      episode
    }
    airingSchedule {
      edges {
        node {
          airingAt
          timeUntilAiring
          episode
        }
      }
    }
    externalLinks {
      url
      site
    }
    siteUrl
  }
}
"""

MOVIE_GRAPHQL_QUERY = """
query ($id: Int, $search: String, $seasonYear: Int) {
  Media(id: $id, type: ANIME, format: MOVIE, search: $search, seasonYear: $seasonYear) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    type
    format
    status(version: 2)
    description(asHtml: false)
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    duration
    countryOfOrigin
    source
    hashtag
    trailer {
      id
      site
      thumbnail
    }
    updatedAt
    coverImage {
      large
    }
    bannerImage
    genres
    synonyms
    averageScore
    meanScore
    popularity
    trending
    favourites
    studios {
      nodes {
         name
         siteUrl
      }
    }
    isAdult
    externalLinks {
      url
      site
    }
    siteUrl
  }
}
"""

def is_movie_title(name: str) -> bool:

    name_lower = name.lower()
    if "movie" in name_lower:
        return True
    if re.search(r'\\b(19|20)\\d{2}\\b', name):
        return True
    return False

MANGA_GRAPHQL_QUERY = '''
query ($search: String) {
  Media(type: MANGA, search: $search) {
    id
    title {
      romaji
      english
      native
    }
    description
    status(version: 2)
    volumes
    chapters
    genres
    averageScore
    meanScore
    popularity
    coverImage {
      large
    }
    bannerImage
    siteUrl
  }
}
'''


class AniLister:
    def __init__(self, anime_name: str, year: int, is_movie: bool = False) -> None:
        self.__api = "https://graphql.anilist.co"
        self.__ani_name = anime_name
        self.__ani_year = year
        self.__vars = {'search': self.__ani_name, 'seasonYear': self.__ani_year}
        self.is_movie = is_movie

    def __update_vars(self, year=True) -> None:
        if year:
            self.__ani_year -= 1
            self.__vars['seasonYear'] = self.__ani_year
        else:
            self.__vars = {'search': self.__ani_name}

    async def post_data(self):
        global _anime_anilist_last_call
        async with _anime_anilist_lock:
            now = asyncio.get_event_loop().time()
            wait_time = 1 - (now - _anime_anilist_last_call)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            _anime_anilist_last_call = asyncio.get_event_loop().time()
        query = MOVIE_GRAPHQL_QUERY if self.is_movie else ANIME_GRAPHQL_QUERY
        async with ClientSession() as sess:
            async with sess.post(self.__api, json={'query': query, 'variables': self.__vars}) as resp:
                if resp.status == 429:
                    return (resp.status, None, resp.headers)
                try:
                    return (resp.status, await resp.json(), resp.headers)
                except Exception:
                    return (resp.status, None, resp.headers)

    async def get_anidata(self, retry_count=0, max_retries=Var.MAX_RETRIES):
        res_code, resp_json, res_heads = await self.post_data()
        while res_code == 404 and self.__ani_year > 2020:
            self.__update_vars()
            await rep.report(f"AniList Query Name: {self.__ani_name}, Retrying with {self.__ani_year}", "warning", log=False)
            res_code, resp_json, res_heads = await self.post_data()

        if res_code == 404:
            self.__update_vars(year=False)
            res_code, resp_json, res_heads = await self.post_data()

        if res_code == 200 and resp_json:
            return resp_json.get('data', {}).get('Media', {}) or {}
        elif res_code == 429:
            if retry_count >= max_retries:
                await rep.report(f"AniList API FloodWait: {res_code}, Max retries reached. Skipping.", "error")
                return {}
            f_timer = int(res_heads.get('Retry-After', 60))
            await rep.report(f"AniList API FloodWait: {res_code}, Sleeping for {f_timer} !! (Retry {retry_count+1}/{max_retries})", "error")
            await asleep(f_timer)
            return await self.get_anidata(retry_count=retry_count+1, max_retries=max_retries)
        elif res_code in [500, 501, 502]:
            if retry_count >= max_retries:
                await rep.report(f"AniList Server API Error: {res_code}, Max retries reached. Skipping.", "error")
                return {}
            await rep.report(f"AniList Server API Error: {res_code}, Waiting 5s to Try Again !! (Retry {retry_count+1}/{max_retries})", "error")
            await asleep(5)
            return await self.get_anidata(retry_count=retry_count+1, max_retries=max_retries)
        else:
            await rep.report(f"AniList API Error: {res_code}", "error", log=False)
            return {}
    
class MangaLister:
    def __init__(self, manga_name: str, year: int) -> None:
        self.__api = "https://graphql.anilist.co"
        self.__manga_name = manga_name
        self.__manga_year = year
        self.__vars = {'search': self.__manga_name, 'seasonYear': self.__manga_year}

    def __update_vars(self, year=True) -> None:
        if year:
            self.__manga_year -= 1
            self.__vars['seasonYear'] = self.__manga_year
        else:
            self.__vars = {'search': self.__manga_name}

    async def post_data(self):
        global _manga_anilist_last_call
        async with _manga_anilist_lock:
            now = asyncio.get_event_loop().time()
            wait_time = 1 - (now - _manga_anilist_last_call)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            _manga_anilist_last_call = asyncio.get_event_loop().time()
        async with ClientSession() as sess:
            async with sess.post(self.__api, json={'query': MANGA_GRAPHQL_QUERY, 'variables': self.__vars}) as resp:
                res_code = resp.status
                resp_json = await resp.json()
                res_heads = resp.headers
                return res_code, resp_json, res_heads

    async def get_mangadata(self, retry_count=0, max_retries=Var.MAX_RETRIES):
        res_code, resp_json, res_heads = await self.post_data()
        while res_code == 404 and self.__manga_year > 2000:
            self.__update_vars()
            await rep.report(f"AniList Manga Query Name: {self.__manga_name}, Retrying with {self.__manga_year}", "warning", log=False)
            res_code, resp_json, res_heads = await self.post_data()
        if res_code == 404:
            self.__update_vars(year=False)
            res_code, resp_json, res_heads = await self.post_data()
        if res_code == 200 and resp_json:
            return resp_json.get('data', {}).get('Media', {}) or {}
        elif res_code == 429:
            if retry_count >= max_retries:
                return {}
            f_timer = int(res_heads.get('Retry-After', 60))
            await rep.report(f"AniList Manga API FloodWait: {res_code}, Sleeping for {f_timer} !! (Retry {retry_count+1}/{max_retries})", "error")
            await asleep(f_timer)
            return await self.get_mangadata(retry_count=retry_count+1, max_retries=max_retries)
        elif res_code in [500, 501, 502]:
            if retry_count >= max_retries:
                return {}
            await rep.report(f"AniList Manga Server API Error: {res_code}, Waiting 5s to Try Again !! (Retry {retry_count+1}/{max_retries})", "error")
            await asleep(5)
            return await self.get_mangadata(retry_count=retry_count+1, max_retries=max_retries)
        else:
            await rep.report(f"AniList Manga API Error: {res_code}", "error", log=False)
            return {}
    

class TextEditor:
    def __init__(self, name):
        self.__name = name
        self.adata = {}
        self.pdata = parse(name)

    async def load_anilist(self):
        cache_names = []
        is_movie = is_movie_title(self.__name)
        manual_name = MANUAL_ANILIST_NAMES.get(self.__name)
        if manual_name:
            ani_name = manual_name
            self.adata = await AniLister(ani_name, datetime.now().year, is_movie=is_movie).get_anidata()
            if self.adata:
                return
        for option in [(False, False), (False, True), (True, False), (True, True)]:
            ani_name = await self.parse_name(*option)
            if ani_name in cache_names:
                continue
            cache_names.append(ani_name)
            self.adata = await AniLister(ani_name, datetime.now().year, is_movie=is_movie).get_anidata()
            if self.adata:
                break

    async def load_jikan(self):
        async with ClientSession() as sess:
            query = self.pdata.get("anime_title")
            url = f"https://api.jikan.moe/v4/anime?q={query}"
            async with sess.get(url) as resp:
                data = await resp.json()
                if data.get("data"):
                    anime = data["data"][0]
                    anime_type = anime.get("type", "")
                    self.adata = {
                        "title": {
                            "english": anime.get("title_english"),
                            "romaji": anime.get("title"),
                            "native": anime.get("title_japanese"),
                        },
                        "format": anime.get("type"),
                        "genres": [g["name"] for g in anime.get("genres", [])],
                        "averageScore": anime.get("score"),
                        "status": anime.get("status"),
                        "episodes": anime.get("episodes"),
                        "description": anime.get("synopsis"),
                        "siteUrl": anime.get("url"),
                        "startDate": anime.get("aired", {}).get("from", {}),
                        "endDate": anime.get("aired", {}).get("to", {}),
                        "duration": anime.get("duration"),
                    }

    async def load_info(self):
        api = await db.get_api_source()
        if api == "jikan":
            await self.load_jikan()
            ani = AniLister(self.pdata.get("anime_title"), datetime.now().year)
            ani_data = await ani.get_anidata()
            if ani_data:
                self.adata["poster_url"] = f"https://img.anili.st/media/{ani_data.get('id')}"
                self.adata["id"] = ani_data.get("id")
            else:
                self.adata["poster_url"] = "https://envs.sh/E7p.png?isziC=1"
        else:
            await self.load_anilist()
            if self.adata:
                self.adata["poster_url"] = f"https://img.anili.st/media/{self.adata.get('id')}" if self.adata.get("id") else "https://envs.sh/E7p.png?isziC=1"
            else:
                self.adata["poster_url"] = "https://envs.sh/E7p.png?isziC=1"

    @handle_logs
    async def get_id(self):
        if (ani_id := self.adata.get('id')) and str(ani_id).isdigit():
            return ani_id
            
    @handle_logs
    async def parse_name(self, no_s=False, no_y=False):
        anime_name = self.pdata.get("anime_title")
        anime_season = self.pdata.get("anime_season")
        anime_year = self.pdata.get("anime_year")
        if is_movie_title(self.__name):
            name = anime_name or self.__name
            name = re.sub(r"(19|20)\d{2}", "", name)
            name = re.sub(r"\[.*?\]|\(.*?\)", "", name)
            name = re.sub(r"[._]", " ", name)
            name = re.sub(r"\s+", " ", name).strip()
            return name
        if anime_name:
            pname = anime_name
            if not no_s and self.pdata.get("episode_number") and anime_season:
                pname += f" {anime_season}"
            if not no_y and anime_year:
                pname += f" {anime_year}"
            return pname
        return self.__name
        
    @handle_logs
    async def get_poster(self):
        if anime_id := await self.get_id():
            return f"https://img.anili.st/media/{anime_id}"
        return "https://envs.sh/E7p.png?isziC=1"
        
    @handle_logs
    async def get_upname(self, qual=""):
        anime_name = self.pdata.get("anime_title") or self.__name
        codec = 'HEVC' if 'libx265' in ffargs[qual] else 'AV1' if 'libaom-av1' in ffargs[qual] else ''
        if self.pdata.get("audio_type"):
            lang = self.pdata["audio_type"]
        else:
            name_lower = self.__name.lower()
            if any(x in name_lower for x in ['multi-audio', 'multi audio']):
                lang = 'Multi'
            elif any(x in name_lower for x in ['dual-audio', 'dual audio']):
                lang = 'Dual'
            elif any(x in name_lower for x in ['english-audio', 'english audio', 'english dub', 'english-dub']):
                lang = 'Dub'
            else:
                lang = 'Sub'
                
        anime_season = str(ani_s[-1]) if (ani_s := self.pdata.get('anime_season', '01')) and isinstance(ani_s, list) else str(ani_s)
        ep_no = self.pdata.get("episode_number") if self.pdata.get("episode_number") else None
        if ep_no:
            ep_no_str = str(ep_no).zfill(2)
            return f"""[S{anime_season}-{str(ep_no_str)}] {anime_name} {'['+qual+'p]' if qual else ''} {'['+codec.upper()+'] ' if codec else ''}{'['+lang+']'} {Var.BRAND_UNAME}.mkv"""
        else:
            return f"""[S0-01] {anime_name} {'['+qual+'p]' if qual else ''} {'['+codec.upper()+'] ' if codec else ''}{'['+lang+']'} {Var.BRAND_UNAME}.mkv"""

    @handle_logs
    async def get_caption(self):
        def parse_date(date_val):
            if isinstance(date_val, dict):
                if date_val.get('day') and date_val.get('year') and date_val.get('month'):
                    return f"{month_name[date_val['month']]} {date_val['day']}, {date_val['year']}"
            elif isinstance(date_val, str) and date_val:
                try:
                    dt = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
                    return f"{month_name[dt.month]} {dt.day}, {dt.year}"
                except Exception:
                    return date_val
            return "N/A"

        sd = self.adata.get('startDate', {})
        ed = self.adata.get('endDate', {})
        startdate = parse_date(sd)
        enddate = parse_date(ed)
        titles = self.adata.get("title", {})
        ep_no = self.pdata.get("episode_number")

        ani_s = self.pdata.get('anime_season', '01')
        if isinstance(ani_s, list) and ani_s:
            anime_season = str(ani_s[-1])
        elif isinstance(ani_s, str) and ani_s.isdigit():
            anime_season = ani_s
        else:
            anime_season = '01'

        ep_no = self.pdata.get("episode_number")
        anime_format = self.adata.get("format", "").lower()
        is_movie = anime_format == "movie" or is_movie_title(self.__name)
        if is_movie:
            ep_no_str = "01"
        else:
            try:
                ep_no_str = str(int(ep_no)).zfill(2)
            except Exception:
                ep_no_str = "01"

        anime_name = self.pdata.get("anime_title") or self.__name
        titles = self.adata.get("title", {})
        title = titles.get('english') or titles.get('romaji') or titles.get('native') or anime_name
        status = self.adata.get("status", "RELEASING")
        genres = ", ".join(self.adata.get('genres') or [])
        duration = self.adata.get("duration", "N/A")
        if self.pdata.get("audio_type"):
            lang = self.pdata["audio_type"]
        else:
            name_lower = self.__name.lower()
            if any(x in name_lower for x in ['multi-audio', 'multi audio']):
                lang = 'Multi'
            elif any(x in name_lower for x in ['dual-audio', 'dual audio']):
                lang = 'English & Japanese'
            elif any(x in name_lower for x in ['english-audio', 'english audio', 'english dub', 'english-dub']):
                lang = 'English'
            else:
                lang = 'Japanese'

        if is_movie:
            return MOVIE_CAPTION.format(
                title=title,
                form=self.adata.get("format") or "N/A",
                genres=genres,
                avg_score=f"{sc}%" if (sc := self.adata.get('averageScore')) else "N/A",
                status=status,
                anime_season=anime_season,
                start_date=startdate,
                lang=lang,
                end_date=enddate,
                t_eps=self.adata.get("episodes") or "N/A",
                plot=(desc if (desc := self.adata.get("description") or "N/A") and len(desc) < 200 else desc[:200] + "..."),
                ep_no=ep_no_str,
                surl=self.adata.get("siteUrl"),
                dura=duration,
                cred=Var.BRAND_UNAME,
            )
        else:
            return CAPTION_FORMAT.format(
                title=title,
                form=self.adata.get("format") or "N/A",
                genres=genres,
                avg_score=f"{sc}%" if (sc := self.adata.get('averageScore')) else "N/A",
                status=status,
                anime_season=anime_season,
                start_date=startdate,
                lang=lang,
                end_date=enddate,
                t_eps=self.adata.get("episodes") or "N/A",
                plot=(desc if (desc := self.adata.get("description") or "N/A") and len(desc) < 200 else desc[:200] + "..."),
                ep_no=ep_no_str,
                surl=self.adata.get("siteUrl"),
                dura=duration,
                cred=Var.BRAND_UNAME,
            )

def parse_manga_title(raw_title: str) -> dict:
    title_parts = {
        'title': '',
        'volume': 'N/A',
        'chapter': 'N/A',
        'chapter_title': 'N/A'
    }
    
    if not raw_title:
        return title_parts

    parts = raw_title.split(":", 1)
    title_parts['title'] = parts[0].strip()

    vol_match = re.search(r'Vol\.?\s*(\d+)', raw_title, re.IGNORECASE)
    ch_match = re.search(r'Ch\.?\s*(\d+)', raw_title, re.IGNORECASE)
    
    if vol_match:
        title_parts['volume'] = f"Vol.{vol_match.group(1)}"
    if ch_match:
        title_parts['chapter'] = f"Ch.{ch_match.group(1)}"

    if len(parts) > 1:
        chapter_title = parts[1].strip()
        chapter_title = re.sub(r'^(?:Vol\.?\s*\d+\s*)?(?:Ch\.?\s*\d+\s*)?[-:]?\s*', '', chapter_title)
        if chapter_title:
            title_parts['chapter_title'] = chapter_title

    return title_parts

def get_manga_filename(raw_title: str, brand_channel: str) -> str:
    parts = parse_manga_title(raw_title)
    
    filename = "[FM] "

    if parts['volume'] != 'N/A' and parts['chapter'] != 'N/A':
        vol_num = parts['volume'].replace('Vol.', '')
        ch_num = parts['chapter'].replace('Ch.', '')
        filename += f"[V{vol_num}-C{ch_num}] "
    elif parts['chapter'] != 'N/A':
        ch_num = parts['chapter'].replace('Ch.', '')
        filename += f"[C{ch_num}] "
    
    filename += f"{parts['title']} {brand_channel}"
    return filename

async def get_manga_caption(manga_info: dict, raw_title: str) -> str:
    title_parts = parse_manga_title(raw_title)
    
    anilist_data = {
        'title': title_parts['title'],
        'status': manga_info.get('status', 'N/A'),
        'genres': ', '.join(manga_info.get('genres', [])) or 'N/A',
        'description': manga_info.get('description', 'N/A')
    }

    if anilist_data['description'] != 'N/A':
        anilist_data['description'] = re.sub(r'<[^>]+>', '', anilist_data['description'])
        desc_lines = [line for line in anilist_data['description'].split('\n') 
                     if not line.startswith(('(Source:', 'Note:'))]
        anilist_data['description'] = '\n'.join(desc_lines)
        if len(anilist_data['description']) > 200:
            anilist_data['description'] = anilist_data['description'][:200] + '...'

    caption = MANGA_CAPTION_FORMAT.format(
        title=anilist_data['title'],
        status=anilist_data['status'],
        volume=title_parts['volume'],
        chapter=title_parts['chapter'],
        genres=anilist_data['genres'],
        description=anilist_data['description']
    )

    return caption
