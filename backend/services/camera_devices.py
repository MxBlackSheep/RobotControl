"""DirectShow device identities, enumerated without opening capture devices.

The enumeration order is the order used by OpenCV's DirectShow backend. Device
paths are saved identities; indexes are resolved again for every connection.
"""
import ctypes as C
import sys
import uuid


def enumerate_devices():
    if sys.platform != "win32":
        return []
    ole = C.OleDLL("ole32")
    automation = C.OleDLL("oleaut32")
    pointer = C.c_void_p
    guid = lambda value: (C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)

    def invoke(obj, slot, result, args, *values):
        table = C.cast(obj, C.POINTER(C.POINTER(pointer))).contents
        return C.WINFUNCTYPE(result, pointer, *args)(table[slot])(obj, *values)

    def release(obj):
        if obj:
            invoke(obj, 2, C.c_ulong, [])

    # VARIANT is 24 bytes on Win64 (16 on Win32), with its data at offset 8.
    class Variant(C.Structure):
        _fields_ = [("vt", C.c_ushort), ("reserved", C.c_ushort * 3),
                    ("data", C.c_ubyte * (16 if C.sizeof(pointer) == 8 else 8))]

    def property_value(bag, name):
        value = Variant()
        try:
            hr = invoke(bag, 3, C.c_long, [C.c_wchar_p, pointer, pointer], name, C.byref(value), None)
            if hr < 0 or value.vt != 8:  # VT_BSTR
                return None
            address = C.cast(C.byref(value, 8), C.POINTER(pointer)).contents.value
            return C.wstring_at(address) if address else None
        finally:
            automation.VariantClear(C.byref(value))

    initialized = ole.CoInitializeEx(None, 0)  # private MTA on the caller's worker
    if initialized < 0:
        raise RuntimeError("Cannot initialize camera device enumeration")
    enumerator, sequence = pointer(), pointer()
    devices = []
    try:
        hr = ole.CoCreateInstance(C.byref(guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")), None, 1,
                                  C.byref(guid("29840822-5B84-11D0-BD3B-00A0C911CE86")), C.byref(enumerator))
        if hr < 0:
            raise RuntimeError("Cannot enumerate DirectShow cameras")
        hr = invoke(enumerator, 3, C.c_long, [pointer, pointer, C.c_ulong],
                    C.byref(guid("860BB310-5D01-11D0-BD3B-00A0C911CE86")), C.byref(sequence), 0)
        if hr == 1:
            return []
        if hr < 0:
            raise RuntimeError("Cannot list video input devices")
        index = 0
        while True:
            moniker, bag = pointer(), pointer()
            if invoke(sequence, 3, C.c_long, [C.c_ulong, pointer, pointer], 1, C.byref(moniker), None) != 0:
                break
            try:
                hr = invoke(moniker, 9, C.c_long, [pointer, pointer, pointer, pointer], None, None,
                            C.byref(guid("55272A00-42CB-11CE-8135-00AA004BB851")), C.byref(bag))
                if hr < 0:
                    raise RuntimeError(f"Cannot read identity of camera {index}")
                identity = property_value(bag, "DevicePath")
                devices.append({"id": index, "name": property_value(bag, "FriendlyName") or f"Camera {index}",
                                "device_identity": identity, "status": "available" if identity else "unidentifiable"})
            finally:
                release(bag)
                release(moniker)
            index += 1
        return devices
    finally:
        release(sequence)
        release(enumerator)
        ole.CoUninitialize()


def resolve_device(devices, identity):
    matches = [device for device in devices if device.get("device_identity") == identity and identity]
    if len(matches) != 1:
        raise ValueError("Selected camera is missing or ambiguous. Refresh cameras and select it explicitly.")
    return matches[0]
