from motor.motor_asyncio import AsyncIOMotorClient
from bot import Var
import datetime 
import asyncio

class MongoDB:
    def __init__(self, uri, database_name):
        self.__client = AsyncIOMotorClient(uri)
        self.__db = self.__client[database_name]
        self.__animes = self.__db.animes[Var.BOT_TOKEN.split(':')[0]]
        self.__anime_channels = self.__db.anime_channels
        self.__manga_channels = self.__db.manga_channels
        self.__manga_banners = self.__db.manga_banners
        self.__ffmpeg_configs = self.__db.ffmpeg_configs

    async def add_user(self, user_id: int):
        await self.__db.users.update_one({'_id': user_id}, {'$set': {'_id': user_id}}, upsert=True)

    async def getAnime(self, ani_id):
        botset = await self.__animes.find_one({'_id': ani_id})
        return botset or {}

    async def saveAnime(self, ani_id, ep, qual, post_id=None):
        if ep is None:
            ep = "default_ep"
        ep = str(ep)
        allowed_quals = Var.QUALS + ["pdf"]
        quals = (await self.getAnime(ani_id)).get(ep, {qual: False for qual in Var.QUALS})
        if qual not in allowed_quals:
            print(f"Error: Invalid quality type ({qual})")
            return
        quals[qual] = True
        timestamp = datetime.datetime.now()
        quals["timestamp"] = timestamp
        quals = {key if key is not None else "default_key": value for key, value in quals.items()}

        try:
            await self.__animes.update_one({'_id': ani_id}, {'$set': {ep: quals}}, upsert=True)
            if post_id:
                await self.__animes.update_one({'_id': ani_id}, {'$set': {"msg_id": post_id}}, upsert=True)

            print(f"Successfully updated anime {ani_id} episode {ep}")

        except Exception as e:
            print(f"Error updating anime {ani_id} episode {ep}: {e}")

    async def add_anime_channel_mapping(self, anime_name: str, channel: str):
        await self.__anime_channels.update_one(
            {"anime_name": anime_name.lower()},
            {"$set": {"channel_id": channel}},
            upsert=True
        )

    async def remove_anime_channel_mapping(self, anime_name: str, channel: str | int | None = None):
        query = {"anime_name": anime_name.lower()}
        if channel is not None:
            query["channel_id"] = int(channel) if str(channel).lstrip("-").isdigit() else channel
        await self.__anime_channels.delete_one(query)

    async def get_anime_channel(self, anime_name: str) -> int | None:
        entry = await self.__anime_channels.find_one({"anime_name": anime_name.lower()})
        return entry["channel_id"] if entry else None
        
    async def get_all_anime_channels(self):
        try:
            anime_channels = await self.__anime_channels.find().to_list(length=None)
            
            return {entry['anime_name']: entry['channel_id'] for entry in anime_channels if 'channel_id' in entry}
        except Exception as e:
            print(f"Error fetching anime channels: {e}")
            return {}

    async def set_api_source(self, api_name: str):
        await self.__db.settings.update_one({"_id": "api_source"}, {"$set": {"api": api_name}}, upsert=True)

    async def get_api_source(self) -> str:
        doc = await self.__db.settings.find_one({"_id": "api_source"})
        return doc["api"] if doc and "api" in doc else "anilist"

    async def set_anime_banner(self, anime_name: str, banner_url: str):
        await self.__anime_channels.update_one(
            {"anime_name": anime_name.lower()},
            {"$set": {"banner_url": banner_url}},
            upsert=True
        )

    async def get_anime_banner(self, anime_name: str) -> str | None:
        entry = await self.__anime_channels.find_one({"anime_name": anime_name.lower()})
        return entry["banner_url"] if entry and "banner_url" in entry else None

    async def del_anime_banner(self, anime_name: str):
        await self.__anime_channels.update_one(
            {"anime_name": anime_name.lower()},
            {"$unset": {"banner_url": ""}}
        )

    async def list_anime_banners(self):
        banners = []
        async for doc in self.__anime_channels.find({"banner_url": {"$exists": True}}):
            banners.append((doc["anime_name"], doc["banner_url"]))
        return banners
        
    async def set_global_thumb(self, file_id: str):
        await self.__db.settings.update_one({"_id": "global_thumb"}, {"$set": {"file_id": file_id}}, upsert=True)

    async def get_global_thumb(self) -> str | None:
        doc = await self.__db.settings.find_one({"_id": "global_thumb"})
        return doc["file_id"] if doc and "file_id" in doc else None

    async def del_global_thumb(self):
        await self.__db.settings.delete_one({"_id": "global_thumb"})

    async def set_auto_del(self, value: bool):
        await self.__db.settings.update_one({"_id": "auto_del"}, {"$set": {"value": value}}, upsert=True)

    async def get_auto_del(self) -> bool:
        doc = await self.__db.settings.find_one({"_id": "auto_del"})
        return doc["value"] if doc and "value" in doc else Var.AUTO_DEL

    async def set_del_timer(self, value: int):
        await self.__db.settings.update_one({"_id": "del_timer"}, {"$set": {"value": value}}, upsert=True)

    async def get_del_timer(self) -> int:
        doc = await self.__db.settings.find_one({"_id": "del_timer"})
        return doc["value"] if doc and "value" in doc else Var.DEL_TIMER

    async def set_sticker_id(self, sticker_id: str):
        await self.__db.settings.update_one({"_id": "sticker_id"}, {"$set": {"value": sticker_id}}, upsert=True)

    async def get_sticker_id(self) -> str | None:
        doc = await self.__db.settings.find_one({"_id": "sticker_id"})
        return doc["value"] if doc and "value" in doc else None

    async def del_sticker_id(self):
        await self.__db.settings.delete_one({"_id": "sticker_id"})

    async def set_start_photo(self, value: str):
        await self.__db.settings.update_one({"_id": "start_photo"}, {"$set": {"value": value}}, upsert=True)

    async def get_start_photo(self) -> str | None:
        doc = await self.__db.settings.find_one({"_id": "start_photo"})
        return doc["value"] if doc and "value" in doc else None

    async def set_send_schedule(self, value: bool):
        await self.__db.settings.update_one({"_id": "send_schedule"}, {"$set": {"value": value}}, upsert=True)

    async def get_send_schedule(self) -> bool:
        doc = await self.__db.settings.find_one({"_id": "send_schedule"})
        return doc["value"] if doc and "value" in doc else Var.SEND_SCHEDULE

    @property
    def fsub(self):
        return self.__db.fsub

    async def add_fsub(self, channel_id: int):
        await self.fsub.update_one({'_id': channel_id}, {'$set': {'_id': channel_id}}, upsert=True)

    async def del_fsub(self, channel_id: int):
        await self.fsub.delete_one({'_id': channel_id})

    async def list_fsubs(self):
        docs = await self.fsub.find().to_list(length=None)
        return [doc['_id'] for doc in docs]

    async def set_fsub_mode(self, channel_id: int, mode: str):
        await self.fsub.update_one({'_id': channel_id}, {'$set': {'mode': mode}}, upsert=True)

    async def get_fsub_mode(self, channel_id: int) -> str:
        doc = await self.fsub.find_one({'_id': channel_id})
        return doc.get('mode', 'normal') if doc else 'normal'

    async def list_fsubs_with_mode(self):
        docs = await self.fsub.find().to_list(length=None)
        return [(doc['_id'], doc.get('mode', 'normal')) for doc in docs]

    async def set_channel_creation(self, value: bool):
        await self.__db.settings.update_one({"_id": "channel_creation"}, {"$set": {"enabled": value}}, upsert=True)

    async def get_channel_creation(self) -> bool:
        doc = await self.__db.settings.find_one({"_id": "channel_creation"})
        return doc.get("enabled", False) if doc else False

    async def set_encoding(self, value: bool):
        await self.__db.settings.update_one({"_id": "encoding"}, {"$set": {"enabled": value}}, upsert=True)

    async def get_encoding(self) -> bool:
        doc = await self.__db.settings.find_one({"_id": "encoding"})
        return doc.get("enabled", True) if doc else True

    async def set_mode(self, mode: str):
        await self.__db.settings.update_one({"_id": "mode"}, {"$set": {"value": mode}}, upsert=True)

    async def get_mode(self) -> str:
        doc = await self.__db.settings.find_one({"_id": "mode"})
        return doc["value"] if doc and "value" in doc else "anime"

    async def add_manga_channel_mapping(self, manga_name: str, channel: str):
        await self.__manga_channels.update_one(
            {"manga_name": manga_name.lower()},
            {"$set": {"channel_id": channel}},
            upsert=True
        )

    async def remove_manga_channel_mapping(self, manga_name: str, channel: str | int | None = None):
        query = {"manga_name": manga_name.lower()}
        if channel is not None:
            query["channel_id"] = int(channel) if str(channel).lstrip("-").isdigit() else channel
        await self.__manga_channels.delete_one(query)

    async def get_manga_channel(self, manga_name: str) -> int | None:
        entry = await self.__manga_channels.find_one({"manga_name": manga_name.lower()})
        return entry["channel_id"] if entry else None
        
    async def get_all_manga_channels(self):
        try:
            manga_channels = await self.__manga_channels.find().to_list(length=None)
            return {entry['manga_name']: entry['channel_id'] for entry in manga_channels if 'channel_id' in entry}
        except Exception as e:
            print(f"Error fetching manga channels: {e}")
            return {}

    async def set_manga_banner(self, manga_name: str, banner_url: str):
        await self.__manga_banners.update_one(
            {"manga_name": manga_name.lower()},
            {"$set": {"banner_url": banner_url}},
            upsert=True
        )

    async def get_manga_banner(self, manga_name: str) -> str | None:
        entry = await self.__manga_banners.find_one({"manga_name": manga_name.lower()})
        return entry["banner_url"] if entry else None

    async def del_manga_banner(self, manga_name: str):
        await self.__manga_banners.delete_one({"manga_name": manga_name.lower()})

    async def list_manga_banners(self):
        banners = await self.__manga_banners.find().to_list(length=None)
        return [(banner["manga_name"], banner["banner_url"]) for banner in banners]

    async def set_anime_ffmpeg(self, anime_name: str, ffmpeg_config: str):
        await self.__ffmpeg_configs.update_one(
            {"anime_name": anime_name.lower()},
            {"$set": {"config": ffmpeg_config}},
            upsert=True
        )

    async def get_anime_ffmpeg(self, anime_name: str) -> str | None:
        entry = await self.__ffmpeg_configs.find_one({"anime_name": anime_name.lower()})
        return entry["config"] if entry else None

    async def del_anime_ffmpeg(self, anime_name: str):
        await self.__ffmpeg_configs.delete_one({"anime_name": anime_name.lower()})

    async def list_anime_ffmpeg(self):
        configs = await self.__ffmpeg_configs.find().to_list(length=None)
        return [(config["anime_name"], config["config"]) for config in configs]

    async def set_upload_mode(self, mode: str):
        await self.__db.settings.update_one(
            {"_id": "upload_mode"},
            {"$set": {"mode": mode}},
            upsert=True
        )

    async def get_upload_mode(self) -> str:
        doc = await self.__db.settings.find_one({"_id": "upload_mode"})
        return doc["mode"] if doc else "high_end"

    async def set_low_end_rename(self, value: bool):
        await self.__db.settings.update_one({"_id": "low_end_rename"}, {"$set": {"enabled": value}}, upsert=True)

    async def get_low_end_rename(self) -> bool:
        doc = await self.__db.settings.find_one({"_id": "low_end_rename"})
        return doc.get("enabled", True) if doc else True

    async def save_rss_link(self, link_type: str, rss_link: str, quality: str = None):
        doc = {"type": link_type, "link": rss_link}
        if quality:
            doc["quality"] = quality
        await self.__db.rss_links.update_one(
            doc,
            {"$set": doc},
            upsert=True
        )

    async def mark_episode_completed(self, ani_id, ep):
        if ep is None:
            ep = "default_ep"
        ep = str(ep)
        try:
            await self.__animes.update_one(
                {'_id': ani_id},
                {'$set': {f"{ep}.completed": True}},
                upsert=True
            )
            print(f"Marked anime {ani_id} episode {ep} as completed")
        except Exception as e:
            print(f"Error marking episode as completed: {e}")

    async def save_rss_links_bulk(self, links: list[dict]):
        if not links:
            return
        operations = []
        for link in links:
            doc = {"type": link["type"], "link": link["link"]}
            if "quality" in link and link["quality"]:
                doc["quality"] = link["quality"]
            operations.append(
                self.__db.rss_links.update_one(
                    doc,
                    {"$set": doc},
                    upsert=True
                )
            )
        await asyncio.gather(*operations)

    async def add_admin(self, user_id: int):
        await self.__db.settings.update_one(
            {"_id": "admins"},
            {"$addToSet": {"ids": user_id}},
            upsert=True
        )

    async def get_admins(self):
        doc = await self.__db.settings.find_one({"_id": "admins"})
        return doc.get("ids", []) if doc else []
    
    async def remove_admin(self, user_id: int):
        await self.__db.settings.update_one(
            {"_id": "admins"},
            {"$pull": {"ids": user_id}}
        )

    async def delete_rss_link(self, link_type: str, link: str):
        await self.__db.rss_links.delete_one({"type": link_type, "link": link})

    async def delete_all_ffmpeg_configs(self):
        await self.__ffmpeg_configs.delete_many({})

    async def delete_all_anime_mappings(self):
        await self.__anime_channels.delete_many({})

    async def delete_all_anime_banners(self):
        await self.__anime_channels.update_many({}, {"$unset": {"banner_url": ""}})

    async def get_users_count(self):
        users = await self.__db.users.count_documents({}) if "users" in await self.__db.list_collection_names() else 0
        return users

    async def get_all_users(self):
        if "users" not in await self.__db.list_collection_names():
            return []
        users = await self.__db.users.find().to_list(length=None)
        return [u["_id"] for u in users if "_id" in u]

    async def get_all_rss_links(self):
        cursor = self.__db.rss_links.find({})
        links = []
        async for doc in cursor:
            links.append(doc)
        return links

    async def delete_all_manga_mappings(self):
        await self.__manga_channels.delete_many({})

    async def delete_all_manga_banners(self):
        await self.__manga_banners.delete_many({})

    async def add_user(self, user_id: int):
        await self.__db.users.update_one({'_id': user_id}, {'$set': {'_id': user_id}}, upsert=True)

        async def reboot(self):
            await self.__animes.drop()
        
        async def delete_anime_by_id(self, ani_id):
            await self.__animes.delete_one({"_id": ani_id})

db = MongoDB(Var.MONGO_URI, Var.MONGO_NAME)
