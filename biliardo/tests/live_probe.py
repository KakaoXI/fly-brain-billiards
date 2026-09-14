"""Bounded HTTP check of the actual GPU-driven application, then restore memory.

Run only on a fresh table. Writes evidence; never claims a learned playing skill.
"""
from pathlib import Path
import json
import time
import urllib.request

BASE = 'http://127.0.0.1:8766'
OUT = Path(__file__).resolve().parents[1]/'logs/live-probe.json'


def get(path):
    with urllib.request.urlopen(BASE+path, timeout=15) as response:
        return json.load(response)


boot = get('/api/bootstrap')
token = boot['token']


def command(name, **args):
    req = urllib.request.Request(BASE+'/api/command', data=json.dumps({'name': name, **args}).encode(),
                                 headers={'Content-Type': 'application/json', 'X-Biliardo-Token': token})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def wait_for(predicate, timeout=50):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        state = get('/api/state')
        if state['phase'] == 'error':
            raise RuntimeError(state['error'])
        if predicate(state):
            return state
        time.sleep(.2)
    raise TimeoutError('Live test did not complete within its deadline')


initial = boot['state']
if initial['game']['shot_id'] != 0 or initial['game']['turn'] != 'human':
    raise SystemExit('Table already in use; leaving the user’s game untouched.')
report = {'started': time.time(), 'graph': initial['brain']['hash'], 'neurons': initial['brain']['neurons'],
          'edges': initial['brain']['edges'], 'before_neural_ms': initial['brain']['sim_ms']}
command('pause', enabled=True)
command('save')
saved = wait_for(lambda s: s.get('command', {}).get('file'))
baseline = saved['command']['file']
report['baseline'] = baseline
try:
    command('pause', enabled=False)
    command('shoot', angle=0., power=.85)
    after_break = wait_for(lambda s: s['game']['phase'] != 'moving')
    report['break'] = after_break['game']['last_result']
    if after_break['game']['turn'] == 'human' and not after_break['game']['winner']:
        command('shoot', angle=1.57079632679, power=.1)
    samples = []
    def finished(s):
        b = s['brain']
        samples.append({'turn': s['game']['turn'], 'phase': s['game']['phase'], 'shot': s['game']['shot_id'],
                        'angle': b['body']['angle'], 'power': b['body']['power'], 'motor_spikes': b['body']['release_spikes'],
                        'active': b['stats'].get('active'), 'sim_ms': b['sim_ms']})
        return s['game']['fly_shots'] > initial['game']['fly_shots']
    done = wait_for(finished)
    command('pause', enabled=True)
    report['samples'] = samples
    report['fly_result'] = done['game']['last_result']
    report['body_updates'] = done['brain']['body']['updates']
    report['after_neural_ms'] = done['brain']['sim_ms']
    report['actual_motor_spikes'] = max(s['motor_spikes'] for s in samples)
    report['cue_body_moved'] = max(s['angle'] for s in samples)-min(s['angle'] for s in samples) > .02
    report['autonomous_shot_completed'] = done['game']['last_result']['actor'] == 'fly'
    assert report['autonomous_shot_completed'] and report['actual_motor_spikes'] > 0
    report['passed'] = True
finally:
    command('pause', enabled=True)
    command('load', file=baseline)
    restored = wait_for(lambda s: s.get('command', {}).get('message') == 'Memoria caricata. Premi Riprendi.')
    report['restored_initial_table'] = restored['game']['shot_id'] == 0
    report['restored_neural_ms'] = restored['brain']['sim_ms']
    report['baseline_neural_ms'] = saved['brain']['sim_ms']
    assert restored['brain']['sim_ms'] == saved['brain']['sim_ms']
    OUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    command('pause', enabled=False)
print(json.dumps({k: report.get(k) for k in ['passed', 'neurons', 'edges', 'autonomous_shot_completed', 'actual_motor_spikes', 'cue_body_moved', 'restored_initial_table']}, indent=2))
