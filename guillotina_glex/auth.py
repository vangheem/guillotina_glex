import uuid
from guillotina.utils import get_authenticated_user
from lru import LRU
from guillotina.auth.extractors import BasePolicy
from guillotina.auth import find_user


_tokens = LRU(500)


def get_token(request):
    user = get_authenticated_user(request)
    token = uuid.uuid4().hex
    _tokens[token] = user.id
    return token


class TokenAuthPolicy(BasePolicy):
    name = 'token'

    async def extract_token(self):
        if 'token' not in self.request.GET:
            return None
        token = self.request.GET['token']
        if token not in _tokens:
            return None
        return {
            "type": 'token',
            "id": _tokens[token],
            "token": token
        }


class TokenValidator:

    for_validators = ('token',)

    def __init__(self, request):
        self.request = request

    async def validate(self, token):
        if token.get('type') != 'token':
            return
        user = await find_user(self.request, token)
        if user is not None and user.id == token['id']:
            return user
