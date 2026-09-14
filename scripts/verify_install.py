"""Check the installed graph and a short full-network GPU update."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import numpy as np
    from flyblox.config import load_config
    from flyblox.brain.connectome import Connectome
    from flyblox.brain.runtime import Brain
    graph = Connectome()
    brain = Brain(graph, load_config())
    counts, elapsed = brain.step(np.full(len(graph.retina), .2, np.float32),
                                 np.full(len(graph.r8), .2, np.float32), 40, learning=False)
    result = {'neurons': graph.n, 'edges': len(graph.post), 'graph_hash': graph.hash,
              'model_hash': brain.model_hash, 'spikes': int(counts.sum()),
              'wall_ms': elapsed*1000, 'saved_memory_modified': False}
    if graph.n != 166700 or len(graph.post) != 25582938:
        raise RuntimeError('Prepared graph counts differ from the pinned experiment.')
    if not np.isfinite(counts).all():
        raise RuntimeError('Neural update contains invalid values.')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
