import re
import logging
import pandas
from teamcity import is_running_under_teamcity
import numpy as np
import os

log = logging.getLogger(__name__)

class ModuleSummary(object):
    # Regex designed to match:
    # command line: [2]
    _moduleRe = re.compile(r"(.*):\s\[([0-9]+)\]")

    def __init__(self, moduleSummaryContents, deviceName="FSP3xx"):
        self.contents = moduleSummaryContents
        self.deviceName = deviceName

        self._parseModules()

    def _parseModules(self):
        moduleMatches = ModuleSummary._moduleRe.findall(self.contents)
        self.modules = { int(moduleId): moduleName for (moduleName, moduleId) in moduleMatches }
        self.modules[1] = self.deviceName


class PlacementSummary(object):
    # Regex designed to match:
    # "P2":  place in [from 0x20000000 to 0x20007fff] {
    #           rw, block CSTACK, block HEAP, section .noinit };
    _placeRe = (
        re.compile(
            r'"([A-Z0-9]{2})":  place in \[from 0x([0-9a-z]+) to 0x([0-9a-z]+)\]\s' +
            r"(\|\n\s+\[from 0x([0-9a-z]+) to 0x([0-9a-z]+)\]\s)?" +
            r"\{([^{}]+)\};",
            flags=re.DOTALL))
    # Regex designed to match:
    # "P1":                                      0x2ce6b
    # ... many newlines of anything here ...
    #                              - 0x20007588   0x7588
    _blockDefRe = re.compile(
        r"\"(P[0-9]+)\"(?:, part [0-9]+ of [0-9]+)?\:\s+0x([0-9a-f]+)((.(?!\n\n))*)\n\s+-\s0x([0-9a-f]+)\s+0x[0-9a-f]+",
        flags=re.DOTALL)
    # format and unpack regex match
    _unpackBlock = staticmethod(lambda n,s,c,cS,e: {
        "name": n,
        "size": int(s, 16),
        "contents": c,
        "end": int(e, 16)
    })
    # Regex designed to match:
    #   .text               ro code  0x000040a0   0x288c  SensorFusionMobile.cpp.obj [6]
    _objectRe = re.compile(
        r"\s(.{20})\s([a-z]{2}\s)?(([a-z]+)\s)?\s+" + # name, block*, kindStr*, kind* ; * = optional
        r"0x([a-f0-9]{8})\s{1,6}0x([a-f0-9]{1,6})\s\s"+ # addr, size, 
        r"([^[\n]+)(\[([0-9]+)\])?", # object, moduleStr*, moduleRef*
        flags=re.DOTALL)
    # format and unpack regex match
    _unpackObject = staticmethod(lambda se,kM,kS,k,a,sz,n,mS,mR: {
        "section": se.strip(),
        "kindMod": kM,
        "kind": k,
        "addr": int(a, 16),
        "size": int(sz, 16),
        "object": n.strip(),
        "module": se.strip() if mR == None else mR,
    })

    def __init__(self, placementSummaryContents, moduleSummary):
        self.contents = placementSummaryContents
        self.moduleSummary = moduleSummary

        self._parseBlocks()
        self._parsePlacement()

    def _parseBlocks(self):
        blocks = {}
        matches = self._placeRe.findall(self.contents)
        for (label, startAddr, endAddr, extraAddrs, xStartAddr, xEndAddr, sectionStr) in matches:
            # split by column, then chop off the section type.
            # for instance "block HEAP" -> "HEAP"
            cleanAndChop = lambda s: s.strip().split(" ")[-1]
            sections = [cleanAndChop(entry) for entry in sectionStr.split(", ")]
            blocks[label] = {
                'startAddr': int(startAddr, 16),
                'endAddr': int(endAddr, 16),
                'sections': sections
            }
            blocks[label]["size"] = blocks[label]["endAddr"] - blocks[label]["startAddr"]
            if extraAddrs != "":
                blocks[label]["size"] += int(xEndAddr, 16) - int(xStartAddr, 16)

        self.blockTable = pandas.DataFrame(blocks)

    def _parsePlacement(self):
        objectMap = {}
        blockMatches = self._blockDefRe.findall(self.contents)
        blockDicts = [PlacementSummary._unpackBlock(*block)
            for block in blockMatches]
        for blockDict in blockDicts:
            blockKindMod = "ro" if blockDict["name"] == "P1" else "rw"
            lines = blockDict["contents"].split("\n")
            for line in lines:
                if line == "":
                    continue
                try:
                    obj = PlacementSummary._objectRe.search(line)
                    objDict = PlacementSummary._unpackObject(*obj.groups())
                except TypeError:
                    log.error("Failed to parse line: '{}'".format(line))
                    continue
                except ValueError:
                    log.error("Failed to parse line: '{}'".format(line))
                    continue
                if objDict["kind"] == None:
                    log.warn("Skipped (nokind): '{}'".format(objDict["object"]))
                    continue
                if objDict["size"] == 0:
                    log.warn("Skipped (nosize): '{}'".format(objDict["object"]))
                    continue
                if objDict["kindMod"] == None:
                    objDict["kindMod"] = blockKindMod
                else:
                    objDict["kindMod"] = objDict["kindMod"].strip()
                    assert objDict["kindMod"] == blockKindMod, "{} != {}".format(
                        objDict["kindMod"], blockKindMod)
                try:
                    moduleId = int(objDict["module"])
                    objDict["module"] = self.moduleSummary.modules[moduleId]
                except ValueError:
                    pass
                if objDict["object"].startswith("<"):
                    objDict["object"] = objDict["section"]
                objDict["block"] = blockDict["name"]
                objAddr = objDict.pop("addr")
                if objAddr in objectMap:
                    raise KeyError("Object address double counted: {}".format(hex(objAddr)))
                objectMap[objAddr] = objDict

        self.objectTable = pandas.DataFrame(objectMap).T
        blockSizeTable = self.objectTable.pivot_table(values="size", index=['block'], aggfunc=np.sum)
        for blockName in blockSizeTable.index:
            unusedAddr = 0
            for blockDict in blockDicts:
                if blockDict["name"] == blockName:
                    unusedAddr = blockDict["end"]
                    break
            totalBlockSize = self.blockTable[blockName]["size"]
            unusedSize = totalBlockSize - blockSizeTable[blockName]
            # Yield the unused block as an object
            self.objectTable = self.objectTable.append(pandas.Series({
                "section" : "unused",
                "kindMod" : "ro" if blockDict["name"] == "P1" else "rw",
                "kind"    : "unused",
                "size"    : unusedSize,
                "object"  : "unused",
                "module"  : "unused",
                "block"   : blockName,
            }), ignore_index=True)

