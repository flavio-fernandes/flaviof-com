#!/usr/bin/env python3
"""Strip identifying metadata from the images this site publishes.

Why this exists: the photos under static/img/ come off phones and out of photo
editors, and they arrive carrying EXIF GPS coordinates, capture timestamps,
camera and lens models, and editor provenance. Everything in static/img/ is
copied verbatim to the live server, so whatever is in a file is published.
One of the about-page photos reached this repo with the GPS position of the
place it was taken; a picture captioned "trails near home" would have
published a home address the same way.

Do not rely on `sips -Z` to clean a file. It strips metadata inconsistently:
in practice it flattened ten photos to colour-space tags and left an eleventh
(one that arrived with a Lightroom-written EXIF/XMP block) almost untouched.

This rewrites the *container* only -- the compressed image data is copied
through byte for byte, so there is no re-encoding and no quality loss. Run it
on anything before committing it:

    python3 tools/strip-image-metadata.py static/img
    python3 tools/strip-image-metadata.py --check static/img   # report only

--check exits non-zero if anything identifying is still present, so it also
works as a guard in a hook or a pre-commit check.

SVG and PDF are reported but never rewritten: both can carry metadata, and
neither is safe to edit blind with the standard library.
"""

import argparse
import os
import struct
import sys

# JPEG ---------------------------------------------------------------------
# Markers that stand alone, with no length field following them.
JPEG_STANDALONE = {0x01} | set(range(0xD0, 0xDA))
JPEG_SOS = 0xDA
JPEG_COM = 0xFE


def clean_jpeg(data):
    """Drop APPn and COM segments, keeping only JFIF and a real ICC profile.

    APP1 holds EXIF (GPS, timestamps, camera body and lens) and XMP (editor
    history, ratings, place names). APP13 holds IPTC. APP2 is kept when it is
    an ICC colour profile: that carries no identity, and dropping it can shift
    colours on wide-gamut displays.
    """
    if data[:2] != b"\xff\xd8":
        return None, []

    out = bytearray(b"\xff\xd8")
    removed = []
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            # Not at a marker boundary; copy the rest rather than guess.
            out += data[i:]
            break
        marker = data[i + 1]

        if marker == JPEG_SOS:
            out += data[i:]  # scan data runs to EOI; copy it untouched
            break
        if marker in JPEG_STANDALONE:
            out += data[i:i + 2]
            i += 2
            continue

        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        segment = data[i:i + 2 + length]
        payload = data[i + 4:i + 2 + length]

        keep = True
        if marker == 0xE0:
            keep = True                       # APP0/JFIF: density only
        elif marker == 0xE2:
            keep = payload.startswith(b"ICC_PROFILE\x00")
        elif 0xE1 <= marker <= 0xEF or marker == JPEG_COM:
            keep = False

        if keep:
            out += segment
        else:
            removed.append("%s(%dB)" % (jpeg_marker_name(marker, payload), length))
        i += 2 + length

    return bytes(out), removed


def jpeg_marker_name(marker, payload):
    if marker == JPEG_COM:
        return "COM"
    if marker == 0xE1:
        if payload.startswith(b"Exif\x00\x00"):
            return "APP1/EXIF"
        if b"xmpmeta" in payload or payload.startswith(b"http://ns.adobe.com/xap"):
            return "APP1/XMP"
        return "APP1"
    if marker == 0xED:
        return "APP13/IPTC"
    return "APP%d" % (marker - 0xE0)


# PNG ----------------------------------------------------------------------
# Critical chunks plus the ancillary ones that affect rendering. Everything
# else -- tEXt/zTXt/iTXt (free-form text, often editor and author strings),
# eXIf, tIME, and Apple's iDOT -- is dropped.
PNG_KEEP = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM",
    b"sRGB", b"iCCP", b"bKGD", b"pHYs", b"sBIT",
    b"acTL", b"fcTL", b"fdAT",            # APNG animation
}


def clean_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, []

    out = bytearray(data[:8])
    removed = []
    i = 8
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        chunk = data[i:i + 12 + length]
        if ctype in PNG_KEEP:
            out += chunk
        else:
            removed.append("%s(%dB)" % (ctype.decode("ascii", "replace"), length))
        i += 12 + length
        if ctype == b"IEND":
            break
    return bytes(out), removed


# GIF ----------------------------------------------------------------------
def clean_gif(data):
    """Drop comment and plain-text extensions, and application extensions
    other than the NETSCAPE block that animation looping depends on."""
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None, []

    out = bytearray(data[:13])
    removed = []
    i = 13
    flags = data[10]
    if flags & 0x80:                                  # global colour table
        n = 3 * (2 ** ((flags & 0x07) + 1))
        out += data[i:i + n]
        i += n

    def sub_blocks(j):
        """Walk a chain of length-prefixed sub-blocks; return end offset."""
        while j < len(data) and data[j] != 0x00:
            j += 1 + data[j]
        return j + 1

    while i < len(data):
        b = data[i]
        if b == 0x3B:                                 # trailer
            out += data[i:i + 1]
            break
        if b == 0x21:                                 # extension
            label = data[i + 1]
            end = sub_blocks(i + 2)
            block = data[i:end]
            if label == 0xFE:
                removed.append("comment-ext(%dB)" % len(block))
            elif label == 0x01:
                removed.append("plaintext-ext(%dB)" % len(block))
            elif label == 0xFF and data[i + 3:i + 14] != b"NETSCAPE2.0":
                removed.append("app-ext:%s(%dB)"
                               % (data[i + 3:i + 11].decode("ascii", "replace"), len(block)))
            else:
                out += block
            i = end
            continue
        if b == 0x2C:                                 # image descriptor
            lflags = data[i + 9]
            j = i + 10
            if lflags & 0x80:
                j += 3 * (2 ** ((lflags & 0x07) + 1))
            j += 1                                    # LZW minimum code size
            end = sub_blocks(j)
            out += data[i:end]
            i = end
            continue
        out += data[i:]                               # unknown; copy the rest
        break
    return bytes(out), removed


