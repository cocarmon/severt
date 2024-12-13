import gzip
from config import CONFIG
from datetime import datetime, timezone
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

    def _is_valid_headers(self):
        if not self.event.get("Host"):
            return False
        return True

    def _process_request(self):
        # print(self.sock, self.event.get("Location"))
        is_valid_headers = self._is_valid_headers()

        if is_valid_headers:
            content = b""
            base_path = CONFIG.location
            content_encoding = "Identity"
            location = self.event.get("Location")
            requested_file = "/index.html" if location == "/" else location

            full_path = base_path + requested_file
            try:
                # replace with threads
                with open(full_path, mode="rb") as f:
                    content = f.read()

                if "gzip" in self.event.get("Accept-Encoding").split(", "):
                    content_encoding = "gzip"
                    content = gzip.compress(content)

                gmt_string = datetime.now(timezone.utc).strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                )

                header_bytes = str.encode(
                    f"HTTP/1.1 200 OK\r\ncontent-encoding:{content_encoding}\r\ndate:{gmt_string}\r\ncontent-length:{len(content)}\r\nConnection: keep-alive\r\n\r\n"
                )
            except FileNotFoundError:
                header_bytes = str.encode("HTTP/1.1 404 Not Found\r\n\r\n")
        else:
            header_bytes = str.encode("HTTP/1.1 400 Bad Request\r\n\r\n")

        self._send_buffer += header_bytes + content
        self._write()

    def _write(self):
        if self._send_buffer:
            sent = self.sock.send(self._send_buffer)
            self._send_buffer = self._send_buffer[sent:]
            if sent and not self._send_buffer:
                self._send_buffer = b""
