"""Read only VENUS's two simulation settings; never expose other cfg contents."""
from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Optional


@dataclass(frozen=True)
class SimulationMode:
    state: str  # on, off, unknown
    reason: str = ''
    setting: Optional[str] = None  # venus or instrument when on


def _cfg_value(path: Path, section: bytes, key: bytes) -> bytes:
    """Hamilton binary cfg versions 2/3. Only the requested value leaves this reader."""
    data = path.read_bytes()
    if data.startswith(b'HxCfgFile'):
        raise ValueError('is in text form')
    pos = 0

    def unpack(fmt):
        nonlocal pos
        end = pos + struct.calcsize(fmt)
        if end > len(data):
            raise ValueError('ends early')
        value = struct.unpack_from(fmt, data, pos)
        pos = end
        return value

    def string():
        nonlocal pos
        size, = unpack('<B')
        if size == 0xff:
            size, = unpack('<H')
            if size == 0xffff:
                size, = unpack('<I')
        end = pos + size
        if end > len(data):
            raise ValueError('ends early')
        value = data[pos:end]
        pos = end
        return value

    version, _, count = unpack('<HHI')
    if version not in (2, 3):
        raise ValueError('has an unsupported format version')
    found = None
    for _ in range(count):
        name = string()
        _, pairs = unpack('<HI')
        for _ in range(pairs):
            entry, value = string(), string()
            if name == section and entry == key and found is None:
                found = value
    if found is None:
        raise ValueError('has no simulation setting')
    return found


def read_simulation_mode(hxrun_path: str) -> SimulationMode:
    """No cache: global SimulationOn wins; only while off, read SimulateMode."""
    folder = Path(hxrun_path).parent.parent / 'Config'
    for filename, section, key, setting in (
        ('HxServices.cfg', b'HxServicesGeneralSettings,default', b'SimulationOn', 'venus'),
        ('ML_STAR.cfg', b'CommandEdit,default', b'SimulateMode', 'instrument'),
    ):
        try:
            value = _cfg_value(folder / filename, section, key)
            if value not in (b'0', b'1'):
                # Never include the value: a malformed file might put a password here.
                raise ValueError('has a simulation setting other than 0 or 1')
        except FileNotFoundError:
            return SimulationMode('unknown', f'{filename} is missing')
        except OSError:
            return SimulationMode('unknown', f'{filename} cannot be read')
        except ValueError as exc:
            return SimulationMode('unknown', f'{filename} {exc}')
        if value == b'1':
            return SimulationMode('on', setting=setting)
    return SimulationMode('off')


_SIMULATION_UNKNOWN_REASON = 'VENUS Simulation Mode could not be read: '
_SIMULATION_MISMATCH_REASONS = (
    'VENUS is in Simulation Mode; this schedule is real. Turn it off in VENUS: Settings > Simulation Mode.',
    "The instrument's Simulation setting is on; this schedule is real.",
    'VENUS is not in Simulation Mode; this schedule is a simulation.',
)


def is_simulation_reason(reason: str) -> bool:
    return reason in _SIMULATION_MISMATCH_REASONS or reason.startswith(_SIMULATION_UNKNOWN_REASON)


def simulation_block_reason(mode: str, hxrun_path: str) -> Optional[str]:
    current = read_simulation_mode(hxrun_path)
    if current.state == 'unknown':
        return _SIMULATION_UNKNOWN_REASON + current.reason
    if mode == 'real' and current.state == 'on':
        return _SIMULATION_MISMATCH_REASONS[0 if current.setting == 'venus' else 1]
    if mode == 'simulation' and current.state == 'off':
        return _SIMULATION_MISMATCH_REASONS[2]
    return None