# Inspection ---------------------------------------------------------------
IDENT_TAGS = {
    0x010E: "ImageDescription", 0x010F: "Make", 0x0110: "Model",
    0x0132: "DateTime", 0x013B: "Artist", 0x8298: "Copyright",
    0x9003: "DateTimeOriginal", 0x9004: "DateTimeDigitized",
    0xA433: "LensMake", 0xA434: "LensModel", 0xA431: "BodySerialNumber",
}


def inspect(path):
    """Report what a strip would remove, for --check.

    This runs the same cleaners rather than searching for byte patterns, so
    the report and the rewrite can never disagree. (An earlier version looked
    for the GIF comment marker 0x21 0xFE with a plain byte search and flagged
    three animations that have no comment block at all -- those two bytes
    occur freely inside LZW data.) JPEG additionally gets its EXIF walked, so
    the report can name GPS and the other identifying tags outright.
    """
    data = open(path, "rb").read()
    ext = path.lower().rsplit(".", 1)[-1]

    if ext == "svg":
        return inspect_svg(data)
    if ext == "pdf":
        return inspect_pdf(data)

    cleaner = CLEANERS.get(ext)
    if cleaner is None:
        return []
    _cleaned, removed = cleaner(data)
    found = list(removed)

    if ext in ("jpg", "jpeg") and data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 3:
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker == JPEG_SOS:
                break
            if marker in JPEG_STANDALONE:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            payload = data[i + 4:i + 2 + length]
            if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
                found += exif_findings(payload[6:])
            i += 2 + length

    return found


# SVG and PDF are reported, never rewritten -- neither is safe to edit blind
# with the standard library. Both report only what is actually identifying, so
# a clean hand-written SVG or a slide export with nothing but a title does not
# sit in the report forever crying wolf.
SVG_MARKERS = (b"<metadata", b"rdf:RDF", b"sodipodi:", b"inkscape:",
               b"<dc:", b"xmlns:cc", b"<i:pgf", b"xmpmeta")


def inspect_svg(data):
    found = [m.decode("ascii").strip("<:") for m in SVG_MARKERS if m in data]
    return ["svg:%s (strip by hand)" % ", ".join(found)] if found else []


def inspect_pdf(data):
    import re
    # Creator/Producer/Title name the exporting tool or the deck; Author,
    # the timestamps and an XMP packet are the ones that identify a person.
    found = []
    for field in (b"Author", b"Subject", b"Keywords", b"CreationDate", b"ModDate"):
        if re.search(br"/" + field + br"\s*[(<]", data):
            found.append(field.decode())
    if b"<x:xmpmeta" in data:
        found.append("XMP")
    return ["pdf:%s (strip by hand)" % ", ".join(found)] if found else []


def exif_findings(tiff):
    """Walk the TIFF IFDs looking for GPS and identifying tags."""
    if len(tiff) < 8:
        return []
    bo = "<" if tiff[:2] == b"II" else ">"
    found = []

    def walk(off, depth=0):
        if depth > 3 or off <= 0 or off + 2 > len(tiff):
            return
        count = struct.unpack(bo + "H", tiff[off:off + 2])[0]
        if count > 500:
            return
        for k in range(count):
            e = off + 2 + k * 12
            if e + 12 > len(tiff):
                return
            tag, _typ, _cnt = struct.unpack(bo + "HHI", tiff[e:e + 8])
            val = tiff[e + 8:e + 12]
            if tag == 0x8825:
                found.append("GPS")
                continue
            if tag in IDENT_TAGS:
                found.append(IDENT_TAGS[tag])
            if tag == 0x8769:
                walk(struct.unpack(bo + "I", val)[0], depth + 1)

    walk(struct.unpack(bo + "I", tiff[4:8])[0])
    return found


# Driver -------------------------------------------------------------------
CLEANERS = {"jpg": clean_jpeg, "jpeg": clean_jpeg, "png": clean_png, "gif": clean_gif}


def walk_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in sorted(files):
                yield os.path.join(dirpath, name)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="files or directories to process")
    ap.add_argument("--check", action="store_true",
                    help="report what is present and exit non-zero if anything is; change nothing")
    args = ap.parse_args()

    dirty = 0
    changed = 0
    for path in walk_files(args.paths):
        ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""

        if args.check:
            if ext not in ("jpg", "jpeg", "png", "gif", "svg", "pdf"):
                continue
            hits = inspect(path)
            if hits:
                dirty += 1
                print("DIRTY  %-58s %s" % (path, ", ".join(sorted(set(hits)))))
            continue

        if ext not in CLEANERS:
            continue
        before = open(path, "rb").read()
        cleaned, removed = CLEANERS[ext](before)
        if cleaned is None or not removed:
            continue
        with open(path, "wb") as fh:
            fh.write(cleaned)
        changed += 1
        print("%-58s -%-6d bytes  removed: %s"
              % (path, len(before) - len(cleaned), ", ".join(removed)))

    if args.check:
        print("\n%d file(s) still carrying metadata." % dirty)
        return 1 if dirty else 0
    print("\n%d file(s) rewritten." % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
