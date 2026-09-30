"""Experimental, read-only missile telemetry export for WRPL version 0x18c1c.

Weapon packet layout adapted from LivingTheDagor/WrplReplayParser (BSD-3-Clause).
See THIRD_PARTY_NOTICES.md. Unknown layouts fail rather than silently skip samples.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import struct
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from replay_sensor import DEFAULT_TEMPERATURE_K, decode_seeker_payload, sensor_columns

ROOT = Path(__file__).resolve().parent
VERSION = 0x18C1C


class ReplayError(ValueError):
    pass


class Bits:
    def __init__(self, data, limit=None):
        self.data, self.pos = data, 0
        self.limit = len(data) * 8 if limit is None else limit
        if self.limit > len(data) * 8:
            raise ReplayError('Truncated bitstream')

    def bits(self, count):
        if count < 0 or self.pos + count > self.limit:
            raise ReplayError(f'Truncated bitstream at bit {self.pos}')
        value = 0
        for _ in range(count):
            value = (value << 1) | ((self.data[self.pos // 8] >> (7 - self.pos % 8)) & 1)
            self.pos += 1
        return value

    def skip(self, count):
        if count < 0 or self.pos + count > self.limit:
            raise ReplayError('Truncated skipped field')
        self.pos += count

    def raw(self, count):
        return bytes(self.bits(8) for _ in range(count))

    def uint(self, count):
        return int.from_bytes(self.raw(count), 'little')

    def varint(self):
        value = 0
        for shift in range(0, 35, 7):
            byte = self.uint(1)
            value |= (byte & 127) << shift
            if not byte & 128:
                if value > 0xFFFFFFFF:
                    break
                return value
        raise ReplayError('Invalid 32-bit varint')

    def floats(self, count):
        values = struct.unpack('<' + 'f' * count, self.raw(4 * count))
        if not all(math.isfinite(v) for v in values):
            raise ReplayError('Nonfinite coordinate or state value')
        return values


def packet_stream(data):
    b = Bits(data)
    timestamp = 0
    while b.pos < b.limit:
        offset = b.pos // 8
        first = b.uint(1)
        if first & 128 and not first & 64:
            size = first & 127
        elif first & 64:
            size = int.from_bytes(bytes([first]) + b.raw(1), 'big') ^ 0x4000
        elif first & 32:
            size = int.from_bytes(bytes([first]) + b.raw(2), 'big') ^ 0x200000
        elif first & 16:
            size = int.from_bytes(bytes([first]) + b.raw(3), 'big') ^ 0x10000000
        else:
            size = b.uint(4)
        if not size:
            continue
        p = Bits(b.raw(size))
        kind, flags = p.uint(1), p.uint(1)
        if kind & 16:
            kind &= ~16
        else:
            timestamp = p.uint(4)
        yield timestamp, kind, p.raw((p.limit - p.pos) // 8), offset


def weapon_sample(b):
    flag1, flag2 = b.bits(1), b.bits(1)
    # This is an opaque sync identifier: do not confuse it with an ECS entity ID.
    identifier = b.uint(4)
    full = b.bits(1)
    if full:
        position = b.floats(3)
    else:
        a, c = b.uint(4), b.uint(4)
        packed = (a >> 10, ((a & 1023) << 10) | (c >> 22), c & 0x3FFFFF)
        position = tuple((value * 2 / maximum - 1) * 15000
                         for value, maximum in zip(packed, (4194303, 1048575, 4194303)))
    raw = {'sync_identifier': identifier, 'position': position,
           'position_encoding': 'float32' if full else 'packed_22_20_22'}
    if not flag2:
        tick = b.varint()
        raw['raw_clock'] = (tick >> 1) ^ -(tick & 1)
        raw['raw_rotation'] = b.floats(3)
        raw['raw_vector_1_u16'] = [b.uint(2) for _ in range(3)]
        raw['raw_vector_2_u16'] = [b.uint(2) for _ in range(3)]
        if b.bits(1):
            b.uint(2)
        flags = b.uint(1)
        if flags & 0xF0:
            raise ReplayError('Unknown weapon state flags')
        raw['raw_timers'] = [b.varint() if flags & (1 << i) else None for i in range(4)]
        if not flag1:
            raw['raw_guidance_scalar'] = b.floats(1)[0]
            raw['raw_guidance_flag'] = b.bits(1)
            size = b.uint(2)
            raw['raw_seeker_bits'] = size
            payload = b.raw(size // 8)
            if size % 8:
                payload += bytes([b.bits(size % 8) << (8 - size % 8)])
            raw['raw_seeker_hex'] = payload.hex()
        elif b.bits(1):
            raise ReplayError('SACLOS weapon state is not supported')
    return raw


def weapon_packet(data):
    outer = Bits(data)
    outer.skip(32)
    count_bits = outer.varint()
    outer.skip((-outer.pos) % 8)
    b = Bits(outer.raw((count_bits + 7) // 8), count_bits)
    if outer.pos != outer.limit:
        raise ReplayError('Unexpected data after weapon packet')
    rows = []
    for kind in ('rocket', 'bomb', 'torpedo'):
        count = b.uint(1)
        if kind != 'rocket' and count:
            raise ReplayError('This exporter currently supports rocket/missile tracks only')
        for _ in range(count):
            rows.append(weapon_sample(b))
    if b.pos != b.limit:
        raise ReplayError('Weapon packet layout changed: unconsumed bits')
    return rows


def network_entity_id(b):
    first = b.uint(2)
    if first & 1:
        return (first >> 2) | (((first & 2) >> 1) << 22)
    if first & 2:
        return (first >> 2) | (b.uint(1) << 22)
    value = first | (b.uint(2) << 16)
    return ((value & 0xFFFFFF) >> 2) | ((value >> 24) << 22)


class CreationReader:
    """Read template headers; only the validated rocket creation prefix is interpreted."""
    def __init__(self):
        self.templates, self.components = {}, {}
        self.rockets, self.destroyed = [], {}

    def read(self, timestamp, data):
        import lz4.block
        if not data or data[0] not in (0x24, 0x25, 0x26):
            return
        if data[0] == 0x26:
            b = Bits(data[1:])
            for _ in range(b.uint(1) + 1):
                self.destroyed[network_entity_id(b)] = timestamp / 1000
            if b.pos != b.limit:
                raise ReplayError('Unexpected entity deletion payload')
            return
        payload = lz4.block.decompress(data[1:], uncompressed_size=8 * len(data)) if data[0] == 0x25 else data[1:]
        b = Bits(payload)
        for _ in range(b.uint(1) + 1):
            entity = network_entity_id(b)
            c = Bits(b.raw(b.varint()))
            template_id = c.varint()
            if template_id not in self.templates:
                name = c.raw(c.varint()).decode('utf-8')
                components = []
                for _ in range(c.uint(2)):
                    cid = c.varint()
                    if cid not in self.components:
                        self.components[cid] = (c.uint(4), c.uint(4))
                    components.append(cid)
                self.templates[template_id] = (name, components)
            name, components = self.templates[template_id]
            if name != 'rocket+arh_shell':
                continue
            if self.components[components[0]] != (0xFE2545CD, 0x2C8F7A75) or c.raw(3) != b'\x00\x02\x00':
                continue  # Positions still export, but no creation/name association.
            c.varint()
            owner, other = network_entity_id(c), network_entity_id(c)
            c.uint(1)
            c.uint(4)
            weapon_ref = c.uint(4)
            position = c.floats(3)
            c.floats(4)
            velocity = c.floats(3)
            c.floats(3)
            c.uint(1)
            c.uint(1)
            creation_time = c.floats(1)[0]
            self.rockets.append(dict(entity_id=entity, owner_id=owner, weapon_ref=weapon_ref,
                                     creation_time_s=creation_time, creation_packet_time_s=timestamp / 1000,
                                     initial_position=position, initial_velocity=velocity))
        if b.pos != b.limit:
            raise ReplayError('Unexpected entity creation packet ending')


def match_creation(first, creations):
    """Match the first sample to a nearby spawn trajectory; reject ambiguous matches."""
    matches = []
    for creation in creations:
        if not 0 <= first['replay_time_s'] - creation['creation_packet_time_s'] <= .25:
            continue
        velocity = creation['initial_velocity']
        delta = [a - b for a, b in zip(first['position'], creation['initial_position'])]
        norm = sum(v * v for v in velocity)
        if not norm:
            continue
        dt = sum(d * v for d, v in zip(delta, velocity)) / norm
        residual = math.sqrt(sum((d - dt * v) ** 2 for d, v in zip(delta, velocity)))
        if 0 <= dt <= .25:
            matches.append((residual, creation))
    matches.sort(key=lambda item: item[0])
    if not matches or matches[0][0] > .06:
        return None
    if len(matches) > 1 and matches[1][0] - matches[0][0] < .10:
        return None
    return dict(matches[0][1], spawn_match_residual_m=matches[0][0])


def slope(samples, index, window_s=.5):
    """Least-squares position slope in a 0.5-second window, shortened at endpoints."""
    now = samples[index]['replay_time_s']
    nearby = [s for s in samples if abs(s['replay_time_s'] - now) <= window_s / 2 + 1e-9]
    if len(nearby) < 3:
        return None
    times = [s['replay_time_s'] - now for s in nearby]
    mean = sum(times) / len(times)
    denom = sum((t - mean) ** 2 for t in times)
    if denom <= 0:
        return None
    return tuple(sum((t - mean) * s['position'][axis] for t, s in zip(times, nearby)) / denom
                 for axis in range(3))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: f'{value:.6f}' if isinstance(value, float) else value
                             for key, value in row.items()})


def export(replay, output=None, scenario=None, temperature_k=DEFAULT_TEMPERATURE_K, view_origin=None):
    import zstandard
    import lz4.block
    if not math.isfinite(temperature_k) or temperature_k <= 0:
        raise ReplayError('Sea-level temperature must be a positive finite Kelvin value')
    if view_origin is not None and (len(view_origin) != 3 or not all(math.isfinite(v) for v in view_origin)):
        raise ReplayError('View origin must contain three finite X Y Z coordinates in metres')
    replay = Path(replay)
    raw_file = replay.read_bytes()
    if len(raw_file) < 1234 or struct.unpack_from('<I', raw_file)[0] != 0x1000ACE5:
        raise ReplayError('Not a supported War Thunder replay')
    version = struct.unpack_from('<I', raw_file, 4)[0]
    if version != VERSION:
        raise ReplayError(f'Unsupported replay version {version:#x}; validated version is {VERSION:#x}')
    start = 1234 + struct.unpack_from('<H', raw_file, 0x2EC)[0]
    end = struct.unpack_from('<I', raw_file, 0x2AC)[0]
    if not 1234 <= start < end <= len(raw_file) or raw_file[start:start + 4] != b'\x28\xb5\x2f\xfd':
        raise ReplayError('Unsupported compressed stream layout')
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw_file[start:end])) as reader:
        stream = reader.read(512 * 1024 * 1024 + 1)
    if len(stream) > 512 * 1024 * 1024:
        raise ReplayError('Replay exceeds the 512 MiB decompressed-size limit')
    tracks = defaultdict(list)
    creations = CreationReader()
    packets = weapon_packets = 0
    for timestamp, kind, data, offset in packet_stream(stream):
        packets += 1
        if kind == 6:
            creations.read(timestamp, data)
        elif kind == 4 and data[:4] in (bytes.fromhex('02581af1'), bytes.fromhex('0258dbf0')):
            weapon_packets += 1
            for row in weapon_packet(data):
                row.update(replay_time_s=timestamp / 1000, packet_stream_offset=offset)
                row['seeker_decoded'] = decode_seeker_payload(row, Bits)
                tracks[row['sync_identifier']].append(row)
    if not tracks:
        raise ReplayError('No supported missile position packets found')
    scenario_data = json.loads(Path(scenario).read_text(encoding='utf-8-sig')) if scenario else None
    summaries, all_rows, associations = [], [], []
    used_entities = set()
    for ordinal, (identifier, samples) in enumerate(tracks.items(), 1):
        if any(b['replay_time_s'] <= a['replay_time_s'] for a, b in zip(samples, samples[1:])):
            raise ReplayError('Non-increasing track timestamps: refusing to calculate speed')
        creation = match_creation(samples[0], creations.rockets)
        if creation:
            if creation['entity_id'] in used_entities:
                raise ReplayError('Ambiguous duplicate spawn association')
            used_entities.add(creation['entity_id'])
        slot = (creation['weapon_ref'] & 0xFFFF) if creation else None
        label = f'track_{ordinal}'
        if scenario_data and creation and creation['weapon_ref'] >> 16 == 8 and slot < len(scenario_data['missiles']):
            label = scenario_data['missiles'][slot]
        rows, distance = [], 0.
        initial_distance = math.dist(creation['initial_position'], samples[0]['position']) if creation else None
        for i, sample in enumerate(samples):
            if i:
                distance += math.dist(samples[i - 1]['position'], sample['position'])
            velocity = slope(samples, i)
            speed = math.sqrt(sum(v * v for v in velocity)) if velocity else None
            row = dict(track=f'track_{ordinal}', label=label, sync_identifier=identifier,
                       replay_time_s=sample['replay_time_s'],
                       time_since_first_sample_s=sample['replay_time_s'] - samples[0]['replay_time_s'],
                       x_m=sample['position'][0], altitude_y_m=sample['position'][1], z_m=sample['position'][2],
                       position_encoding=sample['position_encoding'],
                       speed_estimate_mps=speed if speed is not None else '',
                       speed_estimate_kmh=speed * 3.6 if speed is not None else '',
                       vx_estimate_mps=velocity[0] if velocity else '',
                       vy_estimate_mps=velocity[1] if velocity else '',
                       vz_estimate_mps=velocity[2] if velocity else '',
                       sampled_path_m=distance)
            row.update(sensor_columns(sample, None if initial_distance is None else initial_distance + distance,
                                      temperature_k, view_origin))
            row['travelled_estimate_status'] = 'spawn_plus_sampled_path' if creation else 'spawn_not_identified'
            rows.append(row)
        all_rows.extend(rows)
        speeds = [r['speed_estimate_kmh'] for r in rows if r['speed_estimate_kmh'] != '']
        recorded_speeds = [r['speed_kmh'] for r in rows if r['speed_kmh'] is not None]
        summaries.append(dict(track=f'track_{ordinal}', label=label, sync_identifier=identifier,
                              samples=len(samples), first_sample_replay_s=samples[0]['replay_time_s'],
                              last_sample_replay_s=samples[-1]['replay_time_s'],
                              sampled_duration_s=samples[-1]['replay_time_s'] - samples[0]['replay_time_s'],
                              sampled_path_m=distance, max_estimated_speed_kmh=max(speeds) if speeds else '',
                              max_recorded_speed_kmh=max(recorded_speeds) if recorded_speeds else None,
                              last_recorded_flight_time_s=rows[-1]['flight_time_s'],
                              travelled_estimate_m=rows[-1]['travelled_estimate_m'],
                              max_altitude_m=max(r['altitude_y_m'] for r in rows),
                              creation_simulation_time_s=creation['creation_time_s'] if creation else '',
                              entity_removed_replay_s=creations.destroyed.get(creation['entity_id'], '') if creation else ''))
        associations.append(dict(track=f'track_{ordinal}', label=label, creation=creation,
                                 label_source='supplied scenario slot' if label != f'track_{ordinal}' else 'unidentified'))
    output = Path(output) if output else ROOT / 'telemetry' / (replay.stem + '_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / 'missile_samples.csv', all_rows)
    write_csv(output / 'missile_summary.csv', summaries)
    for summary in summaries:
        write_csv(output / (summary['track'] + '.csv'), [r for r in all_rows if r['track'] == summary['track']])
    limitations = [
        'Experimental decoder, validated on one local replay, version 0x18c1c. Other layouts fail explicitly.',
        'X/Z are horizontal world coordinates in metres; Y is world altitude. Positions are decoded replay samples.',
        'speed_kmh, speed_mps and vx/vy/vz_mps use recorded signed 16-bit velocity components, scaled by 2000/32767 m/s. Resolution is about 0.061 m/s per component; values can saturate near +/-2000 m/s.',
        'Legacy speed_estimate and vector_estimate columns remain a 0.5 s local linear fit of position against packet time; use speed_kmh for recorded speed. Packet scheduling jitter affects those legacy estimates.',
        f'mach_estimate uses the game atmosphere temperature polynomial, with sea-level temperature {temperature_k:.6f} K. Weather temperature is not decoded from this replay; this is an assumption unless supplied by the user.',
        'aoa_estimate_deg is calculated from recorded orientation and velocity using the Sensor View unsigned-angle formula. Exact agreement with rendered playback frames is not validated.',
        'flight_time_s is the recorded lifetime timer at 1/48 second resolution, not packet time minus creation time. Missing timers are blank.',
        'Packed positions have about 7 mm horizontal and 29 mm vertical steps; float32 precision varies with coordinate magnitude. Decimal digits are not accuracy guarantees.',
        'Time since first sample starts after release. Creation simulation time and replay packet time are separate clocks; do not subtract them to infer flight time.',
        'Sampled path excludes flight before the first and after the last sample; track end/entity removal is not proof of a hit or a measured miss distance.',
        'travelled_estimate_m adds the spawn-to-first-sample segment to sampled_path_m when the spawn is identified. It approximates Sensor View Travelled; it is not the runtime distance accumulator.',
        'sensor_distance_m uses the optional supplied fixed viewing origin; otherwise blank. Sensor View Distance changes with camera/selected viewing origin and is NOT necessarily target range.',
        'Creation association is validated geometrically against each spawn position and initial direction. Uncertain matches are left unidentified.',
        'Optional missile names come from the supplied scenario file and recorded weapon slot, not embedded missile names in the replay. Use the scenario saved for that run.',
        'sensor_overload_g and seeker_status are blank with explicit status reasons: exact HUD overload and SEARCH/IOG/IOG_DL/TRK mapping are not yet recovered. Blank means unavailable, not zero or unlocked.',
        'The supported 607-bit radar/inertial/datalink payload is decoded in raw_samples.json. raw_guidance_state is NOT the Sensor View enum: do not interpret raw state 3 as HUD state 3 or as proof of lock. Other seeker layouts are retained unchanged.',
        'Inertial target position/velocity inside seeker_decoded are seeker estimates, not independently measured target motion. They must not be used as ground-truth target range or speed.',
        'Target trajectory, true target range, fuse events, exact impact time and miss distance are not exported. Raw state and full seeker payload bits remain in raw_samples.json.'
    ]
    metadata = dict(source_replay=str(replay.resolve()), source_sha256=hashlib.sha256(raw_file).hexdigest(),
                    replay_version=hex(version), packets=packets, weapon_packets=weapon_packets,
                    missile_samples=len(all_rows), speed_fit_window_s=.5,
                    sea_level_temperature_k=temperature_k, fixed_view_origin_xyz_m=view_origin,
                    associations=associations, supplied_scenario=scenario_data, limitations=limitations)
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (output / 'raw_samples.json').write_text(json.dumps([s for samples in tracks.values() for s in samples], indent=2), encoding='utf-8')
    (output / 'READ_ME.txt').write_text('Open missile_samples.csv in Excel for all missiles, or track_1.csv etc.\n'
                                       'missile_summary.csv summarizes each track. Metadata records identification and limitations.\n\n'
                                       'Sensor View: recorded speed and time; estimated Mach, Travelled and AoA; '
                                       'Distance needs a viewing origin. Overload and displayed seeker status remain unavailable.\n'
                                       'Blank cells mean unavailable, NOT zero. Read REPLAY_FIELDS.md for each field.\n\n'
                                       + '\n\n'.join(limitations), encoding='utf-8')
    field_guide = ROOT / 'REPLAY_FIELDS.md'
    if field_guide.exists():
        (output / 'REPLAY_FIELDS.md').write_text(field_guide.read_text(encoding='utf-8'), encoding='utf-8')
    return output, summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay', nargs='?', help='WRPL file; omit to open a file picker')
    parser.add_argument('--output', type=Path, help='New destination directory')
    parser.add_argument('--scenario', type=Path, help='Optional saved scenario from this exact run, for missile labels')
    parser.add_argument('--sea-level-temperature-k', type=float, default=DEFAULT_TEMPERATURE_K,
                        help='Sea-level air temperature in Kelvin for estimated Mach (default: 288.16)')
    parser.add_argument('--view-origin', type=float, nargs=3, metavar=('X', 'Y', 'Z'),
                        help='Optional fixed Sensor View origin in world metres; Y is altitude, not target range')
    args = parser.parse_args()
    if not args.replay:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        args.replay = filedialog.askopenfilename(title='Choose a replay to export', filetypes=[('War Thunder replay', '*.wrpl')])
        root.destroy()
        if not args.replay:
            return
    try:
        output, summaries = export(args.replay, args.output, args.scenario,
                                   args.sea_level_temperature_k, args.view_origin)
    except ModuleNotFoundError as error:
        print(f'Missing dependency: {error.name}\nInstall replay export dependencies with:\n'
              f'"{sys.executable}" -m pip install -r "{ROOT / "requirements-replay.txt"}"', file=sys.stderr)
        raise SystemExit(1)
    except (ValueError, OSError, RuntimeError) as error:
        print(f'Export stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
    print(f'Exported {sum(s["samples"] for s in summaries)} samples from {len(summaries)} missiles.\n{output}')


if __name__ == '__main__':
    main()
