import asyncio
import base64
import json
import os

from aiohttp.web import HTTPNotFound, Response, StreamResponse

from guillotina import app_settings, configure
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


def _get_title(result):
    if 'data' in result:
        data = result['data']
        if 'Title' in data:
            return data['Title']
    if 'filename' in result:
        return result['filename'].rsplit('.', 1)[0]
    return result['name'].split('/')[-1].rsplit('.', 1)[0]


@configure.service(method='GET', name='@firetv',
                   permission='guillotina.AccessContent')
async def firetv_videos(context, request):
    base_url = str(request.url.origin())
    util = getUtility(IGlexUtility)
    db = await util.get_db()
    videos = db['videos']
    results = []
    for video in videos.values():
        data = video.get('data', {})
        image = data.get('Poster', f'{base_url}/app/movie.png')
        results.append({
            "id": video['id'],
            "title": _get_title(video),
            "thumbURL": image,
            "imgURL": image,
            "videoURL": f'{base_url}/@stream?id={video["id"]}',
            "categories": [
                data.get('Type', 'movie')
            ],
            "description": data.get('Plot', '')
        })
    return {'media': results}


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


async def get_video(video_id):
    util = getUtility(IGlexUtility)
    db = await util.get_db()
    try:
        return db['videos'][video_id]
    except IndexError:
        return None


@configure.service(method='GET', name='@stream',
                   permission='guillotina.AccessContent')
class Stream(DownloadService):

    async def download(self, video):
        resp = StreamResponse(
            status=200,
            headers={
                'Content-Disposition': f'attachment; filename="{video["filename"]}"'
            })
        resp.content_length = video['size']
        resp.content_type = 'video/' + self.get_video_ext(video)
        # request all data...
        written = 0
        await resp.prepare(self.request)
        while True:
            data = await downloader.get_range(
                video, written, written + (1024 * 1024 * 5), preload_end=False)
            if data:
                written += len(data)
                resp.write(data)
                await resp.drain()
            else:
                break
        return resp

    def get_video_ext(self, video):
        return video['name'].split('.')[-1].lower()


    async def __call__(self):
        request = self.request
        video = await get_video(self.request.GET['id'])
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
        video = await get_video(self.request.GET['id'])
        if video is None:
            return HTTPNotFound()
        return await self.download(video)


@configure.service(method='POST', name='@get-token',
                   permission='guillotina.AccessContent')
async def get_token(context, request):
    return auth.get_token(request)


@configure.service(method='POST', name='@edit-data',
                   permission='guillotina.AccessContent')
async def edit_data(context, request):
    req_data = await request.json()
    video = await get_video(req_data['id'])
    if video is None:
        return {'error': True}

    data = req_data['data']
    video['data'] = data

    if not os.path.exists(app_settings['download_folder']):
        os.mkdir(app_settings['download_folder'])
    storage_filename = '{}-info'.format(
        base64.b64encode(video['id'].encode('utf8')).decode('utf8'))
    filepath = os.path.join(app_settings['download_folder'],
                            storage_filename)
    with open(filepath, 'w') as fi:
        fi.write(json.dumps(data))
    return {'success': True}
