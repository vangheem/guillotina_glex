import asyncio

from aiohttp.web import HTTPNotFound, Response, StreamResponse

from guillotina import configure
from guillotina.api.service import DownloadService
from guillotina.component import getUtility
from guillotina.utils import get_dotted_name
from lru import LRU

from . import auth, downloader
from .utility import IGlexUtility

_cache = LRU(100)
CHUNK_SIZE = 1024 * 1024 * 1


def invalidate(key):
    if key in _cache:
        del _cache[key]


def cache(duration=10 * 60):
    def decorator(original_func):
        key = get_dotted_name(original_func)

        async def func(*args):
            if key in _cache:
                return _cache[key]
            resp = await original_func(*args)
            _cache[key] = resp
            loop = asyncio.get_event_loop()
            loop.call_later(duration, invalidate, key)
            return resp
        return func
    return decorator


@configure.service(method='GET', name='@videos',
                   permission='guillotina.AccessContent')
async def videos(context, request):
    util = getUtility(IGlexUtility)
    db = await util.get_db()
    return db['videos']


@configure.service(method='HEAD', name='@stream',
                   permission='guillotina.AccessContent')
async def stream_head(context, request):
    util = getUtility(IGlexUtility)
    db = await util.get_db()
    try:
        video = db['videos'][request.GET['id']]
    except IndexError:
        return HTTPNotFound()
    return Response(headers={
        'Accept-Ranges': 'bytes',
        'Content-Length': video['size']})


@configure.service(method='HEAD', name='@download',
                   permission='guillotina.AccessContent')
async def download_head(context, request):
    util = getUtility(IGlexUtility)
    db = await util.get_db()
    try:
        video = db['videos'][request.GET['id']]
    except IndexError:
        return HTTPNotFound()
    return Response(headers={
        'Content-Length': video['size']})


@configure.service(method='GET', name='@stream',
                   permission='guillotina.AccessContent')
class Stream(DownloadService):

    async def download(self, video):
        resp = StreamResponse(status=200)
        resp.content_length = video['size']
        resp.content_type = 'video/' + self.get_video_ext(video)
        # request all data...
        written = 0
        await resp.prepare(self.request)
        while True:
            data = await downloader.get_range(
                video, written, 1024 * 1024 * 5)
            if data:
                written += len(data)
                resp.write(data)
                await resp.drain()
            else:
                break
        return resp

    def get_video_ext(self, video):
        return video['name'].split('.')[-1].lower()

    async def get_video(self):
        util = getUtility(IGlexUtility)
        db = await util.get_db()
        try:
            return db['videos'][self.request.GET['id']]
        except IndexError:
            return None

    async def __call__(self):
        request = self.request
        video = await self.get_video()
        if video is None:
            return HTTPNotFound()

        status = 200
        if 'Range' in request.headers:
            status = 206

        if status == 200:
            return await self.download(video)
        else:
            range_val = request.headers['Range']
            start, _, end = range_val.replace('bytes=', '').partition('-')
            start = int(start)
            if not end:
                end = min(start + CHUNK_SIZE, int(video['size']) - 1)
            end = int(end)

            data = await downloader.get_range(video, start, end + 1)
            resp = Response(
                headers={
                    'Accept-Ranges': 'Bytes',
                    'Content-Range': f'bytes {start}-{end}/{video["size"]}',
                },
                status=206,
                body=data,
                content_type='video/' + self.get_video_ext(video))
            await resp.prepare(request)
            return resp


@configure.service(method='GET', name='@download',
                   permission='guillotina.AccessContent')
class Download(Stream):
    async def __call__(self):
        video = await self.get_video()
        if video is None:
            return HTTPNotFound()
        return await self.download(video)


@configure.service(method='POST', name='@get-token',
                   permission='guillotina.AccessContent')
async def get_token(context, request):
    return auth.get_token(request)
