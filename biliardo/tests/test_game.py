import math
import unittest
from biliardo.game import Game, RADIUS, pocket_distance


class PoolTests(unittest.TestCase):
    def fixture(self, actor='fly'):
        game = Game()
        game.turn = actor
        game.shoot(actor, 0, .5)
        game.current_shot['first_contact'] = 9 if actor == 'fly' else 1
        game.current_shot['rail'] = True
        for ball in game.balls:
            ball.vx = ball.vy = 0.
        return game

    def test_full_rack_unique_and_no_overlap(self):
        game = Game()
        self.assertEqual([b.number for b in game.balls], list(range(16)))
        for i, a in enumerate(game.balls):
            for b in game.balls[i+1:]:
                self.assertGreaterEqual(math.hypot(a.x-b.x, a.y-b.y), 2*RADIUS)

    def test_real_break_collides_and_settles(self):
        game = Game()
        game.shoot('human', 0, .85)
        result = None
        for _ in range(6000):
            result = game.step()
            if result:
                break
        self.assertIsNotNone(result)
        self.assertEqual(result['first_contact'], 1)
        self.assertTrue(any(abs(b.x-710) > 60 and b.number for b in game.balls[1:]))
        self.assertTrue(all(b.vx == b.vy == 0 for b in game.balls))

    def test_physical_pocket_entry(self):
        game = self.fixture()
        ball = game.balls[9]
        ball.x, ball.y, ball.vx, ball.vy = 500, 40, 0, -150
        for _ in range(150):
            game.step()
        self.assertTrue(ball.pocketed)
        self.assertIn(9, game.current_shot['pots'])

    def test_correct_stripe_high_reward_and_extra_turn(self):
        game = self.fixture()
        game.balls[9].pocketed = True
        game.current_shot['pots'] = [9]
        result = game.finish_shot()
        self.assertEqual((result['reward'], result['level'], game.turn), (10, 'high', 'fly'))

    def test_opponents_solid_no_dopamine(self):
        game = self.fixture()
        game.balls[1].pocketed = True
        game.current_shot['pots'] = [1]
        result = game.finish_shot()
        self.assertEqual(result['reward'], 0)
        self.assertEqual(game.turn, 'human')

    def test_mixed_pots_reward_only_own(self):
        game = self.fixture()
        game.current_shot['pots'] = [1, 9]
        self.assertEqual(game.finish_shot()['reward'], 10)

    def test_medium_near_reward(self):
        game = self.fixture()
        game.balls[9].x, game.balls[9].y = 500, 48
        result = game.finish_shot()
        self.assertEqual((result['reward'], result['level']), (2, 'medium'))

    def test_repeated_near_position_cannot_farm_reward(self):
        game = self.fixture()
        game.balls[9].x, game.balls[9].y = 500, 48
        game.best_distance['9'] = 47.
        self.assertEqual(game.finish_shot()['reward'], .5)

    def test_touch_own_stripe_small_reward_without_cushion(self):
        game = self.fixture()
        game.current_shot['rail'] = False
        result = game.finish_shot()
        self.assertEqual((result['reward'], result['level']), (.5, 'contact'))
        self.assertEqual(game.turn, 'human')

    def test_touch_solid_no_contact_reward(self):
        game = self.fixture()
        game.current_shot['first_contact'] = 1
        self.assertEqual(game.finish_shot()['reward'], 0)

    def test_plain_miss_zero(self):
        game = self.fixture()
        game.current_shot['first_contact'] = None
        self.assertEqual(game.finish_shot()['reward'], 0)

    def test_wrong_first_contact_cancels_correct_pot(self):
        game = self.fixture()
        game.current_shot.update(first_contact=1, pots=[9])
        result = game.finish_shot()
        self.assertEqual(result['reward'], 0)
        self.assertIsNotNone(result['foul'])

    def test_scratch_respots_without_overlap_and_no_reward(self):
        game = self.fixture()
        game.balls[0].pocketed = True
        game.current_shot['pots'] = [0, 9]
        result = game.finish_shot()
        self.assertEqual(result['reward'], 0)
        self.assertTrue(game.ball_in_hand)
        cue = game.balls[0]
        self.assertFalse(cue.pocketed)
        self.assertTrue(all(math.hypot(cue.x-b.x, cue.y-b.y) > 2*RADIUS for b in game.balls[1:] if not b.pocketed))

    def test_early_black_loses(self):
        game = self.fixture()
        game.current_shot['pots'] = [8]
        result = game.finish_shot()
        self.assertEqual((result['winner'], result['reward'], game.phase), ('human', 0, 'over'))

    def test_last_black_wins(self):
        game = self.fixture()
        game.current_shot.update(targets=[8], first_contact=8, pots=[8])
        result = game.finish_shot()
        self.assertEqual((result['winner'], result['reward']), ('fly', 10))

    def test_own_pot_with_illegal_black_still_zero(self):
        game = self.fixture()
        game.current_shot['pots'] = [9, 8]
        result = game.finish_shot()
        self.assertEqual((result['winner'], result['reward']), ('human', 0))

    def test_no_fly_reward_for_human_shot(self):
        game = self.fixture('human')
        game.current_shot['pots'] = [9]
        self.assertEqual(game.finish_shot()['reward'], 0)

    def test_invalid_commands_do_not_change_table(self):
        game = Game()
        before = game.state()
        for actor, angle, power in [('fly', 0, .5), ('human', float('nan'), .5), ('human', 0, 2)]:
            with self.assertRaises(ValueError):
                game.shoot(actor, angle, power)
        self.assertEqual(game.state(), before)

    def test_new_table_preserves_lifetime_memory_metrics(self):
        game = self.fixture()
        game.current_shot['pots'] = [9]
        game.finish_shot()
        game.new_game()
        self.assertEqual((game.fly_shots, game.reward_total), (1, 10))

    def test_full_midshot_game_roundtrip(self):
        game = Game()
        game.shoot('human', .1, .73)
        for _ in range(600):
            game.step()
        restored = Game.restore(game.state())
        for _ in range(200):
            game.step()
            restored.step()
        self.assertEqual(game.state(), restored.state())

    def test_speed_power_changes_travel(self):
        distances = []
        for power in [.1, .4]:
            game = Game()
            for b in game.balls[1:]:
                b.pocketed = True
            game.shoot('human', 0, power)
            for _ in range(120):
                game.step()
            distances.append(game.balls[0].x)
        self.assertGreater(distances[1], distances[0]+100)


if __name__ == '__main__':
    unittest.main()
