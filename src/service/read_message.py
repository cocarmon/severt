import io
import time
import socket
import http.client
from codecs import decode
from http.client import HTTPMessage
from selectors import DefaultSelector
from util import pendingWrites, write_instance_ids, read_instance_ids


class ReadMessage:
    __slots__ = ("sock", "sel", "headers", "_recv_buffer", "last_activity")

    def __init__(self, sock, sel):
        self.sock: socket.socket = sock
        self.sel: DefaultSelector = sel
        self._recv_buffer = io.BytesIO()
        self.last_activity: float | int = 0

    def read(self) -> None:
        try:
            data: bytes = self.sock.recv(4096)
            # ensure the client didn't close the connection by checking for b''
            if data:
                # HTTP headers are delimited by an empty line (CRLF)
                # check for its byte sequence to determine the end of the headers
                delimiter = b"\r\n\r\n"
                self._recv_buffer.write(data)
                self.last_activity = time.time()
                if delimiter in self._recv_buffer.getvalue():
                    header = self._parse_http_headers()
                    if header:
                        print(header)
                        socket_fd: int = self.sock.fileno()
                        pendingWrites[socket_fd] = header
                        self._recv_buffer = io.BytesIO()
            else:
                self._close_socket()
        except Exception:
            self._close_socket()

    def _parse_http_headers(self) -> HTTPMessage:
        # set the pointer at the beginning of the buffer
        self._recv_buffer.seek(0)
        eol = b"\r\n"
        start_line_index = self._recv_buffer.getvalue().find(eol)
        # decode converts the byte array returned by .read()
        # into a string
        start_line = decode(
            self._recv_buffer.read(start_line_index + len(eol)),
            encoding="utf-8",
        )
        header = http.client.parse_headers(self._recv_buffer)
        header["Method"] = start_line.split(" ")[0]
        header["Location"] = start_line.split(" ")[1]
        return header

    def _close_socket(self) -> None:
        try:
            # grabt the current classes file descriptor
            socket_fd = self.sock.fileno()
            # if the socket fd is -1, it means the socket was closed
            # you can't perform any operations on a closed socket
            if socket_fd != -1:
                self._recv_buffer.close()
                self.sel.unregister(self.sock)
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
        finally:
            del pendingWrites[socket_fd]
            # we will implement write_instance_ids and read_instance_ids shortly
            if socket_fd in write_instance_ids:
                del write_instance_ids[socket_fd]
            if socket_fd in read_instance_ids:
                del read_instance_ids[socket_fd]
