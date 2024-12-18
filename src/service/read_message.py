import io
import socket
import time
import http.client
from http.client import HTTPMessage
from codecs import decode
from util.writes import pending_writes
from collections import deque


class ReadMessage:
    def __init__(self, sock, addr, sel) -> None:
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self.headers: HTTPMessage | None = None
        self._recv_buffer = io.BytesIO()
        self.last_activity = 0

    def read(self):
        self._process_incoming_request()

    def _process_incoming_request(self):
        try:
            data = self.sock.recv(4096)
            if data:
                # HTTP headers are delimited by an empty line (CRLF) check for its byte sequence to determine the end of the headers
                # https://www.rfc-editor.org/rfc/rfc7230#page-19
                delimiter = b"\r\n\r\n"
                self._recv_buffer.write(data)
                self.last_activity = time.time()
                if delimiter in self._recv_buffer.getvalue():
                    # parse_headers doesn't parse the start_line
                    # This must be parsed manually (https://docs.python.org/3/library/http.client.html#http.client.HTTPMessage)
                    self._recv_buffer.seek(0)
                    eol = b"\r\n"
                    # WARNING: this does not check for whitespace afer the status line so request smuggling is possible.
                    start_line_index = self._recv_buffer.getvalue().find(eol)
                    start_line = decode(
                        self._recv_buffer.read(start_line_index + len(eol)),
                        encoding="utf-8",
                    )

                    headers = http.client.parse_headers(self._recv_buffer)
                    headers["Method"] = start_line.split(" ")[0]
                    headers["Location"] = start_line.split(" ")[1]
                    self.headers = headers

                    if (
                        headers
                        and "Content-length" not in headers
                        and "Transfer-Encoding" not in headers
                    ):
                        file_number = self.sock.fileno()
                        if file_number in pending_writes:
                            pending_writes[file_number] = pending_writes[
                                file_number
                            ].append(headers)
                        else:
                            pending_writes[file_number] = deque([headers])
                        self._recv_buffer = io.BytesIO()
            else:
                print("closing in readmessage")
                del pending_writes[self.sock.fileno()]
                self._recv_buffer.close()
                self.sel.unregister(self.sock)
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()

        except Exception:
            return

    def _clean_up(self):
        pass
