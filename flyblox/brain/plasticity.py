"""Uses upstream centered rule; human actions never enter this module."""
import numpy as np


class Plasticity:
    def __init__(self, graph, eta):
        from stonkfly.neural.rule import advance
        self.advance = advance
        self.circuit = graph.circuit
        self.eta = eta
        self.baseline = graph.weight[self.circuit['edges']].copy()
        self.kc_trace = np.zeros(len(self.baseline), np.float64)
        self.dan_trace = np.zeros(len(self.circuit['dan']), np.float64)
        self.u = np.zeros_like(self.kc_trace)
        self.w = np.zeros_like(self.kc_trace)

    def step(self, counts, seconds, enabled):
        # OFF and EVALUATION both freeze weights AND learning traces.
        if not enabled:
            return self.weights()
        c = self.circuit
        self.advance(self.kc_trace, self.dan_trace, self.u, self.w,
                     counts[c['pre']] / seconds, counts[c['dan']] / seconds,
                     c['gain'], seconds, self.eta, learning=True, frozen=False)
        return self.weights()

    def weights(self):
        return (self.baseline * (1 + self.w)).astype(np.float32)

    def reset(self):
        for a in [self.kc_trace, self.dan_trace, self.u, self.w]:
            a.fill(0)

    def summary(self):
        fraction = 1 + self.w
        return {'plastic_edges': len(fraction), 'changed_edges': int(np.count_nonzero(self.weights() != self.baseline)),
                'min_fraction': float(fraction.min()), 'max_fraction': float(fraction.max()),
                'mean_fraction': float(fraction.mean()), 'imitation': False}
