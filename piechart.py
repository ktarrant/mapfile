from mapReport2 import MapFileHelper
import logging
import plotly.offline as py
from plotly.graph_objs import *

logging.basicConfig(level=logging.DEBUG)
with open("FSP312.map", 'r') as fobj:
    mapFile = MapFileHelper(fobj.read())
blockTable = (mapFile.placement.blockTable)
# print(blockTable)
objectTable = (mapFile.placement.objectTable)

tableP2 = (objectTable["P2"])
sztable = tableP2.loc[["object", "size"]]
print(sztable)
#print(tableP2.pivot("object", "size"))

fig = {
    'data': [
        {
            'labels': tableP2.loc[["object"]].values[0],
            'values': tableP2.loc[["size"]].values[0],
            'type': 'pie',
            'name': 'P2',
            'hoverinfo':'label+percent+name',
            'textinfo':'none'
        },
    ],
    'layout': {'title': 'Code Size Usage',
               'showlegend': False}
}

url = py.plot(fig, filename='Pie Chart Subplot Example')