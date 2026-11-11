#!/usr/bin/env python3
"""Check thin arm64 Mach-O CodeDirectory page hashes without loading code.

This supplements, never replaces, macOS codesign --verify and a real host
integration test. It catches install_name_tool edits made after signing.
"""
import argparse
import hashlib
import struct
import zipfile
from pathlib import Path


def verify_bytes(data):
    def unpack(fmt, offset):
        return struct.unpack_from(fmt, data, offset)
    if unpack('<I', 0)[0] != 0xfeedfacf:
        raise ValueError('expected thin 64-bit Mach-O')
    if unpack('<I', 4)[0] != 0x100000c:
        raise ValueError('expected arm64 Mach-O')
    offset = 32
    signature = None
    for _ in range(unpack('<I', 16)[0]):
        cmd, size = unpack('<II', offset)
        if size < 8 or offset + size > len(data):
            raise ValueError('invalid load command')
        if cmd == 0x1d:
            signature = unpack('<II', offset + 8)
        offset += size
    if signature is None:
        raise ValueError('missing embedded code signature')
    start, size = signature
    if start + size > len(data):
        raise ValueError('truncated signature')
    magic, length, count = unpack('>III', start)
    if magic != 0xfade0cc0 or length > size:
        raise ValueError('invalid signature superblob')
    checked = 0
    for i in range(count):
        _, relative = unpack('>II', start + 12 + i * 8)
        cd = start + relative
        if unpack('>I', cd)[0] != 0xfade0c02:
            continue
        cd_length = unpack('>I', cd + 4)[0]
        hash_offset, _, _, slots, limit = unpack('>5I', cd + 16)
        hash_size, hash_type, _, page_exp = unpack('>4B', cd + 36)
        algorithm = {1: 'sha1', 2: 'sha256', 3: 'sha256', 4: 'sha384'}.get(hash_type)
        if not algorithm or not hash_size or page_exp > 30:
            raise ValueError('unsupported CodeDirectory hash format')
        if limit > start or cd + cd_length > start + length:
            raise ValueError('invalid CodeDirectory bounds')
        page_size = 1 << page_exp
        if slots != (limit + page_size - 1) // page_size:
            raise ValueError('invalid code page count')
        if hash_offset + slots * hash_size > cd_length:
            raise ValueError('truncated code hashes')
        for slot in range(slots):
            actual = hashlib.new(algorithm, data[slot * page_size:min((slot + 1) * page_size, limit)]).digest()[:hash_size]
            begin = cd + hash_offset + slot * hash_size
            if actual != data[begin:begin + hash_size]:
                raise ValueError('code signature page %d does not match final bytes' % slot)
        checked += 1
    if not checked:
        raise ValueError('missing CodeDirectory')
    return checked


def verify_oxt(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist()
                 if n.startswith('native/macos/lib/') and n.endswith('.dylib')]
        if not names:
            raise ValueError('no bundled macOS dylibs')
        for name in names:
            try:
                verify_bytes(archive.read(name))
            except (ValueError, struct.error) as exc:
                raise ValueError('%s: %s' % (name, exc)) from exc
        return len(names)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('oxt', type=Path)
    args = parser.parse_args()
    print('Verified page hashes for %d macOS dylibs' % verify_oxt(args.oxt))
