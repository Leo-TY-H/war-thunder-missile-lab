import copy
import math
import re
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from missile_lab import ROOT, direction, generate, load_config, matrix, replace_block, position_at, motion_times


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.c = load_config(ROOT / 'scenario.example.json')
        # Synthetic fixture: tests run without installing or distributing game assets.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        game = Path(folder.name)
        sample = game / 'content/pkg_local/gameData/flightModels/sample_i_185_m82.blk'
        sample.parent.mkdir(parents=True)
        sample.write_text('cockpit{}\ncommonWeapons{}\nweapon_presets{}\nfmFile:t="fm/sample.blk"\n', encoding='utf-8')
        model = game / 'content/pkg_local/res/sample_i_185.grp'
        model.parent.mkdir(parents=True)
        model.touch()
        (game / 'aces.vromfs.bin').touch()
        self.c['game_root'] = str(game)
        self.c.update(zero_warmup=False, ignore_projectile_fuses=False, isolate_missile_damage=False, setup_delay_s=0,
                      motion_duration_s=2, release_mode='grouped', missiles=['us_aim9l_sidewinder', 'us_aim9m_sidewinder'])

    def test_cardinal_headings_and_rotation(self):
        for angle, expected in [(0, (1, 0)), (90, (0, 1)), (180, (-1, 0)), (270, (0, -1))]:
            actual = direction(angle)
            for a, b in zip(actual, expected):
                self.assertAlmostEqual(a, b)
            self.assertAlmostEqual(sum(x*x for x in actual), 1)

    def test_fresh_checkout_loads_example_without_writing_local_config(self):
        import missile_lab
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if path == ROOT / 'scenario.json':
                self.fail('A missing local configuration must not be read')
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'exists', return_value=False), patch.object(Path, 'read_text', read):
            c = missile_lab.load_config()
        self.assertEqual(c['game_root'], 'C:/Program Files (x86)/Steam/steamapps/common/War Thunder')
        with self.assertRaises(FileNotFoundError):
            load_config(Path(self.c['game_root']) / 'missing-explicit-config.json')

    def test_block_replacement_ignores_comments_and_strings(self):
        text = 'a{ text:t="} {"; }\n// commonWeapons{bad}\ncommonWeapons{ child{ x:t="}"; } }\nz:i=2'
        result = replace_block(text, 'commonWeapons', 'commonWeapons{}')
        self.assertIn('// commonWeapons{bad}', result)
        self.assertNotIn('child{', result)
        self.assertTrue(result.endswith('z:i=2'))

    def test_transforms_preserve_independent_states(self):
        self.c['target'].update(x_m=7654, z_m=-3456, altitude_m=8765, heading_deg=90, speed_kmh=360)
        _, files = generate(self.c)
        mission = files['UserMissions/wt_missile_lab.blk']
        self.assertIn('[7654, 8765, -3456]', mission)
        self.assertIn('velocity:r=360', mission)
        self.assertIn('speed:r=360', mission)
        self.assertIn('lookat:t="target_heading"', mission)
        self.assertIn('wing:t="launcher"', mission)

    def test_grouped_and_individual_release(self):
        key = 'content/pkg_local/gameData/flightModels/weaponPresets/wt_missile_lab_loadout.blk'
        self.c['missiles'] = ['us_aim9l_sidewinder', 'su_r_73', 'us_aim9l_sidewinder']
        _, files = generate(self.c)
        self.assertEqual(files[key].count('order:i=0'), 3)
        self.assertEqual(files[key].count('separate:b=no'), 3)
        self.c['release_mode'] = 'individual'
        _, files = generate(self.c)
        self.assertIn('order:i=3', files[key])
        self.assertEqual(files[key].count('separate:b=yes'), 3)

    def test_unmodified_missiles_by_default(self):
        _, files = generate(self.c)
        self.assertFalse(any('/weapons/rocketGuns/' in p for p in files))
        self.c['zero_warmup'] = True
        _, files = generate(self.c)
        overrides = [s for p, s in files.items() if '/weapons/rocketGuns/' in p]
        self.assertEqual(len(overrides), len(set(self.c['missiles'])))
        self.assertTrue(all('warmUpTime' in s for s in overrides))
        self.assertTrue(all('force' not in s and 'mass' not in s for s in overrides))

    def test_disable_fixed_motion(self):
        self.c['fixed_motion'] = False
        _, files = generate(self.c)
        mission = files['UserMissions/wt_missile_lab.blk']
        self.assertNotIn('correct_motion{', mission)
        self.assertNotIn('motion_sample_', mission)
        self.assertNotIn('_motion_1', mission)
        self.assertNotIn('playerControls{', mission)

    def test_speed_is_not_divided_by_3_6(self):
        self.c['launcher']['speed_kmh'] = 1500
        self.c['target']['speed_kmh'] = 700
        self.c['fixed_motion'] = True
        _, files = generate(self.c)
        mission = files['UserMissions/wt_missile_lab.blk']
        # Both initialization and subsequent corrections use the same units.
        velocities = re.findall(r'velocity:r=([\d.]+)', mission)
        self.assertEqual(set(velocities), {'1500', '700'})
        self.assertEqual(velocities.count('1500'), velocities.count('700'))
        self.assertGreater(velocities.count('1500'), 2)
        self.assertNotIn('velocity:r=416', mission)
        self.assertNotIn('velocity:r=194', mission)

    def test_fuse_override_is_independent_of_warmup(self):
        for warmup in (False, True):
            self.c.update(ignore_projectile_fuses=True, zero_warmup=warmup,
                          missiles=['cn_pl12a', 'us_aim_120a', 'su_r_77_1', 'cn_pl12a'])
            _, files = generate(self.c)
            wrappers = {p: s for p, s in files.items() if '/weapons/rocketGuns/' in p}
            self.assertEqual(len(wrappers), 3)
            for content in wrappers.values():
                self.assertIn('"@override:proximityFuse" { "@override:detectShells":b=no;', content)
                self.assertEqual('warmUpTime' in content, warmup)
                # Do not disable the aircraft proximity fuse or change performance.
                for field in ('hasProximityFuse', 'radius', 'timeOut', 'shellCollision', 'force', 'mass'):
                    self.assertNotIn(field, content)
            preset = files['content/pkg_local/gameData/flightModels/weaponPresets/wt_missile_lab_loadout.blk']
            for missile in self.c['missiles']:
                self.assertIn(f'rocketGuns/wt_missile_lab_{missile}.blk', preset)

    def test_old_scenarios_enable_fuse_fix(self):
        self.c.pop('ignore_projectile_fuses')
        c, files = generate(self.c)
        self.assertTrue(c['ignore_projectile_fuses'])
        self.assertTrue(any('detectShells' in value for value in files.values()))

    def test_isolation_preserves_aircraft_fuse_and_flight_performance(self):
        self.c.update(isolate_missile_damage=True, ignore_projectile_fuses=True)
        _, files = generate(self.c)
        for path, content in files.items():
            if '/weapons/rocketGuns/' not in path:
                continue
            self.assertIn('shellCollision:b=no', content)
            self.assertIn('"@delete:DamageEffects" {}', content)
            self.assertIn('DamageEffects {}', content)
            self.assertIn('"@override:detectShells":b=no', content)
            for unchanged in ('hasProximityFuse', 'radius', 'timeOut', 'mass', 'force', 'explosiveMass', 'radarSeeker'):
                self.assertNotIn(unchanged, content)

    def test_j16_default_radar_and_legacy_selection(self):
        self.c.pop('radar', None)
        self.c.pop('flight_model', None)
        c, files = generate(self.c)
        self.assertEqual(c['flight_model'], 'j_16')
        aircraft = files['content/pkg_local/gameData/flightModels/wt_missile_lab_launcher.blk']
        self.assertIn('fm/j_16.blk', aircraft)
        self.assertNotIn('us_an_apg_68_v_7', aircraft)
        self.assertIn('sensors/wt_missile_lab_j16_tws_150.blk', aircraft)
        radar = files['content/pkg_local/gameData/sensors/wt_missile_lab_j16_tws_150.blk']
        self.assertIn('cn_klj_j16.blk', radar)
        self.assertIn('"@override:range1":r=150000', radar)
        self.assertIn('"@override:scanPattern1":t="radarTwsNarrow"', radar)
        self.assertIn('"@override:stateTo":t="search"', radar)
        self.c['radar'] = 'apg68'
        _, files = generate(self.c)
        self.assertFalse(any('/sensors/' in path for path in files))
        self.assertIn('us_an_apg_68_v_7', files['content/pkg_local/gameData/flightModels/wt_missile_lab_launcher.blk'])

    def test_invalid_inputs_rejected(self):
        for change in [lambda c: c.update(missiles=[]), lambda c: c.update(missiles=['x']*9),
                       lambda c: c['launcher'].update(speed_kmh=float('nan')),
                       lambda c: c['target'].update(aircraft='../bad'),
                       lambda c: c.update(correction_interval_s=0),
                       lambda c: c.update(correction_interval_s=.025),
                       lambda c: c.update(motion_duration_s=0),
                       lambda c: c.update(motion_duration_s=1.5),
                       lambda c: c.update(motion_duration_s=float('inf')),
                       lambda c: c.update(motion_duration_s=600, correction_interval_s=.02)]:
            c = copy.deepcopy(self.c)
            change(c)
            with self.assertRaises(ValueError):
                generate(c)

    def test_countdown_defers_motion_and_releases_controls(self):
        for fixed in (True, False):
            self.c.update(setup_delay_s=5, fixed_motion=fixed)
            _, files = generate(self.c)
            mission = files['UserMissions/wt_missile_lab.blk']
            self.assertIn('timeExpires{ time:r=5;', mission)
            self.assertIn('triggerDisable{ target:t="setup_hold";', mission)
            self.assertIn('setup_count_4{', mission)
            self.assertIn('periodicEvent{ time:r=0.02;', mission)
            if fixed:
                self.assertNotIn('correct_motion', mission)
                self.assertIn('timeExpires{ time:r=5.05;', mission)
                self.assertNotIn('timeExpires{ time:r=0.05;', mission)
            else:
                self.assertIn('setStatus:t="enable"', mission)
            locale = files['UserMissions/usr_wt_missile_lab.csv']
            for remaining in range(1, 6):
                self.assertIn(f'RADAR SETUP: {remaining} s', locale)

    def test_prescribed_displacement_regression_1500_kmh(self):
        self.c['launcher'].update(x_m=0, z_m=0, heading_deg=0, speed_kmh=1500)
        self.c['target'].update(x_m=30000, z_m=0, heading_deg=180, speed_kmh=1500)
        self.c.update(setup_delay_s=5, motion_duration_s=20, correction_interval_s=.05)
        _, files = generate(self.c)
        mission = files['UserMissions/wt_missile_lab.blk']
        # Independent inspection of the emitted mission: at mission time 25,
        # both aircraft have flown 20 s. No self-referential movement targets.
        block = mission.split('  motion_sample_400{', 1)[1].split('  release_all_missiles{', 1)[0]
        self.assertIn('timeExpires{ time:r=25;', block)
        self.assertIn('target:t="launcher_motion_400"', block)
        self.assertIn('target:t="target_motion_400"', block)
        positions = {}
        for name in ('launcher', 'target'):
            point = mission.split(f'  {name}_motion_400{{', 1)[1].split('objLayer', 1)[0]
            coords = re.findall(r'\[([^\[\]]+)\]', point)[-1]
            positions[name] = tuple(float(v) for v in coords.split(','))
        self.assertAlmostEqual(positions['launcher'][0], 8333.333333, places=4)
        self.assertAlmostEqual(positions['target'][0], 21666.666667, places=4)
        self.assertAlmostEqual(positions['target'][0] - positions['launcher'][0], 13333.333334, places=4)
        self.assertNotIn('target:t="launcher"', mission)
        self.assertNotIn('target:t="target"', mission)
        self.assertIn('name:t="wt_missile_lab_motion_end"', block)
        self.assertIn('setStatus:t="enable"', block)

    def test_trajectory_geometry_and_interval_independence(self):
        state = dict(x_m=-1234, z_m=987, altitude_m=6500, heading_deg=37, speed_kmh=1500)
        original = dict(state)
        result = position_at(state, 20)
        self.assertAlmostEqual(math.hypot(result['x_m'] - state['x_m'], result['z_m'] - state['z_m']), 8333.333333333)
        self.assertEqual(result['altitude_m'], 6500)
        self.assertEqual(state, original)
        self.assertEqual(position_at(dict(state, speed_kmh=0), 20)['x_m'], state['x_m'])
        for interval in (.02, .05, .3, 1):
            self.c.update(correction_interval_s=interval, motion_duration_s=20)
            times = list(motion_times(self.c))
            self.assertEqual(times[-1], 20)
            self.assertTrue(all(a < b for a, b in zip(times, times[1:])))
            self.assertEqual(len(times), math.ceil(20 / interval))
            self.assertEqual(position_at(state, times[-1]), result)

    def test_legacy_scenario_gets_bounded_motion_duration(self):
        self.c.pop('motion_duration_s')
        self.c['correction_interval_s'] = 1
        validated, _ = generate(self.c)
        self.assertEqual(validated['motion_duration_s'], 120)

    def test_release_all_is_one_command_on_separate_shortcut(self):
        self.c.update(release_mode='salvo', missiles=['cn_pl12a', 'us_aim_120a', 'su_r_77_1',
            'cn_pl12', 'jp_aam4', 'us_aim_120d', 'su_r_77', 'fr_mica_em'])
        for delay in (0, 5):
            self.c['setup_delay_s'] = delay
            _, files = generate(self.c)
            mission = files['UserMissions/wt_missile_lab.blk']
            self.assertEqual(mission.count('unitDropAmmo{'), 1)
            release = mission.split('  release_all_missiles{', 1)[1].split('mission_objectives', 1)[0]
            self.assertIn('enableAfterComplete:b=no', release)
            self.assertIn('control:t="ID_ROCKETS_SERIES"', release)
            self.assertIn('object:t="launcher"', release)
            self.assertNotIn('playerEmulateShortcut', release)
            self.assertIn('is_enabled:b=' + ('no' if delay else 'yes'), release)
            self.assertEqual('triggerEnable{ target:t="release_all_missiles";' in mission, bool(delay))
            preset = files['content/pkg_local/gameData/flightModels/weaponPresets/wt_missile_lab_loadout.blk']
            self.assertEqual(preset.count('Weapon{'), 8)
            self.assertEqual(preset.count('bullets:i=1'), 8)
            self.assertIn('FIRE ROCKET SALVO', files['UserMissions/usr_wt_missile_lab.csv'])
        for mode in ('grouped', 'individual'):
            self.c['release_mode'] = mode
            _, files = generate(self.c)
            self.assertNotIn('unitDropAmmo', files['UserMissions/wt_missile_lab.blk'])


if __name__ == '__main__':
    unittest.main()
