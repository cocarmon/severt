from typing import Deque
from collections import deque
from http.client import HTTPMessage


class PendingWrites:
    # implements singleton pattern
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super(PendingWrites, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        if not hasattr(self, "_writes"):
            self._writes: dict[int, Deque[HTTPMessage]] = {}

    def __getitem__(self, key: int) -> Deque:
        return self._writes[key]

    def __setitem__(self, key: int, value: HTTPMessage) -> None:
        if key in self._writes:
            self._writes[key].append(value)
        else:
            self._writes[key] = deque([value])

    def __contains__(self, key) -> bool:
        return key in self._writes

    def __delitem__(self, key) -> None:
        if key in self._writes:
            del self._writes[key]

    def remove_write(self, key) -> None:
        self._writes[key].popleft()
        if len(self._writes[key]) == 0:
            del self._writes[key]


pendingWrites = PendingWrites()
