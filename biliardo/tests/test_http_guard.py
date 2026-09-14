import asyncio
import unittest

from starlette.responses import Response, StreamingResponse

from biliardo.http_guard import LocalGuard


def scope(method='GET', host='127.0.0.1:8766', **headers):
    return {'type': 'http', 'method': method, 'asgi': {'spec_version': '2.3'},
            'headers': [(k.encode(), v.encode()) for k, v in {'host': host, **headers}.items()]}


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, request_scope):
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': b''}
        async def send(message):
            messages.append(message)
        await LocalGuard(Response('ok'), lambda: 'local-token')(request_scope, receive, send)
        return messages

    async def test_preserves_host_origin_and_token_checks(self):
        cases = [
            (scope(), 200),
            (scope(host='remote.example'), 403),
            (scope('POST'), 403),
            (scope('POST', **{'x-biliardo-token': 'wrong'}), 403),
            (scope('POST', **{'x-biliardo-token': 'local-token', 'origin': 'https://remote.example'}), 403),
            (scope('POST', **{'x-biliardo-token': 'local-token', 'origin': 'http://127.0.0.1:8766'}), 200),
        ]
        for request_scope, status in cases:
            response = await self.request(request_scope)
            self.assertEqual(response[0]['status'], status)
            headers = dict(response[0]['headers'])
            self.assertEqual(headers[b'cache-control'], b'no-store')
            self.assertEqual(headers[b'x-content-type-options'], b'nosniff')

    async def test_stream_first_frame_is_immediate_and_disconnect_cleans_up(self):
        delivered, closed = asyncio.Event(), asyncio.Event()
        async def frames():
            try:
                yield b'first frame'
                await asyncio.sleep(30)
            finally:
                closed.set()
        async def receive():
            await delivered.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            if message['type'] == 'http.response.body':
                self.assertEqual(message['body'], b'first frame')
                delivered.set()
        app = LocalGuard(StreamingResponse(frames()), lambda: 'local-token')
        await asyncio.wait_for(app(scope(), receive, send), 1)
        self.assertTrue(delivered.is_set())
        self.assertTrue(closed.is_set())
