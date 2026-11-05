from __future__ import annotations

import os
import hashlib
import sqlite3
import struct
from bisect import bisect_left
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from .binary import BinaryFormatError, align
from .constants import DSAR_MAGIC, TOC_MAGIC


CONTINUE_CHUNK = 0x04
START_CHUNK = 0x02
COMPRESSED_CHUNK = 0x03


@dataclass
class BundleEntry:
    original_archive_offset: int
    start_offset: int
    bundle_index: int


@dataclass
class BundledPackage:
    name: str
    size: int
    entries: list[BundleEntry] = field(default_factory=list)


class PackageStore:
    def __init__(self, game_data: Path):
        self.game_data = game_data.resolve()
        if not self.game_data.is_dir():
            raise FileNotFoundError(f"Game data directory does not exist: {self.game_data}")
        self.is_bundled = not (self.game_data / "9ba626afa44a3aa3").exists()
        self.packages: dict[str, BundledPackage] = {}
        self._bundle_headers: OrderedDict[
            Path, list[tuple[int, int, int, int, int, int]]
        ] = OrderedDict()
        if self.is_bundled:
            self._initialize_bundle_mapping()

    def package_names(self) -> list[str]:
        if self.is_bundled:
            names = self.packages.keys()
        else:
            names = (
                path.name
                for path in self.game_data.iterdir()
                if path.is_file() and path.suffix == ""
            )
        return sorted(
            name
            for name in names
            if ".patch_" not in name
            and not name.endswith(".gpu_resources")
            and not name.endswith(".stream")
        )

    def index_package_names(self) -> list[str]:
        names = self.package_names()
        if not self.is_bundled:
            return names
        return sorted(
            names,
            key=lambda name: (
                self.packages[name].entries[0].bundle_index
                if self.packages[name].entries
                else 0xFFFF,
                self.packages[name].entries[0].start_offset
                if self.packages[name].entries
                else 0xFFFFFFFF,
                name,
            ),
        )

    def index_fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(b"anim-batch-mod-resource-index-v2\x00")
        if self.is_bundled:
            candidates = [
                self.game_data / "bundle_database.data",
                self.game_data / "bundles.nxa",
                *self.game_data.glob("bundles.*.nxa"),
            ]
        else:
            candidates = [
                path
                for path in self.game_data.iterdir()
                if path.is_file() and path.suffix == ""
            ]
        for path in sorted(candidates, key=lambda item: item.name):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            digest.update(path.name.encode("utf-8", errors="surrogatepass"))
            digest.update(struct.pack("<QQ", stat.st_size, stat.st_mtime_ns))
        return digest.hexdigest()

    def has_package(self, name: str) -> bool:
        if self.is_bundled:
            return name in self.packages
        return (self.game_data / name).is_file()

    def load_package(self, name: str) -> tuple[bytearray, bytearray, bytearray]:
        return (
            self._load_package_part(name),
            self._load_package_part(f"{name}.gpu_resources"),
            self._load_package_part(f"{name}.stream"),
        )

    def load_package_toc(self, name: str) -> bytearray:
        return self._load_package_part(name)

    def load_toc_header(self, name: str) -> bytes:
        if self.is_bundled:
            package = self.packages.get(name)
            if not package or not package.entries:
                return b""
            first = package.entries[0]
            return self._read_bundle_resource(
                self.game_data / f"bundles.{first.bundle_index:02d}.nxa",
                first.start_offset,
            )

        path = self.game_data / name
        if not path.is_file():
            return b""
        with path.open("rb") as handle:
            magic_data = handle.read(4)
            if len(magic_data) != 4:
                return b""
            magic = int.from_bytes(magic_data, "little")
            if magic == DSAR_MAGIC:
                return self._read_bundle_resource(path, 0)
            handle.seek(0)
            header = handle.read(12)
            if len(header) != 12:
                return b""
            magic, type_count, file_count = struct.unpack("<III", header)
            if magic != TOC_MAGIC:
                return b""
            handle.seek(0)
            return handle.read(72 + type_count * 32 + file_count * 80)

    def _load_package_part(self, name: str) -> bytearray:
        path = self.game_data / name
        if path.exists():
            with path.open("rb") as handle:
                magic_data = handle.read(4)
                if len(magic_data) != 4:
                    return bytearray()
                magic = int.from_bytes(magic_data, "little")
            if magic == DSAR_MAGIC:
                return bytearray(self._decompress_dsar(path))
            return bytearray(path.read_bytes())

        package = self.packages.get(name)
        if not package:
            return bytearray()
        output = bytearray(package.size)
        for index, entry in enumerate(package.entries):
            if index + 1 < len(package.entries):
                size = (
                    package.entries[index + 1].original_archive_offset
                    - entry.original_archive_offset
                )
            else:
                size = package.size - entry.original_archive_offset
            parts = []
            loaded = 0
            offset = entry.start_offset
            bundle_path = self.game_data / f"bundles.{entry.bundle_index:02d}.nxa"
            while loaded < size:
                resource = self._read_bundle_resource(bundle_path, offset + loaded)
                if not resource:
                    raise BinaryFormatError(
                        f"Unable to reconstruct package {name} at bundle offset {offset + loaded}"
                    )
                parts.append(resource)
                loaded += len(resource)
            combined = b"".join(parts)
            start = entry.original_archive_offset
            output[start:start + len(combined)] = combined
        return output

    def _initialize_bundle_mapping(self) -> None:
        bundles_index = self.game_data / "bundles.nxa"
        if not bundles_index.is_file():
            raise FileNotFoundError(
                f"Bundled game data is missing bundles.nxa: {bundles_index}"
            )
        contents = self._decompress_dsar(bundles_index)
        if len(contents) < 0x18:
            raise BinaryFormatError("bundles.nxa index is too small")
        package_count = int.from_bytes(contents[0x10:0x14], "little")
        for package_index in range(package_count):
            location = 0x18 + package_index * 0x18
            package_size = int.from_bytes(contents[location:location + 8], "little")
            name_offset = int.from_bytes(contents[location + 8:location + 12], "little")
            item_count = int.from_bytes(contents[location + 12:location + 16], "little")
            items_offset = int.from_bytes(contents[location + 16:location + 20], "little")
            name_end = contents.find(b"\x00", name_offset)
            if name_end < 0:
                raise BinaryFormatError("Unterminated package name in bundles.nxa")
            name = contents[name_offset:name_end].decode("utf-8")
            entries = []
            for item_index in range(item_count):
                item = items_offset + item_index * 0x10
                entries.append(
                    BundleEntry(
                        original_archive_offset=int.from_bytes(
                            contents[item:item + 8], "little"
                        ),
                        start_offset=int.from_bytes(contents[item + 8:item + 12], "little"),
                        bundle_index=contents[item + 15],
                    )
                )
            self.packages[name] = BundledPackage(name, package_size, entries)

    def _decompress_dsar(self, path: Path) -> bytes:
        headers = self._read_bundle_headers(path)
        output = []
        with path.open("rb") as handle:
            for _, compressed_offset, uncompressed_size, compressed_size, compression, _ in headers:
                handle.seek(compressed_offset)
                data = handle.read(compressed_size)
                output.append(self._decompress_chunk(data, compression, uncompressed_size))
        return b"".join(output)

    def _read_bundle_resource(self, path: Path, resource_offset: int) -> bytes:
        headers = self._read_bundle_headers(path)
        start_index = bisect_left(headers, resource_offset, key=lambda header: header[0])
        if start_index >= len(headers) or headers[start_index][0] != resource_offset:
            return b""
        output = []
        with path.open("rb") as handle:
            for index in range(start_index, len(headers)):
                (
                    _,
                    compressed_offset,
                    uncompressed_size,
                    compressed_size,
                    compression,
                    chunk_type,
                ) = headers[index]
                if index != start_index and chunk_type & START_CHUNK:
                    break
                handle.seek(compressed_offset)
                data = handle.read(compressed_size)
                output.append(self._decompress_chunk(data, compression, uncompressed_size))
        return b"".join(output)

    def _read_bundle_headers(self, path: Path):
        path = path.resolve()
        cached = self._bundle_headers.pop(path, None)
        if cached is not None:
            self._bundle_headers[path] = cached
            return cached
        with path.open("rb") as handle:
            magic = int.from_bytes(handle.read(4), "little")
            if magic != DSAR_MAGIC:
                raise BinaryFormatError(f"Not a DSAR bundle: {path}")
            handle.seek(8)
            chunk_count = int.from_bytes(handle.read(4), "little")
            handle.seek(0x20)
            headers = [struct.unpack("<QQIIBB6x", handle.read(0x20)) for _ in range(chunk_count)]
        self._bundle_headers[path] = headers
        while len(self._bundle_headers) > 2:
            self._bundle_headers.popitem(last=False)
        return headers

    @staticmethod
    def _decompress_chunk(data: bytes, compression: int, uncompressed_size: int) -> bytes:
        if compression != COMPRESSED_CHUNK:
            return data
        try:
            from utils.lz4_311 import block
        except ImportError as error:
            raise RuntimeError(
                "The bundled LZ4 module could not be imported. Run with Python 3.11 from the repository root."
            ) from error
        return block.decompress(data, uncompressed_size=uncompressed_size)


