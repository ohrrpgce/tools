#!/usr/bin/env python
import sys
import time
import cPickle as pickle
import os
import glob
import numpy as np
from nohrio.ohrrpgce import *
from nohrio.dtypes import dt
from nohrio.wrappers import OhrData

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Expected pickled file")
    pickled = sys.argv[1]
else:
    pickled = 'gamedata.bin'

with open(pickled, 'rb') as f:
    d = pickle.load(f)

rpgidx = d['rpgidx']
gen = d['gen']
mas = d['mas']
fnt = d['fnt']
del d

# A more convenient name for each game
for r in rpgidx:
    r.name = "%-30s %s" % (r.id, r.longname)


# END OF BOILERPLATE

# And now a bunch of sample code....


# Lets find the minimum and maximum value of each field in gen.

# First we need to cast the record type to an array of 500 INTs so that numpy
# treats it as numerical data

gen_array = gen.view((INT, 500))
gen_min = gen_array.min(axis=0) #.view(dt['gen'])
gen_max = gen_array.max(axis=0) #.view(dt['gen'])

# Lets see where those min/max are attained...
# (Note we can't append .view(dt['gen']) because these are arrays of 32(or native?) bit ints)
gen_argmin = gen_array.argmin(axis=0)
gen_argmax = gen_array.argmax(axis=0)


if __name__ == '__main__':

    # Print out minimum and maximum values of gen entries: checking for unexpected garbage

    for offset in range(500):
        best = [-1, '']
        for field in gen.dtype.names:
            type, foffset = gen.dtype.fields[field]
            foffset /= 2  # from bytes to array index
            if offset == foffset and type.itemsize == 2:
                fieldname = field
                #if gen_min[field] != 0:
                #    print "   min in", rpgidx[gen_argmin[offset]].name
                #print "   max in", rpgidx[gen_argmax[offset]].name
                break
            if foffset <= offset and foffset > best[0]:
                best = [foffset, field]
        else:
            fieldname = '%s[%d]' % (best[1], offset - best[0])
        print "%3d: gen.%-19s min=%d max=%d" % (offset, fieldname , gen_min[offset], gen_max[offset])
            
    print
    gen_min = gen_min.view(dt['gen'])
    gen_max = gen_max.view(dt['gen'])

    for field in gen.dtype.names:
        if field.startswith('max'):
            type, offset = gen.dtype.fields[field]
            offset /= 2  # from bytes to array index
            print "max(gen.%s)=%d attained in" % (field, gen_max[field])
            print "  ", rpgidx[gen_argmax[offset]].name

    print

mas_ints = mas.view( (INT, (256,3)) )
# Magnus' MAS lump contains garbage, so form an array of 'notcorrupt' booleans
mas_notcorrupt = mas[np.where(mas_ints.max(axis = 2).max(axis = 1) <= 63)]

# Hash every MAS palette, pick out the unique ones, and count occurrences
mashashes, indices, iindices = np.unique([a.view(OhrData).md5() for a in mas_notcorrupt.color], return_index = True, return_inverse = True)
palettes = [[0, mas[i]] for i in indices]
for i in iindices:
    palettes[i][0] += 1
palettes.sort(reverse = True)
print len(palettes), "unique master palettes (in MAS)"

# Same for fonts
fnthashes, indices, iindices = np.unique([fnt[i:i+1].md5() for i in range(len(fnt))], return_index = True, return_inverse = True)
fonts = [[0, fnt[i]] for i in indices]
for i in iindices:
    fonts[i][0] += 1
fonts.sort(reverse = True)
print len(fonts), "unique fonts"

if __name__ == '__main__':
    # Export unique master palettes and fonts as PNGs...

    try:
        import pygame
    except ImportError:
        print "pygame missing, skipping image export stuff"
    else:
        pygame.init()

        def mas2palette(mas):
            def scale(a):
                a = min(a, 63)
                return (a << 2) + (a / 16)

            return [(scale(r), scale(g), scale(b)) for r, g, b in mas['color']]

        if 1:
            # Export master palettes

            zoom = 8
            pixels = np.ndarray((16 * zoom, 16 * zoom), dtype = np.int8)
            for i in range(16 * zoom):
                pixels[:,i] = np.arange(16 * zoom) / zoom + (i / zoom) * 16
            palsurf = pygame.surfarray.make_surface(pixels)

            allpals = pygame.surface.Surface((16 * zoom, 20 * zoom * len(palettes) - 4 * zoom))

            for fname in glob.glob('masterpal*.png'):
                os.remove(fname)

            print
            for i, (count, pal) in enumerate(palettes):
                a = mas2palette(pal)
                palsurf.set_palette(a) 
                fname = "masterpal%02d.png" % i
                pygame.image.save(palsurf, fname)
                print fname, "used in", count, "games"
                allpals.blit(palsurf, (0, 20 * zoom * i))
            print

            pygame.image.save(allpals, "masterpal_all.png")


        def char2surf(char):
            "pygame surface for an individual character in a FNT file"
            pixels = np.ndarray((8 * 8, 8), dtype = np.int8)
            for x, col in enumerate(char):
                for y in range(8):
                    pixels[x][y] = int(col & (1 << y)) and 1

            surf = pygame.surfarray.make_surface(pixels)
            surf.set_palette( [(0,0,0), (255,255,255), (50,50,50)] )
            return surf


        def fnt2surf(fnt):
            pixels = np.ndarray((256 * 8, 8), dtype = np.int8)
            for x, col in enumerate(fnt['characters']['bitmaps'].flatten()):
                for y in range(8):
                    pixels[x][y] = int(col & (1 << y)) and 1

            surf = pygame.surfarray.make_surface(pixels)
            surf.set_palette( [(0,0,0), (255,255,255), (50,50,50)] )
            return surf

        if 1:
            # Export the set of unique characters from all fonts

            seen_chars = set()
            unique_chars = []

            print "Scanning font characters",
            #charlist = fnt['characters']['bitmaps'].flatten().view(OhrData)
            for char in fnt['characters']['bitmaps'].reshape((len(fnt) * 256, 8)):
                md5 = char.md5()
                if md5 not in seen_chars:
                    unique_chars.append(char2surf(char))
                    seen_chars.add(md5)
                    if (len(seen_chars) % 100) == 0:
                        sys.stdout.write('.')

            print
            print len(seen_chars), "unique characters"

            print
            print "creating fontchars.png",
            all_chars = pygame.Surface((16 * 8, 8 * (len(unique_chars) / 16)))
            for i, char in enumerate(unique_chars):
                all_chars.blit(char, ((i % 16) * 8, (i / 16) * 8))
                if (i % 100) == 0:
                    sys.stdout.write('.')
            print

            pygame.image.save(all_chars, "unique_chars.png")

        if 1:
            # Export individual fonts, and also a giant PNG containing them all...

            allfonts = pygame.surface.Surface((16 * 8, 14 * 8 * len(fonts)))

            for fname in glob.glob('font*.png'):
                os.remove(fname)

            for i, (count, font) in enumerate(fonts):
                fntsurf = fnt2surf(font)
                surf = pygame.Surface((16 * 8, 16 * 8))
                #print surf.get_rect(), fntsurf.get_rect()
                for j in range(0, 256, 16):
                    surf.blit(fntsurf, (0, ((j - 0) / 16) * 8), (j * 8, 0, 16 * 8, 8))
                fname = "font%03d.png" % i
                pygame.image.save(surf, fname)
                print fname, "used in", count, "games"
                allfonts.blit(surf, (0, 16 * 8 * i))

            pygame.image.save(allfonts, "font_all.png")
