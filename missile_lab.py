"""Local CDK mission builder. Uses installed sample assets; no game archive edits."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent
PREFIX = "wt_missile_lab"
IDENT = re.compile(r"[a-zA-Z0-9_-]+\Z")


def ident(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError(f"Invalid internal aircraft/weapon ID: {value!r}")
    return value


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("All coordinates and speeds must be finite numbers.")
    return value


def fmt(value):
    return format(number(value), ".10g")


def direction(heading):
    """CDK coordinates: 0 degrees = +X; 90 degrees = +Z; Y is up."""
    angle = math.radians(number(heading) % 360)
    return math.cos(angle), math.sin(angle)


def matrix(state):
    c, s = direction(state["heading_deg"])
    return (f"[[{fmt(c)}, 0, {fmt(s)}] [0, 1, 0] "
            f"[{fmt(-s)}, 0, {fmt(c)}] "
            f"[{fmt(state['x_m'])}, {fmt(state['altitude_m'])}, {fmt(state['z_m'])}]]")


def replace_block(source, name, replacement):
    """Replace one root block, respecting strings, comments and nested braces."""
    token = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|[A-Za-z_][\w-]*|[{}]')
    tokens = list(token.finditer(source))
    depth = 0
    for i, match in enumerate(tokens):
        text = match.group()
        if text.startswith(('"', '//', '/*')):
            continue
        if depth == 0 and text == name and i + 1 < len(tokens) and tokens[i + 1].group() == '{':
            nest = 0
            for end in tokens[i + 1:]:
                if end.group() == '{':
                    nest += 1
                elif end.group() == '}':
                    nest -= 1
                    if nest == 0:
                        return source[:match.start()] + replacement + source[end.end():]
            raise ValueError(f"Unclosed block: {name}")
        depth += (text == '{') - (text == '}')
    raise ValueError(f"Expected sample block not found: {name}")


def validate(config):
    c = copy.deepcopy(config)
    # Existing scenarios gain projectile-insensitive proximity fuses on rebuild.
    c.setdefault("ignore_projectile_fuses", True)
    c.setdefault("isolate_missile_damage", True)
    c.setdefault("flight_model", "j_16")
    c.setdefault("radar", "j16_tws_150")
    c.setdefault("setup_delay_s", 5)
    if isinstance(c['setup_delay_s'], bool) or c['setup_delay_s'] != int(number(c['setup_delay_s'])) or not 0 <= number(c['setup_delay_s']) <= 30:
        raise ValueError("Setup countdown must be a whole number from 0 to 30 seconds.")
    c['setup_delay_s'] = int(c['setup_delay_s'])
    if c["radar"] not in ("j16_tws_150", "apg68"):
        raise ValueError("Radar must be j16_tws_150 or apg68.")
    game = Path(c["game_root"])
    sample = game / "content/pkg_local/gameData/flightModels/sample_i_185_m82.blk"
    model = game / "content/pkg_local/res/sample_i_185.grp"
    for path in (sample, model, game / "aces.vromfs.bin"):
        if not path.is_file():
            raise ValueError(f"Required installed CDK/game file missing: {path}")
    for who in ("launcher", "target"):
        for field in ("x_m", "z_m", "altitude_m", "speed_kmh", "heading_deg"):
            c[who][field] = number(c[who][field])
        if not 0 <= c[who]["speed_kmh"] <= 5000:
            raise ValueError(f"{who}: speed must be 0–5000 km/h.")
        if not 50 <= c[who]["altitude_m"] <= 40000:
            raise ValueError(f"{who}: altitude must be 50–40000 m for this ocean test.")
        if max(abs(c[who]["x_m"]), abs(c[who]["z_m"])) > 200000:
            raise ValueError(f"{who}: starting X/Z must be within +/-200000 m.")
    ident(c["target"]["aircraft"])
    ident(c["flight_model"])
    if not 1 <= len(c["missiles"]) <= 8:
        raise ValueError("Choose 1–8 missiles; the supplied custom model has eight rocket emitters.")
    for missile in c["missiles"]:
        ident(missile)
    if c["release_mode"] not in ("salvo", "grouped", "individual"):
        raise ValueError("Release mode must be salvo, grouped or individual.")
    for key in ("fixed_motion", "immortal_target", "zero_warmup", "ignore_projectile_fuses", "isolate_missile_damage"):
        if not isinstance(c[key], bool):
            raise ValueError(f"{key} must be a boolean.")
    c["correction_interval_s"] = number(c["correction_interval_s"])
    if not 0.02 <= c["correction_interval_s"] <= 1:
        raise ValueError("Motion correction interval must be 0.02–1 seconds.")
    if not re.fullmatch(r"levels/[A-Za-z0-9_-]+\.bin", c["level"]):
        raise ValueError("Level must be a simple levels/name.bin path.")
    return c


def unit(name, state, aircraft, army, weapons=""):
    return f'''  armada{{
    name:t="{name}"
    tm:m={matrix(state)}
    unit_class:t="{aircraft}"
    objLayer:i=0
    closed_waypoints:b=no
    weapons:t="{weapons}"
    props{{
      army:i={army}
      count:i=1
      skill:i=4
      attack_type:t="hold_fire"
      plane{{ ai_skill:t="NORMAL"; task:t="FLY_WAYPOINT"; }}
    }}
    way{{}}
  }}'''


def area(name, state, ahead=0):
    state = dict(state)
    dx, dz = direction(state["heading_deg"])
    state["x_m"] += ahead * dx
    state["z_m"] += ahead * dz
    return f'''  {name}{{
    type:t="Point"
    tm:m={matrix(state)}
    objLayer:i=0
    props{{}}
  }}'''


def teleport(name, state, initial=False):
    # CDK velocity accepts km/h here. Dividing by 3.6 made 1500 become 417 in game.
    return f'''      unitMoveTo{{
        object:t="{name}"
        target:t="{name + '_start' if initial else name}"
        target_type:t="any"
        move_type:t="teleport"
        teleportHeightType:t="absolute"
        useUnitHeightForTele:b=no
        teleportHeightValue:r={fmt(state['altitude_m'])}
        lookat:t="{name}_heading"
        horizontalDirectionForTeleport:b=yes
        velocity:r={fmt(state['speed_kmh'])}
        distributionRadius:r=0
        shouldKeepFormation:b=no
      }}'''


def trigger(name, actions, interval=None, *, enabled=True, after=None, conditions="", once=False):
    event = (f"timeExpires{{ time:r={fmt(after)}; }}" if after is not None else
             "initMission{}" if interval is None else f"periodicEvent{{ time:r={fmt(interval)}; }}")
    return f'''  {name}{{
    is_enabled:b={'yes' if enabled else 'no'}
    props{{
      actionsType:t="PERFORM_ONE_BY_ONE"
      conditionsType:t="ALL"
      enableAfterComplete:b={'no' if interval is None or once else 'yes'}
    }}
    events{{ {event} }}
    conditions{{{conditions}}}
    actions{{
{actions}
    }}
  }}'''


def mission(c):
    initial = []
    delay = c['setup_delay_s']
    for name in ("launcher", "target"):
        state = c[name]
        immortal = name == "launcher" or c["immortal_target"]
        initial.append(f'''      unitSetProperties{{
        object:t="{name}"
        isImmortal:b={'yes' if immortal else 'no'}
        speed:r={fmt(state['speed_kmh'])}
        lockSpeed:b=yes
        ignoresEnemy:b=yes
        aiGunnersEnabled:b=no
        attack_type:t="hold_fire"
      }}''')
        initial.append(teleport(name, state, initial=True))
    target_move = f'''      unitMoveTo{{
        object:t="target"
        target:t="target_heading"
        move_type:t="move"
        speed:r={fmt(c['target']['speed_kmh'])}
        tas:b=yes
        follow_target:b=no
        getToLOS:b=no
        altRange:p2={fmt(c['target']['altitude_m'])}, {fmt(c['target']['altitude_m'])}
      }}'''
    if not delay:
        initial.append(target_move)
    if c["fixed_motion"] or delay:
        axes = ["AXIS_MOUSE_AIM_X", "AXIS_MOUSE_AIM_Y", "AXIS_AILERONS", "AXIS_ELEVATOR", "AXIS_RUDDER", "AXIS_THROTTLE"]
        initial.append('      playerControls{\n' + ''.join(f'        control:t="{x}"\n' for x in axes) + '        setStatus:t="disable"\n      }')
    help_hint = '      playHint{ name:t="wt_missile_lab_help"; action:t="show"; time:r=15; }'
    initial.append(f'      playHint{{ name:t="{PREFIX}_count_{delay}"; action:t="show"; time:r=1; }}' if delay else help_hint)
    triggers = [trigger("initialize", '\n'.join(initial))]
    if delay:
        # Hold starting positions while the simulation/radar continue running.
        # Retain configured velocities for Doppler calculations. This is a
        # positional correction every .02 s, not a global physics pause.
        triggers.append(trigger("setup_hold", '\n'.join(teleport(name, c[name], initial=True) for name in ('launcher', 'target')), 0.02))
        for elapsed in range(1, delay):
            triggers.append(trigger(f"setup_count_{elapsed}", f'      playHint{{ name:t="{PREFIX}_count_{delay-elapsed}"; action:t="show"; time:r=1; }}', after=elapsed))
        release = ['      triggerDisable{ target:t="setup_hold"; }']
        release.extend(teleport(name, c[name], initial=True) for name in ('launcher', 'target'))
        release.append(target_move)
        if c['fixed_motion']:
            release.append('      triggerEnable{ target:t="correct_motion"; }')
        else:
            release.append('      playerControls{\n' + ''.join(f'        control:t="{x}"\n' for x in axes) + '        setStatus:t="enable"\n      }')
        if c['release_mode'] == 'salvo':
            release.append('      triggerEnable{ target:t="release_all_missiles"; }')
        release.append(help_hint)
        triggers.append(trigger('start_test', '\n'.join(release), after=delay))
    if c["fixed_motion"]:
        triggers.append(trigger("correct_motion", '\n'.join(teleport(name, c[name]) for name in ("launcher", "target")), c["correction_interval_s"], enabled=not delay))
    if c['release_mode'] == 'salvo':
        # The ordinary AAM trigger only released a pair in the user's test.
        # CDK documents unitDropAmmo as firing all rockets. Whether it retains
        # mixed-AAM target designation and releases in one frame needs testing.
        # A separate shortcut avoids firing a normal pair before this action.
        triggers.append(trigger('release_all_missiles', '''      unitDropAmmo{ object:t="launcher"; }
      playHint{ name:t="wt_missile_lab_salvo_sent"; action:t="show"; time:r=8; }''',
            0.01, enabled=not delay, once=True, conditions='''
      playerShortcutPressed{
        control:t="ID_ROCKETS_SERIES"
        pressed:b=yes
        checkUp:b=no
      }
    '''))
    return f'''// Generated by missile_lab.py. Grouped launch and fixed motion require in-game validation.
selected_tag:t=""
bin_dump_file:t=""
mission_settings{{
  atmosphere{{ pressure:r=760; temperature:r=15; }}
  player{{ army:i=1; wing:t="launcher"; }}
  player_teamB{{ army:i=2; }}
  mission{{
    name:t="{PREFIX}"
    locName:t="Missile Lab - Launcher and Target"
    locDesc:t="Configurable missile test. Experimental grouped release and motion correction."
    level:t="{c['level']}"
    type:t="singleMission"
    restoreType:t="attempts"
    optionalTakeOff:b=no
    campaign:t="UserMissions"
    environment:t="Day"
    weather:t="clear"
    difficulty:t="realistic"
    fuelAmount:r=50
  }}
}}
imports{{}}
triggers{{
  isCategory:b=yes
  is_enabled:b=yes
{chr(10).join(triggers)}
}}
mission_objectives{{ isCategory:b=yes; is_enabled:b=yes; }}
variables{{}}
dialogs{{}}
airfields{{}}
effects{{}}
units{{
{unit('launcher', c['launcher'], PREFIX + '_launcher', 1, PREFIX + '_loadout')}
{unit('target', c['target'], c['target']['aircraft'], 2)}
}}
areas{{
{chr(10).join(area(name + '_start', c[name]) + chr(10) + area(name + '_heading', c[name], 1000000) for name in ('launcher', 'target'))}
}}
objLayers{{ layer{{ enabled:b=yes; }} }}
wayPoints{{}}
'''


def j16_radar():
    # Keep the installed radar's detection/tracking parameters and FSM. The stock
    # initToMprfTws transition already selects TWS; reorder its scope/scan choices.
    # Stock narrow pattern: +/-15 azimuth, six 2.5-degree elevation bars.
    return '''include "#/develop/gameBase/gameData/sensors/cn_klj_j16.blk"
"@override:scopeRangeSets" {
  "@override:common" {
    "@override:range1":r=150000
    "@override:range2":r=300000
    "@override:range3":r=20000
    "@override:range4":r=40000
    "@override:range5":r=80000
  }
}
"@override:scanPatternSets" {
  "@override:radarTws" {
    "@override:scanPattern1":t="radarTwsNarrow"
    "@override:scanPattern2":t="radarTwsMedium"
  }
}
"@override:fsms" {
  "@override:main" {
    "@override:actionsTemplates" {
      "@override:init" {
        "@override:setEnabled" { "@override:value":b=yes; }
      }
    }
    "@override:transitions" {
      "@override:init" {
        "@override:stateTo":t="search"
        "@override:actions" {
          doCustomActionTemplate { fsm:t="main"; name:t="setSearchMode"; }
        }
      }
    }
  }
}
'''


def generate(config):
    c = validate(config)
    game = Path(c['game_root'])
    base = game / 'content/pkg_local/gameData'
    source = (base / 'flightModels/sample_i_185_m82.blk').read_text(encoding='utf-8-sig')
    source = replace_block(source, 'cockpit', 'cockpit{}')
    source = replace_block(source, 'commonWeapons', 'commonWeapons{}')
    source = replace_block(source, 'weapon_presets', f'''weapon_presets{{
  preset{{ name:t="{PREFIX}_loadout"; blk:t="gameData/flightModels/weaponPresets/{PREFIX}_loadout.blk"; }}
}}''')
    source = re.sub(r'fmFile:t="[^"]+"', f'fmFile:t="fm/{c["flight_model"]}.blk"', source, count=1)
    # Sensor is independent of nonexistent radar damage nodes in the sample model.
    radar = PREFIX + '_j16_tws_150' if c['radar'] == 'j16_tws_150' else 'us_an_apg_68_v_7'
    source += f'\nsensors{{ sensor{{ blk:t="gameData/sensors/{radar}.blk"; }} }}\n'
    source += '''
advancedInstructor:b=yes
advancedMouseAim:b=yes
'''
    weapons = []
    files = {}
    if c['radar'] == 'j16_tws_150':
        files[f'content/pkg_local/gameData/sensors/{radar}.blk'] = j16_radar()
    for i, missile in enumerate(c['missiles'], 1):
        weapon_id = missile
        if c['zero_warmup'] or c['ignore_projectile_fuses'] or c['isolate_missile_damage']:
            weapon_id = PREFIX + '_' + missile
            overrides = []
            if c['zero_warmup']:
                overrides.append('  "@override:guidance" { "@override:warmUpTime":r=0; }')
            if c['ignore_projectile_fuses']:
                overrides.append('  "@override:proximityFuse" { "@override:detectShells":b=no; }')
            if c['isolate_missile_damage']:
                # detectShells alone does not cover projectile impacts or the
                # DamageEffects/part/onHit inFlight explosion reaction.
                # Delete/add also handles missiles without these optional keys.
                overrides.append('''  "@delete:shellCollision":b=no
  shellCollision:b=no
  "@delete:DamageEffects" {}
  DamageEffects {}''')
            files[f'content/pkg_local/gameData/weapons/rocketGuns/{weapon_id}.blk'] = (
                f'include "#/develop/gameBase/gameData/Weapons/rocketGuns/{missile}.blk"\n'
                '"@override:rocket" {\n' + '\n'.join(overrides) + '\n}\n')
        weapons.append(f'''Weapon{{
  trigger:t="aam"
  blk:t="gameData/Weapons/rocketGuns/{weapon_id}.blk"
  emitter:t="rocket{i}"
  bullets:i=1
  external:b=yes
  separate:b={'yes' if c['release_mode'] == 'individual' else 'no'}
  order:i={i if c['release_mode'] == 'individual' else 0}
}}''')
    files[f'content/pkg_local/gameData/flightModels/{PREFIX}_launcher.blk'] = source
    files[f'content/pkg_local/gameData/flightModels/weaponPresets/{PREFIX}_loadout.blk'] = '\n\n'.join(weapons) + '\n'
    files[f'UserMissions/{PREFIX}.blk'] = mission(c)
    help_text = ('Lock target and activate AAM seeker, then press FIRE ROCKET SALVO for the experimental release-all command. Restart mission to reset.'
                 if c['release_mode'] == 'salvo' else
                 'Lock target and fire air-to-air missiles. Normal grouped release fired only a pair in testing. Restart mission to reset.')
    files[f'UserMissions/usr_{PREFIX}.csv'] = (
        '<ID|readonly|noverify>;<English>\n'
        f'{PREFIX}_launcher;"Missile Lab custom launcher"\n'
        f'{PREFIX}_launcher_shop;"Missile Lab custom launcher"\n'
        f'weapons/{PREFIX}_loadout;"Missile Lab selected missiles"\n'
        f'wt_missile_lab_help;"{help_text}"\n'
        'wt_missile_lab_salvo_sent;"Release-all command sent. Check missile count and guidance; ammunition is consumed. Restart mission to reset."\n')
    files[f'UserMissions/usr_{PREFIX}.csv'] += ''.join(
        f'{PREFIX}_count_{remaining};"RADAR SETUP: {remaining} s - aircraft held at start. Designate the target now."\n'
        for remaining in range(1, c['setup_delay_s'] + 1))
    return c, files


def build(config, install=False):
    c, files = generate(config)
    out = ROOT / 'build'
    for relative, content in files.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    manifest = {'generated_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'config': c,
                'files': list(files), 'validation': 'Generated; not yet validated in War Thunder.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if install:
        backup = ROOT / 'backups' / dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        for relative in files:
            dest = Path(c['game_root']) / relative
            if dest.exists():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, saved)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out / relative, dest)
    return out, list(files)


def load_config(path=ROOT / 'scenario.json'):
    path = Path(path)
    # A fresh checkout starts from the portable example. Save/build in the GUI
    # creates scenario.json locally; an explicit missing --config stays an error.
    if path == ROOT / 'scenario.json' and not path.exists():
        path = ROOT / 'scenario.example.json'
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'scenario.json')
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    try:
        out, files = build(load_config(args.config), args.install)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(f"{'Installed' if args.install else 'Built'} {len(files)} files. Build directory: {out}")
    print('Mission: Missile Lab - Launcher and Target. Runtime validation is still required.')


if __name__ == '__main__':
    main()
