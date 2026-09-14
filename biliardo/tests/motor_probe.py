"""Read-only live spike replay into a separate copy of the saved cue body.

No game commands, reward injections or writes to the user's memory. This
measures motor responsiveness, not learned billiards ability.
"""
import io
import json
from pathlib import Path
import time
import urllib.request
import zipfile

import numpy as np

from biliardo.body import NeuralBody
from flyblox.brain.connectome import Connectome


def read(path):
    with urllib.request.urlopen('http://127.0.0.1:8766'+path, timeout=10) as response:
        return response.read()


def main():
    with zipfile.ZipFile(io.BytesIO(read('/api/saves/latest.save'))) as archive:
        saved = json.loads(archive.read('state.json'))
    body = NeuralBody(Connectome())
    body.restore(saved['body'])
    body.pending = None  # New hypothetical turn in this disposable copy only.
    samples, live_shots, actions = [], [], []
    previous_sim = None
    started = previous = time.perf_counter()
    while time.perf_counter()-started < 12:
        state = json.loads(read('/api/state'))
        brain = state.get('brain')
        if not brain or brain['sim_ms'] == previous_sim or state['paused']:
            time.sleep(.05)
            continue
        counts = np.frombuffer(read('/api/activity'), dtype='<u2')
        if len(counts) != brain['neurons']:
            raise ValueError('Activity length differs from the installed graph')
        now = time.perf_counter()
        elapsed = now-previous if previous_sim is not None else brain['cycle_wall_ms']/1000
        previous, previous_sim = now, brain['sim_ms']
        neural_seconds = brain['neural_step_ms']/1000
        features = body.observe(counts, neural_seconds)
        action = body.tick(features, counts, neural_seconds, elapsed)
        samples.append({'step_ms': brain['step_wall_ms'], 'cycle_ms': brain['cycle_wall_ms'],
                        'cpu_ms': brain['step_thread_cpu_ms'], 'motor_spikes': sum(int(counts[ix].sum()) for ix in body.groups[32:40])})
        if action:
            actions.append({'aim_seconds': body.aim_seconds, 'release_spikes': body.release_spikes,
                            'angle': action[0], 'power': action[1]})
        live_shots.append({'at': round(now-started, 3), 'game': state['game']['game_number'],
                           'shot': state['game']['shot_id'], 'phase': state['game']['phase'],
                           'turn': state['game']['turn'], 'aim_seconds': brain['body']['aim_seconds']})
        time.sleep(.05)
    assert len(actions) == 1, 'The disposable motor body did not release exactly once'
    report = {'read_only': True, 'purpose': 'Motor latency only, not learned skill',
              'saved_fly_shots': saved['game']['fly_shots'], 'model_hash': brain['model_hash'],
              'replay_actions': actions, 'samples': samples, 'live_trace': live_shots,
              'step_median_ms': float(np.median([s['step_ms'] for s in samples])),
              'step_p95_ms': float(np.percentile([s['step_ms'] for s in samples], 95)),
              'client_metrics': state['client_metrics']}
    path = Path(__file__).resolve().parents[1]/'logs/motor-latency-validation.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ['samples', 'live_trace']}, indent=2))


if __name__ == '__main__':
    main()
