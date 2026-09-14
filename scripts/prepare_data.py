"""Verified public MaleCNS download, upstream import and sensory preparation."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'malecns_v1'
UPSTREAM = ROOT / 'external' / 'stonkfly'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    lock_path = ROOT / 'config/sources.lock.json'
    if lock_path.exists():
        expected = json.loads(lock_path.read_text())
        for name in ['FastFly', 'stonkfly']:
            actual = subprocess.check_output(['git','-C',str(ROOT/'external'/name),'rev-parse','HEAD'],text=True).strip()
            dirty = subprocess.check_output(['git','-C',str(ROOT/'external'/name),'status','--porcelain','--untracked-files=no'],text=True).strip()
            if actual != expected[name]['commit'] or dirty:
                raise RuntimeError(f'Upstream checkout changed: {name}. Restore the pinned revision after preserving local work.')
    DATA.mkdir(parents=True, exist_ok=True)
    sources = json.loads((UPSTREAM / 'stonkfly/neural/sources.lock.json').read_text())
    for name, info in sources.items():
        target = DATA / name
        if not target.exists():
            temporary = target.with_suffix('.partial')
            print(f'Download {name}: {info["bytes"]/1e6:.1f} MB', flush=True)
            with urllib.request.urlopen(info['url'], timeout=120) as response, temporary.open('wb') as stream:
                while chunk := response.read(8 * 1024 * 1024):
                    stream.write(chunk)
            if digest(temporary) != info['sha256']:
                raise RuntimeError(f'Incorrect checksum: {temporary}')
            temporary.replace(target)
        if target.stat().st_size != info['bytes'] or digest(target) != info['sha256']:
            raise RuntimeError(f'Invalid dataset: {target}. Preserve the file before downloading again.')
        print(f'SHA256 OK: {name}', flush=True)
    (DATA / 'source.lock.json').write_text(json.dumps(sources, indent=2))
    os.environ['STONKFLY_DATA'] = str(DATA)
    sys.path.insert(0, str(UPSTREAM))
    from stonkfly.neural.connectome import import_graph
    from stonkfly.neural.prepare import prepare
    if not (DATA / 'normalized/report.json').exists():
        print('Running the pinned Stonkfly importer...', flush=True)
        import_graph()
    graph_existed = (DATA / 'graph.npz').exists()
    if not graph_existed:
        print('Preparing the pinned graph and retinal projection...', flush=True)
        prepare()
    lock = expected.copy() if lock_path.exists() else {}
    for name in ['FastFly', 'stonkfly']:
        path = ROOT / 'external' / name
        lock[name] = {'commit': subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip(),
                      'url': subprocess.check_output(['git', '-C', str(path), 'remote', 'get-url', 'origin'], text=True).strip()}
    lock['MaleCNS'] = sources
    (ROOT / 'config/sources.lock.json').write_text(json.dumps(lock, indent=2))
    graph_lock=ROOT / 'config/graph.lock.json'
    current_hash=digest(DATA / 'graph.npz')
    if graph_existed and graph_lock.exists() and json.loads(graph_lock.read_text())['sha256']!=current_hash:
        raise RuntimeError('Compiled graph changed: a replacement checksum is not accepted automatically.')
    graph_lock.write_text(json.dumps({'sha256': current_hash, 'dataset': 'MaleCNS v1.0'}, indent=2))
    print('MaleCNS ready.', flush=True)


if __name__ == '__main__':
    main()
