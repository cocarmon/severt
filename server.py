#!/usr/bin/env python3

import selectors
import socket
import sys
from libserver import Message

sel = selectors.DefaultSelector()


def accept_wrapper(sock):
    conn, addr = sock.accept()
    conn.setblocking(False)
    message = Message(conn, addr, sel)
    sel.register(conn, selectors.EVENT_READ, data=message)


def main():
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
                    message.process_events(mask)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    finally:
        sel.close()


if __name__ == "__main__":
    main()
