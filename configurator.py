"""Desktop editor for the launcher/target mission."""
import copy
import json
import math
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from missile_lab import ROOT, build, direction, load_config, validate


class Configurator(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=20)
        self.pack(fill='both', expand=True)
        self.config = load_config()
        self.fields = {}
        self.status = tk.StringVar(value='Ready. Runtime behavior has not yet been verified in War Thunder.')
        master.title('War Thunder · Missile Lab')
        master.minsize(850, 700)
        style = ttk.Style(master)
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
        style.configure('Subtitle.TLabel', foreground='#555555')
        ttk.Label(self, text='Missile Lab', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self, text='Set the encounter, choose the missiles, then build the local user mission.', style='Subtitle.TLabel').pack(anchor='w', pady=(3, 14))

        install = ttk.Frame(self)
        install.pack(fill='x', pady=(0, 14))
        ttk.Label(install, text='War Thunder folder').pack(side='left', padx=(0, 10))
        self.game_root = tk.StringVar(value=self.config['game_root'])
        ttk.Entry(install, textvariable=self.game_root).pack(side='left', fill='x', expand=True)
        ttk.Button(install, text='Browse', command=self.browse).pack(side='left', padx=(8, 0))

        book = ttk.Notebook(self)
        book.pack(fill='both', expand=True)
        encounter = ttk.Frame(book, padding=16)
        weapons = ttk.Frame(book, padding=16)
        settings = ttk.Frame(book, padding=16)
        book.add(encounter, text='  Launcher & target  ')
        book.add(weapons, text='  Missiles  ')
        book.add(settings, text='  Motion & setup  ')
        encounter.columnconfigure((0, 1), weight=1)
        labels = [('x_m', 'X position (m)'), ('z_m', 'Z position (m)'), ('altitude_m', 'Altitude (m ASL)'), ('speed_kmh', 'Speed (km/h TAS)'), ('heading_deg', 'Heading (degrees)')]
        for column, name in enumerate(('launcher', 'target')):
            frame = ttk.LabelFrame(encounter, text=name.title(), padding=14)
            frame.grid(row=0, column=column, sticky='nsew', padx=(0, 8) if column == 0 else (8, 0))
            frame.columnconfigure(1, weight=1)
            for row, (field, label) in enumerate(labels):
                value = tk.StringVar(value=str(self.config[name][field]))
                self.fields[name, field] = value
                ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=9, padx=(0, 16))
                ttk.Entry(frame, textvariable=value, width=14).grid(row=row, column=1, sticky='ew')
            if name == 'target':
                self.aircraft = tk.StringVar(value=self.config[name]['aircraft'])
                ttk.Label(frame, text='Aircraft internal ID').grid(row=5, column=0, sticky='w', pady=9)
                ttk.Entry(frame, textvariable=self.aircraft, width=22).grid(row=5, column=1, sticky='ew')
            else:
                ttk.Label(frame, text='Custom launcher using the CDK sample body.\nFlight dynamics are selectable in Motion & setup.', wraplength=310, style='Subtitle.TLabel').grid(row=5, column=0, columnspan=2, sticky='w', pady=12)
        ttk.Label(encounter, text='Heading convention: 0° = +X, 90° = +Z, 180° = −X, 270° = −Z.\nBoth aircraft start level. Coordinates are in the CDK world, not latitude/longitude.', style='Subtitle.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=18)
        ttk.Button(encounter, text='Calculate initial separation', command=self.separation).grid(row=2, column=0, sticky='w')
        self.geometry = tk.StringVar()
        ttk.Label(encounter, textvariable=self.geometry).grid(row=3, column=0, columnspan=2, sticky='w', pady=12)

        ttk.Label(weapons, text='One missile per station. Repeat an ID to carry multiple missiles of that type.').pack(anchor='w')
        ttk.Label(weapons, text='Select an ID or type any installed AAM rocketGun filename without .blk.', style='Subtitle.TLabel').pack(anchor='w', pady=(4, 12))
        catalog_path = ROOT / 'missiles.json'
        catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else self.config['missiles']
        self.missile_vars = []
        grid = ttk.Frame(weapons)
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        for i in range(8):
            value = tk.StringVar(value=self.config['missiles'][i] if i < len(self.config['missiles']) else '')
            self.missile_vars.append(value)
            ttk.Label(grid, text=f'Station {i + 1}').grid(row=i, column=0, sticky='w', padx=(0, 20), pady=6)
            ttk.Combobox(grid, textvariable=value, values=[''] + catalog, width=45).grid(row=i, column=1, sticky='ew')
        self.release = tk.StringVar(value=self.config['release_mode'])
        modes = ttk.Frame(weapons)
        modes.pack(fill='x', pady=(16, 6))
        ttk.Radiobutton(modes, text='Release all (experimental)', variable=self.release, value='salvo').pack(side='left', padx=(0, 14))
        ttk.Radiobutton(modes, text='Legacy grouped (pair observed)', variable=self.release, value='grouped').pack(side='left', padx=(0, 14))
        ttk.Radiobutton(modes, text='Individual release', variable=self.release, value='individual').pack(side='left')
        ttk.Label(weapons, text='Release all: after radar setup, lock the target and activate the AAM seeker, then press Fire rocket salvo. This sends one CDK release-all command and consumes the loadout. Missile count, guidance and same-frame release need in-game verification. Restart the mission to retry.', wraplength=700, style='Subtitle.TLabel').pack(anchor='w', pady=8)

        self.fixed = tk.BooleanVar(value=self.config['fixed_motion'])
        self.immortal = tk.BooleanVar(value=self.config['immortal_target'])
        self.warmup = tk.BooleanVar(value=self.config['zero_warmup'])
        self.ignore_projectiles = tk.BooleanVar(value=self.config.get('ignore_projectile_fuses', True))
        self.isolate_damage = tk.BooleanVar(value=self.config.get('isolate_missile_damage', True))
        self.radar = tk.StringVar(value=self.config.get('radar', 'j16_tws_150'))
        self.interval = tk.StringVar(value=str(self.config['correction_interval_s']))
        self.setup_delay = tk.StringVar(value=str(self.config.get('setup_delay_s', 5)))
        self.fm = tk.StringVar(value=self.config['flight_model'])
        ttk.Checkbutton(settings, text='Hold both aircraft at the configured speed, altitude and heading', variable=self.fixed).pack(anchor='w', pady=6)
        ttk.Label(settings, text='Uses periodic velocity/orientation corrections; flight controls are disabled.\nCamera, radar and weapon controls stay available. This is an experimental correction loop, not a verified exact physics lock.', wraplength=710, style='Subtitle.TLabel').pack(anchor='w', padx=22, pady=(0, 12))
        row = ttk.Frame(settings)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='Correction interval (seconds)').pack(side='left')
        ttk.Entry(row, textvariable=self.interval, width=12).pack(side='left', padx=16)
        row = ttk.Frame(settings)
        row.pack(fill='x', pady=8)
        ttk.Label(row, text='Radar setup hold (seconds, 0 disables)').pack(side='left')
        ttk.Entry(row, textvariable=self.setup_delay, width=12).pack(side='left', padx=16)
        ttk.Checkbutton(settings, text='Make target invulnerable for side-by-side missile tests', variable=self.immortal).pack(anchor='w', pady=8)
        ttk.Checkbutton(settings, text='Ignore projectiles in missile proximity fuses', variable=self.ignore_projectiles).pack(anchor='w', pady=8)
        ttk.Label(settings, text='Prevents proximity detection of nearby missiles/shells. Aircraft fuse detection remains enabled.', wraplength=710, style='Subtitle.TLabel').pack(anchor='w', padx=22)
        ttk.Checkbutton(settings, text='Isolate missiles from projectile collisions and damage reactions (testing)', variable=self.isolate_damage).pack(anchor='w', pady=8)
        ttk.Label(settings, text='Disables shell collision and missile hit/kill effects. Keeps aircraft proximity fuses. Needs in-game retest.', wraplength=710, style='Subtitle.TLabel').pack(anchor='w', padx=22)
        ttk.Checkbutton(settings, text='Set missile warm-up time to zero (changes launch preparation)', variable=self.warmup).pack(anchor='w', pady=8)
        row = ttk.Frame(settings)
        row.pack(fill='x', pady=12)
        ttk.Label(row, text='Launcher flight-model ID').pack(side='left')
        ttk.Entry(row, textvariable=self.fm, width=30).pack(side='left', padx=16)
        row = ttk.Frame(settings)
        row.pack(fill='x', pady=6)
        ttk.Label(row, text='Launcher radar preset').pack(side='left')
        ttk.Combobox(row, textvariable=self.radar, values=['j16_tws_150', 'apg68'], state='readonly', width=26).pack(side='left', padx=16)
        ttk.Label(settings, text='Default: J-16 dynamics and KLJ-16 radar, TWS / 150 km / 30° × 15°.\nRadar is selected separately from dynamics. The visible body remains the CDK I-185.\nMissile propulsion and guidance use stock definitions.', wraplength=710, style='Subtitle.TLabel').pack(anchor='w', pady=8)
        ttk.Label(settings, text='The current mission uses the ocean map. Terrain/void work is deferred.\nRestart War Thunder after installation if it has already cached custom units.', style='Subtitle.TLabel').pack(anchor='w', pady=12)

        buttons = ttk.Frame(self)
        buttons.pack(fill='x', pady=(16, 10))
        ttk.Button(buttons, text='Save scenario', command=self.save).pack(side='left')
        ttk.Button(buttons, text='Open build folder', command=lambda: os.startfile(ROOT / 'build')).pack(side='left', padx=10)
        ttk.Button(buttons, text='Build & install mission', command=self.install).pack(side='right')
        ttk.Label(self, textvariable=self.status, wraplength=790).pack(anchor='w')
        self.separation()

    def browse(self):
        path = filedialog.askdirectory(initialdir=self.game_root.get(), title='Select the War Thunder game folder')
        if path:
            self.game_root.set(path)

    def values(self):
        c = copy.deepcopy(self.config)
        c['game_root'] = self.game_root.get()
        for (name, field), value in self.fields.items():
            c[name][field] = float(value.get())
        c['target']['aircraft'] = self.aircraft.get().strip()
        c['flight_model'] = self.fm.get().strip()
        c['setup_delay_s'] = int(self.setup_delay.get())
        c['missiles'] = [v.get().strip() for v in self.missile_vars if v.get().strip()]
        c.update(release_mode=self.release.get(), fixed_motion=self.fixed.get(), immortal_target=self.immortal.get(), zero_warmup=self.warmup.get(), ignore_projectile_fuses=self.ignore_projectiles.get(), isolate_missile_damage=self.isolate_damage.get(), radar=self.radar.get(), correction_interval_s=float(self.interval.get()))
        return validate(c)

    def separation(self):
        try:
            states = [{k: float(self.fields[name, k].get()) for k in ('x_m', 'z_m', 'altitude_m', 'speed_kmh', 'heading_deg')} for name in ('launcher', 'target')]
            a, b = states
            distance = math.sqrt(sum((a[k] - b[k]) ** 2 for k in ('x_m', 'z_m', 'altitude_m')))
            self.geometry.set(f'Initial separation: {distance / 1000:.3f} km   ·   Altitude difference: {b["altitude_m"] - a["altitude_m"]:+.0f} m')
        except ValueError:
            self.geometry.set('Enter numeric positions to calculate separation.')

    def persist(self, c):
        (ROOT / 'scenario.json').write_text(json.dumps(c, indent=2) + '\n', encoding='utf-8')
        self.config = c

    def save(self):
        try:
            self.persist(self.values())
            self.status.set('Scenario saved. Build & install to apply it to the mission.')
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Check configuration', str(exc))

    def install(self):
        try:
            c = self.values()
            out, files = build(c, install=True)
            self.persist(c)
            self.status.set(f'Installed {len(files)} files. Launch User Missions → Missile Lab - Launcher and Target. In-game validation is still required.')
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Build failed', str(exc))


if __name__ == '__main__':
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    window = tk.Tk()
    Configurator(window)
    window.mainloop()
