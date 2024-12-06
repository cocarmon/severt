import aiofiles
from http.client import HTTPMessage
from util.queue import event_queue
from config import CONFIG


class WriteMessage:
    def __init__(self, sock, addr, sel) -> None:
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self.event: HTTPMessage | None = None
        self._send_buffer = b""

    async def event_listener(self) -> None:
        if len(event_queue) > 0:
            event = event_queue.popleft()
            self.event = event
            await self._process_file()

    async def _process_file(self):
        async with aiofiles.open(
            CONFIG["server"]["location"] + self.event.get("location"), mode="rb"
        ) as f:
            content = await f.read()
        header_bytes = str.encode(
            f"HTTP/1.1 200 OK\r\ncontent-type:text/html\r\ncontent-encoding:Identity\r\ncontent-length: {len(content)}\r\n\r\n"
        )
        self._send_buffer += header_bytes + content
        self._write()

    def _write(self):
        if self._send_buffer:
            sent = self.sock.send(self._send_buffer)
            self._send_buffer = self._send_buffer[sent:]
            if sent and not self._send_buffer:
                self.sel.unregister(self.sock)
                self.sock.close()
