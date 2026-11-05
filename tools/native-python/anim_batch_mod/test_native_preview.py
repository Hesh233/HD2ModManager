import copy
import struct
import tempfile
import unittest
from pathlib import Path

from anim_batch_mod.archive import InlinePatchWriter, TocArchive, TocEntry
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.native_skeleton import load_avatar_template


class StandaloneAvatarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'test.patch_0'
        self.archive = TocArchive(99, bytes(range(56)), {})

    def write(self, entries):
        counts = {e.type_id: sum(x.type_id == e.type_id for x in entries) for e in entries}
        writer = InlinePatchWriter(self.archive, self.path, counts, standalone=True)
        try:
            for entry in entries:
                writer.append(entry)
            return writer.finish()
        finally:
            writer.close()

    def test_mixed_payloads_keep_aligned_sidecars_and_normalized_header(self):
        entries = [TocEntry(1, 2, b'a', b'gpu', b'stream'),
                   TocEntry(3, 4, b'animation'), TocEntry(5, 2, b'unit', b'GPU2', b'S2')]
        paths = self.write(entries)
        data, gpu, stream = (p.read_bytes() for p in paths)
        parsed = TocArchive.parse_parts(data, gpu, stream)
        for entry in entries:
            actual = parsed.entries[entry.file_id, entry.type_id]
            self.assertEqual((actual.toc_data, actual.gpu_data, actual.stream_data),
                             (entry.toc_data, entry.gpu_data, entry.stream_data))
        self.assertEqual(parsed.unknown, 0)
        expected = bytearray(56)
        struct.pack_into('<Q', expected, 16, len(data))
        self.assertEqual(parsed.header_data, expected)
        for i in range(3):
            record = struct.unpack_from('<QQQQQQQIIIIII', data, 136+80*i)
            self.assertEqual(record[2] % 16, 0)
            self.assertEqual(record[3] % 64, 0)
            self.assertEqual(record[4] % 64, 0)

    def test_inline_mode_still_rejects_external_data(self):
        writer = InlinePatchWriter(self.archive, self.path, {2: 1})
        self.addCleanup(writer.close)
        with self.assertRaises(ValueError):
            writer.append(TocEntry(1, 2, b'unit', b'gpu'))

    def test_finish_detects_sidecar_corruption(self):
        writer = InlinePatchWriter(self.archive, self.path, {2: 1}, standalone=True)
        self.addCleanup(writer.close)
        writer.append(TocEntry(1, 2, b'unit', b'gpu'))
        writer.external[0].seek(0)
        writer.external[0].write(b'bad')
        with self.assertRaisesRegex(ValueError, 'External payload'):
            writer.finish()

    def unit(self):
        data = bytearray(64+16+136)
        struct.pack_into('<Q', data, 8, 123)
        struct.pack_into('<Q', data, 32, 456)
        struct.pack_into('<I', data, 52, 64)
        struct.pack_into('<I', data, 64, 1)
        struct.pack_into('<16f', data, 80, 1,0,0,0,1,0,0,0,1,0,0,0,1,1,1,0)
        struct.pack_into('<I', data, len(data)-4, 42)
        return TocEntry(7, UNIT_TYPE_ID, data, b'mesh')

    def test_template_accepts_identical_bind_with_different_mesh_packaging(self):
        standalone = self.unit()
        original = copy.deepcopy(standalone)
        struct.pack_into('<Q', original.toc_data, 16, 789)
        original.gpu_data = b''
        self.write([standalone])
        result = load_avatar_template(self.path, original)
        self.assertEqual(result.toc_data, standalone.toc_data)
        self.assertEqual(result.gpu_data, b'mesh')

    def test_template_rejects_stale_bind_and_reference(self):
        original = self.unit()
        for offset, value in ((116, 0.1), (8, 124)):
            stale = copy.deepcopy(original)
            struct.pack_into('<f' if offset == 116 else '<Q', stale.toc_data, offset, value)
            self.write([stale])
            with self.assertRaises(ValueError):
                load_avatar_template(self.path, original)

    def test_template_rejects_composite_and_extra_resources(self):
        original = self.unit()
        composite = copy.deepcopy(original)
        struct.pack_into('<Q', composite.toc_data, 16, 789)
        for entries in ([composite], [original, TocEntry(99, 2, b'animation')]):
            self.write(entries)
            with self.assertRaises(ValueError):
                load_avatar_template(self.path, original)


if __name__ == '__main__':
    unittest.main()
