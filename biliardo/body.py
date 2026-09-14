"""Declared artificial neural-to-cue interface; no ball coordinates or solver.

Policy gradient learns only from actual neural rate features and scalar reward.
The stochastic motor exploration is artificial, not an anatomical fly circuit.
"""
import math
import numpy as np


class NeuralBody:
    VERSION = 1

    def __init__(self, graph, seed=731):
        self.rng = np.random.default_rng(seed)
        self.names, self.groups = [], []
        # Spatial receptive fields keep sensory spike information in the readout.
        for y in range(4):
            for x in range(8):
                uv = graph.uv
                selected = graph.retina[(np.minimum((uv[:, 0]*8).astype(int), 7) == x) & (np.minimum((uv[:, 1]*4).astype(int), 3) == y)]
                self.names.append(f'Retina {x+1}/{y+1}')
                self.groups.append(selected)
        for name, types in [('DNa02 L', ['DNa02']), ('DNa02 R', ['DNa02']), ('DNg13 L', ['DNg13']), ('DNg13 R', ['DNg13']),
                            ('DNpe017', ['DNpe017']), ('DNp20', ['DNp20']), ('DNp09', ['DNp09']), ('MDN', ['MDN'])]:
            self.names.append(name)
            self.groups.append(graph.population(types, name[-1] if name.endswith((' L', ' R')) else None))
        for name, key in [('KC', 'kc'), ('PAM reward', 'reward'), ('PPL aversivo', 'aversive')]:
            self.names.append(name)
            self.groups.append(np.asarray(graph.circuit[key]))
        self.size = len(self.groups)+1
        self.weights = self.rng.normal(0, .035, (2, self.size))
        self.weights[1, 0] = -.15
        self.ema = np.zeros(len(self.groups))
        self.pending = None
        self.learning = True
        self.updates = 0
        self.baseline = 0.
        self.angle = 0.
        self.power = .48
        self.target_angle = 0.
        self.target_power = .48
        self.aim_seconds = 0.
        self.release_spikes = 0.
        self.status = 'In attesa del turno'
        self.last_gradient = 0.
        self.last_rates = {}

    def observe(self, counts, neural_seconds):
        rates = np.array([float(counts[ix].mean()/neural_seconds) if len(ix) else 0. for ix in self.groups])
        self.ema += (1-math.exp(-neural_seconds/.2))*(rates-self.ema)
        self.last_rates = dict(zip(self.names, (float(v) for v in self.ema)))
        return np.r_[1., np.tanh(self.ema/100)]

    def begin(self, features):
        # Circular exploration reaches the whole table, including backward shots.
        mu = self.weights @ features
        sigma = np.array([1.5, .85]) if self.learning else np.array([.12, .10])
        noise = self.rng.normal(size=2)
        latent = mu+sigma*noise
        self.target_angle = float(latent[0] % math.tau)
        self.target_power = float(.08+.92/(1+math.exp(-float(np.clip(latent[1], -12, 12)))))
        self.pending = {'features': features.tolist(), 'noise': noise.tolist(), 'sigma': sigma.tolist(),
                        'latent': latent.tolist(), 'learning': self.learning, 'fired': False}
        self.aim_seconds = self.release_spikes = 0.
        self.status = 'Mira e carica guidate dagli impulsi'

    def tick(self, features, counts, neural_seconds, wall_seconds):
        if not math.isfinite(wall_seconds) or wall_seconds <= 0:
            return None
        if self.pending is None:
            self.begin(features)
        if self.pending['fired']:
            return None
        self.aim_seconds += wall_seconds
        # Muscles actuate only if the descending populations emitted spikes.
        motor = sum(float(counts[ix].sum()) for ix in self.groups[32:40])
        if motor <= 0:
            self.status = 'Attesa di impulsi discendenti'
            return None
        self.release_spikes += motor
        error = (self.target_angle-self.angle+math.pi) % math.tau-math.pi
        # Integrate actual active time. Clipping dt to .2 made slow neural
        # windows stretch a settled shot into many seconds of extra waiting.
        # The bounded position delta cannot overshoot even for a long window.
        gain = min(1., motor/25)*wall_seconds
        self.angle = (self.angle + np.clip(error, -2.6*gain, 2.6*gain)) % math.tau
        self.power += float(np.clip(self.target_power-self.power, -.6*gain, .6*gain))
        error = (self.target_angle-self.angle+math.pi) % math.tau-math.pi
        if abs(error) >= .025:
            self.status = 'Allinea la stecca'
        elif abs(self.target_power-self.power) >= .025:
            self.status = 'Carica il colpo'
        elif self.release_spikes < 80:
            self.status = 'Attende il rilascio neurale'
        else:
            self.pending['fired'] = True
            self.status = 'Colpo eseguito · osservazione del risultato'
            return float(self.angle), float(self.power)
        return None

    def outcome(self, reward):
        if self.pending and self.pending['fired'] and self.pending['learning'] and self.learning:
            # A zero-reward miss is not a dopamine punishment. The adaptive
            # readout can still compare it against its learned reward baseline.
            advantage = float(np.clip(reward/10-self.baseline, -1, 2))
            features = np.array(self.pending['features'])
            gradient = np.outer(np.array(self.pending['noise'])/np.array(self.pending['sigma']), features)
            gradient *= .018*advantage / max(1., float(np.linalg.norm(features)))
            self.weights = np.clip(self.weights+gradient, -4, 4)
            self.last_gradient = float(np.linalg.norm(gradient))
            self.baseline = .95*self.baseline+.05*(reward/10)
            self.updates += 1
        self.pending = None
        self.status = 'In attesa del turno'

    def state(self):
        return {'version': self.VERSION, 'weights': self.weights.tolist(), 'ema': self.ema.tolist(),
                'rng': self.rng.bit_generator.state, **{k: getattr(self, k) for k in ['pending', 'learning', 'updates', 'baseline', 'angle', 'power',
                'target_angle', 'target_power', 'aim_seconds', 'release_spikes', 'status', 'last_gradient', 'last_rates']}}

    def restore(self, data):
        weights, ema = np.asarray(data['weights']), np.asarray(data['ema'])
        if data.get('version') != self.VERSION or weights.shape != self.weights.shape or ema.shape != self.ema.shape or not np.isfinite(weights).all() or not np.isfinite(ema).all():
            raise ValueError('Interfaccia motoria incompatibile nel salvataggio.')
        candidate_rng = np.random.default_rng()
        candidate_rng.bit_generator.state = data['rng']
        for k in ['pending', 'learning', 'updates', 'baseline', 'angle', 'power', 'target_angle', 'target_power', 'aim_seconds', 'release_spikes', 'status', 'last_gradient', 'last_rates']:
            setattr(self, k, data[k])
        self.weights, self.ema, self.rng = weights, ema, candidate_rng
