"""Authoritative local pool physics and fixed-group 8-ball training rules.

The reward evaluator is not available to the motor policy. Positions reach the
brain only through the rendered image. No optimal shot solver is used.
"""
from dataclasses import dataclass, asdict
import math
import random

WIDTH, HEIGHT, RADIUS = 1000.0, 500.0, 11.0
POCKET_RADIUS = 23.0
POCKETS = [(0., 0.), (500., 0.), (1000., 0.), (0., 500.), (500., 500.), (1000., 500.)]
COLORS = ['#f5f1df', '#e8b733', '#3970c3', '#c84849', '#9164b9', '#e88c31', '#3d9366', '#8d3545', '#20222a']


def group(number):
    return 'solids' if 1 <= number <= 7 else 'stripes' if 9 <= number <= 15 else 'black' if number == 8 else 'cue'


def pocket_distance(ball):
    return min(math.hypot(ball.x-x, ball.y-y) for x, y in POCKETS)


@dataclass
class Ball:
    number: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    pocketed: bool = False


class Game:
    def __init__(self, seed=42):
        self.seed = seed
        self.game_number = 0
        self.history = []
        self.reward_total = 0.0
        self.fly_shots = 0
        self.fly_pots = 0
        self.new_game()

    def new_game(self):
        self.game_number += 1
        self.balls = [Ball(0, 240., 250.)]
        # Black at the center, opposite groups at back corners.
        order = [1, 9, 2, 10, 8, 3, 11, 4, 12, 5, 6, 13, 7, 14, 15]
        i = 0
        for column in range(5):
            for row in range(column+1):
                self.balls.append(Ball(order[i], 710+column*math.sqrt(3)*(RADIUS+.2), 250+(row-column/2)*2*(RADIUS+.2)))
                i += 1
        self.balls.sort(key=lambda b: b.number)
        self.turn = 'human'
        self.phase = 'aim'
        self.winner = None
        self.ball_in_hand = False
        self.shot_id = 0
        self.current_shot = None
        self.shot_seconds = 0.
        self.quiet_seconds = 0.
        self.best_distance = {str(b.number): pocket_distance(b) for b in self.balls if b.number}
        self.message = 'Apri tu: piene 1–7. La mosca gioca le mezze 9–15.'
        self.last_result = None

    def remaining(self, actor):
        own = 'solids' if actor == 'human' else 'stripes'
        return [b.number for b in self.balls if group(b.number) == own and not b.pocketed]

    def legal_targets(self, actor):
        return self.remaining(actor) or [8]

    def shoot(self, actor, angle, power):
        if self.phase != 'aim' or self.turn != actor or self.winner:
            raise ValueError('Non è il tuo turno di tiro.')
        if not all(math.isfinite(v) for v in [angle, power]) or not .03 <= power <= 1:
            raise ValueError('Forza valida: da 3% a 100%; angolo finito.')
        cue = self.balls[0]
        if cue.pocketed:
            raise ValueError('Posiziona la bianca sul tavolo.')
        self.shot_id += 1
        self.current_shot = {'id': self.shot_id, 'actor': actor, 'angle': angle % math.tau,
                             'power': power, 'pots': [], 'first_contact': None, 'rail': False,
                             'targets': self.legal_targets(actor),
                             'before': {str(b.number): pocket_distance(b) for b in self.balls if b.number and not b.pocketed}}
        speed = 100 + 1050 * power
        cue.vx, cue.vy = math.cos(angle)*speed, math.sin(angle)*speed
        self.phase = 'moving'
        self.ball_in_hand = False
        self.shot_seconds = self.quiet_seconds = 0.
        self.message = 'Palline in movimento…'

    def place_cue(self, x, y):
        if self.turn != 'human' or self.phase != 'aim' or not self.ball_in_hand:
            raise ValueError('La bianca si può spostare solo dopo un fallo della mosca.')
        if not all(math.isfinite(v) for v in [x, y]) or not RADIUS <= x <= WIDTH-RADIUS or not RADIUS <= y <= HEIGHT-RADIUS:
            raise ValueError('Scegli un punto dentro il tavolo.')
        if any(math.hypot(x-b.x, y-b.y) < 2*RADIUS+1 for b in self.balls[1:] if not b.pocketed):
            raise ValueError('La bianca non può sovrapporsi a un’altra palla.')
        if min(math.hypot(x-px, y-py) for px, py in POCKETS) <= POCKET_RADIUS+RADIUS:
            raise ValueError('Posiziona la bianca lontano dalla buca.')
        self.balls[0].x, self.balls[0].y = float(x), float(y)

    def step(self, dt=1/240):
        if self.phase != 'moving':
            return None
        self.shot_seconds += dt
        shot = self.current_shot
        live = [b for b in self.balls if not b.pocketed]
        for b in live:
            b.x += b.vx*dt
            b.y += b.vy*dt
            speed = math.hypot(b.vx, b.vy)
            if speed:
                factor = max(0., speed-105*dt) / speed
                b.vx *= factor
                b.vy *= factor
            if pocket_distance(b) < POCKET_RADIUS:
                b.pocketed = True
                b.vx = b.vy = 0.
                shot['pots'].append(b.number)
                continue
            # Gaps between the cushion segments lead into the six pockets.
            side_gap = b.y < 31 or b.y > HEIGHT-31
            end_gap = b.x < 31 or b.x > WIDTH-31 or abs(b.x-WIDTH/2) < 29
            rail = False
            if not side_gap:
                if b.x < RADIUS:
                    b.x = RADIUS
                    b.vx = abs(b.vx)*.83
                    rail = True
                elif b.x > WIDTH-RADIUS:
                    b.x = WIDTH-RADIUS
                    b.vx = -abs(b.vx)*.83
                    rail = True
            if not end_gap:
                if b.y < RADIUS:
                    b.y = RADIUS
                    b.vy = abs(b.vy)*.83
                    rail = True
                elif b.y > HEIGHT-RADIUS:
                    b.y = HEIGHT-RADIUS
                    b.vy = -abs(b.vy)*.83
                    rail = True
            # A pocket mouth cannot let a ball escape the simulation.
            if b.x < -RADIUS or b.x > WIDTH+RADIUS or b.y < -RADIUS or b.y > HEIGHT+RADIUS:
                b.pocketed = True
                b.vx = b.vy = 0.
                shot['pots'].append(b.number)
            if rail and shot['first_contact'] is not None:
                shot['rail'] = True
        live = [b for b in live if not b.pocketed]
        for i, a in enumerate(live):
            for b in live[i+1:]:
                dx, dy = b.x-a.x, b.y-a.y
                distance = math.hypot(dx, dy)
                if distance >= 2*RADIUS:
                    continue
                nx, ny = (dx/distance, dy/distance) if distance > 1e-8 else (1., 0.)
                overlap = (2*RADIUS-distance+.001)/2
                a.x -= nx*overlap
                a.y -= ny*overlap
                b.x += nx*overlap
                b.y += ny*overlap
                closing = (a.vx-b.vx)*nx + (a.vy-b.vy)*ny
                if closing <= 0:
                    continue
                impulse = .97*closing
                a.vx -= impulse*nx
                a.vy -= impulse*ny
                b.vx += impulse*nx
                b.vy += impulse*ny
                if shot['first_contact'] is None and (a.number == 0 or b.number == 0):
                    shot['first_contact'] = b.number if a.number == 0 else a.number
        maximum_speed = max((math.hypot(b.vx, b.vy) for b in live), default=0.)
        self.quiet_seconds = self.quiet_seconds+dt if maximum_speed < 2 else 0.
        if self.quiet_seconds > .3 or self.shot_seconds > 22:
            for b in self.balls:
                b.vx = b.vy = 0.
            return self.finish_shot()
        return None

    def _return_cue(self):
        cue = self.balls[0]
        cue.pocketed = False
        for x in range(240, 960, 28):
            for y in [250, *range(45, 460, 28)]:
                if all(math.hypot(x-b.x, y-b.y) > 2*RADIUS+1 for b in self.balls[1:] if not b.pocketed):
                    cue.x, cue.y = float(x), float(y)
                    return

    def finish_shot(self):
        s = self.current_shot
        actor, pots = s['actor'], s['pots']
        own_pots = [n for n in pots if n in s['targets'] and n != 8]
        foul = ('Bianca in buca' if 0 in pots else 'Nessuna palla colpita' if s['first_contact'] is None
                else 'Prima palla del gruppo sbagliato' if s['first_contact'] not in s['targets']
                else 'Nessuna sponda o buca dopo il contatto' if not s['rail'] and not pots else None)
        value, level, reason = 0., 'none', 'Nessun premio'
        if 8 in pots:
            self.winner = actor if s['targets'] == [8] and not foul else ('fly' if actor == 'human' else 'human')
            self.phase = 'over'
            reason = 'Nera regolare: partita vinta' if self.winner == actor else 'Nera anticipata o fallo: partita persa'
        else:
            self.phase = 'aim'
        if actor == 'fly':
            self.fly_shots += 1
            if not foul and self.winner != 'human' and (own_pots or (8 in pots and self.winner == 'fly')):
                value, level = 10.*max(1, len(own_pots)), 'high'
                reason = 'Mezza in buca' if own_pots else 'Nera regolare: vittoria'
                self.fly_pots += len(own_pots)
            elif not foul and not pots and not self.winner:
                improved = [b.number for b in self.balls if b.number in s['targets'] and not b.pocketed
                            and pocket_distance(b) < 65
                            and pocket_distance(b) < min(s['before'].get(str(b.number), 0), self.best_distance.get(str(b.number), 0))-8]
                if improved:
                    value, level, reason = 2., 'medium', 'Avvicinamento utile alla buca: '+', '.join(map(str, improved))
            if value == 0 and not pots and not self.winner and s['first_contact'] in range(9, 16) and foul in [None, 'Nessuna sponda o buca dopo il contatto']:
                value, level, reason = .5, 'contact', 'Bianca sulla propria mezza · primo contatto corretto'
            if foul and value == 0:
                reason = foul+' · premio zero'
            elif value == 0 and any(group(n) == 'solids' for n in pots):
                reason = 'Piena dell’avversario · premio zero'
        for b in self.balls:
            if b.number and not b.pocketed:
                self.best_distance[str(b.number)] = min(self.best_distance.get(str(b.number), math.inf), pocket_distance(b))
        self.reward_total += value
        result = {**s, 'game': self.game_number, 'foul': foul, 'reward': value, 'level': level,
                  'reason': reason, 'winner': self.winner, 'duration': round(self.shot_seconds, 3)}
        self.history.append(result)
        self.history = self.history[-200:]
        self.last_result = result
        if not self.winner and (foul or not own_pots):
            self.turn = 'fly' if actor == 'human' else 'human'
        if foul:
            self.ball_in_hand = True
            if self.balls[0].pocketed:
                self._return_cue()
        self.message = reason if self.winner else (('Fallo: '+foul+'. ') if foul else '')+('Tocca a te.' if self.turn == 'human' else 'La mosca prepara il tiro.')
        return result

    def state(self):
        return {k: v for k, v in self.__dict__.items() if k != 'balls'} | {'balls': [asdict(b) for b in self.balls]}

    @classmethod
    def restore(cls, state):
        if len(state.get('balls', [])) != 16 or sorted(b['number'] for b in state['balls']) != list(range(16)):
            raise ValueError('Salvataggio: palle non valide.')
        if state.get('phase') not in ['aim', 'moving', 'over'] or state.get('turn') not in ['human', 'fly']:
            raise ValueError('Salvataggio: turno non valido.')
        obj = cls()
        for raw in state['balls']:
            if not all(math.isfinite(raw[k]) and abs(raw[k]) < 1e5 for k in ['x', 'y', 'vx', 'vy']):
                raise ValueError('Salvataggio: coordinate non valide.')
        obj.__dict__.update({k: v for k, v in state.items() if k in obj.__dict__ and k != 'balls'})
        obj.balls = [Ball(**b) for b in sorted(state['balls'], key=lambda b: b['number'])]
        return obj
