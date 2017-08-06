from guillotina_gcloudstorage.interfaces import IGCloudBlobStore
from guillotina.component import getUtility
import aiohttp
import os
from guillotina import app_settings
import asyncio
import base64


def _get_filename(video):
    return base64.b64encode(video['id'].encode('utf8')).decode('utf8')


_tasks = {}


END_SIZE = 1024 * 1024 * 10


async def download_task_end(video):
    util = getUtility(IGCloudBlobStore)
    if not os.path.exists(app_settings['download_folder']):
        os.mkdir(app_settings['download_folder'])
    filepath = os.path.join(app_settings['download_folder'],
                            _get_filename(video))

    print(f'Downloading {video["id"]} end')
    async with aiohttp.ClientSession() as session:
        # peek ahead and store...
        api_resp_end = await session.get(video['link'], headers={
            'AUTHORIZATION': 'Bearer %s' % await util.get_access_token(),
            'Range': f'bytes={int(video["size"]) - END_SIZE}-'
        })
        filepath_end = filepath + '-end'
        fi_end = open(filepath_end, 'wb')
        fi_end.write(await api_resp_end.content.read())
        fi_end.close()
    print(f'Finished Downloading {video["id"]} end')


async def download_task(video):
    util = getUtility(IGCloudBlobStore)
    if not os.path.exists(app_settings['download_folder']):
        os.mkdir(app_settings['download_folder'])
    filepath = os.path.join(app_settings['download_folder'],
                            _get_filename(video))
    fi = open(filepath, 'wb')
    os.utime(filepath, None)  # force filename...

    print(f'Downloading {video["id"]}')
    async with aiohttp.ClientSession() as session:
        api_resp = await session.get(video['link'], headers={
            'AUTHORIZATION': 'Bearer %s' % await util.get_access_token()
        })

        count = 0
        # file_size = int(video['size'])
        while True:
            chunk = await api_resp.content.read(1024 * 1024 * 5)
            if len(chunk) > 0:
                count += len(chunk)
                # print("Download {}%.".format(int((count / file_size) * 100)))
                fi.write(chunk)
                fi.flush()
                os.fsync(fi.fileno())
            else:
                break
    fi.close()
    print(f'Finished download {video["id"]}')
    if video['id'] in _tasks:
        del _tasks[video['id']]


async def get_range(video, start, end):
    if end > (int(video['size']) + 1):
        return b''

    filepath = os.path.join(app_settings['download_folder'],
                            _get_filename(video))
    if not os.path.exists(filepath):
        _tasks[video['id']] = [
            asyncio.Task(download_task(video)),
            asyncio.Task(download_task_end(video))
        ]

    while not os.path.exists(filepath):
        print(f'waiting for file {filepath}')
        await asyncio.sleep(0.1)

    st = os.stat(filepath)
    current_size = st.st_size
    if current_size != int(video['size']) and video['id'] not in _tasks:
        # if video not done, it should be in tasks,
        print(f'Stale unfinished video, restarting {video["id"]}')
        os.remove(filepath)
        return await get_range(video, start, end)

    while current_size < (end - 1):
        # need to wait for it to download
        start_end = (int(video['size']) - END_SIZE)
        if (start > start_end and os.path.exists(filepath + '-end') and
                os.stat(filepath + '-end').st_size > 0):
            fi = open(filepath + '-end', 'rb')
            fi.seek(start - start_end)
            data = fi.read(end - start)
            fi.close()
            return data
        await asyncio.sleep(0.2)
        st = os.stat(filepath)
        current_size = st.st_size

    fi = open(filepath, 'rb')
    fi.seek(start)
    data = fi.read(end - start)
    fi.close()
    return data
