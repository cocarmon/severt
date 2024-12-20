import sys
import time
import socket

import selectors
from service import read_message, write_message
from util.pending_operations import (
    pending_writes,
    write_instance_ids,
    read_instance_ids,
    clean_operation_states,
)
from util.logger import logger
from config import CONFIG

# Chooses the most efficient polling based on platform
sel = selectors.DefaultSelector()


def accept_wrapper(sock) -> None:
    conn, addr = sock.accept()
    conn.setblocking(False)
    sel.register(
        conn,
        selectors.EVENT_READ | selectors.EVENT_WRITE,
        data={"sock": conn, "addr": addr, "sel": sel},
    )


def main() -> None:
    if len(sys.argv) != 3:
        print("Severt requires 2 arguments.")
        sys.exit(1)

    host, port = sys.argv[1], int(sys.argv[2])

    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((host, port))

    lsock.listen(30)

    start_stmt = (
        f"Server started on http://{host}:{port}, serving directory {CONFIG.location}."
    )

    logger.info(start_stmt)
    print(start_stmt)

    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)
    last_clean = time.time()
    try:
        while True:
            events = sel.select(timeout=10)
            for key, mask in events:
                # Setup client socket connection
                if key.data is None:
                    accept_wrapper(key.fileobj)
                elif mask & selectors.EVENT_READ:
                    message = key.data
                    socket_fd = message["sock"].fileno()
                    if socket_fd not in read_instance_ids:
                        readMessage = read_message.ReadMessage(**message)
                        read_instance_ids[socket_fd] = readMessage
                    else:
                        readMessage = read_instance_ids[socket_fd]
                    readMessage.read()

                elif mask & selectors.EVENT_WRITE:
                    message = key.data
                    socket_fd = message["sock"].fileno()
                    if socket_fd in pending_writes:
                        if socket_fd not in write_instance_ids:
                            writeMessage = write_message.WriteMessage(**message)
                            write_instance_ids[socket_fd] = writeMessage
                        else:
                            writeMessage = write_instance_ids[socket_fd]
                        writeMessage.event_listener()

            if time.time() - last_clean > 25 and len(read_instance_ids) >= 1:
                last_clean = time.time()
                for socket_key in list(read_instance_ids):
                    read_instance = read_instance_ids[socket_key]
                    read_socket_fd = read_instance.sock.fileno()
                    if (
                        time.time() - read_instance.last_activity > 15
                        and read_socket_fd not in pending_writes
                        and read_instance.sock != lsock
                        and read_socket_fd != -1
                    ):
                        try:
                            read_instance.sel.unregister(read_instance.sock)
                            read_instance.sock.shutdown(socket.SHUT_RDWR)
                            read_instance.sock.close()
                        except Exception:
                            logger.exception("GarbageCollectionError")
                        finally:
                            clean_operation_states(read_socket_fd)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    except Exception:
        logger.exception("ServerError")
    finally:
        if sys.exc_info()[0] is KeyboardInterrupt or sys.exc_info()[0] is None:
            logger.info("Server shut down gracefully.")
        else:
            logger.info("Server shut down due to an error.")
        sel.close()


if __name__ == "__main__":
    main()
