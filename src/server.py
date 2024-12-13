import sys
import socket
import config
import selectors
from service import read_message, write_message

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
    host, port = sys.argv[1], int(sys.argv[2])

    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((host, port))

    lsock.listen()
    print(f"Listening on {(host, port)}")
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)

    try:
        while True:
            events = sel.select(timeout=None)
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

    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    finally:
        sel.close()


if __name__ == "__main__":
    main()
