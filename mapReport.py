import re
import logging
import pandas

log = logging.getLogger(__name__)

class PlacementSummary(object):
    # Regex designed to match:
    # "P2":  place in [from 0x20000000 to 0x20007fff] {
    #           rw, block CSTACK, block HEAP, section .noinit };
    _placeRe = (
        re.compile(
            r'"([A-Z0-9]{2})":  place in \[from 0x([0-9a-z]+) to 0x([0-9a-z]+)\] \{([^{}]+)\};',
            flags=re.DOTALL))
    # Regex designed to match:
    # "P1":                                      0x2ce6b
    # ... many newlines of anything here ...
    #                              - 0x20007588   0x7588
    _blockDefRe = re.compile(
        r"\"(P[0-9]+)\":\s+0x([0-9a-f]+)((.(?!\n\n))*)\n\s+-\s0x([0-9a-f]+)\s+0x[0-9a-f]+",
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
        r"\s(.{20})\s([a-z]+)?(\s([a-z]+)\s\s)?\s+" + # name, block*, kindStr*, kind* ; * = optional
        r"0x([a-f0-9]{8})\s{1,6}0x([a-f0-9]{1,6})\s\s"+ # addr, size, 
        r"([A-Za-z0-9._<>\s]+)(\s\[([0-9]+)\])?", # object, moduleStr*, moduleRef*
        flags=re.MULTILINE)
    # format and unpack regex match
    _unpackObject = staticmethod(lambda se,kM,kS,k,a,sz,n,mS,mR: {
        "section": se.strip(),
        "kindMod": kM,
        "kind": k,
        "addr": int(a, 16),
        "size": int(sz, 16),
        "object": n,
        "module": mR if mR != "" else se.strip()
    })

    def __init__(self, placementSummaryContents):
        self.contents = placementSummaryContents

        self._parseBlocks()
        self._parsePlacement()

    def _parseBlocks(self):
        blocks = {}
        for (label, startAddr, endAddr, sectionStr) in self._placeRe.findall(self.contents):
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
        self.blockTable = pandas.DataFrame(blocks)

    def _getObjectsByBlock(self):
        blocks = self._blockDefRe.findall(self.contents)
        for block in blocks:
            blockDict = PlacementSummary._unpackBlock(*block)
            objs = self._objectRe.findall(blockDict["contents"])
            for obj in objs:
                objDict = PlacementSummary._unpackObject(*obj)
                yield (blockDict["name"], objDict)

            totalBlockSize = self.blockTable[blockDict["name"]]["size"]
            unusedSize = totalBlockSize - blockDict["size"]
            print("totalBlockSize", totalBlockSize, "usedSize", blockDict["size"], "unusedSize", unusedSize)
            # Yield the unused block as an object
            unusedObject = {
                "section": "unused",
                "kindMod": "",
                "kind": "unused",
                "addr": blockDict["end"],
                "size": unusedSize,
                "object": "unused",
                "module": "unused"
            }
            yield(blockDict["name"], unusedObject)

    def _parsePlacement(self):
        objectMap = {}
        for (blockName, objDict) in self._getObjectsByBlock():
            if objDict["kind"] == "":
                continue
            if objDict["size"] == 0:
                continue
            objDict["block"] = blockName
            objAddr = objDict.pop("addr")
            if objAddr in objectMap:
                raise KeyError("Object address double clounted: {}".format(hex(objAddr)))
            objectMap[objAddr] = objDict
        self.objectTable = pandas.DataFrame(objectMap).T


class MapFileHelper(object):
    # Regex designed to match:
    # *******************************************************************************
    # *** RUNTIME MODEL ATTRIBUTES
    # ***
    _mainHeaderRe = re.compile(r"\*{79}\n\*{3}\s(.*)\n\*{3}")

    def __init__(self, mapFileContents):
        self.sections = {}
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
        self.placement = PlacementSummary(self.sections["PLACEMENT SUMMARY"])

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    with open("FSP312.map", 'r') as fobj:
        mapFile = MapFileHelper(fobj.read())
    blockTable = (mapFile.placement.blockTable)
    print(blockTable)
    objectTable = (mapFile.placement.objectTable)
    print(objectTable)