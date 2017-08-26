import asyncio
import logging

import aiohttp

from guillotina import app_settings, configure
from guillotina.async import IAsyncUtility
from guillotina.component import getUtility
from guillotina_gcloudstorage.interfaces import IGCloudBlobStore
from guillotina_gcloudstorage.storage import OBJECT_BASE_URL

from .db import DB

logger = logging.getLogger(__name__)


_ignored_titles = (
    'workout',
    'pilates',
    'all about',
    'songs',
    'insanity',
)


OMDB_URL = 'http://www.omdbapi.com/'


class IGlexUtility(IAsyncUtility):
    pass


@configure.utility(provides=IGlexUtility)
class GlexUtility:

    def __init__(self, settings={}, loop=None):
        self._settings = settings
        self._loop = loop

    async def initialize(self, app=None):
        self._queue = asyncio.Queue()
        self._db = DB()

        for prefix in app_settings["bucket_folders"]:
            await self.load_videos(prefix)

        while True:
            try:
                video = await self._queue.get()
                await self.get_video_data(video)
            except Exception:
                logger.warn(
                    'error getting video data',
                    exc_info=True)
                await asyncio.sleep(1)
            finally:
                self._queue.task_done()

    async def get_video_data(self, video):
        filename = video['name'].split('/')[-1]
        video['filename'] = filename
        name = '.'.join(filename.split('.')[:-1])
        for ignored in _ignored_titles:
            if ignored in name.lower():
                return
        tries = [name]
        if '-' in name:
            tries.append(name.split('-')[0].strip())
        for name in tries:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(OMDB_URL, params={
                    't': name,
                    'apikey': app_settings['omdb_api_key']
                })
                if resp.status == 200:
                    data = await resp.json()
                    if data['Response']:
                        video['data'] = data
                        return
                else:
                    data = await resp.text()
                    logger.warn(f'error getting video data for {name}, status: {resp.status}, text: {data}')
                    return

    async def finalize(self, app=None):
        pass

    async def get_db(self):
        return await self._db.get()

    async def load_videos(self, prefix='Movies/'):
        db = await self._db.get()
        if 'videos' not in db:
            db['videos'] = {}

        util = getUtility(IGCloudBlobStore)
        async with aiohttp.ClientSession() as session:
            access_token = await util.get_access_token()
            url = '{}/vangheem-media/o'.format(OBJECT_BASE_URL)
            resp = await session.get(url, headers={
                'AUTHORIZATION': 'Bearer %s' % access_token
            }, params={
                'prefix': prefix
            })
            data = await resp.json()

        for video in data['items']:
            filename = video['name']
            if filename == prefix:
                continue
            ext = filename.split('.')[-1].lower()
            if ext not in ('m4v', 'mov', 'mp4'):
                continue
            video = {
                'name': filename,
                'id': video['id'],
                'created': video['timeCreated'],
                'updated': video['updated'],
                'link': video['mediaLink'],
                'size': video['size'],
                'selfLink': video['selfLink']
            }
            db['videos'][video['id']] = video
            await self._queue.put(video)
            await self._db.save()
