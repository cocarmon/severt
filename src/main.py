import sys
import time
import socket
import selectors
from config import CONFIG
from util import read_instance_ids, logger, write_instance_ids
from service import ReadMessage, WriteMessage

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
                # copy the code below this comment
                message = key.data
                socket_fd = message["sock"].fileno()
                if socket_fd in read_instance_ids:
                    read_instance = read_instance_ids[socket_fd]
                else:
                    read_instance = ReadMessage(**message)
                    read_instance_ids[socket_fd] = read_instance
                read_instance.read()
            elif mask & selectors.EVENT_WRITE:
                message = key.data
                socket_fd = message["sock"].fileno()
                if socket_fd in write_instance_ids:
                    write_instance = write_instance_ids[socket_fd]
                else:
                    write_instance = WriteMessage(**message)
                    write_instance_ids[socket_fd] = write_instance
                write_instance.send()


if __name__ == "__main__":
    main()
