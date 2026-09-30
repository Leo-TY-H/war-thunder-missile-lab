# Reading your missile export

Use **speed_kmh** and **flight_time_s** for the recorded missile speed and age. The older `speed_estimate_kmh` column is a smoothed position-based estimate, kept for comparison.

This exporter does **not yet reproduce every Sensor View readout**. A replay stores state updates; Sensor View also uses the game's playback physics, interpolation, atmosphere, and viewing origin. Blank cells mean **unavailable**, never zero or unlocked.

| Sensor View readout | Export column | What you get |
|---|---|---|
| Speed | `speed_kmh` | Magnitude of the recorded velocity, converted to km/h. |
| M | `mach_estimate` | Calculated with the game temperature model. Assumes sea-level temperature 288.16 K unless you supply another value. Replay weather temperature has not been decoded. |
| Distance | `sensor_distance_m` | Distance from an optional **fixed viewing origin**. Blank by default because the camera/selected origin is not recovered. This is not necessarily distance to the target. |
| Travelled | `travelled_estimate_m` | Sum of the recorded path segments, including the segment from the matched spawn. An approximation to the game's accumulated distance. Blank if the spawn cannot be identified. |
| Time | `flight_time_s` | Recorded missile lifetime, in steps of 1/48 second. |
| Overload | `sensor_overload_g` | **Not decoded yet.** Requires additional playback physics state; position-derived acceleration is not substituted. |
| AoA | `aoa_estimate_deg` | Unsigned angle calculated from the recorded orientation and velocity using the Sensor View formula. Agreement at the exact rendered frame is not validated. |
| Seeker | `seeker_status` | **Not decoded reliably yet.** The raw guidance state is exported separately, but is not the displayed SEARCH / IOG / IOG+DL / TRK enum. |

## Timing and precision

Each row is one recorded missile update. `replay_time_s` is the packet timestamp; `flight_time_s` is the missile's own lifetime timer. These are different clocks. Playback can display an interpolated or extrapolated state between updates, so matching a rounded HUD time alone does not establish an exact frame match.

Velocity components use signed 16-bit values with about **0.061 m/s** resolution and a range near ±2000 m/s per component. The speed is calculated from that vector, without smoothing. Position precision is about 7 mm horizontally and 29 mm vertically for packed positions; float32 precision varies with coordinate magnitude. Six decimal places in CSV do not imply six-decimal accuracy.

`sampled_path_m` starts at the first recorded position. `travelled_estimate_m` also includes a straight segment from the matched spawn to that position. Both omit motion after the last update and can underestimate curved motion between updates. A track ending does not establish a hit or a miss distance.

AoA here follows Sensor View's unsigned angle definition, folded into 0–90 degrees. It is not a signed pitch-only angle of attack. Mach and AoA are calculations, not independent sensor measurements.

## Optional settings

To label missiles, supply the scenario saved **for this particular test**. The exporter matches creation records to tracks and uses the recorded weapon slot; missile names are not read directly from the replay.

```bat
"Export Replay Measurements.cmd" "D:\Replays\test.wrpl" --scenario "D:\Replays\test-scenario.json"
```

If you know the sea-level air temperature for the replay, provide it in Kelvin (Celsius + 273.15):

```bat
"Export Replay Measurements.cmd" "D:\Replays\test.wrpl" --sea-level-temperature-k 288.16
```

If you want distance from a fixed world location, supply **X Y Z in metres**, with Y as altitude:

```bat
"Export Replay Measurements.cmd" "D:\Replays\test.wrpl" --view-origin 0 5000 0
```

That last example measures distance from a fixed point at 5 km altitude. It does not follow the launcher, target, camera, or selected missile. A Sensor View readout of 0 km does not mean the missile hit its target.

## Seeker data and remaining gaps

For the observed 607-bit radar/inertial/datalink layout, `raw_samples.json` preserves both the original payload and its decoded internal state. Other layouts are marked unsupported and preserved as raw bits. The CSV includes the raw two-bit guidance state and datalink byte for inspection. **Do not map these numbers directly to HUD labels or treat them as proof of lock.**

The target coordinates inside the inertial guidance payload are **the missile's target estimate**, not ground-truth aircraft telemetry. They may change sharply with guidance corrections and are unsuitable for measuring actual target speed or closest approach.

Exact HUD overload and seeker labels remain unfinished. Overload depends on aerodynamic coefficients, mass, thrust, atmosphere, and playback state. The displayed seeker label depends on tracking state beyond the raw guidance enum. These gaps are explicitly marked in each row rather than filled with guesses.

The current layout was checked against one replay containing three simultaneously launched radar-guided missiles, WRPL version `0x18c1c`. It is experimental. Source basis: the replay's bit fields, offline inspection of the installed game's serialization and Sensor View calculations, and the [game's Sensor View UI script](https://github.com/gszabi99/War-Thunder-Datamine/blob/master/gui.vromfs.bin_u/reactivegui/hud/sensorviewindicator.das). No game executable or asset files are distributed with this exporter.
