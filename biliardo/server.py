"""Local-only MaleCNS billiards service. Start with python -m biliardo.server."""
import argparse
import asyncio
from collections import deque
import copy
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import queue
import re
import secrets
import threading
import time

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from flyblox.config import ROOT, load_config
from .game import Game
from .http_guard import LocalGuard
from .timing import responsive_timing
from .vision import render_eye

BASE = Path(__file__).resolve().parent
(BASE/'logs').mkdir(parents=True, exist_ok=True)
(BASE/'saves').mkdir(parents=True, exist_ok=True)
log = logging.getLogger('biliardo')


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.commands = queue.Queue()
        self.results = queue.Queue()
        self.frames = deque(maxlen=720)
        self.frame_id = 0
        self.stream_epoch = secrets.token_hex(6)
        self.maintenance = False
        self.brain_public = None
        self.client_metrics = {}
        self.game = Game()
        self.brain = self.graph = self.body = self.retina = None
        self.phase = 'loading'
        self.loading = 'Verifica del connectoma completo…'
        self.error = None
        self.paused = False
        self.learning = True
        self.token = os.environ.pop('BILIARDO_RESUME_TOKEN', None) or secrets.token_urlsafe(32)
        self.source = 'Nuova memoria biliardo'
        self.saved_at = None
        self.saved_file = None
        self.command_status = None
        self.observation = {}
        self.activity = np.zeros(0, dtype=np.uint16)
        self.points = b''
        self.neuron_stats = {}
        self.wall_step = 0.
        self.cpu_step = 0.
        self.neural_cycle = 0.
        self.profile_steps = 0
        self._motor_generation = 0
        self._motor_context = None
        self._motor_tick = None
        self.neural_seconds = .04
        self.reward_count = 0
        self.last_reward = {'value': 0., 'level': 'none', 'reason': 'Ancora nessun tiro della mosca'}
        self.rate_history = []
        self.last_autosave = time.monotonic()
        self.worker = threading.Thread(target=self.run, name='MaleCNS-billiards', daemon=True)
        self.physics_worker = threading.Thread(target=self.physics_loop, name='Pool-physics-240Hz', daemon=True)

    def start(self):
        self.worker.start()

    def initialize(self):
        from flyblox.brain.connectome import Connectome
        from flyblox.brain.runtime import Brain
        from flyblox.vision.retina import Retina
        from .body import NeuralBody
        self.graph = Connectome()
        self.loading = f'Caricamento GPU: {self.graph.n:,} neuroni…'
        self.brain = Brain(self.graph, load_config())
        self.body = NeuralBody(self.graph)
        self.retina = Retina(self.graph, [160, 90])
        own_save = BASE/'saves/latest.save'
        if own_save.exists():
            self._load(own_save)
        else:
            seed = ROOT/'checkpoints/latest.npz'
            if seed.exists():
                self.brain.load(seed)
                self.brain.clear_reward()
                self.source = 'Import iniziale: checkpoints/latest.npz · memoria Roblox conservata separatamente'
        # Actual soma coordinates for every neuron, NaN means no known soma.
        self.points = self.graph.positions.astype('<f4').tobytes()
        self.activity = np.zeros(self.graph.n, dtype='<u2')
        self.phase = 'ready'
        self.publish_brain()
        self.loading = 'Connectoma completo pronto'
        log.info('Ready: %s neurons, %s edges. Source: %s', self.graph.n, len(self.graph.post), self.source)

    def run(self):
        try:
            self.initialize()
            self._save('latest.save')
            self.physics_worker.start()
            while not self.stop.is_set():
                loop = time.perf_counter()
                self.process_commands()
                had_result = False
                while not self.results.empty():
                    self.on_result(self.results.get_nowait())
                    had_result = True
                if had_result or time.monotonic()-self.last_autosave > 90:
                    self._save('latest.save')
                if self.paused:
                    self.publish_brain()
                    self.stop.wait(.04)
                    continue
                if not self.learning:
                    self.brain.clear_reward()
                if self.profile_steps:
                    import cProfile
                    profiler = cProfile.Profile()
                    profiler.runcall(self.neural_step)
                    if self.wall_step > .3:
                        profiler.dump_stats(str(BASE/'logs'/f'neural-slow-{self.profile_steps}.prof'))
                        self.profile_steps -= 1
                else:
                    self.neural_step()
                self.stop.wait(max(.001, .1-(time.perf_counter()-loop)))
        except Exception as exc:
            log.exception('Engine failed')
            self.error = str(exc)
            self.phase = 'error'
        finally:
            self.stop.set()
            if self.physics_worker.is_alive():
                self.physics_worker.join(timeout=3)
            if self.phase == 'ready':
                try:
                    while not self.results.empty():
                        self.on_result(self.results.get_nowait())
                    self._save('latest.save')
                except Exception:
                    log.exception('Final save failed')

    def physics_loop(self):
        previous = time.perf_counter()
        accumulator = 0.
        idle_frame = 0.
        while not self.stop.is_set():
            now = time.perf_counter()
            elapsed = min(.1, now-previous)
            previous = now
            with self.lock:
                active = self.phase == 'ready' and not self.paused and not self.maintenance
                if active and self.game.phase == 'moving':
                    accumulator += elapsed
                    while accumulator >= 1/240:
                        outcome = self.game.step()
                        accumulator -= 1/240
                        # Every physics tick is retained, including contact ticks;
                        # stream messages batch these for smooth interpolation.
                        self.push_frame(now-accumulator)
                        if outcome:
                            self.results.put(outcome)
                            break
                else:
                    accumulator = 0.
                    if now-idle_frame >= 1/60:
                        self.push_frame(now)
                        idle_frame = now
            self.stop.wait(.002)

    def push_frame(self, timestamp):
        self.frame_id += 1
        self.frames.append({'id': self.frame_id, 'epoch': self.stream_epoch, 't': timestamp*1000,
                            'game': self.game.game_number, 'shot': self.game.shot_id,
                            'phase': self.game.phase, 'turn': self.game.turn,
                            'paused': self.paused or self.maintenance,
                            'hand': self.game.ball_in_hand,
                            'body': [float(self.body.angle), float(self.body.power)] if self.body else [0., .5],
                            'balls': [[round(b.x, 4), round(b.y, 4), round(b.vx, 3), round(b.vy, 3), int(b.pocketed)] for b in self.game.balls]})

    def frames_after(self, index):
        with self.lock:
            if index < 0:
                return list(self.frames)[-1:]
            return [frame for frame in self.frames if frame['id'] > index][-120:]

    def neural_step(self):
        from flyblox.vision.retina import jpeg
        started = time.perf_counter()
        with self.lock:
            visible_game = self.game.state()
            observed_context = self.motor_context()
        frame = render_eye(visible_game, self.body.angle)
        obs = self.retina.transform(frame)
        cpu_start = time.thread_time()
        counts, wall = self.brain.step(obs['light'], obs['color'], self.neural_seconds*1000, learning=self.learning)
        self.cpu_step = time.thread_time()-cpu_start
        self.wall_step = wall
        features = self.body.observe(counts, self.neural_seconds)
        self.activity = np.clip(counts, 0, 65535).astype('<u2')
        total = int(counts.sum())
        active = int(np.count_nonzero(counts))
        top = np.argpartition(counts, -6)[-6:]
        top = top[np.argsort(counts[top])[::-1]]
        self.neuron_stats = {'active': active, 'spikes': total, 'mean_hz': total/(self.graph.n*self.neural_seconds),
                             'window_ms': self.neural_seconds*1000, 'total_spikes': self.brain.total_spikes,
                             'top': [dict(cell, spikes=int(counts[i]), hz=float(counts[i]/self.neural_seconds))
                                     for cell, i in zip(self.graph.cells(top), top)]}
        self.observation = {'eye': jpeg(frame, 80), 'retina': jpeg(obs['frame'], 85),
                            'left': jpeg(obs['left']), 'right': jpeg(obs['right']), 'motion': jpeg(obs['motion']),
                            'summary': obs['summary']}
        with self.lock:
            self.actuate_body(features, counts, observed_context, started, time.perf_counter())
        self.neural_cycle = time.perf_counter()-started
        self.rate_history.append({'t': self.brain.sim_ms/1000, 'hz': self.neuron_stats['mean_hz'],
                                  'pam': self.body.last_rates.get('PAM reward', 0.), 'motor': self.body.last_rates.get('DNp20', 0.)})
        self.rate_history = self.rate_history[-120:]
        self.publish_brain()

    def motor_context(self):
        return (self.stream_epoch, self.game.game_number, self.game.shot_id,
                self.game.turn, self.game.phase, self._motor_generation)

    def reset_motor_clock(self):
        # Call under the game lock. Pauses, disk work and another turn must
        # never be counted as time spent moving the current cue.
        self._motor_generation += 1
        self._motor_context = self._motor_tick = None

    def actuate_body(self, features, counts, observed_context, started, now):
        context = self.motor_context()
        if (self.paused or self.maintenance or self.game.turn != 'fly'
                or self.game.phase != 'aim' or not self.results.empty()
                or observed_context != context):
            self._motor_context = self._motor_tick = None
            return
        previous = self._motor_tick if self._motor_context == context else started
        self._motor_context, self._motor_tick = context, now
        self.body.learning = self.learning
        action = self.body.tick(features, counts, self.neural_seconds, max(0., now-previous))
        if action:
            self.game.shoot('fly', *action)

    def on_result(self, result):
        if result['actor'] != 'fly':
            return
        self.body.outcome(result['reward'])
        self.last_reward = {'value': result['reward'], 'level': result['level'], 'reason': result['reason']}
        if self.learning and result['reward']:
            # Explicit bounded artificial reward injection: same current, longer
            # high pulse. This is a model variable, not a measured emotion.
            duration_ms = {'high': 2000., 'medium': 350., 'contact': 120.}[result['level']]
            self.brain.pulses['reward'] = max(self.brain.pulses['reward'], self.brain.sim_ms+duration_ms)
            self.reward_count += 1
        with (BASE/'logs/shots.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({**result, 'neural_ms': self.brain.sim_ms, 'learning': self.learning}, ensure_ascii=False)+'\n')

    def extra(self):
        return {'source': self.source, 'learning': self.learning, 'reward_count': self.reward_count,
                'last_reward': self.last_reward, 'saved_at': datetime.now(timezone.utc).isoformat()}

    def _save(self, name):
        from .storage import save_archive
        with self.lock:
            while not self.results.empty():
                self.on_result(self.results.get_nowait())
            game_snapshot = Game.restore(copy.deepcopy(self.game.state()))
            extra = self.extra()
            self.reset_motor_clock()
        # Compression and disk I/O never hold the physics lock. The neural
        # worker owns brain/body state, so those remain stable during this save.
        save_archive(BASE/'saves'/name, self.brain, game_snapshot, self.body, self.retina, extra)
        self.saved_at, self.saved_file = extra['saved_at'], name
        self.last_autosave = time.monotonic()

    def _load(self, path):
        from .storage import load_archive
        game, body, previous, extra = load_archive(path, self.brain, self.graph)
        with self.lock:
            self.game, self.body = game, body
            self.reset_motor_clock()
            self.stream_epoch = secrets.token_hex(6)
            self.frames.clear()
            while not self.results.empty():
                self.results.get_nowait()
        self.retina.previous = previous
        self.source = extra.get('source', 'Salvataggio biliardo')
        self.learning = bool(extra.get('learning', True))
        self.reward_count = extra.get('reward_count', 0)
        self.last_reward = extra.get('last_reward', self.last_reward)
        self.saved_at, self.saved_file = extra.get('saved_at'), path.name
        self.rate_history = []
        self.observation = {}
        self.neuron_stats = {}

    def process_commands(self):
        handled = False
        while not self.commands.empty():
            command, payload = self.commands.get_nowait()
            handled = True
            try:
                if command == 'save':
                        name = datetime.now().strftime('memoria-%Y%m%d-%H%M%S-%f.save')
                        self._save(name)
                        self._save('latest.save')
                        self.command_status = {'ok': True, 'message': 'Memoria salvata: '+name, 'file': name}
                elif command == 'load':
                        self.maintenance = True
                        # Preserve the current session before replacing it.
                        if payload != 'before-load.save':
                            self._save('before-load.save')
                        self._load(BASE/'saves'/payload)
                        self.paused = True
                        self._save('latest.save')
                        self.command_status = {'ok': True, 'message': 'Memoria caricata. Premi Riprendi.'}
                elif command == 'new':
                        self.maintenance = True
                        self._save('before-new-game.save')
                        with self.lock:
                            self.game.new_game()
                            self.stream_epoch = secrets.token_hex(6)
                            self.frames.clear()
                            while not self.results.empty():
                                self.on_result(self.results.get_nowait())
                            self.body.pending = None
                            self.body.status = 'In attesa del turno'
                        self.brain.clear_reward()
                        self._save('latest.save')
                        self.command_status = {'ok': True, 'message': 'Nuovo tavolo. Tutta la memoria è conservata.'}
            except Exception as exc:
                log.exception('Command failed')
                self.command_status = {'ok': False, 'message': str(exc)}
            finally:
                self.maintenance = False
                self.publish_brain()
        return handled

    def publish_brain(self):
        if self.phase == 'ready':
                pulse = max(0, self.brain.pulses['reward']-self.brain.sim_ms)
                brain = {'neurons': self.graph.n, 'edges': len(self.graph.post), 'hash': self.graph.hash, 'model_hash': self.brain.model_hash,
                         'report': self.graph.report, 'stats': self.neuron_stats, 'sim_ms': self.brain.sim_ms,
                         'step_wall_ms': self.wall_step*1000, 'neural_step_ms': self.neural_seconds*1000,
                         'step_thread_cpu_ms': self.cpu_step*1000, 'cycle_wall_ms': self.neural_cycle*1000,
                         'pulse_ms': pulse, 'dopamine_current': self.brain.cfg['dopamine_current'],
                         'memory': self.brain.memory.summary(), 'source': self.source,
                         'body': {k: getattr(self.body, k) for k in ['angle', 'power', 'target_angle', 'target_power', 'aim_seconds', 'release_spikes', 'status', 'updates', 'baseline', 'last_gradient', 'last_rates']},
                         'readout_parameters': int(self.body.weights.size), 'reward_count': self.reward_count,
                         'last_reward': self.last_reward, 'rates': self.rate_history.copy()}
                self.brain_public = brain

    def state(self):
        with self.lock:
            game = self.game.state()
            game['history'] = game['history'][-8:]
            return {'phase': self.phase, 'loading': self.loading, 'error': self.error, 'paused': self.paused,
                    'learning': self.learning, 'game': game, 'brain': self.brain_public, 'saved_at': self.saved_at,
                    'saved_file': self.saved_file, 'command': self.command_status, 'queued': self.commands.qsize(),
                    'build': 'smooth-4', 'client_metrics': self.client_metrics}


engine = Engine()


@asynccontextmanager
async def lifespan(app):
    with responsive_timing():
        engine.start()
        try:
            yield
        finally:
            engine.stop.set()
            engine.worker.join(timeout=25)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(LocalGuard, get_token=lambda: engine.token)


@app.get('/api/bootstrap')
def bootstrap():
    return {'token': engine.token, 'state': engine.state()}


@app.get('/api/state')
def state():
    return engine.state()


@app.get('/api/stream')
async def stream(request: Request, token: str = ''):
    if token != engine.token:
        raise HTTPException(403, 'Token di sessione richiesto')
    async def events():
        cursor = -1
        # StreamingResponse already cancels this generator on disconnect.
        # Polling receive here created additional cancellation tasks per frame.
        while not engine.stop.is_set():
            frames = engine.frames_after(cursor)
            if frames:
                cursor = frames[-1]['id']
                yield 'data:'+json.dumps({'frames': frames}, separators=(',', ':'))+'\n\n'
            await asyncio.sleep(1/60)
    return StreamingResponse(events(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})


@app.get('/api/vision')
def vision():
    with engine.lock:
        return engine.observation


class ClientMetrics(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    build: str = Field(max_length=40)
    fps: float = Field(ge=0, le=1000)
    frame_p95_ms: float = Field(ge=0, le=60000)
    draw_p95_ms: float = Field(ge=0, le=60000)
    stream_age_ms: float = Field(ge=0, le=1000000000)
    table_visible: bool
    brain_visible: bool


@app.post('/api/client-metrics')
def client_metrics(metrics: ClientMetrics):
    engine.client_metrics = metrics.model_dump() | {'received_at': time.time()}
    return {'ok': True}


@app.get('/api/positions')
def positions():
    if engine.phase != 'ready':
        raise HTTPException(503, 'Cervello in caricamento')
    return Response(engine.points, media_type='application/octet-stream')


@app.get('/api/activity')
def activity():
    with engine.lock:
        return Response(engine.activity.tobytes(), media_type='application/octet-stream')


@app.get('/api/neuron/{index}')
def neuron(index: int):
    with engine.lock:
        if engine.phase != 'ready' or not 0 <= index < engine.graph.n:
            raise HTTPException(404, 'Neurone non disponibile')
        return engine.graph.cells([index])[0] | {'spikes': int(engine.activity[index]), 'window_ms': engine.neural_seconds*1000}


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str
    angle: float | None = None
    power: float | None = None
    x: float | None = None
    y: float | None = None
    enabled: bool | None = None
    file: str | None = None


@app.post('/api/command')
def command(c: Command):
    with engine.lock:
        if engine.phase != 'ready':
            raise HTTPException(409, 'Attendi il caricamento del cervello.')
        try:
            if c.name == 'shoot':
                if engine.paused:
                    raise ValueError('Riprendi la simulazione prima di tirare.')
                if c.angle is None or c.power is None:
                    raise ValueError('Angolo e forza richiesti.')
                engine.game.shoot('human', c.angle, c.power)
            elif c.name == 'place':
                if c.x is None or c.y is None:
                    raise ValueError('Coordinate richieste.')
                engine.game.place_cue(c.x, c.y)
            elif c.name == 'pause':
                if c.enabled is None:
                    raise ValueError('Stato pausa richiesto.')
                engine.paused = c.enabled
                engine.reset_motor_clock()
            elif c.name == 'learning':
                if c.enabled is None:
                    raise ValueError('Stato apprendimento richiesto.')
                engine.learning = engine.body.learning = c.enabled
            elif c.name in ['save', 'load', 'new']:
                if c.name == 'load' and (not c.file or not re.fullmatch(r'[A-Za-z0-9_-]+\.save', c.file) or not (BASE/'saves'/c.file).is_file()):
                    raise ValueError('Scegli un salvataggio locale esistente.')
                if engine.commands.qsize() > 3:
                    raise ValueError('Attendi la fine del salvataggio in corso.')
                engine.commands.put((c.name, c.file))
                engine.command_status = {'ok': True, 'message': 'Operazione in corso…'}
            else:
                raise ValueError('Comando sconosciuto.')
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return {'accepted': True, 'state': engine.state()}


@app.get('/api/saves')
def saves():
    return [{'name': p.name, 'bytes': p.stat().st_size, 'modified': p.stat().st_mtime}
            for p in sorted((BASE/'saves').glob('*.save'), key=lambda p: p.stat().st_mtime, reverse=True)]


@app.get('/api/saves/{name}')
def download_save(name: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.save', name) or not (BASE/'saves'/name).is_file():
        raise HTTPException(404, 'Salvataggio non trovato')
    return FileResponse(BASE/'saves'/name, filename=name, media_type='application/octet-stream')


app.mount('/', StaticFiles(directory=BASE/'dist', html=True), name='site')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--profile-neural', action='store_true', help='Record three slow neural updates for local diagnosis')
    args = parser.parse_args()
    engine.profile_steps = 3 if args.profile_neural else 0
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(BASE/'logs/server.log', encoding='utf-8'), logging.StreamHandler()])
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False, timeout_graceful_shutdown=3)
