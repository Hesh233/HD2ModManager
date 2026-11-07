"""Lossless, lazy playback templates from the user-accepted normal animation pack.

The single route must fail closed if its bundled template is absent or changed.
Native/dual processors do not open this dependency. ZIP members are read lazily
by the bounded batch workers; no archive extraction or whole-pack parse is needed.
"""
from pathlib import Path
import hashlib
import json
import struct
import zipfile

REFERENCE_SHA256 = '4030765f8066141df8ecd0440322d128a4827d2cf9f5064a3a918b34eaefbf18'
REFERENCE_CLIPS = 3180
BUNDLE_SHA256 = '5df2f22b11bba8b30ffa4a231c6c56949ada67b66d56b429482e260e052ddc5a'
BUNDLE_RELATIVE = 'presets/single-normal-reference/playback.zip'
PLAYBACK_REVISION = 'normal-reference-r2'
FRAME_TIME_POLICY = 'user-normal-pack-template'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class NormalPlaybackReference:
    def __init__(self, path, *, expected_sha256=BUNDLE_SHA256,
                 expected_count=REFERENCE_CLIPS, expected_source=REFERENCE_SHA256):
        self.path = Path(path)
        if not self.path.is_file():
            raise ValueError('Missing single normal playback template; repair the manager runtime')
        self.sha256 = sha256(self.path)
        if self.sha256 != expected_sha256:
            raise ValueError('Single normal playback template SHA256 mismatch; repair the manager runtime')
        self.archive = zipfile.ZipFile(self.path)
        try:
            self.manifest = json.loads(self.archive.read('normal-reference.json'))
            m = self.manifest
            names = self.archive.namelist()
            if (m.get('schema') != 1 or m.get('revision') != PLAYBACK_REVISION
                    or m.get('sourceSha256') != expected_source
                    or m.get('clipCount') != expected_count or not isinstance(m.get('clips'), dict)
                    or len(m['clips']) != expected_count or len(names) != len(set(names))):
                raise ValueError('Invalid single normal playback template manifest')
            self.clips = {int(key, 16): row for key, row in m['clips'].items()}
            if (len(self.clips) != expected_count
                    or set(names) != {'normal-reference.json'} | {f'{i:016x}.animation' for i in self.clips}):
                raise ValueError('Invalid single normal playback template members')
        except Exception:
            self.archive.close()
            raise

    @classmethod
    def bundled(cls):
        return cls(Path(__file__).parent / BUNDLE_RELATIVE)

    def validate_ids(self, ids):
        if set(ids) != set(self.clips):
            raise ValueError('Game animation set differs from the accepted playback template; do not fall back to R1')

    def read(self, animation_id):
        row = self.clips.get(animation_id)
        if row is None:
            raise ValueError(f'Missing normal playback template for {animation_id:016x}')
        raw = self.archive.read(f'{animation_id:016x}.animation')
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError(f'Corrupt normal playback template for {animation_id:016x}')
        return raw

    def report(self):
        return dict(referencePlaybackSha256=self.manifest['sourceSha256'],
                    referencePlaybackBundleSha256=self.sha256,
                    referencePlaybackClips=len(self.clips),
                    referencePlaybackPath=BUNDLE_RELATIVE,
                    preserveReferencePlayback=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.archive.close()


def build_bundle(source, output):
    """Reproducible lossless resource ZIP; only the exact accepted pack is allowed."""
    from .constants import ANIMATION_TYPE_ID
    source, output = Path(source), Path(output)
    if sha256(source) != REFERENCE_SHA256:
        raise ValueError('Playback source is not the user-accepted normal pack')
    with source.open('rb') as stream:
        header = stream.read(72)
        type_count, count = struct.unpack_from('<II', header, 4)
        stream.seek(72 + 32 * type_count)
        rows = [struct.unpack('<QQQQQQQIIIIII', stream.read(80)) for _ in range(count)]
        if len(rows) != REFERENCE_CLIPS or len({r[0] for r in rows}) != len(rows) or any(r[1] != ANIMATION_TYPE_ID for r in rows):
            raise ValueError('Normal source must contain the complete animation-only set')
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.zip-incomplete')
        manifest = dict(schema=1, revision=PLAYBACK_REVISION, sourceSha256=REFERENCE_SHA256,
                        sourceBytes=source.stat().st_size, clipCount=len(rows), clips={})
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                def write(name, data):
                    info = zipfile.ZipInfo(name, (2026, 11, 7, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    archive.writestr(info, data, compresslevel=6)
                for number, row in enumerate(sorted(rows), 1):
                    stream.seek(row[2]); raw = stream.read(row[7])
                    if len(raw) != row[7]:
                        raise ValueError('Truncated normal animation')
                    key = f'{row[0]:016x}'
                    manifest['clips'][key] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                    write(key + '.animation', raw)
                    if number % 500 == 0:
                        print(f'playback template {number}/{len(rows)}', flush=True)
                write('normal-reference.json', json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
            if BUNDLE_SHA256 != 'PENDING_BUILD' and sha256(temporary) != BUNDLE_SHA256:
                raise ValueError('Rebuilt playback bundle differs from certified bundle')
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    return dict(path=str(output), bytes=output.stat().st_size, sha256=sha256(output), clips=REFERENCE_CLIPS)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build_bundle(args.source, args.output)))