@dataclass
class TocEntry:
    file_id: int
    type_id: int
    toc_data: bytearray = field(default_factory=bytearray)
    gpu_data: bytearray = field(default_factory=bytearray)
    stream_data: bytearray = field(default_factory=bytearray)
    unknown1: int = 0
    unknown2: int = 0
    unknown3: int = 16
    unknown4: int = 64


@dataclass
class TocArchive:
    unknown: int
    header_data: bytes
    entries: dict[tuple[int, int], TocEntry]

    @classmethod
    def parse_parts(
        cls,
        toc_data: bytes | bytearray,
        gpu_data: bytes | bytearray = b"",
        stream_data: bytes | bytearray = b"",
        load_external_data: bool = True,
    ) -> "TocArchive":
        if len(toc_data) < 72:
            raise BinaryFormatError("TOC archive is too small")
        magic, type_count, file_count, unknown = struct.unpack_from("<IIII", toc_data, 0)
        if magic != TOC_MAGIC:
            raise BinaryFormatError(f"Unexpected TOC magic: {magic}")
        header_data = bytes(toc_data[16:72])
        offset = 72 + type_count * 32
        entries = {}
        for _ in range(file_count):
            values = struct.unpack_from("<QQQQQQQIIIIII", toc_data, offset)
            (
                file_id,
                type_id,
                toc_offset,
                stream_offset,
                gpu_offset,
                unknown1,
                unknown2,
                toc_size,
                stream_size,
                gpu_size,
                unknown3,
                unknown4,
                _,
            ) = values
            if toc_size and toc_offset + toc_size > len(toc_data):
                raise BinaryFormatError(f"TOC entry {file_id} data is outside the archive")
            if load_external_data and gpu_size and gpu_offset + gpu_size > len(gpu_data):
                raise BinaryFormatError(f"TOC entry {file_id} GPU data is outside the archive")
            if (
                load_external_data
                and stream_size
                and stream_offset + stream_size > len(stream_data)
            ):
                raise BinaryFormatError(f"TOC entry {file_id} stream data is outside the archive")
            entries[(file_id, type_id)] = TocEntry(
                file_id=file_id,
                type_id=type_id,
                toc_data=bytearray(toc_data[toc_offset:toc_offset + toc_size]),
                gpu_data=(
                    bytearray(gpu_data[gpu_offset:gpu_offset + gpu_size])
                    if load_external_data
                    else bytearray()
                ),
                stream_data=(
                    bytearray(stream_data[stream_offset:stream_offset + stream_size])
                    if load_external_data
                    else bytearray()
                ),
                unknown1=unknown1,
                unknown2=unknown2,
                unknown3=unknown3,
                unknown4=unknown4,
            )
            offset += 80
        return cls(unknown=unknown, header_data=header_data, entries=entries)

    @classmethod
    def load(cls, store: PackageStore, package_name: str) -> "TocArchive":
        return cls.parse_parts(*store.load_package(package_name))

    @classmethod
    def load_toc_only(cls, store: PackageStore, package_name: str) -> "TocArchive":
        return cls.parse_parts(
            store.load_package_toc(package_name), load_external_data=False
        )

    def get_entry(self, file_id: int, type_id: int) -> TocEntry | None:
        return self.entries.get((file_id, type_id))

    def entries_of_type(self, type_id: int) -> list[TocEntry]:
        return [entry for entry in self.entries.values() if entry.type_id == type_id]

    def write_patch(self, output_path: Path, entries: list[TocEntry]) -> tuple[Path, Path, Path]:
        type_ids = []
        for entry in entries:
            if entry.type_id not in type_ids:
                type_ids.append(entry.type_id)
        type_counts = {
            type_id: sum(entry.type_id == type_id for entry in entries) for type_id in type_ids
        }
        header_size = 72 + len(type_ids) * 32 + len(entries) * 80
        toc = bytearray(header_size)
        gpu = bytearray()
        stream = bytearray()
        toc_cursor = header_size
        entry_values = []
        for index, entry in enumerate(entries, start=1):
            toc_offset = toc_cursor
            toc.extend(entry.toc_data)
            toc_cursor += len(entry.toc_data)

            gpu_offset = align(len(gpu), 64)
            if len(gpu) < gpu_offset:
                gpu.extend(b"\x00" * (gpu_offset - len(gpu)))
            gpu.extend(entry.gpu_data)

            stream_offset = align(len(stream), 64)
            if len(stream) < stream_offset:
                stream.extend(b"\x00" * (stream_offset - len(stream)))
            stream.extend(entry.stream_data)
            entry_values.append(
                (
                    entry.file_id,
                    entry.type_id,
                    toc_offset,
                    stream_offset,
                    gpu_offset,
                    entry.unknown1,
                    entry.unknown2,
                    len(entry.toc_data),
                    len(entry.stream_data),
                    len(entry.gpu_data),
                    entry.unknown3,
                    entry.unknown4,
                    index,
                )
            )

        minimum_size = 256 * len(entries)
        if len(toc) < minimum_size:
            toc.extend(b"\x00" * (minimum_size - len(toc)))
        struct.pack_into(
            "<IIII56s",
            toc,
            0,
            TOC_MAGIC,
            len(type_ids),
            len(entries),
            self.unknown,
            self.header_data,
        )
        offset = 72
        for type_id in type_ids:
            struct.pack_into("<QQQII", toc, offset, 0, type_id, type_counts[type_id], 16, 64)
            offset += 32
        for values in entry_values:
            struct.pack_into("<QQQQQQQIIIIII", toc, offset, *values)
            offset += 80

        output_path.parent.mkdir(parents=True, exist_ok=True)
        gpu_path = Path(f"{output_path}.gpu_resources")
        stream_path = Path(f"{output_path}.stream")
        output_path.write_bytes(toc)
        gpu_path.write_bytes(gpu)
        stream_path.write_bytes(stream)
        return output_path, gpu_path, stream_path


