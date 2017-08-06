from guillotina_gcloudstorage.storage import OBJECT_BASE_URL
from guillotina.component import getUtility
from guillotina_gcloudstorage.interfaces import IGCloudBlobStore
from guillotina import configure
from guillotina.async import IAsyncUtility
import asyncio, logging, aiohttp
from .db import DB
from guillotina import app_settings


logger = logging.getLogger(__name__)


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
                self._queue.task_done()
            except Exception:
                logger.warn(
                    'Error invalidating queue',
                    exc_info=True)
                await asyncio.sleep(1)

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
