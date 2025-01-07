import sys
import time
import socket
import selectors
from config import CONFIG
from util.logger import logger

# Chooses the most efficient polling based on platform
sel = selectors.DefaultSelector()


# Creates a new socket to communicate with the client socket
def accept_wrapper(sock) -> None:
    conn, _ = sock.accept()
    conn.setblocking(False)
    # register this socket to notify us on i/o read and write events
    # when a i/o read or write event happens it also passes the
    # selector and socket by using the data parameter
    sel.register(
        conn,
        selectors.EVENT_READ | selectors.EVENT_WRITE,
        data={"sock": conn, "sel": sel},
    )


def main() -> None:
    bsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # set socket option
    bsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bsock.bind((CONFIG.host, CONFIG.port))
    bsock.listen()
    start_stmt = f"Server started on http://{CONFIG.host}:{CONFIG.port}, serving directory {CONFIG.location['static']}."

    logger.info(start_stmt)
    # set sockets to be unblocking
    bsock.setblocking(False)
    # register this socket to receive notifications for I/O read events
    sel.register(bsock, selectors.EVENT_READ, data=None)

    # start of event loop
    while True:
        events = sel.select()
        for key, mask in events:
            # setup client socket connection
            if key.data is None:
                accept_wrapper(key.fileobj)
            elif mask & selectors.EVENT_READ:
                # add the following 3 lines
                read_socket = key.data["sock"]
                data = read_socket.recv(4096)
                print(data)
            elif mask & selectors.EVENT_WRITE:
                pass  # here we will implement a class to write to the socket


if __name__ == "__main__":
    main()