class MapFileHelper(object):
    # Regex designed to match:
    # *******************************************************************************
    # *** RUNTIME MODEL ATTRIBUTES
    # ***
    _mainHeaderRe = re.compile(r"\*{79}\n\*{3}\s(.*)\n\*{3}")

    def __init__(self, mapFileContents, deviceName="FSP3xx"):
        self.sections = {}
        self.deviceName = deviceName
        remainingText = mapFileContents
        thisHeader = MapFileHelper._mainHeaderRe.search(remainingText)
        while thisHeader != None:
            sectionName = thisHeader.group(1)
            remainingText = remainingText[thisHeader.end(0):]
            nextHeader = MapFileHelper._mainHeaderRe.search(remainingText)
            if nextHeader == None:
                self.sections[sectionName] = remainingText
            else:
                self.sections[sectionName] = remainingText[:nextHeader.start(0)]
            thisHeader = nextHeader
        log.debug("Loaded sections: {}".format(self.sections.keys()))

        self._makeSectionHelpers()

    def _makeSectionHelpers(self):
        self.module = ModuleSummary(self.sections["MODULE SUMMARY"], deviceName=self.deviceName)
        self.placement = PlacementSummary(self.sections["PLACEMENT SUMMARY"], self.module)

def tc_buildStatistic(devname, mode, key, value):
    fullKey = key = ".".join([devname, mode, key])
    return "##teamcity[buildStatisticValue key='{}' value='{}']".format(fullKey, value)

def to_teamcity(df, devname):
    for ((mode, module), size) in zip(df.index, df):
        module = module.replace(".", "_").replace(" ", "")
        print(tc_buildStatistic(devname, mode, module, size))

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extracts information from Map files.")
    parser.add_argument("mapfile", help="Path to map file to parse.")
    parser.add_argument("--tc", help="Use TeamCity output.", action="store_true")
    parser.add_argument("--devname", help="Label for the chip executable")
    args = parser.parse_args()

    basename = os.path.basename(args.mapfile)
    if not args.devname:
        args.devname = basename.split(".")[0]

    logging.basicConfig(level=logging.DEBUG)
    with open(args.mapfile, 'r') as fobj:
        mapFile = MapFileHelper(fobj.read(), deviceName=args.devname)

    blockTable = (mapFile.placement.blockTable)
    objectTable = (mapFile.placement.objectTable)
    modTable = objectTable.pivot_table(values="size", 
        index=['kindMod', 'module'], aggfunc=np.sum)

    if args.tc or is_running_under_teamcity():
        # print(blockTable)
        # print(modTable)
        print(tc_buildStatistic(args.devname, "ro", "total", blockTable["P1"]["size"]))
        print(tc_buildStatistic(args.devname, "rw", "total", blockTable["P2"]["size"]))
        to_teamcity(modTable, args.devname)
    else:
        print(blockTable)
        print(modTable)


