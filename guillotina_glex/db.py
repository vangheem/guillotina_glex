import json
import asyncio
import os


FILENAME = 'db.json'


class DB:

    def __init__(self):
        self._lock = asyncio.Lock()
        self._data = None

    async def get(self):
        async with self._lock:
            if self._data is None:
                if os.path.exists(FILENAME):
                    with open(FILENAME) as fi:
                        self._data = json.loads(fi.read())
                else:
                    self._data = {}
        return self._data

    async def save(self):
        async with self._lock:
            with open(FILENAME, 'w') as fi:
                fi.write(json.dumps(self._data))