class InlinePatchWriter:
    """Stream a companion archive, optionally preserving external resource data."""

    def __init__(self, archive, path, type_counts, *, standalone=False):
        self.path = Path(path)
        self.standalone = standalone
        self.type_counts = dict(type_counts)
        self.count = sum(type_counts.values())
        self.header_size = 72 + 32*len(type_counts) + 80*self.count
        self.file = self.path.open('w+b')
        self.file.write(struct.pack('<IIII56s', TOC_MAGIC,len(type_counts),self.count,
                                    0 if standalone else archive.unknown,
                                    bytes(56) if standalone else archive.header_data))
        for kind,count in type_counts.items():
            self.file.write(struct.pack('<QQQII',0,kind,count,16,64))
        self.file.write(bytes(80*self.count))
        self.records = []
        self.seen = set()
        self.sides = [Path(str(self.path)+suffix) for suffix in ('.gpu_resources','.stream')]
        self.external = [side.open('w+b') for side in self.sides] if standalone else []
        self.external_records = []

    def append(self, entry):
        import hashlib
        key = entry.file_id,entry.type_id
        if key in self.seen or (not self.standalone and (entry.gpu_data or entry.stream_data)) or len(self.records)>=self.count:
            raise ValueError('Duplicate, external or excessive inline resource')
        if entry.type_id not in self.type_counts:
            raise ValueError('Unexpected resource type')
        self.seen.add(key)
        if self.standalone:
            self.file.write(bytes(-self.file.tell()%16))
        offset=self.file.tell()
        self.file.write(entry.toc_data)
        offsets = [0, 0]
        for i, (stream, payload) in enumerate(zip(self.external, (entry.gpu_data, entry.stream_data))):
            if not payload:
                continue
            stream.write(bytes(-stream.tell()%64))
            offsets[i] = stream.tell()
            stream.write(payload)
            self.external_records.append((i, offsets[i], len(payload), hashlib.sha256(payload).digest()))
        values=(*key,offset,offsets[1],offsets[0],
                0 if self.standalone else entry.unknown1,0 if self.standalone else entry.unknown2,
                len(entry.toc_data),len(entry.stream_data),len(entry.gpu_data),
                entry.unknown3,entry.unknown4,len(self.records)+1)
        self.records.append((values,hashlib.sha256(entry.toc_data).digest()))

    def finish(self):
        import hashlib
        from collections import Counter
        if Counter(v[1] for v,_ in self.records)!=self.type_counts:
            raise ValueError('Incomplete single-patch resource set')
        if self.file.tell()<256*self.count:
            self.file.write(bytes(256*self.count-self.file.tell()))
        if self.standalone:
            self.file.write(bytes(-self.file.tell()%16))
            size = self.file.tell()
            self.file.seek(32)
            self.file.write(struct.pack('<Q', size))
        self.file.seek(72+32*len(self.type_counts))
        for values,_ in self.records:
            self.file.write(struct.pack('<QQQQQQQIIIIII',*values))
        self.file.flush()
        # Check the actual on-disk offsets, sizes and payloads before promotion.
        for index,(expected,digest) in enumerate(self.records):
            self.file.seek(72+32*len(self.type_counts)+80*index)
            actual=struct.unpack('<QQQQQQQIIIIII',self.file.read(80))
            if actual!=expected: raise ValueError('Inline metadata verification failed')
            self.file.seek(actual[2])
            if hashlib.sha256(self.file.read(actual[7])).digest()!=digest:
                raise ValueError('Inline payload verification failed')
        for stream in self.external:
            stream.flush()
        for i, offset, size, digest in self.external_records:
            self.external[i].seek(offset)
            if hashlib.sha256(self.external[i].read(size)).digest()!=digest:
                raise ValueError('External payload verification failed')
        self.close()
        if not self.standalone:
            for side in self.sides: side.write_bytes(b'')
        return self.path,*self.sides

    def close(self):
        self.file.close()
        for stream in self.external:
            stream.close()


