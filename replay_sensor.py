"""Sensor View related calculations for the validated WRPL 0x18c1c layout.

These operate on recorded samples, not the game's interpolated playback state.
See REPLAY_FIELDS.md for provenance, assumptions, and unsupported HUD fields.
"""
import math


DEFAULT_TEMPERATURE_K = 288.1600036621094


def signed16(value):
    if not 0 <= value <= 65535:
        raise ValueError('Invalid packed signed 16-bit value')
    return value if value < 32768 else value - 65536


def recorded_velocity(sample):
    packed = sample.get('raw_vector_1_u16')
    if packed is None:
        return None
    if len(packed) != 3:
        raise ValueError('Expected three velocity components')
    return tuple(signed16(v) * (2000.0 / 32767.0) for v in packed)


def flight_time(sample):
    timers = sample.get('raw_timers')
    # Zero is a sentinel, not a negative flight time. An absent field is not zero.
    if not timers or timers[0] in (None, 0):
        return None
    return (timers[0] - 1) / 48.0


def mach_estimate(speed_mps, altitude_m, temperature_k=DEFAULT_TEMPERATURE_K):
    """Game atmosphere temperature polynomial, with explicit sea-level temperature."""
    if not all(math.isfinite(v) for v in (speed_mps, altitude_m, temperature_k)):
        raise ValueError('Nonfinite Mach input')
    if temperature_k <= 0 or speed_mps < 0:
        raise ValueError('Temperature must be positive and speed nonnegative')
    h = min(altitude_m, 18300.0)
    ratio = (((3.9730601514748866e-18 * h - 5.711039686951899e-14) * h
              + 2.1806899341836328e-10) * h - 2.277120074722916e-05) * h + 1.0
    if ratio <= 0:
        raise ValueError('Altitude outside supported atmosphere calculation')
    return speed_mps / (20.100000381469727 * math.sqrt(temperature_k * ratio))


def aoa_estimate(rotation, velocity):
    """Unsigned Sensor View angle from recorded roll/yaw/pitch and world velocity.

    Sensor View uses asin(sqrt(1 - projected_velocity**2 / max(speed**2, 1))).
    It folds angles above 90 degrees and is not a signed pitch-plane AoA.
    """
    roll, yaw, pitch = rotation
    forward = (math.cos(pitch) * math.cos(yaw), math.sin(pitch),
               -math.cos(pitch) * math.sin(yaw))
    projection = sum(a * b for a, b in zip(forward, velocity))
    sin_squared = 1.0 - projection ** 2 / max(sum(v * v for v in velocity), 1.0)
    return math.degrees(math.asin(math.sqrt(max(0.0, min(1.0, sin_squared)))))


def decode_seeker_payload(sample, bits_class):
    """Decode only the observed 607-bit radar + inertial + datalink layout.

    No assumption that the two-bit guidance state equals the HUD enum: it does not.
    Other payloads remain intact in raw_samples.json and are explicitly unsupported.
    Field offsets below name serialized state members, not physical measurements.
    """
    result = {'decode_status': 'not_present'}
    if not sample.get('raw_seeker_bits'):
        return result
    result['decode_status'] = 'unsupported_layout'
    if sample['raw_seeker_bits'] != 607:
        return result
    b = bits_class(bytes.fromhex(sample['raw_seeker_hex']), sample['raw_seeker_bits'])
    type_id, state = b.uint(1), b.bits(2)
    if type_id != 3 or state not in (0, 3) or b.bits(1) != 1:
        return result
    target_position, target_velocity, target_acceleration = (b.floats(3) for _ in range(3))
    datalink = b.uint(1)
    if b.bits(1) != 1:
        return result
    common = [b.uint(2) for _ in range(8)]
    v20, b24, b25 = b.uint(2), b.bits(1), b.bits(1)
    v28, v2c, b30 = b.uint(2), b.uint(2), b.bits(1)
    v34, v38 = b.uint(2), b.uint(2)
    v40, v3c, v44 = b.varint(), b.varint(), b.varint()
    if v44 != 0xFFFFFFFF or b.pos != b.limit:
        return result
    return dict(decode_status='radar_inertial_datalink_607', raw_guidance_state=state,
                raw_datalink_state=datalink, inertial_target_position=target_position,
                inertial_target_velocity=target_velocity, inertial_target_acceleration=target_acceleration,
                raw_common_u16=common, raw_20=v20, raw_24=b24, raw_25=b25,
                raw_28=v28, raw_2c=v2c, raw_30=b30, raw_34=v34, raw_38=v38,
                raw_40=(v40 >> 1) ^ -(v40 & 1), raw_3c=v3c, raw_44=v44)


def sensor_columns(sample, travelled_m, temperature_k=DEFAULT_TEMPERATURE_K, view_origin=None):
    velocity = recorded_velocity(sample)
    speed = math.sqrt(sum(v * v for v in velocity)) if velocity is not None else None
    rotation = sample.get('raw_rotation')
    seeker = sample.get('seeker_decoded', {})
    return dict(
        flight_time_s=flight_time(sample),
        speed_mps=speed, speed_kmh=None if speed is None else speed * 3.6,
        vx_mps=None if velocity is None else velocity[0],
        vy_mps=None if velocity is None else velocity[1],
        vz_mps=None if velocity is None else velocity[2],
        mach_estimate=None if speed is None else mach_estimate(speed, sample['position'][1], temperature_k),
        travelled_estimate_m=travelled_m,
        aoa_estimate_deg=None if rotation is None or velocity is None else aoa_estimate(rotation, velocity),
        sensor_distance_m=None if view_origin is None else math.dist(view_origin, sample['position']),
        sensor_distance_status='view_origin_not_supplied' if view_origin is None else 'calculated_from_supplied_fixed_origin',
        sensor_overload_g=None, sensor_overload_status='not_decoded_requires_playback_physics_state',
        seeker_status=None, seeker_status_source='hud_state_not_validated',
        seeker_payload_status=seeker.get('decode_status', 'not_present'),
        raw_guidance_state=seeker.get('raw_guidance_state'),
        raw_datalink_state=seeker.get('raw_datalink_state'),
    )
