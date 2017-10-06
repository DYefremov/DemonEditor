from collections import namedtuple

Channel = namedtuple("Channel", ["name", "service", "freq", "fec"])

FILE_PATH = "files/lamedb"

with open(FILE_PATH) as file:
    lines = file.readlines()


for l in lines:
    l.split()

print(lines)

