# Missile Lab

A configurable local War Thunder user mission with a player-controlled custom launcher and an AI target. The launcher uses the CDK's compiled I-185 sample body, selectable flight dynamics (J-16 by default), and a separate radar preset (J-16 KLJ-16 by default). No external mod or Blender installation is needed.

**Status: prototype runs in-game according to user testing.** The speed scaling bug has been corrected. The first proximity-only fix did not resolve the user-reported missile detonations; the revised isolation option also disables projectile collision and missile damage reactions. The new radar preset, isolation and setup countdown require an in-game retest. Normal grouped AAM firing released only two missiles in the user test. An experimental CDK release-all mode has now been added; all-missile launch, retained guidance and same-frame timing remain unverified. Precise motion stability also remains unverified. The ocean map is used for now; a void level is deferred.

## Requirements

- Windows with War Thunder and the War Thunder CDK sample aircraft installed into the same game folder.
- Python 3.10 or newer with Tkinter (included in the standard Windows installer). No pip packages are required.

## Use

Download this repository as a ZIP and extract it, or clone it with Git. Generated game files are built locally; game assets are not included in this repository.

1. Open **Open Missile Lab.cmd** in this folder. It detects the Windows Python launcher, Anaconda, or Python on PATH. You can also run `python configurator.py`, or set `MISSILE_LAB_PYTHON` to a specific `python.exe`. On first use, browse to your War Thunder game folder (the folder containing `aces.vromfs.bin`, not the `WarThunderCDK` subfolder).
2. Set the launcher and target's X, Z, altitude, speed, and heading. Set the target's internal aircraft ID if desired.
3. Select up to eight missiles in the Missiles tab. Duplicate IDs are allowed. The list contains 102 AAM definitions checked against the public data snapshot; availability and compatibility still depend on your game version. You can also type another installed rocketGun ID.
4. Choose **Build & install mission**. This saves `scenario.json` and installs the generated files.
5. Start/restart War Thunder. Open **Battles → User Missions → Missile Lab - Launcher and Target**.
6. Use the initial five-second **RADAR SETUP** countdown to adjust the radar and designate the target. Both aircraft are held at their start positions, then released automatically. Acquire the target, activate the seeker with **Weapon lock (air-to-air)**, then, in the new **Release all (experimental)** mode, press **Fire rocket salvo** once. Bind that action in Controls → Aircraft → Weaponry if it has no key. Use a different key from **Fire air-to-air missile**; pressing the normal AAM control still uses the ordinary pair/individual release path. The release-all control is enabled after the setup countdown. For Individual/legacy Grouped mode, use **Fire air-to-air missile**. Radar-guided missiles additionally need appropriate target designation; SARH missiles need continued radar support.
7. Restart the mission for a fresh run. Rebuild and restart the game after changing aircraft/weapon definitions, which may be cached.

The included example starts with a tail chase. `scenario.example.json` supplies first-run defaults; saving from the configurator creates your local `scenario.json`, which Git ignores. The target is invulnerable by default so the first hit should not end later missiles' tests. The two isolation options below address projectile proximity fusing and projectile damage separately; neither fix is yet confirmed in-game.

## Coordinates and fixed motion

- X and Z are horizontal world coordinates in metres; altitude is Y, metres above sea level.
- Heading is defined as 0° along +X, 90° along +Z, 180° along −X, and 270° along −Z. This is a CDK coordinate convention, not a promise of matching the cockpit compass.
- Speed inputs and the generated teleport velocity are both in km/h. The previous division by 3.6 produced 417 for a requested 1500; that conversion has been removed for both launcher and target. Check against TAS rather than IAS.
- Both aircraft start with level pitch and roll.

**Fixed motion is an experimental correction loop.** Every 0.05 seconds by default, `unitMoveTo` teleports each aircraft to its own current horizontal position, restores the chosen altitude, points it toward a distant marker on its prescribed heading, and resets its velocity. The target also receives `lockSpeed` and a straight flight command. The player's flight axes are disabled while weapon, radar and camera controls remain available.

This does not continuously integrate an exact prescribed trajectory. Departures between corrections, frame scheduling, or engine teleport behavior can affect speed, heading, and radar tracking. The heading marker is finite (1,000 km ahead); restart before passing it. Do not treat this prototype as an exact kinematic test fixture before validating these effects. Turn fixed motion off to diagnose whether corrections interfere with guidance.

## Missile release

