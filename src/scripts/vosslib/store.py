"""Text kept small inside a database.

A database of health text is mostly prose, and prose squeezes well. So long text (a topic summary, a
label section) is not stored row by row: many pieces are packed into one block, the block is compressed,
and a piece is found again by (block, start, length). SQLite has no compression of its own, so this is
done here, with the standard library and nothing else.

A block is unpacked once and kept while the call lasts. Reading one piece costs one block, a few
milliseconds, however big the database is.
"""
import zlib

from .core import die

# zlib is in every Python. The other two are in every ordinary one, and squeeze prose a good deal harder,
# but a Python can be built without them: then a database packed with one cannot be read, and says so
try:
    import bz2
except ImportError:
    bz2 = None
try:
    import lzma
except ImportError:
    lzma = None

RAW, ZLIB, BZ2, LZMA = "raw", "zlib", "bz2", "lzma"
CODECS = (RAW, ZLIB, BZ2, LZMA)
SMALLEST = "smallest"       # for a builder: try every codec this Python has and keep the smallest result
TABLE = "text_block"
KEEP = 4                    # blocks held unpacked at once
_MIN_DICT, _MAX_DICT = 1 << 16, 1 << 23


def available():
    """The codecs this Python can read and write."""
    return [c for c, module in ((RAW, True), (ZLIB, True), (BZ2, bz2), (LZMA, lzma)) if module]


def _filters(size):
    """The dictionary need be no larger than the block: a reader then allocates that much, and not the 64 MiB
    the strongest preset would ask for."""
    want = _MIN_DICT
    while want < size and want < _MAX_DICT:
        want <<= 1
    return [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME, "dict_size": want}]


def pack(raw, codec):
    """(the codec used, the packed bytes). SMALLEST tries them all; anything that does not shrink stays raw."""
    if codec == SMALLEST:
        tries = [pack(raw, c) for c in available()]
        return min(tries, key=lambda t: len(t[1]))
    if codec not in available():
        die("this Python cannot pack text with %s: it has %s" % (codec, ", ".join(available())))
    if codec == ZLIB:
        packed = zlib.compress(raw, 9)
    elif codec == BZ2:
        packed = bz2.compress(raw, 9)
    elif codec == LZMA:
        packed = lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC32, filters=_filters(len(raw)))
    else:
        packed = raw
    return (codec, packed) if len(packed) < len(raw) else (RAW, raw)


_DAMAGE = (zlib.error, EOFError, OSError, ValueError) + ((lzma.LZMAError,) if lzma is not None else ())


def unpack(data, codec):
    if codec not in CODECS:
        die("the database packs its text in a way this version does not know: it needs a newer toolkit")
    if codec not in available():
        die("this database is packed with %s, which this Python was built without: it cannot be read here" % codec)
    try:
        if codec == ZLIB:
            return zlib.decompress(data)
        if codec == BZ2:
            return bz2.decompress(data)
        if codec == LZMA:
            return lzma.decompress(data, format=lzma.FORMAT_XZ)
        return bytes(data)
    except _DAMAGE:
        die("a block of text in the database is damaged: rebuild or replace the file")


class Reader:
    """Reads pieces of text out of one open database."""

    def __init__(self, con):
        self.con = con
        self.blocks = {}

    def block(self, number):
        if number not in self.blocks:
            row = self.con.execute("SELECT codec, data FROM %s WHERE id = ?" % TABLE, (number,)).fetchone()
            if row is None:
                die("the database points at a block of text it does not hold: rebuild or replace the file")
            if len(self.blocks) >= KEEP:
                self.blocks.pop(next(iter(self.blocks)))
            self.blocks[number] = unpack(row[1], row[0])
        return self.blocks[number]

    def text(self, block, start, length):
        """One piece of text. An empty address (no block) is empty text."""
        if block is None:
            return ""
        raw = self.block(block)[start:start + length]
        if len(raw) != length:
            die("the database points past the end of a block of text: rebuild or replace the file")
        return raw.decode("utf-8")

    def everything(self):
        """Every block in turn, unpacked: (number, bytes). For a search through all the text."""
        for number, codec, data in self.con.execute("SELECT id, codec, data FROM %s ORDER BY id" % TABLE):
            yield number, unpack(data, codec)
