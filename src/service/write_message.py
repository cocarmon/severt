import os
import gzip
from config import CONFIG
from http.client import HTTPMessage
from util.queue import event_queue


class WriteMessage:
    def __init__(self, sock, addr, sel) -> None:
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self.event: HTTPMessage | None = None
        self._send_buffer = b""

    def event_listener(self) -> None:
        if len(event_queue) > 0:
            event = event_queue.popleft()
            self.event = event
            self._process_request()

    def _process_request(self):
        # Check if server is setup for reverse proxy if not and gets a request other than GET return 405
        if not CONFIG.forward and self.event.get("Method") == "GET":
            content_type = ""
            content = b""
            base_path = CONFIG.location
            requested_file = self.event.get("Location")
            file_extension = requested_file.split(".")[-1]
            if file_extension == "png":
                content_type = "image"
            elif file_extension == "html":
                content_type = "text/html"
            elif file_extension == "css":
                content_type = "text/css"

            if requested_file == "/":
                requested_file = "/index.html"

            full_path = base_path + requested_file

            if not os.path.exists(full_path):
                header_bytes = str.encode("HTTP/1.1 404 Not Found\r\n\r\n")
            else:
                # replace with threads
                with open(full_path, mode="rb") as f:
                    raw_bytes = f.read()
                content = gzip.compress(raw_bytes)
                header_bytes = str.encode(
                    f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-encoding:gzip\r\ncontent-length: {len(content)}\r\n\r\n"
                )
        else:
            header_bytes = str.encode("HTTP/1.1 405 Method Not Allowed\r\n\r\n")

        self._send_buffer += header_bytes + content
        self._write()

    def _write(self):
        if self._send_buffer:
            sent = self.sock.send(self._send_buffer)
            self._send_buffer = self._send_buffer[sent:]
            if sent and not self._send_buffer:
                self.sel.unregister(self.sock)
                self.sock.close()
