import os
import sys
import numpy as np
from nohrio.ohrrpgce import *
from nohrio.rpg2 import RPG, CorruptionError
#from nohrio.ohrstring import *
import zipfile
from tempfile import mkdtemp
from weakref import proxy
import shutil
import hashlib
import calendar
import time
import traceback
import re
import zlib

path = os.path

def file_ext_in(name, *types):
    return path.splitext(name)[1].lower()[1:] in types

def is_rpg(name):
    return file_ext_in(name, 'rpg', 'rpgdir')

top_level = ["defineconstant", "definetrigger", "defineoperator", 
             "globalvariable", "definefunction", "definescript", "include"]

def is_script(f):
    "Given a (text) file try to determine whether it contains hamsterspeak scripts"

    #with filename_or_handle(f, 'r') as f:
    # Read up to the first top level token, ignoring # comments
    for line in f:
        match = re.search('[,()#]', line)
        if match:
            line = line[:match.start()]
        line = line.lower().strip().replace(' ', '')
        if line:
            return line in top_level
    return False

def lumpbasename(name, rpg):
    "Returns the archinym-independent part of a lump name, eg. ohrrpgce.gen -> gen"
    name = os.path.basename(name)
    if name.startswith(rpg.archinym.prefix):
        name = name[len(rpg.archinym.prefix)+1:]
    return name

def md5_add_file(md5, fname):
    with open(fname, 'rb') as f:
        while True:
            data = f.read(8192)
            if not data:
                break
            md5.update(data)

def safe_extract(archive, srcfile, destfile):
    # Reimplementing ZipFile.extract, so that the target is
    # closed immediately if interrupted by an exception
    source = archive.open(srcfile)
    with open(destfile, "wb") as target:
        shutil.copyfileobj(source, target)
    source.close()

def escape_string(s):
    return s
    ret = ''
    for c in s:
        if ord(c) >= 32 and ord(c) < 128:
            ret += c
        else:
            ret += "\\x%02X" % ord(c)
    print "RESULT :", ret
    return ret

def readbit(array, bitnum, offset = 0):
    assert array.itemsize == 1
    return array[offset + bitnum / 8] & (1 << (bitnum % 8)) != 0

class RPGInfo(object):
    def loadname(self, rpg):
        if rpg.lump_size('browse.txt'):
            browse = rpg.data('browse.txt')
            self.longname = escape_string(get_str8(browse.longname[0]))
            self.aboutline = escape_string(get_str8(browse.about[0]))
            del browse
        else:
            self.longname = ''
            self.aboutline = ''
        self.name = ("%-30s %s" % (self.id, self.longname)).strip()

    def __str__(self):
        return self.id + ' -- ' + self.longname

class ArchiveInfo(object):
    pass

