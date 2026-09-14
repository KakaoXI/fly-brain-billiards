from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile
import numpy as np

from biliardo.body import NeuralBody
from biliardo.game import Game
from biliardo.storage import save_archive, load_archive
from biliardo.vision import render_eye


class TinyGraph:
    hash = 'test-graph'
    retina = np.arange(32)
    uv = np.array([[(x+.5)/8, (y+.5)/4] for y in range(4) for x in range(8)])
    circuit = {'kc': np.array([40]), 'reward': np.array([41]), 'aversive': np.array([42])}

    def population(self, types, side=None):
        return np.array([32+(['DNa02', 'DNg13', 'DNpe017', 'DNp20', 'DNp09', 'MDN'].index(types[0]))])


class StubBrain:
    def __init__(self):
        self.graph = TinyGraph()
        self.model_hash = 'test-model'
        self.loaded = False

    def save(self, path, extra):
        Path(path).write_bytes(b'test neural state')

    def load(self, path):
        assert Path(path).read_bytes() == b'test neural state'
        self.loaded = True


class BodyTests(unittest.TestCase):
    def setUp(self):
        self.body = NeuralBody(TinyGraph())
        self.counts = np.ones(43, dtype=int)*4
        self.features = self.body.observe(self.counts, .04)

    def test_quiet_descending_neurons_cannot_shoot(self):
        for _ in range(100):
            self.assertIsNone(self.body.tick(self.features, np.zeros(43), .04, .1))
        self.assertEqual(self.body.release_spikes, 0)

    def test_spikes_actuate_body_and_trigger_one_shot(self):
        outputs = [self.body.tick(self.features, self.counts, .04, .1) for _ in range(100)]
        shots = [v for v in outputs if v is not None]
        self.assertEqual(len(shots), 1)
        self.assertTrue(.08 <= shots[0][1] <= 1.)
        self.assertGreater(self.body.release_spikes, 0)

    def test_slow_neural_windows_do_not_stretch_ready_shot_timer(self):
        self.body.begin(self.features)
        self.body.angle = 0.
        self.body.target_angle = 3.
        self.body.power, self.body.target_power = .1, .9
        actions = []
        for _ in range(4):
            action = self.body.tick(self.features, self.counts, .04, .6)
            if action:
                actions.append(action)
        self.assertEqual(len(actions), 1)
        self.assertLessEqual(self.body.aim_seconds, 2.4)
        self.assertAlmostEqual(actions[0][0], 3.)
        self.assertAlmostEqual(actions[0][1], .9)

    def test_settled_cue_releases_without_arbitrary_minimum_wait(self):
        self.body.begin(self.features)
        self.body.angle, self.body.power = self.body.target_angle, self.body.target_power
        actions = [self.body.tick(self.features, self.counts, .04, .1) for _ in range(3)]
        self.assertIsNotNone(actions[-1])
        self.assertLess(self.body.aim_seconds, .4)

    def test_previous_spikes_cannot_release_during_silence(self):
        self.body.begin(self.features)
        self.body.angle, self.body.power = self.body.target_angle, self.body.target_power
        self.body.release_spikes = 100
        pose = (self.body.angle, self.body.power)
        self.assertIsNone(self.body.tick(self.features, np.zeros(43), .04, 8.))
        self.assertFalse(self.body.pending['fired'])
        self.assertEqual(pose, (self.body.angle, self.body.power))
        self.assertIsNotNone(self.body.tick(self.features, self.counts, .04, .1))

    def test_reward_updates_neural_readout(self):
        for _ in range(100):
            self.body.tick(self.features, self.counts, .04, .1)
        before = self.body.weights.copy()
        self.body.outcome(10)
        self.assertFalse(np.array_equal(before, self.body.weights))
        self.assertEqual(self.body.updates, 1)

    def test_evaluation_freezes_readout(self):
        self.body.learning = False
        for _ in range(100):
            self.body.tick(self.features, self.counts, .04, .1)
        before = self.body.weights.copy()
        self.body.outcome(10)
        np.testing.assert_array_equal(before, self.body.weights)
        self.assertEqual(self.body.updates, 0)

    def test_rng_and_motor_roundtrip(self):
        self.body.begin(self.features)
        saved = self.body.state()
        other = NeuralBody(TinyGraph())
        other.restore(saved)
        np.testing.assert_array_equal(self.body.rng.normal(size=12), other.rng.normal(size=12))
        self.assertEqual(self.body.pending, other.pending)

    def test_retinal_frame_does_not_include_reward_or_hud(self):
        game = Game()
        original = render_eye(game.state())
        game.reward_total = 99999
        game.message = 'SECRET REWARD'
        game.history = [{'reward': 100}]
        np.testing.assert_array_equal(original, render_eye(game.state()))
        game.balls[9].x += 100
        self.assertFalse(np.array_equal(original, render_eye(game.state())))

    def test_save_roundtrip_and_corruption_rejected_before_brain_load(self):
        brain = StubBrain()
        retina = SimpleNamespace(previous=np.ones((90, 160), np.float32))
        game = Game()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'latest.save'
            save_archive(path, brain, game, self.body, retina, {'test': True})
            restored, body, previous, extra = load_archive(path, brain, brain.graph)
            self.assertTrue(brain.loaded)
            self.assertEqual(restored.state(), game.state())
            np.testing.assert_array_equal(self.body.weights, body.weights)
            np.testing.assert_array_equal(previous, retina.previous)
            self.assertTrue(extra['test'])
            save_archive(path, brain, game, self.body, retina, {'test': True})
            self.assertTrue(path.with_name('previous.save').exists())
            with zipfile.ZipFile(path) as z:
                payload = {name: z.read(name) for name in z.namelist()}
            payload['state.json'] += b' '
            bad = Path(directory)/'bad.save'
            with zipfile.ZipFile(bad, 'w') as z:
                for name, data in payload.items():
                    z.writestr(name, data)
            brain.loaded = False
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_archive(bad, brain, brain.graph)
            self.assertFalse(brain.loaded)


if __name__ == '__main__':
    unittest.main()
