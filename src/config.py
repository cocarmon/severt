import yaml
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    name: str
    location: dict[str, str]
    port: int = 8000
    host: str = "localhost"


with open("C:/Users/codyw/Desktop/Papers/part_one/servert.yml", "r") as file:
    CONFIG = Config(**yaml.safe_load(file))