class ResourceIndex:
    CACHE_SCHEMA_VERSION = "2"

    def __init__(
        self,
        store: PackageStore,
        cache_path: Path | None = None,
        indexed_type_ids: set[int] | None = None,
    ):
        self.store = store
        self.cache_path = cache_path
        self.indexed_type_ids = indexed_type_ids
        self.connection: sqlite3.Connection | None = None
        self._archives: OrderedDict[str, TocArchive] = OrderedDict()

    def load_or_build(self, progress=None) -> bool:
        """Open a valid cache or build one. Returns True when cache was reused."""
        if self.cache_path is None:
            self._build_database(":memory:", progress)
            return False
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self._open_existing_cache():
            return True
        temporary_path = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary_path.unlink(missing_ok=True)
        self._build_database(str(temporary_path), progress)
        self.close()
        os.replace(temporary_path, self.cache_path)
        if not self._open_existing_cache():
            raise RuntimeError("Resource index cache was written but could not be reopened")
        return False

    def build(self, progress=None) -> None:
        self.load_or_build(progress)

    def _build_database(self, database_path: str, progress=None) -> None:
        connection = sqlite3.connect(database_path)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA cache_size=-8192")
        connection.execute(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE resources ("
            "file_id BLOB NOT NULL, type_id BLOB NOT NULL, package_name TEXT NOT NULL, "
            "PRIMARY KEY (file_id, type_id, package_name)) WITHOUT ROWID"
        )
        package_names = self.store.index_package_names()
        batch = []
        for index, package_name in enumerate(package_names, start=1):
            if progress:
                progress(index, len(package_names), package_name)
            data = self.store.load_toc_header(package_name)
            if len(data) < 72:
                continue
            try:
                magic, type_count, file_count = struct.unpack_from("<III", data, 0)
                if magic != TOC_MAGIC:
                    continue
                offset = 72 + type_count * 32
                required = offset + file_count * 80
                if required > len(data):
                    continue
                for _ in range(file_count):
                    file_id, type_id = struct.unpack_from("<QQ", data, offset)
                    if self.indexed_type_ids is None or type_id in self.indexed_type_ids:
                        batch.append(
                            (
                                _uint64_blob(file_id),
                                _uint64_blob(type_id),
                                package_name,
                            )
                        )
                        if len(batch) >= 4096:
                            connection.executemany(
                                "INSERT OR IGNORE INTO resources VALUES (?, ?, ?)", batch
                            )
                            batch.clear()
                    offset += 80
            except (struct.error, BinaryFormatError):
                continue
            if index % 250 == 0:
                if batch:
                    connection.executemany(
                        "INSERT OR IGNORE INTO resources VALUES (?, ?, ?)", batch
                    )
                    batch.clear()
                connection.commit()
        if batch:
            connection.executemany(
                "INSERT OR IGNORE INTO resources VALUES (?, ?, ?)", batch
            )
        metadata = [
            ("schema_version", self.CACHE_SCHEMA_VERSION),
            ("game_fingerprint", self.store.index_fingerprint()),
            (
                "indexed_types",
                ",".join(str(value) for value in sorted(self.indexed_type_ids or set())),
            ),
        ]
        connection.executemany("INSERT INTO metadata VALUES (?, ?)", metadata)
        connection.commit()
        self.connection = connection

    def _open_existing_cache(self) -> bool:
        if self.cache_path is None or not self.cache_path.is_file():
            return False
        connection = None
        try:
            connection = sqlite3.connect(self.cache_path)
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            expected_types = ",".join(
                str(value) for value in sorted(self.indexed_type_ids or set())
            )
            if (
                metadata.get("schema_version") != self.CACHE_SCHEMA_VERSION
                or metadata.get("game_fingerprint") != self.store.index_fingerprint()
                or metadata.get("indexed_types") != expected_types
            ):
                connection.close()
                return False
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA cache_size=-4096")
            self.connection = connection
            return True
        except (sqlite3.DatabaseError, OSError):
            if connection is not None:
                connection.close()
            return False

    def locate(self, file_id: int, type_id: int) -> str:
        if self.connection is None:
            raise RuntimeError("Resource index is not loaded")
        row = self.connection.execute(
            "SELECT package_name FROM resources "
            "WHERE file_id = ? AND type_id = ? ORDER BY package_name LIMIT 1",
            (_uint64_blob(file_id), _uint64_blob(type_id)),
        ).fetchone()
        if row is None:
            raise LookupError(f"Resource not found: file_id={file_id}, type_id={type_id}")
        return row[0]

    def resource_ids(self, type_id: int) -> list[int]:
        """Return all indexed resource IDs of a given type in stable order."""
        if self.connection is None:
            raise RuntimeError("Resource index is not loaded")
        rows = self.connection.execute(
            "SELECT DISTINCT file_id FROM resources WHERE type_id = ? ORDER BY file_id",
            (_uint64_blob(type_id),),
        ).fetchall()
        return [struct.unpack("<Q", row[0])[0] for row in rows]

    def resolve(self, file_id: int, type_id: int) -> tuple[str, TocEntry]:
        package_name = self.locate(file_id, type_id)
        archive = self.load_archive(package_name)
        entry = archive.get_entry(file_id, type_id)
        if entry is None:
            raise LookupError(
                f"Indexed resource disappeared from package {package_name}: {file_id}/{type_id}"
            )
        return package_name, entry

    def load_archive(self, package_name: str) -> TocArchive:
        archive = self._archives.pop(package_name, None)
        if archive is None:
            archive = TocArchive.load_toc_only(self.store, package_name)
        self._archives[package_name] = archive
        while len(self._archives) > 4:
            self._archives.popitem(last=False)
        return archive

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __del__(self):
        self.close()


def _uint64_blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def flatten_archive_catalog(data: dict) -> list[tuple[str, str]]:
    result = []
    for category, values in data.items():
        if not isinstance(values, dict):
            continue
        for archive_id, name in values.items():
            result.append((archive_id, f"{category}: {name}"))
    return result
