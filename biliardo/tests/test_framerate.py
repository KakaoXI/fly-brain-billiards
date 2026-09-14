from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
import json
import zipfile
from unittest.mock import patch
import numpy as np

import biliardo.server as server_module
from biliardo.body import NeuralBody
from biliardo.tests.test_body_storage import TinyGraph, StubBrain


class SlowSavingBrain(StubBrain):
    def save(self, path, extra):
        time.sleep(.22)
        super().save(path, extra)


class FramerateTests(unittest.TestCase):
    def motor_engine(self):
        engine = server_module.Engine()
        engine.game.turn = 'fly'
        durations = []
        engine.body = SimpleNamespace(learning=True, tick=lambda f, c, n, dt: durations.append(dt))
        return engine, durations

    def test_motor_clock_includes_whole_active_update_interval(self):
        engine, durations = self.motor_engine()
        context = engine.motor_context()
        engine.actuate_body(None, None, context, 10., 10.6)
        engine.actuate_body(None, None, context, 10.8, 11.3)
        np.testing.assert_allclose(durations, [.6, .7])

    def test_pause_resume_discards_in_flight_motor_observation(self):
        engine, durations = self.motor_engine()
        context = engine.motor_context()
        engine.actuate_body(None, None, context, 10., 10.2)
        engine.paused = True
        engine.reset_motor_clock()
        engine.actuate_body(None, None, engine.motor_context(), 10.2, 50.)
        engine.paused = False
        engine.reset_motor_clock()
        engine.actuate_body(None, None, context, 10.2, 50.2)
        engine.actuate_body(None, None, engine.motor_context(), 50.3, 50.5)
        np.testing.assert_allclose(durations, [.2, .2])

    def test_motor_clock_excludes_disk_work_and_another_turn(self):
        engine, durations = self.motor_engine()
        engine.actuate_body(None, None, engine.motor_context(), 10., 10.2)
        engine.reset_motor_clock()  # Save takes 20 seconds.
        engine.actuate_body(None, None, engine.motor_context(), 30.2, 30.4)
        engine.game.turn = 'human'
        human_context = engine.motor_context()
        engine.actuate_body(None, None, human_context, 30.4, 40.)
        engine.game.turn = 'fly'
        engine.game.shot_id += 1
        engine.actuate_body(None, None, human_context, 40., 40.2)
        engine.actuate_body(None, None, engine.motor_context(), 40.3, 40.5)
        np.testing.assert_allclose(durations, [.2, .2, .2])

    def test_save_commits_pending_shot_reward_and_releases_motor(self):
        engine = server_module.Engine()
        engine.brain = StubBrain()
        engine.brain.sim_ms = 30.
        engine.brain.pulses = {'reward': 0., 'aversive': 0.}
        engine.body = NeuralBody(TinyGraph())
        engine.retina = SimpleNamespace(previous=None)
        features = engine.body.observe(np.ones(43, dtype=int)*4, .04)
        engine.body.begin(features)
        engine.body.pending['fired'] = True
        engine.game.turn = 'fly'
        engine.game.shoot('fly', 0, .5)
        engine.game.current_shot.update(first_contact=9, rail=True)
        engine.results.put(engine.game.finish_shot())
        with tempfile.TemporaryDirectory() as directory, patch.object(server_module, 'BASE', Path(directory)):
            (Path(directory)/'logs').mkdir()
            engine._save('settled.save')
            with zipfile.ZipFile(Path(directory)/'saves/settled.save') as archive:
                saved = json.loads(archive.read('state.json'))
            self.assertIsNone(saved['body']['pending'])
            self.assertEqual(saved['extra']['reward_count'], 1)
            self.assertEqual(saved['game']['reward_total'], .5)
            self.assertEqual(engine.brain.pulses['reward'], 150.)

    def test_disk_save_does_not_stop_physics(self):
        engine = server_module.Engine()
        engine.phase = 'ready'
        engine.brain = SlowSavingBrain()
        engine.body = NeuralBody(TinyGraph())
        engine.retina = SimpleNamespace(previous=None)
        engine.game.shoot('human', 0, .9)
        with tempfile.TemporaryDirectory() as directory, patch.object(server_module, 'BASE', Path(directory)):
            engine.physics_worker.start()
            try:
                engine._save('io-test.save')
                self.assertGreater(engine.game.shot_seconds, .15)
                frames = engine.frames_after(0)
                self.assertGreater(len(frames), 30)
                intervals = np.diff([f['t'] for f in frames])
                self.assertLess(float(np.percentile(intervals, 95)), 6.)
            finally:
                engine.stop.set()
                engine.physics_worker.join(timeout=2)

    def test_head_on_contact_transfers_velocity_without_overlap(self):
        engine = server_module.Engine()
        game = engine.game
        for ball in game.balls[1:]:
            ball.pocketed = ball.number != 9
        game.balls[0].x, game.balls[0].y = 200., 250.
        game.balls[9].x, game.balls[9].y = 400., 250.
        game.turn = 'fly'
        game.shoot('fly', 0, 1.)
        contact = False
        for _ in range(70):
            game.step()
            distance = np.hypot(game.balls[0].x-game.balls[9].x, game.balls[0].y-game.balls[9].y)
            self.assertGreaterEqual(distance, 22.-.01)
            if game.current_shot['first_contact'] == 9:
                contact = True
                self.assertGreater(game.balls[9].vx, 800)
                self.assertLess(game.balls[0].vx, 40)
                break
        self.assertTrue(contact)
