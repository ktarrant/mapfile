from mapReport import MapFileHelper
import logging
import plotly.offline as py
from plotly.graph_objs import *

logging.basicConfig(level=logging.DEBUG)
with open("FSP312.map", 'r') as fobj:
    mapFile = MapFileHelper(fobj.read())
blockTable = (mapFile.placement.blockTable)
# print(blockTable)
objectTable = (mapFile.placement.objectTable)
# print(objectTable)

roTable = objectTable[objectTable["block"] == "P1"]
print(roTable)
rwTable = objectTable[objectTable["block"] == "P2"]
print(rwTable)

fig = {
    'data': [
        {
            'labels': roTable["object"],
            'values': roTable["size"],
            'type': 'pie',
            'name': 'readonly',
            'textposition':'inside',
            'domain': {'x': [0, 0.5], 'y': [0.5, 1]},
        },
        {
            'labels': rwTable["object"],
            'values': rwTable["size"],
            'type': 'pie',
            'name': 'readwrite',
            'textposition':'inside',
            'domain': {'x': [0.5, 1], 'y': [0.5, 1]},
        },
    ],
    'layout': {'title': 'Code Size Usage'}
}

url = py.plot(fig, filename='CodeSize.html')