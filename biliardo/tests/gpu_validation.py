"""Validate full-graph rewards and memory in a separate, disposable GPU instance.

Does not touch the live game's state, learning or checkpoints.
"""
from pathlib import Path
import json
import tempfile
import urllib.request
import numpy as np

from flyblox.config import load_config
from flyblox.brain.connectome import Connectome
from flyblox.brain.runtime import Brain
from flyblox.vision.retina import Retina
from biliardo.body import NeuralBody
from biliardo.game import Game
from biliardo.storage import save_archive, load_archive
from biliardo.vision import render_eye
import biliardo.server as server_module

BASE = Path(__file__).resolve().parents[1]


def result_for(kind):
    g = Game()
    g.turn = 'fly'
    g.shoot('fly', .3, .5)
    g.current_shot.update(first_contact=9, rail=True)
    if kind == 'high':
        g.current_shot['pots'] = [9]
        g.balls[9].pocketed = True
    elif kind == 'medium':
        g.balls[9].x, g.balls[9].y = 500, 48
    elif kind == 'opponent':
        g.current_shot['pots'] = [1]
        g.balls[1].pocketed = True
    return g, g.finish_shot()


graph = Connectome()
brain = Brain(graph, load_config())
report = {'neurons': graph.n, 'edges': len(graph.post), 'graph': graph.hash, 'model_hash': brain.model_hash}
with tempfile.TemporaryDirectory(prefix='gpu-qa-', dir=BASE/'logs') as temporary:
    directory = Path(temporary).resolve()
    assert directory.is_relative_to((BASE/'logs').resolve())
    source = directory/'source.save'
    # Use the application's normal download API; its atomic saves can inherit
    # the service account's Windows ACL when moved from a private temp directory.
    with urllib.request.urlopen('http://127.0.0.1:8766/api/saves/latest.save', timeout=15) as response:
        source.write_bytes(response.read())
    game, body, previous, extra = load_archive(source, brain, graph)
    retina = Retina(graph, [160, 90])
    retina.previous = previous
    report['live_memory_loaded'] = True
    obs = retina.transform(render_eye(game.state(), body.angle))
    brain.clear_reward()
    counts, _ = brain.step(obs['light'], obs['color'], 80, learning=False)
    report['baseline_pam_hz'] = float(counts[graph.circuit['reward']].mean()/.08)
    engine = server_module.Engine()
    engine.graph, engine.brain, engine.body, engine.retina = graph, brain, body, retina
    server_module.BASE = directory
    (directory/'logs').mkdir()
    engine.body.pending = None
    engine.body.learning = True
    features = body.observe(counts, .08)
    body.begin(features)
    body.pending['fired'] = True
    readout_before = body.weights.copy()
    memory_before = brain.memory.w.copy()
    engine.game, result = result_for('high')
    engine.on_result(result)
    report['high_reward'] = result['reward']
    report['high_pulse_ms'] = brain.pulses['reward']-brain.sim_ms
    assert report['high_pulse_ms'] == 2000
    counts, _ = brain.step(obs['light'], obs['color'], 100, learning=True)
    report['reward_pam_hz'] = float(counts[graph.circuit['reward']].mean()/.1)
    report['active_neurons'] = int(np.count_nonzero(counts))
    report['native_plasticity_changed'] = bool(np.any(brain.memory.w != memory_before))
    report['readout_changed'] = bool(np.any(body.weights != readout_before))
    assert report['active_neurons'] > 0 and report['readout_changed'] and report['native_plasticity_changed']
    assert report['reward_pam_hz'] > report['baseline_pam_hz']
    brain.clear_reward()
    engine.game, result = result_for('medium')
    engine.on_result(result)
    report['medium_reward'] = result['reward']
    report['medium_pulse_ms'] = brain.pulses['reward']-brain.sim_ms
    assert report['medium_pulse_ms'] == 350
    brain.clear_reward()
    engine.game, result = result_for('contact')
    engine.on_result(result)
    report['contact_reward'] = result['reward']
    report['contact_pulse_ms'] = brain.pulses['reward']-brain.sim_ms
    assert report['contact_reward'] == .5 and report['contact_pulse_ms'] == 120
    brain.clear_reward()
    engine.game, result = result_for('opponent')
    engine.on_result(result)
    report['opponent_reward'] = result['reward']
    report['opponent_pulse_ms'] = max(0, brain.pulses['reward']-brain.sim_ms)
    assert report['opponent_reward'] == report['opponent_pulse_ms'] == 0
    frozen = brain.memory.w.copy()
    brain.step(obs['light'], obs['color'], 40, learning=False)
    np.testing.assert_array_equal(frozen, brain.memory.w)
    report['evaluation_freezes_native_weights'] = True
    saved_v, saved_w, saved_body = brain.v.get(), brain.memory.w.copy(), body.state()
    saved_tick, saved_game = brain.tick, game.state()
    path = directory/'roundtrip.save'
    save_archive(path, brain, game, body, retina, {'validation_only': True})
    brain.reset_state()
    brain.reset_learning()
    restored_game, restored_body, restored_retina, restored_extra = load_archive(path, brain, graph)
    np.testing.assert_array_equal(brain.v.get(), saved_v)
    np.testing.assert_array_equal(brain.memory.w, saved_w)
    np.testing.assert_array_equal(restored_retina, retina.previous)
    assert restored_body.state() == saved_body
    assert restored_game.state() == saved_game and brain.tick == saved_tick
    assert restored_extra['validation_only']
    report['full_save_roundtrip_exact'] = True
    report['user_game_modified'] = False
    report['passed'] = True
(BASE/'logs/gpu-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
