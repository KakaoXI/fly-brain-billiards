"""Read-only check of live physics stream cadence; never plays a shot."""
from pathlib import Path
import json
import time
import urllib.request
import numpy as np

BASE = 'http://127.0.0.1:8766'
with urllib.request.urlopen(BASE+'/api/bootstrap', timeout=10) as r:
    bootstrap = json.load(r)
packets, frames = [], []
start = time.perf_counter()
with urllib.request.urlopen(BASE+'/api/stream?token='+bootstrap['token'], timeout=20) as response:
    for line in response:
        if line.startswith(b'data:'):
            now = time.perf_counter()
            packets.append(now)
            frames.extend(json.loads(line[5:])['frames'])
            if now-start >= 8:
                break
intervals = np.diff(packets)*1000
moving_intervals = [b['t']-a['t'] for a, b in zip(frames, frames[1:]) if a['phase']==b['phase']=='moving' and a['shot']==b['shot']]
report = {'build': bootstrap['state'].get('build'), 'seconds': time.perf_counter()-start,
          'packets': len(packets), 'frames': len(frames), 'packet_p50_ms': float(np.percentile(intervals, 50)),
          'packet_p95_ms': float(np.percentile(intervals, 95)),
          'moving_step_p95_ms': float(np.percentile(moving_intervals, 95)) if moving_intervals else None,
          'game_modified': False}
assert len(packets)>200 and report['packet_p95_ms'] < 70
report['passed'] = True
out = Path(__file__).resolve().parents[1]/'logs/stream-validation.json'
out.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
