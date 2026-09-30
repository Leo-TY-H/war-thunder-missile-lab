import math
import struct
import unittest

from export_replay import Bits, ReplayError, match_creation, packet_stream, slope, weapon_packet
from replay_sensor import (aoa_estimate, decode_seeker_payload, flight_time, mach_estimate,
                           recorded_velocity, sensor_columns, signed16)


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


class ReplayExportTests(unittest.TestCase):
    def test_unaligned_bytes_and_truncation(self):
        b = Bits(bytes.fromhex('b4c0'))
        self.assertEqual(b.bits(3), 5)
        self.assertEqual(b.raw(1), b'\xa6')
        self.assertEqual(b.bits(5), 0)
        with self.assertRaises(ReplayError):
            b.bits(1)

    def test_packet_sizes_and_inherited_time(self):
        first = bytes([4, 0]) + struct.pack('<I', 1234) + b'abc'
        second = bytes([0x14, 0]) + b'def'
        stream = bytes([0x80 | len(first)]) + first + bytes([0x80 | len(second)]) + second
        decoded = list(packet_stream(stream))
        self.assertEqual([(t, kind, data) for t, kind, data, _ in decoded],
                         [(1234, 4, b'abc'), (1234, 4, b'def')])
        with self.assertRaises(ReplayError):
            list(packet_stream(stream[:-1]))

    def test_full_position_sample_and_packet_boundary(self):
        # Independently construct one unaligned full-coordinate sample, no optional state.
        raw_bits = ''.join(f'{byte:08b}' for byte in b'\x01')
        raw_bits += '01' + ''.join(f'{byte:08b}' for byte in struct.pack('<I', 123))
        raw_bits += '1' + ''.join(f'{byte:08b}' for byte in struct.pack('<fff', 20000., 5000., -30.))
        raw_bits += '00000000' * 2
        length = len(raw_bits)
        padded = raw_bits + '0' * (-length % 8)
        data = bytes.fromhex('02581af1') + varint(length) + int(padded, 2).to_bytes(len(padded) // 8, 'big')
        rows = weapon_packet(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['sync_identifier'], 123)
        self.assertEqual(rows[0]['position'], (20000., 5000., -30.))
        with self.assertRaises(ReplayError):
            weapon_packet(data[:-1])
        with self.assertRaises(ReplayError):
            weapon_packet(data + b'\0')

    def test_packed_position_extremes(self):
        for first, second, expected in [(0, 0, (-15000.,) * 3),
                                         (0xFFFFFFFF, 0xFFFFFFFF, (15000.,) * 3)]:
            raw_bits = '00000001' + '01' + '00000000' * 4 + '0'
            raw_bits += ''.join(f'{byte:08b}' for byte in struct.pack('<II', first, second))
            raw_bits += '00000000' * 2
            length = len(raw_bits)
            padded = raw_bits + '0' * (-length % 8)
            packet = bytes.fromhex('02581af1') + varint(length) + int(padded, 2).to_bytes(len(padded) // 8, 'big')
            self.assertEqual(weapon_packet(packet)[0]['position'], expected)

    def test_speed_estimate_with_irregular_times(self):
        times = [0., .039, .081, .126, .167, .209, .248, .29, .333]
        samples = [dict(replay_time_s=t, position=(100 + 400 * t, 5000 + 30 * t, -20 * t)) for t in times]
        for i in range(len(samples)):
            actual = slope(samples, i)
            for a, b in zip(actual, (400., 30., -20.)):
                self.assertAlmostEqual(a, b, places=8)
        self.assertIsNone(slope(samples[:1], 0))

    def test_spawn_association_rejects_ambiguity(self):
        first = dict(replay_time_s=5.08, position=(8.2, 5000., 2.6))
        a = dict(creation_packet_time_s=5.05, initial_velocity=(400., 0., 0.), initial_position=(0., 5000., 2.6), entity_id=1)
        b = dict(a, initial_position=(0., 5000., 2.4), entity_id=2)
        self.assertEqual(match_creation(first, [a, b])['entity_id'], 1)
        self.assertIsNone(match_creation(first, [a, dict(a, entity_id=3)]))
        self.assertIsNone(match_creation(dict(first, replay_time_s=10), [a]))

    def test_recorded_velocity_signed_units_and_observed_speed(self):
        self.assertEqual([signed16(v) for v in (0, 32767, 32768, 65535)], [0, 32767, -32768, -1])
        self.assertEqual(recorded_velocity({'raw_vector_1_u16': [32767, 0, 32769]}), (2000., 0., -2000.))
        velocity = recorded_velocity({'raw_vector_1_u16': [12996, 63944, 65533]})
        speed_kmh = math.sqrt(sum(v*v for v in velocity)) * 3.6
        self.assertAlmostEqual(speed_kmh, 2876.999903, places=5)
        self.assertLess(velocity[1], 0)
        self.assertIsNone(recorded_velocity({}))

    def test_lifetime_sentinel_and_48_hz_timer(self):
        self.assertEqual(flight_time({'raw_timers': [1]}), 0)
        self.assertEqual(flight_time({'raw_timers': [49]}), 1)
        self.assertAlmostEqual(flight_time({'raw_timers': [887]}), 18.458333333)
        for sample in ({}, {'raw_timers': [None]}, {'raw_timers': [0]}):
            self.assertIsNone(flight_time(sample))

    def test_mach_temperature_and_altitude(self):
        self.assertAlmostEqual(mach_estimate(2876.999903 / 3.6, 5001.043945), 2.487042, places=5)
        self.assertEqual(mach_estimate(0, 5000), 0)
        self.assertAlmostEqual(mach_estimate(800, 20000), mach_estimate(800, 18300))
        self.assertLess(mach_estimate(800, 5000, 300), mach_estimate(800, 5000, 280))
        for temperature in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                mach_estimate(800, 5000, temperature)

    def test_aoa_pitch_yaw_and_roll_invariance(self):
        self.assertAlmostEqual(aoa_estimate((0, 0, 0), (800, 0, 0)), 0)
        self.assertAlmostEqual(aoa_estimate((0, 0, math.radians(10)), (800, 0, 0)), 10)
        self.assertAlmostEqual(aoa_estimate((2, math.pi/2, 0), (0, 0, -800)), 0)
        self.assertAlmostEqual(aoa_estimate((0, 0, 0), (-800, 0, 0)), 0)
        self.assertAlmostEqual(aoa_estimate((0, 0, 0), (0, 800, 0)), 90)

    def test_sensor_unavailable_is_not_zero_or_unlocked(self):
        sample = dict(position=(3, 5000, 4), raw_vector_1_u16=[0, 0, 0], raw_timers=[1])
        row = sensor_columns(sample, 0)
        self.assertEqual(row['speed_kmh'], 0)
        self.assertEqual(row['flight_time_s'], 0)
        for key in ('sensor_distance_m', 'sensor_overload_g', 'seeker_status', 'aoa_estimate_deg'):
            self.assertIsNone(row[key])
        self.assertEqual(sensor_columns(sample, 0, view_origin=(0, 5000, 0))['sensor_distance_m'], 5)

    def test_seeker_layout_retention_without_invented_hud_label(self):
        # Synthetic, independently assembled MSB-first payload at unaligned boundaries.
        bits = '00000011' + '11' + '1'
        bits += ''.join(f'{v:08b}' for v in struct.pack('<9f', 100, 5000, 0, -400, 0, 0, 0, 0, 0))
        bits += '00000001' + '1'  # datalink byte, compressed common state
        bits += '0' * 128 + '0' * 16 + '01' + '0' * 32 + '1' + '0' * 32
        bits += ''.join(f'{v:08b}' for v in varint(0) + varint(0xffffffff) + varint(0xffffffff))
        self.assertEqual(len(bits), 607)
        payload = int(bits + '0', 2).to_bytes(76, 'big').hex()
        sample = dict(raw_seeker_bits=607, raw_seeker_hex=payload)
        result = decode_seeker_payload(sample, Bits)
        self.assertEqual(result['raw_guidance_state'], 3)
        self.assertEqual(result['inertial_target_position'], (100, 5000, 0))
        self.assertNotIn('seeker_status', result)
        self.assertEqual(decode_seeker_payload({}, Bits)['decode_status'], 'not_present')
        unsupported = dict(sample, raw_seeker_bits=606)
        self.assertEqual(decode_seeker_payload(unsupported, Bits)['decode_status'], 'unsupported_layout')
        # A different type must not be interpreted using the radar layout.
        self.assertEqual(decode_seeker_payload(dict(sample, raw_seeker_hex='02' + payload[2:]), Bits)['decode_status'],
                         'unsupported_layout')
        with self.assertRaises(ReplayError):
            decode_seeker_payload(dict(sample, raw_seeker_hex=payload[:-2]), Bits)


if __name__ == '__main__':
    unittest.main()
