import selectors
from codecs import decode


class Message:
    def __init__(self, sock, addr, sel):
        self.sock = sock
        self.addr = addr
        self.sel = sel
        self._content_len = None
        self._recv_buffer = bytearray()
        self._send_buffer = bytearray()

    def process_events(self, mask):
        if mask & selectors.EVENT_READ:
            self.read()
        if mask & selectors.EVENT_WRITE:
            self.write()

    def read(self):
        data = self.sock.recv(4096)
        if data:
            delimiter = b"\r\n\r\n"
            self._recv_buffer.extend(data)
            # HTTP headers are delimited by an empty line (CRLF) check for its byte sequence to determine the end of the headers
            # https://www.rfc-editor.org/rfc/rfc7230#page-19
            if delimiter in self._recv_buffer:
                index = self._recv_buffer.find(delimiter)
                if index != -1:
                    # rfc7230, delimits each header with \r\n
                    b_headers = self._recv_buffer[:index]
                    headers = decode(b_headers, encoding="utf-8").split("\r\n")
                    content_len = "Content-Length:"
                    for header in headers:
                        if header.startswith(content_len):
                            self._content_len = int(header[len(content_len) :])
                            break
                    self._recv_buffer = self._recv_buffer[index + len(delimiter) :]
            if self._content_len is not None:
                pass

    def write(self):
        pass
