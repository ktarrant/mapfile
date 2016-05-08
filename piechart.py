from mapReport import MapFileHelper
import logging
import itertools
import pandas
import plotly.offline as py
from plotly.graph_objs import *
import numpy as np

class ColorTracker(object):
    def __init__(self, markers, colorHigh=255, colorLow=100, colorMed=175, minMutiplier=0.6):
        self.markers = markers
        self.colorHigh = colorHigh
        self.colorLow = colorLow
        self.minMutiplier = minMutiplier
        self.colorGenerator = itertools.cycle(
            list(set(itertools.permutations([colorLow, colorLow,  colorHigh], 3))) +
            list(set(itertools.permutations([colorLow, colorHigh, colorHigh], 3))) +
            list(set(itertools.permutations([colorMed, colorMed,  colorHigh], 3))) +
            list(set(itertools.permutations([colorMed, colorHigh, colorHigh], 3))) +
            [(colorHigh, colorHigh, colorHigh)]
        )
        self.uniqueMarkers = markers.unique()
        self.markerMap = {}
        for marker in self.uniqueMarkers:
            if marker == "unused":
                # Unused is handled as a special case
                continue
            if marker not in self.markerMap:
                markerCount = len(markers[markers == marker])
                self.markerMap[marker] = (next(self.colorGenerator), 0, markerCount)

    def getBaseColor(self, marker):
        if marker == "unused":
            return (self.colorLow, self.colorLow, self.colorLow)
        else:
            (colorBase, index, count) = self.markerMap[marker]
            return colorBase

    def getUniqueColor(self, marker):
        if marker == "unused":
            # Unused is handled as a special case
            rv = (self.colorLow, self.colorLow, self.colorLow)
        else:
            (colorBase, index, count) = self.markerMap[marker]
            baseMultiplier = float(count - index) / float(count)
            multiplier = self.minMutiplier + (1 - self.minMutiplier) * baseMultiplier
            rv = tuple(int(c * multiplier) for c in colorBase)
            index += 1
            self.markerMap[marker] = (colorBase, index, count)
        return "rgb{}".format(rv)

def makePieChartsFromMapFile(mapFilePath, outputPath):
    with open(mapFilePath, 'r') as fobj:
        mapFile = MapFileHelper(fobj.read())
    blockTable = (mapFile.placement.blockTable)
    objectTable = (mapFile.placement.objectTable)

    roTable = objectTable[objectTable["block"] == "P1"].sort("module")
    rwTable = objectTable[objectTable["block"] == "P2"].sort("module")
    roModTable = roTable.pivot_table(values="size", index=['module'], aggfunc=np.sum)
    rwModTable = rwTable.pivot_table(values="size", index=['module'], aggfunc=np.sum)

    markers = objectTable["module"]
    tracker = ColorTracker(markers)

    roColors = [tracker.getUniqueColor(marker) for marker in roTable["module"]]
    rwColors = [tracker.getUniqueColor(marker) for marker in rwTable["module"]]
    roModColors = [tracker.getBaseColor(marker) for marker in roModTable.index]

    innerRadius = 0.5
    outerRadius = 0.5 - innerRadius
    devTitle = mapFilePath.split(".")[-2]
    fig = {
        'data': [
            {
                'labels': roTable["object"],
                'values': roTable["size"],
                'type': 'pie',
                'marker': { 'colors': roColors },
                'name': 'readonly',
                'textposition':'inside',
                'domain': {'x': [outerRadius, innerRadius], 'y': [0.2, 0.8]},
                'hole': 0.35,
                # 'sort': False,
            },
            {
                'labels': rwTable["object"],
                'values': rwTable["size"],
                'type': 'pie',
                'marker': { 'colors': rwColors },
                'name': 'readwrite',
                'textposition':'inside',
                'domain': {'x': [0.5 + outerRadius, 0.5 + innerRadius], 'y': [0.2, 0.8]},
                'hole': 0.3,
                # 'sort': False,
            },
        ],
        'layout': {
            'title': 'Code Size Usage: {}'.format(args.mapfile),
            'showlegend': True,
            # 'annotations': [
            #     {
            #         "font": {
            #             "size": 20
            #         },
            #         "showarrow": False,
            #         "text": pieName,
            #         "x": pieX,
            #         "y": 0.5
            #     }
            # for (pieName, pieX) in zip(["ro", "rw"], [0.25, 0.75])]
        }
    }

    return py.plot(fig, filename=outputPath, auto_open=(not args.no_open))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mapfile", help="Map file to generate a plot for.")
    parser.add_argument("--output", help="Output html file path",
        default='CodeSize.html')
    parser.add_argument("--no_open", action="store_true",
        help="Flag to prevent plotly from opening the new chart in a window")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)
    makePieChartsFromMapFile(args.mapfile, args.output)