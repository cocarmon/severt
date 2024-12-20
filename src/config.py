import yaml
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    server_name: str
    location: str
    log_location: str
    listen: int = 80
    forward: str | None = None


with open("C:/Users/codyw/Desktop/severt/severt.yml", "r") as file:
    CONFIG = Config(**yaml.safe_load(file))
