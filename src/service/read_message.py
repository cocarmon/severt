import io
import json
import selectors
import http.client
from http.client import HTTPMessage
from codecs import decode
from util.queue import event_queue


class ReadMessage:
    def __init__(self, sock, addr, sel) -> None:
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self.headers: HTTPMessage | None = None
        self._content_len: int | None = None
        self._recv_buffer = io.BytesIO()

    def read(self):
        self._process_incoming_request()

    def _process_incoming_request(self):
        data = self.sock.recv(4096)
        if data:
            # HTTP headers are delimited by an empty line (CRLF) check for its byte sequence to determine the end of the headers
            # https://www.rfc-editor.org/rfc/rfc7230#page-19
            delimiter = b"\r\n\r\n"
            self._recv_buffer.write(data)
            if delimiter in self._recv_buffer.getvalue():
                # parse_headers doesn't parse the start_line
                # This must be parsed manually (https://docs.python.org/3/library/http.client.html#http.client.HTTPMessage)
                self._recv_buffer.seek(0)
                eol = b"\r\n"
                start_line_index = self._recv_buffer.getvalue().find(eol)
                start_line = decode(
                    self._recv_buffer.read(start_line_index + len(eol)),
                    encoding="utf-8",
                )

                headers = http.client.parse_headers(self._recv_buffer)
                headers["method"] = start_line.split(" ")[0]
                headers["location"] = start_line.split(" ")[1]
                self.headers = headers
                if "Content-length" not in headers:
                    self._recv_buffer.close()
                    event_queue.append(self.headers)
            # Check that headers have been set
            # if headers:
            #     if self.headers.get_content_type == "application/json":
            #         delimiter_index = self._recv_buffer.getvalue().find(delimiter)
            #         self._recv_buffer.seek(delimiter_index + len(delimiter))
            #         body = json.loads(self._recv_buffer.read())
            #         print(body)

        else:
            self._recv_buffer.close()

    def write(self):
        pass
