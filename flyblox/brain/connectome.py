"""Verified MaleCNS graph; imported upstream anatomy remains unchanged."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import sys
import numpy as np
from flyblox.config import ROOT

DATA = ROOT / 'data/malecns_v1'


def upstream():
    os.environ['STONKFLY_DATA'] = str(DATA)
    for path in [ROOT / 'external/stonkfly', ROOT / 'external/FastFly']:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


class Connectome:
    def __init__(self):
        upstream()
        path = DATA / 'graph.npz'
        if not path.exists():
            raise FileNotFoundError('Connectoma assente. Esegui setup.bat.')
        with path.open('rb') as stream:
            self.hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        locked = ROOT / 'config/graph.lock.json'
        if not locked.exists() or json.loads(locked.read_text())['sha256'] != self.hash:
            raise ValueError('Hash del grafo non verificato. Riesegui setup.bat.')
        with np.load(path, allow_pickle=False) as g:
            self.ptr, self.post, self.weight, self.ids = [g[k] for k in ['ptr', 'post', 'weight', 'ids']]
            self.retina, self.uv, self.lamina = [g[k] for k in ['retina', 'uv', 'lamina']]
        self.n = len(self.ids)
        from stonkfly.neural.common import annotations
        from stonkfly.neural.circuit import identify
        from stonkfly.neural.visual import projection
        self.annotations = annotations(self.ids)
        self.types = self.annotations.type.fillna('').to_numpy(dtype=str)
        self.sides = self.annotations.somaSide.fillna('').to_numpy(dtype=str)
        self.eye_sides = self.annotations.rootSide.fillna('').to_numpy(dtype=str)
        self.circuit = identify(self)
        self.r8, self.r8_uv, self.r8_confidence = projection(self, self.annotations)
        self.r8_channel = np.where(self.types[self.r8] == 'R8p', 2, 1)
        import pyarrow.feather as feather
        neurons = feather.read_table(DATA / 'normalized/neurons.feather').to_pandas()
        self.modulator = neurons.neurotransmitter.isin(['dopamine', 'octopamine', 'serotonin']).to_numpy(np.uint8)
        self.manifest = json.loads((DATA / 'manifest.json').read_text())
        self.positions = np.full((self.n, 3), np.nan, np.float32)
        for i, value in enumerate(self.annotations.somaLocation):
            if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3:
                self.positions[i] = value
        self.report = {**self.circuit['report'], 'graph_sha256': self.hash,
                       'retina_r1r6': len(self.retina), 'retina_r8': len(self.r8),
                       'coordinates_available': int(np.isfinite(self.positions).all(axis=1).sum())}

    def population(self, types, side=None):
        mask = np.isin(self.types, types)
        if side:
            mask &= self.sides == side
        return np.flatnonzero(mask).astype(np.int32)

    def cells(self, ix):
        return [{'id': str(self.ids[i]), 'index': int(i), 'type': self.types[i], 'side': self.sides[i]} for i in ix]
