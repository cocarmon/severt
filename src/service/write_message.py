import os
import re
import gzip
import socket
from config import CONFIG
from functools import lru_cache
from http.client import HTTPMessage
from selectors import DefaultSelector
from datetime import datetime, timezone
from util import (
    logger,
    mime_mapping,
    content_type_mapping,
    pendingWrites,
    write_instance_ids,
    read_instance_ids,
)


@lru_cache(maxsize=20)
def read_content(full_path: str, content_encoding: str) -> bytes:
    with open(full_path, mode="rb") as f:
        content = f.read()
        if content_encoding == "gzip":
            content = gzip.compress(content)
    return content


class WriteMessage:
    __slots__ = ("sock", "sel", "header", "_send_buffer")

    def __init__(self, sock, sel) -> None:
        self.sock: socket.socket = sock
        self.sel: DefaultSelector = sel
        self.header: HTTPMessage | None = None
        self._send_buffer = b""

    def send(self) -> None:
        # fileno() returns the file descriptor
        if self.sock.fileno() in pendingWrites:
            self.header = pendingWrites[self.sock.fileno()][0]
            self._process_request()

    def _process_request(self) -> None:
        try:
            # will implement the following methods shortly
            is_valid_headers = self._is_valid_headers()
            if is_valid_headers:
                method = self.header.get("Method")
                if method == "GET":
                    self._get_request()
                elif method == "OPTIONS":
                    self._options_request()
                elif method == "HEAD":
                    self._head_request()
                else:
                    # For methods outside of GET,OPTIONS,HEAD
                    header_bytes = str.encode(
                        "HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n"
                    )
                    self._send_buffer = header_bytes
            else:
                # malformed headers
                header_bytes = str.encode(
                    "HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"
                )
                self._send_buffer = header_bytes
        except FileNotFoundError:
            header_bytes = str.encode(
                "HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"
            )
            self._send_buffer = header_bytes
        except Exception:
            header_bytes = str.encode(
                "HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n"
            )
            self._send_buffer = header_bytes
        finally:
            self._write()

    def _is_valid_headers(self) -> bool:
        try:
            if not self.header:
                return False
            # basic http header validation
            if "host" not in self.header or not self.header.get("Host", "").strip():
                return False
            transfer_encoding = self.header.get("Transfer-encoding")
            content_length = self.header.get("Content-length")
            transfer_encoding = self.header.get("Transfer-encoding")
            if content_length and transfer_encoding:
                return False
            if content_length:
                if not content_length.isdigit() or int(content_length) <= 0:
                    return False
            if transfer_encoding:
                if transfer_encoding.lower() != "chunked":
                    return False
                # checking for duplicates
            seen_headers = set()
            for header in self.header.keys():
                if header.lower() in seen_headers:
                    return False
            seen_headers.add(header.lower())
            for key, value in self.header.items():
                # helps mitigate some forms of request smuggling
                if key.strip() != key or value.strip() != value:
                    return False
                # verfies that the header has a valid name
                if not re.match(r"^[A-Za-z0-9-]+$", key):
                    return False
            return True
        except Exception:
            return False

    def _get_request(self) -> None:
        content = b""
        full_path, content_type, content_encoding = self._content_negotiation()
        gmt_string = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        base_header = f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-encoding:{content_encoding}\r\ndate:{gmt_string}\r\nCache-Control: public, max-age=3600, must-revalidate\r\n"
        file_size = os.stat(full_path).st_size
        if file_size < (4000 * 1024):
            content = read_content(full_path, content_encoding)
            header_bytes = str.encode(
                base_header + f"content-length:{len(content)}\r\n\r\n"
            )
            self._send_buffer += header_bytes + content
        else:
            if range := self.header.get("Range"):
                # incoming range format: bytes=-, bytes=0-, bytes=start-end
                range_split = range.split("=")[1]
                byte_range = range_split.split("-")
                DEFAULT_BYTE_RANGE = 100 * 1024
                byte_start, byte_end = 0, DEFAULT_BYTE_RANGE
                if len(byte_range) >= 1:
                    if byte_range[0]:
                        # read in chunks of 1mb
                        byte_start = int(byte_range[0])
                        byte_end = byte_start + DEFAULT_BYTE_RANGE
                        # Prevent read overflow, when you're near the end of the file
                        if byte_start + DEFAULT_BYTE_RANGE > file_size:
                            byte_end = file_size
                    # Length == 2, when start and end bytes are both defined
                    if len(byte_range) == 2:
                        if byte_range[1]:
                            byte_end = int(byte_range[1])
                with open(full_path, mode="rb") as f:
                    f.seek(byte_start)
                    content = f.read(byte_end - byte_start)
                    content_length = len(content)
                    header_bytes = str.encode(
                        f"HTTP/1.1 206 Partial Content\r\ncontent-type:{content_type}\r\ncontent-encoding:{content_encoding}\r\nContent-Length:{content_length}\r\ndate:{gmt_string}\r\ncontent-range:bytes {byte_start}-{byte_end - 1}/{file_size}\r\n\r\n"
                    )
                self._send_buffer += header_bytes + content
            else:
                header_bytes = str.encode(base_header + "Accept-Ranges: bytes\r\n\r\n")
                self._send_buffer += header_bytes

    def _content_negotiation(self) -> tuple[str, str, str]:
        content_type = "text/html"
        content_encoding = "Identity"
        location = self.header["Location"]
        supported_encodings = {"gzip": "gz"}
        requested_file = "/index.html" if location == "/" else location
        name, ext = requested_file.split(".")
        if (encodings := self.header.get("Accept-Encoding")) and ext in ["html", "css"]:
            for encoding in encodings.split(","):
                if encoding in supported_encodings:
                    content_encoding = encoding
                    break
        # Accept is in a format like 'text/html,application/xhtml+xml,application/xml'
        for accept in self.header.get("Accept", "text/html").split(","):
            type = accept.split(";")[0]
            if os.path.exists(
                CONFIG.location["static"]
                + name
                + content_type_mapping.get(type, "does_not_exist.txt")
            ):
                requested_file = name + content_type_mapping[accept]
                content_type = accept
                break
            if type == "*/*":
                content_type = mime_mapping[f".{ext}"]
        full_path = CONFIG.location["static"] + requested_file
        return full_path, content_type, content_encoding

    def _options_request(self) -> None:
        header_bytes = str.encode(
            "HTTP/1.1 200 OK\r\nAllow: OPTIONS, GET, HEAD\r\n\r\n"
        )
        self._send_buffer += header_bytes

    def _head_request(self) -> None:
        content = b""
        content_encoding = "Identity"
        full_path, content_type, content_encoding = self._content_negotiation()
        gmt_string = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        base_header = f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-encoding:{content_encoding}\r\ndate:{gmt_string}\r\nconnection:keep-alive\r\n"
        with open(full_path, mode="rb") as f:
            content = f.read()
            header_bytes = str.encode(
                base_header + f"content-length:{len(content)}\r\n\r\n"
            )
        self._send_buffer += header_bytes

    def _write(self) -> None:
        try:
            # check that buffer isn't empty and the socket is still active
            if self._send_buffer and self.sock.fileno() != -1:
                sent = self.sock.send(self._send_buffer)
                # on 400 errors we want to close the socket
                if (
                    self._send_buffer.startswith(b"HTTP/1.1 4")
                    or self.header.get("Method") == "OPTIONS"
                ):
                    self._close_socket()
                self._send_buffer = self._send_buffer[sent:]
                # If send buffer is empty then the socket sent all of the data and the headers are no longer needed
                socket_fd = self.sock.fileno()
                if not self._send_buffer and socket_fd in pendingWrites:
                    pendingWrites.remove_write(socket_fd)
        except BlockingIOError:
            pass  # This error will throw if the buffer is full
        except Exception:
            logger.exception("WriteMessageError")
            self._close_socket()

    def _close_socket(self) -> None:
        try:
            socket_fd = self.sock.fileno()
            if socket_fd != -1:
                self.sel.unregister(self.sock)
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
                if socket_fd in write_instance_ids:
                    del write_instance_ids[socket_fd]
                if socket_fd in read_instance_ids:
                    del read_instance_ids[socket_fd]
                del pendingWrites[socket_fd]
        except Exception:
            logger.exception("CloseWriteSocketError")
