# War Thunder Missile Lab

Set up a single-player missile test with your own launcher aircraft and an AI target. Choose up to eight air-to-air missiles and set each aircraft's starting position, altitude, speed and heading.

The launcher uses the I-185 sample aircraft's **visible model**, with **J-16 flight dynamics** and a **J-16 KLJ-16 radar preset** by default. Changing its flight-model setting does not change its appearance. The mission takes place over an ocean; a terrain-free void is not included.

**Experimental:** exact simultaneous missile release, missile isolation, radar startup settings and precise motion holding have not been fully verified in-game. Legacy grouped release has only launched two missiles in testing. Release all does not yet guarantee that every selected missile launches and retains guidance.

## Install

You need Windows, War Thunder, the War Thunder CDK, and Python 3.10 or newer with Tkinter. You do not need to edit code or use the CDK editor.

1. Install the [War Thunder CDK](https://wiki.warthunder.com/war_thunder_cdk) into your War Thunder game folder. Missile Lab needs its sample aircraft files.
2. If needed, install [Python for Windows](https://www.python.org/downloads/windows/) with Tcl/Tk support. An existing Anaconda installation also works.
3. On this GitHub page, select **Code → Download ZIP**. Right-click the downloaded ZIP, choose **Extract All**, and open the extracted folder.
4. Double-click **Open Missile Lab.cmd**.
5. Next to **War Thunder folder**, click **Browse**. Select the game folder containing `aces.vromfs.bin`, not its `WarThunderCDK` subfolder.
6. Configure your test in the three tabs, then click **Build & install mission**. Wait for the **Installed … files** message.

**Save scenario** only saves your choices. **Build & install mission** saves them and applies them to the game. No manual copying of mission files is needed.

## Start a test

1. Fully quit and reopen War Thunder after installing or changing the aircraft, radar or missile settings.
2. From the hangar, open **Battles → User Missions → Missile Lab - Launcher and Target**. Use the hangar menu rather than the battle-mode selection panel beneath the battle button.
3. During the **RADAR SETUP** countdown, adjust the radar and acquire the target. The default hold lasts five seconds and ends automatically, whether or not you have a lock. You can keep adjusting the radar afterward.
4. Activate the seeker with **Weapon lock (air-to-air)**, then use the firing control for your selected mode below.
5. Restart the mission to restore starting positions and reload the missiles.

Find and bind these controls under **Controls → Aircraft**. Their keys depend on your control profile.

| Mode in the Missiles tab | Firing control | Behavior |
| --- | --- | --- |
| **Individual release** | **Fire air-to-air missile** | Test missiles separately. Start here to check locking and guidance. |
| **Release all (experimental)** | **Fire rocket salvo** | Attempts to release the entire loadout. Available after the countdown, once per mission run. Missile count, guidance and exact release timing remain unverified. |
| **Legacy grouped (pair observed)** | **Fire air-to-air missile** | Earlier grouped method; only two missiles launched in testing. |

For a first test, select only `us_aim_120a` and **Individual release**. Once that works, add other missiles or try Release all.

For Release all, give **Fire rocket salvo** a different key from **Fire air-to-air missile**. **Release-all command sent** confirms your input was received, not that every missile launched. Check the missiles themselves, not just the ammunition counter.

Radar-guided missiles need suitable target tracking. Semi-active radar missiles, including the example loadout's `su_r_27er1`, need continued radar illumination: use a radar target lock rather than relying on TWS alone. Infrared missiles need their own seeker lock. Mixed guidance types may not all be ready together.

## Configure your test

### Launcher & target

Set each aircraft independently. The launcher is the aircraft you control; the target is the AI aircraft.

| Setting | Meaning |
| --- | --- |
| **X / Z position** | Horizontal map coordinates in metres, from −200,000 to +200,000. These are not latitude and longitude. |
| **Altitude** | Metres above sea level, from 50 to 40,000. |
| **Speed** | Speed in km/h, from 0 to 5,000. Prescribed motion uses this as world distance per elapsed second; with prescribed motion off, the AI receives a TAS command. Check displacement over time as well as the speed display. Accepted values do not guarantee stable flight. |
| **Heading** | 0° = +X, 90° = +Z, 180° = −X, 270° = −Z. These mission directions may differ from the cockpit compass. |
| **Aircraft internal ID** | Target identifier, such as `f_16c_block_50`. Use the internal ID, not its display name. |

Click **Calculate initial separation** after editing positions. Both aircraft start level.

The first-run example places the target **50 km ahead**, flying in the same direction. Both start at **5,000 m**; the launcher starts at **1,500 km/h TAS**, the target at **700 km/h TAS**.

### Missiles

Select one missile per station, using between one and eight stations. Leave unused stations blank. Repeat an ID to carry multiple missiles of that type.

The list uses internal IDs such as `us_aim_120a` and `cn_pl12a`. Availability depends on your game version. You may type another installed missile ID without `.blk`, but the configurator cannot confirm that an unfamiliar ID exists in the game.

### Motion & setup

| Setting | What it does |
| --- | --- |
| **Prescribe straight-line motion for both aircraft** | Schedules absolute positions using the configured speed and time elapsed after radar setup. Flight controls are disabled during the test; radar, weapon and camera controls stay available. Discrete teleports are still used, so tracking disturbances and motion between updates need checking. |
| **Trajectory update interval** | 0.02–1 second in steps of 0.01; default 0.05. Smaller intervals create larger missions and do not guarantee more accurate playback. |
| **Prescribed motion duration** | 1–600 whole seconds after radar setup; default 120. Maximum 12,000 updates. At the end, a message appears, corrections stop and flight controls return. Later flight is outside the controlled test. |
| **Radar setup hold** | Holds aircraft near their starting positions for 0–30 whole seconds; default 5. Enter 0 to skip it. The simulation continues running, so this is not an exact pause. |
| **Make target invulnerable** | Requests an invulnerable target so the first hit does not end the encounter. On by default. |
| **Ignore projectiles in missile proximity fuses** | Disables proximity detection of missiles and shells while retaining aircraft detection. On by default; this option alone did not resolve the reported detonations. |
| **Isolate missiles from projectile collisions and damage reactions** | Also disables projectile collisions and missile damage reactions. On by default; effectiveness is unverified. Changes missile vulnerability, including while carried. |
| **Set missile warm-up time to zero** | Removes seeker warm-up time, not the need for a valid lock. On by default. |
| **Launcher flight-model ID** | Selects flight dynamics; default `j_16`. Changes neither appearance nor radar selection. |
| **Launcher radar preset** | `j16_tws_150` requests KLJ-16 startup in **TWS, 150 km, 30° × 15°**. `apg68` selects the alternative APG-68 radar. |

The radar's **150 km** setting is its display scale, not a guaranteed detection distance. Confirm its actual mode, range and scan size in-game before each comparison.

With motion holding off, flight controls become available when the countdown ends. If radar tracking is unstable, turn motion holding off to check whether corrections are interfering.

The old speed hold repeatedly teleported each aircraft to its own current position. A replay showed only about 5.15 km of movement in 20 seconds at a requested 1500 km/h. It has been replaced by scheduled positions computed from the starting point, heading and absolute elapsed time. This removes dependence on the distance the aircraft happened to travel between updates. **The replacement still needs an in-game displacement check; a correct speed display alone is not validation.**

At 1500 km/h, each aircraft should advance **8,333.33 m in 20 seconds after radar setup**. With the default five-second setup hold, check mission times 5–25 seconds. Head-on aircraft both at that speed close by 16,666.67 m over those 20 seconds. Every build writes **build/expected_motion.csv** with the commanded positions and times for both aircraft; these are reference values, not measured telemetry. Rebuild/install and restart the mission to apply the change; existing replays retain the old movement.

The missile options leave propulsion, drag and in-flight guidance parameters unchanged. They change launch preparation and damage interactions. Turn all three missile override options off to use stock missile definitions.

## Fast travel in replays

Select **Free camera (F)** in the replay. **Hold W and scroll the mouse wheel upward repeatedly** to increase camera travel speed; scroll downward to reduce it for close positioning. This was confirmed in-game for this setup and was fast enough for the requested long-distance travel. An exact speed in km/s has not been measured.

The earlier `debug` overrides `freeCamMoveSpd` and `freeCamTurboSpd` did not deliver the requested replay speed and have been removed from the local game configuration. No mission rebuild or configuration override is needed for mouse-wheel speed adjustment.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| **Python is not recognized / configurator will not open** | Extract the ZIP and use **Open Missile Lab.cmd**. If it reports missing Python, install Python 3.10 or newer with Tcl/Tk support. |
| **Required installed CDK/game file missing** | Select the folder containing `aces.vromfs.bin` and install the CDK there. Missing `sample_i_185_m82.blk` or `sample_i_185.grp` means the required sample aircraft is unavailable. |
| **Mission is missing** | Confirm installation succeeded and you selected the game installation you actually launch. Restart War Thunder. |
| **Only two missiles launch** | Select **Release all (experimental)**, click **Build & install mission**, and use **Fire rocket salvo**. The normal AAM-fire control still uses ordinary release behavior. |
| **Release all does nothing** | Wait until the countdown ends and check the **Fire rocket salvo** binding. Restart the mission if you already used it. Look for **Release-all command sent**. |
| **Ammunition disappears, missiles do not guide, or fewer launch** | Release all is unverified for that loadout. Use Individual release to check each missile and its guidance requirements. |
| **Missiles still detonate near one another** | Enable both isolation options, click **Build & install mission**, and fully restart the game. Isolation remains unverified; successful installation does not prove it works. |
| **Speed looks right but movement is too slow** | Rebuild/install to replace the old self-teleport hold, then restart the mission. Measure displacement after the setup hold and before prescribed motion ends. At 1500 km/h, 20 seconds should cover 8.33 km. The new schedule still requires in-game verification. |
| **TAS and IAS differ** | IAS can differ from TAS at altitude. With prescribed motion off, normal acceleration and deceleration apply. |
| **Aircraft still looks like an I-185 / radar did not change with the aircraft ID** | The I-185 body is expected. Choose the radar separately, click **Build & install mission**, and restart the game. |
| **New settings did not take effect** | Click **Build & install mission**, not just **Save scenario**, and fully restart War Thunder. |

## Export missile measurements from a replay

**Experimental:** the exporter has been checked against one local `.wrpl` replay, version `0x18c1c`, with three simultaneously released radar-guided missiles. It rejects other replay versions. A future game update may require an exporter update.

1. Save your replay in War Thunder. Keep the `scenario.json` used for that test alongside it if you want to identify missiles by loadout slot later.
2. Double-click **Export Replay Measurements.cmd** and choose the `.wrpl` file. You can also drag a replay onto that command file.
3. If dependencies are missing, the window prints a command to install them with your detected Python. Run that command once, then reopen the exporter.
4. Open the output folder printed in the window, inside Missile Lab's **telemetry** folder. Open **missile_samples.csv** in Excel for every missile, **track_1.csv** and the other numbered files for individual tracks, or **missile_summary.csv** for totals.

The export contains recorded **X/Y/Z position, velocity, speed and missile flight time**, plus calculated **Mach, travelled distance and AoA**. Use `speed_kmh` for recorded speed and `flight_time_s` for missile age. Y is altitude; X and Z are horizontal map coordinates, all in metres. The older `speed_estimate_kmh` column remains a smoothed position-based estimate.

**Sensor View coverage is incomplete:** Mach assumes an atmosphere temperature; travelled distance and AoA are reconstructed from recorded samples. Sensor View's **Distance** needs a viewing origin, and **Overload** and the displayed **Seeker** status are not yet decoded reliably. Those unavailable fields stay blank with a reason. See [Reading your missile export](REPLAY_FIELDS.md) for the exact columns, precision limits and optional settings.

Missiles receive numbered track labels by default. To add internal missile names from a saved scenario, open a terminal in the Missile Lab folder and run:

```bat
"Export Replay Measurements.cmd" "D:\Replays\test.wrpl" --scenario "D:\Replays\test-scenario.json"
```

Those names come from the supplied scenario and recorded weapon slots; they are not independently recovered from embedded missile names. Use the scenario from that exact test. The export records how each track was identified in **metadata.json** and preserves uninterpreted fields in **raw_samples.json**.

This exporter does not yet measure true target range, exact impact time, miss distance, or the complete Sensor View overload/seeker readouts. A track ending does not prove a hit. Read **READ_ME.txt** and **REPLAY_FIELDS.md** in the output folder for timing and precision limits. Replay exports remain local and are excluded from Git.

## Save settings and update

Your settings are saved in `scenario.json` inside the Missile Lab folder. Keep a copy to preserve your test setup.

To update, close the configurator, download and extract the new ZIP, then copy your existing `scenario.json` into the new folder. Open the new **Open Missile Lab.cmd**, click **Build & install mission**, and restart War Thunder.

Missile Lab installs its own mission and custom aircraft files. It backs up previous Missile Lab files in its local `backups` folder before replacement. Stock game archives and global control bindings are not changed.

This is an unofficial community project, not affiliated with Gaijin Entertainment.
