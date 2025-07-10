#!/usr/bin/env python3
"""
An rpgbatch example: look for games with certain prefbits set in GEN.
"""
import sys
import time
import numpy as np
from rpgbatch.rpgbatch import RPGIterator, RPGInfo

if len(sys.argv) < 2:
    sys.exit("Specify .rpg files, .rpgdir directories, .zip files, or directories containing any of these as arguments.")
things = sys.argv[1:]

doubletrig = bug430 = 0

rpgs = RPGIterator(things)
for rpg, gameinfo, zipinfo in rpgs:
    print("Processing RPG ", gameinfo.id, "from", gameinfo.src)
    print(" > ", gameinfo.longname, " --- ", gameinfo.aboutline)
    print("mod time =", time.ctime(gameinfo.mtime))


    if rpg.general.prefbit(10):
        print("  ########  Permits double triggering\n")
        doubletrig += 1

    if rpg.general.prefbit(33):
        print("  ########  Simulates bug 430\n")
        bug430 += 1

rpgs.print_summary()
del rpgs


print(doubletrig, "games double triggering enabled")
print(bug430, "games had bug430 compat enabled")
