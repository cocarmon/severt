import os
import yaml

file_path = os.path.join("C:", "Program Files", "Severt", "servert.yml")
with open("C:/Program Files/Severt/severt.yml", "r") as file:
    CONFIG = yaml.safe_load(file)
