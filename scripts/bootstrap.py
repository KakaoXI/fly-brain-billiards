"""Install the pinned local experiment; no game is started by setup."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCES = ('FastFly', 'stonkfly')


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def checkout(name, spec):
    path = ROOT/'external'/name
    git = shutil.which('git')
    if not git:
        raise RuntimeError('Install Git, then run setup again.')
    if not path.exists():
        # The original model hashes raw source bytes, including the upstream
        # rule's CRLF checkout. Pin this independently of global Git settings.
        run(git, '-c', 'core.autocrlf=true', 'clone', '--no-checkout', spec['url'], path)
        run(git, '-C', path, 'config', 'core.autocrlf', 'true')
        run(git, '-C', path, 'checkout', '--detach', spec['commit'])
    actual = subprocess.check_output([git, '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output([git, '-C', str(path), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
    if actual != spec['commit'] or dirty:
        raise RuntimeError(f'{name} is not the clean pinned revision. Preserve any local work before replacing it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-pip', action='store_true', help='Reuse an already installed .venv')
    parser.add_argument('--sources-only', action='store_true', help='Fetch/verify upstream Git sources without installing packages or downloading data')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use Python 3.12 (64-bit) for the pinned environment.')
    for folder in ['external', 'data', 'biliardo/logs', 'biliardo/saves']:
        (ROOT/folder).mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT/'config/sources.lock.json').read_text(encoding='utf-8'))
    for name in RUNTIME_SOURCES:
        checkout(name, lock[name])
    if args.sources_only:
        print('Pinned runtime sources are ready.')
        return
    environment = ROOT/'.venv'
    python = environment/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    if not args.skip_pip:
        run(python, '-m', 'pip', 'install', '--only-binary=:all:', '-r', 'requirements.lock.txt')
    run(python, ROOT/'scripts/prepare_data.py')
    run(python, ROOT/'scripts/verify_install.py')
    print('Setup complete. Start with: .venv\\Scripts\\python.exe -m biliardo.launcher')


if __name__ == '__main__':
    main()
