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
        content_type = mime_mapping.get(f".{extension}", "application/octet-stream")
        full_path = CONFIG.location + requested_file
        try:
            with open(full_path, mode="rb") as f:
                content = f.read()

            gmt_string = datetime.now(timezone.utc).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            header_bytes = str.encode(
                f"HTTP/1.1 200 OK\r\ncontent-encoding:{content_encoding}\r\ncontent-type:{content_type}\r\ncontent-length:{len(content)}\r\ndate:{gmt_string}\r\n\r\n"
            )
        except FileNotFoundError:
            header_bytes = str.encode("HTTP/1.1 404 Not Found\r\n\r\n")
        self._send_buffer += header_bytes + content

    def _head_request(self):
        content = b""
        location = self.event.get("Location")
        requested_file = "/index.html" if location == "/" else location
        extension = requested_file.split(".")[-1]
        content_type = mime_mapping.get(f".{extension}", "application/octet-stream")
        full_path = CONFIG.location + requested_file
        try:
            with open(full_path, mode="rb") as f:
                content = f.read()
            header_bytes = str.encode(
                f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-length:{len(content)}\r\n\r\n"
            )
        except FileNotFoundError:
            header_bytes = str.encode("HTTP/1.1 404 Not Found\r\n\r\n")
        self._send_buffer += header_bytes

    def _options_request(self):
        header_bytes = str.encode(
            "HTTP/1.1 200 OK\r\nAllow: OPTIONS, GET, HEAD\r\n\r\n"
        )
        self._send_buffer += header_bytes

    def _process_request(self):
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

        self._write()

    def _write(self):
        if self._send_buffer:
            sent = self.sock.send(self._send_buffer)
            self._send_buffer = self._send_buffer[sent:]
            if sent and not self._send_buffer:
                self._send_buffer = b""