class RPGIterator(object):
    def __init__(self, things):
        """Pass in a list of paths: .rpg files, .rpgdir folders, .zip files containing the preceding, folders containing the preceding.

        Also, you may pass in strings prefixed with 'src:' which sets the gameinfo.src tag for the following games."""

        self.zipfiles = []
        self.rpgfiles = []
        self.hashs = {}
        self.cleanup_dir = False
        self.current_rpg = None

        # Stats
        self.num_zips = 0
        self.num_badzips = 0
        self.num_badrpgs = 0
        self.num_rpgs = 0
        self.num_uniquerpgs = 0
        self.bytes = 0
        self.timings = []
        self.messages = ''

        self.set_input(things)

    def set_input(self, things):
        self.zipfiles = []
        self.rpgfiles = []
        cur_src = ''
        for arg in things:
            if arg.startswith('src:'):
                cur_src = arg[4:]
            elif path.isdir(arg):
                arg = arg.rstrip('/\\')
                if arg.lower().endswith(".rpgdir"):
                    self._addfile(path.abspath(arg), cur_src)
                else:
                    for node in os.listdir(arg):
                        self._addfile(path.join(arg, node), cur_src)
            elif path.isfile(arg):
                if not self._addfile(arg, cur_src):
                    print "Unrecognised file '%s'" % arg
            else:
                print "Unrecognised argument", arg

    def _addfile(self, node, src):
        if node.lower().endswith(".zip"):
            self.zipfiles.append((path.abspath(node), src))
            self.num_zips += 1
            return True
        if is_rpg(node):
            self.rpgfiles.append((path.abspath(node), src))
            return True

    def _nonduplicate(self, fname, gameid):
        self.num_rpgs += 1
        md5 = hashlib.md5()
        if path.isdir(fname):
            for node in sorted(os.listdir(fname)):
                md5.update(node)
                md5_add_file(md5, path.join(fname, node))
        else:
            md5_add_file(md5, fname)
        digest = md5.digest()
        if digest in self.hashs:
            self.hashs[digest].append(gameid)
            return False
        else:
            self.hashs[digest] = [gameid]
            self.num_uniquerpgs += 1
            return True

    def _get_rpg(self, fname):
        rpg = RPG(fname)
        if path.isfile(fname):
            # unlump; rpg2.RPGFile isn't very useful
            fname = path.join(self.tmpdir, path.basename(fname) + "dir")
            os.mkdir(fname)
            self.cleanup_dir = fname
            for foo in rpg.unlump_all(fname):
                #sys.stdout.write('.')
                pass
            rpg = RPG(fname)
        # We return a proxy because otherwise after being yielded from __iter__ and
        # bound to a variable, it won't be unbound from that variable and deleted
        # until after the next rpg is yielded --- meaning _cleanup() won't work.
        self.current_rpg = rpg
        return proxy(rpg)

    def _cleanup(self):
        self.current_rpg = None
        if self.cleanup_dir:
            shutil.rmtree(self.cleanup_dir, ignore_errors = True)
            self.cleanup_dir = False

    def _print(self, msg):
        self.messages += msg + '\n'
        print msg

    def __iter__(self):
        timer = time.time()
        self.tmpdir = mkdtemp(prefix = "gamescanner_tmp")
        try:
            for fname, src in self.rpgfiles:
                if self._nonduplicate(fname, fname):
                    self._print("Found %s" % fname)
                    gameinfo = RPGInfo()
                    gameinfo.rpgfile = path.basename(fname)
                    gameinfo.id = fname
                    gameinfo.src = src
                    gameinfo.mtime = os.stat(fname).st_mtime
                    gameinfo.size = os.stat(fname).st_size
                    self.bytes += gameinfo.size
                    try:
                        rpg = self._get_rpg(fname)
                    except CorruptionError as e:
                        self._print("%s is corrupt, skipped: %s" % (fname, e))
                        self.num_badrpgs += 1
                        # Clear last exception: it holds onto local variables in stack frames
                        sys.exc_clear()
                    gameinfo.loadname(rpg)
                    yield rpg, gameinfo, None
                    self._cleanup()

            for f, src in self.zipfiles:
                # ZipFile is a context manager only in python 2.7+
                try:
                    try:
                        archive = zipfile.ZipFile(f, "r")
                    except IOError as e:
                        # Catch a file seek "invalid argument" error (in CP game 781 at least, which
                        # appears to be a perfectly valid zip). Probably a zipfile bug.
                        self._print("%s could not be read, skipping: %s" % (f, e))
                        continue

                    #if archive.testzip():
                    #    raise zipfile.BadZipfile

                    zipinfo = ArchiveInfo()
                    zipinfo.zip = proxy(archive)
                    zipinfo.scripts = []
                    zipinfo.exes = []
                    zipinfo.rpgs = []

                    # First scan for interesting stuff
                    for name in archive.namelist():
                        name = name.rstrip('/\\')
                        if is_rpg(name):
                            zipinfo.rpgs.append(name)
                        elif file_ext_in(name, 'hss', 'txt'):
                            source = archive.open(name)
                            if is_script(source):
                                zipinfo.scripts.append(name)
                            source.close()
                        elif file_ext_in(name, 'exe'):
                            zipinfo.exes.append(name)

                    for name_ in zipinfo.rpgs:
                        name = name_.rstrip('/\\')
                        self._print("Found %s in %s" % (name, f))
                        extractto = path.join(self.tmpdir, path.basename(name))
                        if name.endswith('.rpgdir'):
                            os.mkdir(extractto)
                            size = 0
                            for zipped in archive.namelist():
                                if zipped.startswith(name) and len(zipped) >  len(name) + 1:
                                    safe_extract(archive, zipped, path.join(extractto, path.basename(zipped)))
                                    dated_file = zipped  # Pick any old lump
                                    size += archive.getinfo(dated_file).file_size
                        else:
                            safe_extract(archive, name, extractto)
                            dated_file = name_
                            size = os.stat(extractto).st_size
                        gameinfo = RPGInfo()
                        gameinfo.rpgfile = path.basename(name)
                        gameinfo.id = "%s:%s" % (path.basename(f), name)
                        gameinfo.src = src
                        gameinfo.mtime = calendar.timegm(archive.getinfo(dated_file).date_time)
                        gameinfo.size = size
                        if self._nonduplicate(extractto, gameinfo.id):
                            self.bytes += gameinfo.size
                            try:
                                yield self._get_rpg(extractto), gameinfo, zipinfo
                            except CorruptionError as e:
                                self._print("%s is corrupt, skipped: %s" % (gameinfo.id, e))
                                self.num_badrpgs += 1
                                # Clear last exception: it holds onto local variables in stack frames
                                sys.exc_clear()
                            self._cleanup()
                        if path.isdir(extractto):
                            shutil.rmtree(extractto)
                        else:
                            os.remove(extractto)

                except (zipfile.BadZipfile, zlib.error):
                    self._print("%s is corrupt, skipping" % f)
                    self.num_badzips += 1
                finally:
                    if archive:
                        archive.close()

        finally:
            self._cleanup()
            try:
                shutil.rmtree(self.tmpdir)
            except:
                traceback.print_exc(1, sys.stderr)
                print
        timer = time.time() - timer
        self.timings.append("Run %d: Finished in %.2f s" % (len(self.timings) + 1, timer))

    def print_summary(self):
        print '\n'.join(self.timings)
        print "Scanned %d zips (%d bad)" % (self.num_zips, self.num_badzips)
        print "Found %d RPGS, %d corrupt, (%d unique, totalling %.1f MB)" % (self.num_rpgs, self.num_badrpgs, self.num_uniquerpgs, self.bytes / 2.**20)
        print 
        for gameids in self.hashs.itervalues():
            if len(gameids) > 1:
                print "The following are identical:", ', '.join(gameids)
        print
