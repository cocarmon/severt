import sys
import time
import socket
import config
import selectors
from service import read_message, write_message

# Chooses the most efficient polling based on platform
sel = selectors.DefaultSelector()


def accept_wrapper(sock) -> None:
    conn, addr = sock.accept()
    conn.setblocking(False)
    sel.register(
        conn, selectors.EVENT_READ, data={"sock": conn, "addr": addr, "sel": sel}
    )


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <host> <port>")
        sys.exit(1)
    # early_compress()
    host, port = sys.argv[1], int(sys.argv[2])
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((host, port))

    lsock.listen(20)

    print(f"Listening on {(host, port)}")
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)
    connections = {}

    try:
        while True:
            events = sel.select(timeout=5)
            for key, mask in events:
                # Setup client socket connection
                if key.data is None:
                    accept_wrapper(key.fileobj)
                else:
                    message = key.data

                    readMessage = read_message.ReadMessage(**message)
                    writeMessage = write_message.WriteMessage(**message)

                    readMessage.read()
                    writeMessage.event_listener()
                    connections[len(connections)] = (
                        readMessage.sock,
                        readMessage.sel,
                        readMessage.last_activity,
                    )
            # Forced timeout after 10 seconds
            for key in list(connections):
                soc, selector, last_activity = connections[key]
                if time.time() - last_activity > 10 and soc.fileno() != -1:
                    selector.unregister(soc)
                    soc.close()
                    del connections[key]
    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    except Exception as error:
        print(error)
    finally:
        sel.close()


if __name__ == "__main__":
    main()