**Release all (experimental)** uses a one-shot mission trigger watching **Fire rocket salvo** (`ID_ROCKETS_SERIES`). It calls `unitDropAmmo` once for the launcher, rather than repeatedly pressing the ordinary AAM-fire control. The installed CDK schema and [official trigger reference](https://wiki.warthunder.com/cdk/7436-cdk-mission-editor-triggers) document this action as releasing bombs/rockets and emptying ammunition. The launcher carries only the selected missiles.

This is a diagnostic implementation, not a confirmed simultaneous guided-missile salvo: the documentation does not establish mixed-AAM guidance retention or engine scheduling. After locking and activating the seeker, press Fire rocket salvo. A **Release-all command sent** hint confirms that the mission received the input; it does not prove the engine launched eight guided missiles. Check that every missile leaves its station and guides toward the target. If ammunition simply disappears, missiles drop unguided, or fewer launch, report that outcome. Restart the mission to reload and rearm this one-shot trigger.

Legacy grouped mode assigns the same order to all rocket emitters and disables separate release; **the user observed only two missiles launching**, so it is no longer presented as an all-missile launch solution. Individual mode is retained for checking each missile independently. One missile is assigned per occupied emitter. No missile propulsion, guidance, or ignition-delay parameters are changed by selecting the release-all mode.

The preset uses local wrappers around the installed game's missile definitions. **Ignore projectiles in missile proximity fuses** is enabled by default and overrides only `rocket/proximityFuse/detectShells` to `no`. This targets premature detonation from nearby missiles and shells while retaining the inherited aircraft proximity fuse, its radius, and its arming delay. It does not distinguish friendly from enemy projectiles. The separate **Isolate missiles from projectile collisions and damage reactions** option now defaults on. It sets `shellCollision=no` and replaces the missile `DamageEffects` block with an empty block, removing stock in-flight hit/explosion and kill/destruction reactions. This also changes damage behavior of the missiles while carried; use these options for comparative flight tests, not stock missile vulnerability tests. Aircraft proximity fuses, warhead strength, propulsion and guidance remain inherited. Runtime effectiveness still needs retesting.

Optional zero warm-up also overrides `rocket/guidance/warmUpTime` to zero. The options work independently or together. Propulsion, drag and in-flight guidance are inherited unchanged. With all three missile override options off, the preset references stock definitions directly. Restart the configurator after a code update and restart War Thunder to reload changed missile definitions.

The default **j16_tws_150** radar preset includes the installed KLJ-16 definition, requests enabled TWS at startup, makes 150 km the first scope range, and makes the stock narrow TWS scan (30° azimuth × 15° elevation) the first scan pattern. Other stock ranges and scan modes remain selectable. This is the display range, not a promise of detecting every target at 150 km. The previous APG-68 preset remains selectable. Radar and flight-model selectors are independent and explicitly labeled.

The default five-second setup hold uses repeated position/orientation corrections every 0.02 s so the radar simulation and controls can continue running. Configured velocity is retained for Doppler calculations. Small movement between corrections is possible; this is not a global physics pause. Motion starts at countdown expiry. With fixed motion off, flight controls are restored then. Set the setup hold to 0 to disable it (maximum 30 s).

Changing the launcher flight-model ID changes dynamics, not the visible I-185 body. An arbitrary stock aircraft's complete appearance/avionics is not implemented. The target aircraft ID is independently configurable. There is no custom cockpit.

## Files and installation

Select the game root in the configurator. Only project-named files are installed underneath it:

```text
UserMissions/wt_missile_lab.blk
UserMissions/usr_wt_missile_lab.csv
content/pkg_local/gameData/flightModels/wt_missile_lab_launcher.blk
content/pkg_local/gameData/flightModels/weaponPresets/wt_missile_lab_loadout.blk
content/pkg_local/gameData/weapons/rocketGuns/wt_missile_lab_*.blk  [test wrappers]
content/pkg_local/gameData/sensors/wt_missile_lab_j16_tws_150.blk
```

The original CDK files, game archives, and global control configuration are not overwritten. Existing project-named files are backed up under `backups/` before replacement. `build/manifest.json` lists the latest build. The project depends on the model/resources supplied with the CDK.

After saving your game folder and scenario in the configurator, command-line equivalents:

```powershell
python missile_lab.py --install
python -m unittest -v test_missile_lab
python record_telemetry.py --seconds 20
```

The recorder reads only `127.0.0.1:8111`, saves raw samples under `telemetry/`, and reports launcher TAS/altitude variation when valid flight data is available. It does not measure missile release timing.

## Verification still needed

1. Mission loads into the launcher with selected missiles and a visible target.
2. Starting positions/directions match; launcher TAS matches the requested value. Compare target motion independently.
3. Speed, altitude and heading remain stable, including after missile release.
4. One IR missile locks and guides, followed by a grouped IR pair.
5. Radar missiles work individually before testing mixed guidance types.
6. Check release frames in a replay before calling the group simultaneous.

## Implementation references

The installed CDK samples and `unitMoveTo`, `unitSetProperties`, `playerControls`, and `periodicEvent` schemas supply mission syntax. The sample aircraft supplies the compiled model, eight rocket emitters, and base definition.

- [Custom units creation](https://wiki.warthunder.com/cdk/1212-custom-units-creation)
- [Aircraft model integration](https://wiki.warthunder.com/cdk/233-checking-3d-model-of-the-aircraft-in-game)
- [CDK trigger reference](https://old-wiki.warthunder.com/Triggers)
- [Public game-data snapshot](https://github.com/gszabi99/War-Thunder-Datamine/tree/master/aces.vromfs.bin_u/gamedata): used to identify missile IDs, AAM type, sensor paths, and weapon-station fields. Runtime missile physics comes from the installed game, not this snapshot.

Latest regression checks cover radar wiring, scan/range defaults, collision/damage isolation, preserved missile physics, and countdown release with fixed motion both on and off. These checks verify generated files, not engine behavior. Fully quit and relaunch War Thunder after installing this update; restarting only the mission may retain cached definitions.

## Development

Run `python -m unittest -v test_missile_lab`. The tests use a small synthetic sample definition and require no game installation. GitHub Actions runs them on Windows and Linux. A passing test suite validates the generator, not the in-game behavior described above.

`scenario.json`, `build/`, `backups/`, `telemetry/`, and research downloads under `reference/` stay local and are ignored by Git. Keep game assets out of commits. This is an unofficial community project and is not affiliated with Gaijin Entertainment.
