import os
import re
import socket
from config import CONFIG
from util.mime import content_type_mapping
from http.client import HTTPMessage
from datetime import datetime, timezone
from util.writes import pending_writes, read_instance_ids, write_instance_ids


class WriteMessage:
    def __init__(self, sock, addr, sel) -> None:
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self.event: HTTPMessage | None = None
        self._send_buffer = b""

    def event_listener(self) -> None:
        self.event = pending_writes[self.sock.fileno()][0]
        self._process_request()

    def _is_valid_headers(self):
        try:
            # Basic http header validation
            headers = {key.lower(): value for key, value in self.event.items()}

            if "host" not in headers or not headers["host"].strip():
                return False

            content_length = headers.get("content-length")
            transfer_encoding = headers.get("transfer-encoding")

            if content_length and transfer_encoding:
                return False

            if content_length:
                if not content_length.isdigit() or int(content_length) <= 0:
                    return False

            if transfer_encoding:
                if transfer_encoding.lower() != "chunked":
                    return False

            seen_headers = set()
            for header in self.event.keys():
                if header.lower() in seen_headers:
                    return False
                seen_headers.add(header.lower())

            for key, value in self.event.items():
                # Prevent request smuggling
                if key.strip() != key or value.strip() != value:
                    return False
                # Verfies that the header has a valid name
                if not re.match(r"^[A-Za-z0-9-]+$", key):
                    return False

            return True
        except Exception as e:
            return False

    def _get_request(self):
        content = b""
        content_encoding = "Identity"

        full_path, content_type = self._content_negotiation()

        gmt_string = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        header_bytes = f"HTTP/1.1 200 OK\r\ncontent-type:{content_type}\r\ncontent-encoding:{content_encoding}\r\ndate:{gmt_string}\r\n"

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
            # Signals to the client that it's the end of the data
            self._send_buffer += b"0\r\n\r\n"

    def _content_negotiation(self):
        content_type = "text/html"
        location = self.event.get("Location")
        requested_file = "/index.html" if location == "/" else location
        name, _ = requested_file.split(".")

        for accept in self.event.get("Accept", "text/html").split(","):
            if os.path.exists(
                CONFIG.location
                + name
                + content_type_mapping.get(accept.split(";")[0], "does_not_exist.txt")
            ):
                requested_file = name + content_type_mapping[accept]
                content_type = accept
                break
        full_path = CONFIG.location + requested_file
        return full_path, content_type

    def _head_request(self):
        content = b""
        content_encoding = "Identity"
        full_path, content_type = self._content_negotiation()
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
                    header_bytes = str.encode(
                        "HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n"
                    )
                    self._send_buffer = header_bytes
            else:
                header_bytes = str.encode(
                    "HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n"
                )
                self._send_buffer = header_bytes
        except FileNotFoundError:
            header_bytes = str.encode(
                "HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"
            )
            self._send_buffer = header_bytes

        finally:
            self._write()

    def _write(self):
        try:
            # Since it's using nonblocking sockets you have to check that the socket is ready to write
            # Preventing buffer overflow
            if self._send_buffer and self.sock.fileno() != -1:
                sent = self.sock.send(self._send_buffer)

                if (
                    self._send_buffer.startswith(b"HTTP/1.1 4")
                    or self.event.get("Method") == "OPTIONS"
                ):
                    self._close_socket()

                self._send_buffer = self._send_buffer[sent:]
                # If send buffer is empty then the socket sent all of the data and the headers are no longer needed
                socket_fd = self.sock.fileno()
                if not self._send_buffer and socket_fd in pending_writes:
                    pending_writes[socket_fd].popleft()
                    if len(pending_writes[socket_fd]) == 0:
                        del pending_writes[socket_fd]

        except BlockingIOError as e:
            print("Write error:", e)
        except OSError as e:
            print("Write error:", e)
            self._close_socket()

    def _close_socket(self):
        try:
            socket_fd = self.sock.fileno()
            if socket_fd != -1:
                self.sel.unregister(self.sock)
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
                if socket_fd in pending_writes:
                    del pending_writes[socket_fd]
                if socket_fd in read_instance_ids:
                    del read_instance_ids[socket_fd]
                if socket_fd in write_instance_ids:
                    del write_instance_ids[socket_fd]
        except Exception as error:
            print("closing socket")
            print(error)
