import io
import time
import socket
import http.client
from codecs import decode
from collections import deque
from http.client import HTTPMessage
from util.writes import pending_writes, write_instance_ids, read_instance_ids


class ReadMessage:
    def __init__(self, sock, addr, sel) -> None:
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self.headers: HTTPMessage | None = None
        self._recv_buffer = io.BytesIO()
        self.last_activity = 0

    def read(self):
        try:
            data = self.sock.recv(4096)
            if data:
                # HTTP headers are delimited by an empty line (CRLF) check for its byte sequence to determine the end of the headers
                delimiter = b"\r\n\r\n"
                self._recv_buffer.write(data)
                self.last_activity = time.time()
                if delimiter in self._recv_buffer.getvalue():
                    self._parse_http_headers()

                    if self.headers:
                        socket_fd = self.sock.fileno()
                        if socket_fd in pending_writes:
                            pending_writes[socket_fd] = pending_writes[
                                socket_fd
                            ].append(self.headers)
                        else:
                            pending_writes[socket_fd] = deque([self.headers])
                        self._recv_buffer = io.BytesIO()
            else:
                self._close_socket()

        except Exception as e:
            print("read_message")
            print(e)

    def _parse_http_headers(self):
        self._recv_buffer.seek(0)
        eol = b"\r\n"
        start_line_index = self._recv_buffer.getvalue().find(eol)
        start_line = decode(
            self._recv_buffer.read(start_line_index + len(eol)),
            encoding="utf-8",
        )

        headers = http.client.parse_headers(self._recv_buffer)
        headers["Method"] = start_line.split(" ")[0]
        headers["Location"] = start_line.split(" ")[1]
        self.headers = headers

    def _close_socket(self):
        try:
            socket_fd = self.sock.fileno()
            if socket_fd != -1:
                self._recv_buffer.close()
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
