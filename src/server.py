import sys
import time
import socket
import config
import selectors
from service import read_message, write_message
from util.writes import pending_writes

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
        print(f"Usage: {sys.argv[0]} <host> <port>")
        sys.exit(1)

    host, port = sys.argv[1], int(sys.argv[2])

    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((host, port))

    lsock.listen(20)

    print(f"Listening on {(host, port)}")
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)
    write_instance_ids = {}
    read_instance_ids = {}
    last_clean = time.time()
    # connection_garbage_cycle = 25
    # defualt_cleanup = 10
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

            if time.time() - last_clean > 25:
                for key in list(read_instance_ids):
                    read_instance = read_instance_ids[key]
                    if (
                        time.time() - read_instance.last_activity > 10
                        and read_instance.sock.fileno() not in pending_writes
                        and read_instance.sock != lsock
                        and read_instance.sock.fileno() != -1
                    ):
                        try:
                            read_instance.sel.unregister(read_instance.sock)
                            read_instance.sock.shutdown(socket.SHUT_RDWR)
                            read_instance.sock.close()
                            del read_instance_ids[key]
                            del write_instance_ids[key]
                        except Exception:
                            del read_instance_ids[key]
                            del write_instance_ids[key]
                last_clean = time.time()

    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    except Exception as error:
        print(error)
    finally:
        sel.close()


if __name__ == "__main__":
    main()
