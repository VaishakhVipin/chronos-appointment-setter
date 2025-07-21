import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch
from services.assembly import stream_transcribe

class DummyAudioIter:
    def __init__(self, chunks):
        self.chunks = chunks
        self.idx = 0
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self.idx < len(self.chunks):
            chunk = self.chunks[self.idx]
            self.idx += 1
            await asyncio.sleep(0.01)
            return chunk
        raise StopAsyncIteration

@pytest.mark.asyncio
async def test_stream_transcribe_final_only():
    dummy_chunks = [b'pcm1', b'pcm2']
    dummy_audio_iter = DummyAudioIter(dummy_chunks)
    # Mock websockets.connect and ws.recv
    fake_msgs = [
        '{"message_type": "PartialTranscript", "text": "hello"}',
        '{"message_type": "FinalTranscript", "text": "hello world"}',
        '{"message_type": "SessionTerminated"}'
    ]
    async def fake_recv():
        for msg in fake_msgs:
            await asyncio.sleep(0.01)
            yield msg
    class FakeWS:
        def __init__(self):
            self.sent = []
            self.recv_iter = iter(fake_msgs)
        async def send(self, data):
            self.sent.append(data)
        async def recv(self):
            try:
                return next(self.recv_iter)
            except StopIteration:
                raise asyncio.CancelledError()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
    with patch('services.assembly.websockets.connect', return_value=FakeWS()):
        results = []
        async for text in stream_transcribe(dummy_audio_iter):
            results.append(text)
        assert results == ["hello world"] 