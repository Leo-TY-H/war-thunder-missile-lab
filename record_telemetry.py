"""Read local game telemetry to check launcher TAS/altitude stability."""
import argparse
import datetime as dt
import json
import time
import urllib.request
from missile_lab import ROOT


def record(seconds=20):
    folder = ROOT / 'telemetry'
    folder.mkdir(exist_ok=True)
    path = folder / (dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.jsonl')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    start = time.monotonic()
    samples = []
    with path.open('w', encoding='utf-8') as stream:
        while time.monotonic() - start < seconds:
            row = {'elapsed_s': time.monotonic() - start}
            for endpoint in ('state', 'indicators', 'map_obj.json'):
                try:
                    row[endpoint] = json.load(opener.open('http://127.0.0.1:8111/' + endpoint, timeout=0.5))
                except Exception as exc:
                    row[endpoint] = {'error': str(exc)}
            stream.write(json.dumps(row) + '\n')
            if row['state'].get('valid'):
                samples.append(row['state'])
            time.sleep(0.1)
    print(path)
    if not samples:
        print('No valid flight telemetry. Start the mission first; the game must expose its local telemetry server.')
        return
    for key in ('TAS, km/h', 'H, m'):
        values = [s[key] for s in samples if key in s]
        if values:
            print(f'{key}: min={min(values):.3f}, max={max(values):.3f}, spread={max(values)-min(values):.3f}')
    print('Launcher telemetry only; missile release timestamps are not measured. Raw map data is included.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=20)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error('--seconds must be between 0 and 3600')
    record(args.seconds)
