import io
import selectors
import http.client
from codecs import decode


class Message:
    def __init__(self, sock, addr, sel):
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self._content_len = None
        self._recv_buffer = io.BytesIO()
        self._send_buffer = io.BytesIO()

    def process_events(self, mask):
        if mask & selectors.EVENT_READ:
            self.read()
        if mask & selectors.EVENT_WRITE:
            self.write()

    def read(self):
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
                if "Content-length" not in headers:
                    self._recv_buffer.close()
                # print(headers)
                # print(start_line.split(" "))

    def write(self):
        pass
