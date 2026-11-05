from __future__ import annotations

import struct


class BinaryFormatError(ValueError):
    pass


class BinaryReader:
    def __init__(self, data: bytes | bytearray):
        self.data = memoryview(data)
        self.position = 0

    def tell(self) -> int:
        return self.position

    def seek(self, position: int) -> None:
        if position < 0 or position > len(self.data):
            raise BinaryFormatError(
                f"Seek outside data: position={position}, size={len(self.data)}"
            )
        self.position = position

    def read(self, size: int) -> bytes:
        end = self.position + size
        if size < 0 or end > len(self.data):
            raise BinaryFormatError(
                f"Read outside data: position={self.position}, size={size}, "
                f"data_size={len(self.data)}"
            )
        value = self.data[self.position:end].tobytes()
        self.position = end
        return value

    def unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        values = struct.unpack(fmt, self.read(size))
        return values[0] if len(values) == 1 else values

    def uint8(self) -> int:
        return self.unpack("<B")

    def uint16(self) -> int:
        return self.unpack("<H")

    def uint32(self) -> int:
        return self.unpack("<I")

    def uint64(self) -> int:
        return self.unpack("<Q")

    def float32(self) -> float:
        return self.unpack("<f")

    def vec3_float(self) -> list[float]:
        return list(self.unpack("<3f"))


class BinaryWriter:
    def __init__(self):
        self.data = bytearray()
        self.position = 0

    def tell(self) -> int:
        return self.position

    def seek(self, position: int) -> None:
        if position < 0:
            raise BinaryFormatError(f"Negative seek: {position}")
        if position > len(self.data):
            self.data.extend(b"\x00" * (position - len(self.data)))
        self.position = position

    def write(self, value: bytes | bytearray) -> None:
        end = self.position + len(value)
        if end > len(self.data):
            self.data.extend(b"\x00" * (end - len(self.data)))
        self.data[self.position:end] = value
        self.position = end

    def pack(self, fmt: str, *values) -> None:
        self.write(struct.pack(fmt, *values))

    def uint8(self, value: int) -> None:
        self.pack("<B", value)

    def uint16(self, value: int) -> None:
        self.pack("<H", value)

    def uint32(self, value: int) -> None:
        self.pack("<I", value)

    def uint64(self, value: int) -> None:
        self.pack("<Q", value)

    def float32(self, value: float) -> None:
        self.pack("<f", value)

    def vec3_float(self, value) -> None:
        self.pack("<3f", *value)


def align(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment

