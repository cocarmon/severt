import os
import select
import platform
from config import CONFIG
from datetime import datetime, timezone
from http.client import HTTPMessage
from util.queue import event_queue
from util.mime import mime_mapping


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

    def _is_valid_headers(self):
        if not self.event.get("Host"):
            return False
        return True

    def _get_request(self):
        content = b""
        content_encoding = "Identity"
        location = self.event.get("Location")

        requested_file = "/index.html" if location == "/" else location
        extension = requested_file.split(".")[-1]
        full_path = CONFIG.location + requested_file

        content_type = mime_mapping.get(f".{extension}", "application/octet-stream")
        gmt_string = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        header_bytes = f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-encoding:{content_encoding}\r\ndate:{gmt_string}\r\nconnection:keep-alive\r\nKeep-Alive: timeout=10, max=100\r\n"

        if os.stat(full_path).st_size < 4194304:
            with open(full_path, mode="rb") as f:
                content = f.read()
                header_bytes = str.encode(
                    header_bytes + f"content-length:{len(content)}\r\n\r\n"
                )
            self._send_buffer += header_bytes + content
        else:
            header_bytes = str.encode(
                header_bytes + "transfer-encoding:chunked\r\n\r\n"
            )
            with open(full_path, mode="rb") as f:
                self._send_buffer += header_bytes
                while True:
                    content = f.read(2048)
                    prefix = str.encode(f"{len(content):x}\r\n")
                    self._send_buffer += prefix + content + b"\r\n"
                    self._write()
                    if not content:
                        break
            # Signals to the client socket that it's the end of the data
            self._send_buffer += b"0\r\n\r\n"

    def _head_request(self):
        content = b""
        content_encoding = "Identity"
        location = self.event.get("Location")

        requested_file = "/index.html" if location == "/" else location
        extension = requested_file.split(".")[-1]
        full_path = CONFIG.location + requested_file

        content_type = mime_mapping.get(f".{extension}", "application/octet-stream")
        gmt_string = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        header_bytes = f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-encoding:{content_encoding}\r\ndate:{gmt_string}\r\nconnection:keep-alive\r\n"

        with open(full_path, mode="rb") as f:
            content = f.read()
            header_bytes = str.encode(
                header_bytes + f"content-length:{len(content)}\r\n\r\n"
            )

        self._send_buffer += header_bytes

    def _options_request(self):
        header_bytes = str.encode(
            "HTTP/1.1 200 OK\r\nAllow: OPTIONS, GET, HEAD\r\n\r\n"
        )
        self._send_buffer += header_bytes

    def _process_request(self):
        try:
            is_valid_headers = self._is_valid_headers()
            if is_valid_headers:
                method = self.event.get("Method")
                if method == "GET":
                    self._get_request()
                elif method == "OPTIONS":
                    self._options_request()
                elif method == "HEAD":
                    self._head_request()
                else:
                    header_bytes = str.encode("HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                    self._send_buffer = header_bytes
            else:
                header_bytes = str.encode("HTTP/1.1 400 Bad Request\r\n\r\n")
                self._send_buffer = header_bytes
        except FileNotFoundError:
            header_bytes = str.encode("HTTP/1.1 404 Not Found\r\n\r\n")
            self._send_buffer += header_bytes

        finally:
            self._write()

    def _write(self):
        try:
            # Since it's using nonblocking sockets you have to check that the socket is ready to write
            # Preventing buffer overflow
            _, ready_to_write, _ = select.select([], [self.sock], [], 0)
            if ready_to_write and self._send_buffer:
                sent = self.sock.send(self._send_buffer)
                self._send_buffer = self._send_buffer[sent:]
            # triggers when .select() file descriptor limit is hit(1024)
        except Exception:
            header_bytes = (
                "HTTP/1.1 503 Service Unavailable\r\nRetry-After: 120\r\n\r\n".encode()
            )

            self.sock.send(header_bytes)
            self.sel.unregister(self.sock)
            self.sock.close()
