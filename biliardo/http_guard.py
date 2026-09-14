"""Local request checks without buffering or relaying streaming responses."""
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response


class LocalGuard:
    def __init__(self, app, get_token):
        self.app, self.get_token = app, get_token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        host = headers.get('host', '').split(':')[0]
        rejection = None
        if host not in ['127.0.0.1', 'localhost', 'testserver']:
            rejection = 'Localhost only'
        elif scope['method'] not in ['GET', 'HEAD']:
            if headers.get('x-biliardo-token') != self.get_token():
                rejection = 'Token di sessione richiesto'
            origin = headers.get('origin')
            if origin and origin not in ['http://127.0.0.1:8766', 'http://localhost:8766']:
                rejection = 'Origine non valida'

        async def send_headers(message):
            if message['type'] == 'http.response.start':
                response_headers = MutableHeaders(scope=message)
                response_headers['Cache-Control'] = 'no-store'
                response_headers['X-Content-Type-Options'] = 'nosniff'
            await send(message)

        if rejection:
            await Response(rejection, 403)(scope, receive, send_headers)
        else:
            await self.app(scope, receive, send_headers)
