import asyncio

from guillotina import configure
from guillotina.component import getUtility
from guillotina.utils import get_dotted_name
from lru import LRU
from .utility import IGlexUtility
from aiohttp.web import StreamResponse, HTTPNotFound, Response
from . import downloader
from . import auth
from guillotina.api.service import DownloadService


_cache = LRU(100)


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
        'Accept-Ranges': 'bytes',
        'Content-Length': video['size']})


@configure.service(method='GET', name='@download',
                   permission='guillotina.AccessContent')
class Download(DownloadService):
    async def __call__(self):
        request = self.request
        util = getUtility(IGlexUtility)
        db = await util.get_db()
        try:
            video = db['videos'][request.GET['id']]
        except IndexError:
            return HTTPNotFound()

        status = 200
        if 'Range' in request.headers:
            status = 206

        name = video['name']
        ext = name.split('.')[-1].lower()

        if status == 200:
            resp = StreamResponse(status=status)
            resp.content_length = video['size']
            resp.content_type = 'video/' + ext
            # request all data...
            written = 0
            await resp.prepare(request)
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
        else:
            range_val = request.headers['Range']
            start, _, end = range_val.replace('bytes=', '').partition('-')
            start = int(start)
            if not end:
                end = min(start + (1024 * 1024 * 5), int(video['size']) - 1)
            end = int(end)

            data = await downloader.get_range(video, start, end + 1)
            resp = Response(
                headers={
                    'Accept-Ranges': 'Bytes',
                    'Content-Range': f'bytes {start}-{end}/{video["size"]}',
                },
                status=206,
                body=data,
                content_type='video/' + ext)
            await resp.prepare(request)
            return resp


@configure.service(method='POST', name='@get-token',
                   permission='guillotina.AccessContent')
async def get_token(context, request):
    return auth.get_token(request)
