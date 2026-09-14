"""Atomic local .save archives. No pickle, scripts or browser-only memory."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import zipfile
import numpy as np

SAVE_VERSION = 1


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def save_archive(path, brain, game, body, retina, extra):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pool-', dir=path.parent) as directory:
        checkpoint = Path(directory)/'brain.npz'
        brain.save(checkpoint, {'application': 'biliardo', 'version': SAVE_VERSION})
        state = {'game': game.state(), 'body': body.state(),
                 'retina_previous': retina.previous.tolist() if retina.previous is not None else None,
                 'extra': extra}
        payloads = {'brain.npz': checkpoint.read_bytes(), 'state.json': encode(state)}
        manifest = {'version': SAVE_VERSION, 'graph': brain.graph.hash, 'model': brain.model_hash,
                    'sha256': {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}}
        temp = Path(directory)/'archive.save'
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_STORED) as archive:
            for k, v in payloads.items():
                archive.writestr(k, v)
            archive.writestr('manifest.json', encode(manifest))
        with temp.open('r+b') as stream:
            os.fsync(stream.fileno())
        # Keep the last successful autosave as a recovery copy.
        if path.name == 'latest.save' and path.exists():
            backup = path.with_name('previous.save')
            import shutil
            shutil.copy2(path, backup)
        os.replace(temp, path)


def load_archive(path, brain, graph):
    from .game import Game
    from .body import NeuralBody
    with zipfile.ZipFile(path) as archive:
        expected = {'manifest.json', 'brain.npz', 'state.json'}
        if set(archive.namelist()) != expected or len(archive.namelist()) != 3 or any(i.file_size > 100_000_000 for i in archive.infolist()):
            raise ValueError('Archivio .save non valido o troppo grande.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('version') != SAVE_VERSION or manifest.get('graph') != graph.hash or manifest.get('model') != brain.model_hash:
            raise ValueError('Salvataggio incompatibile con questo connectoma/modello.')
        payloads = {k: archive.read(k) for k in ['brain.npz', 'state.json']}
        if any(hashlib.sha256(v).hexdigest() != manifest['sha256'].get(k) for k, v in payloads.items()):
            raise ValueError('Salvataggio danneggiato: checksum non valido.')
    state = json.loads(payloads['state.json'])
    game = Game.restore(state['game'])
    body = NeuralBody(graph)
    body.restore(state['body'])
    previous = state['retina_previous']
    if previous is not None:
        previous = np.asarray(previous, np.float32)
        if previous.shape != (90, 160) or not np.isfinite(previous).all():
            raise ValueError('Stato della retina non valido.')
    # Brain.load validates every array before changing the live neural state.
    with tempfile.TemporaryDirectory(prefix='pool-load-', dir=Path(path).parent) as directory:
        checkpoint = Path(directory)/'brain.npz'
        checkpoint.write_bytes(payloads['brain.npz'])
        brain.load(checkpoint)
    return game, body, previous, state['extra']
