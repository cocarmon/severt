import yaml
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    name: str
    location: dict[str, str]
    port: int = 8000
    host: str = "localhost"


with open("", "r") as file:
    CONFIG = Config(**yaml.safe_load(file))
