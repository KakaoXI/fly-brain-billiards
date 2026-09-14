# Installation and operation

## Tested environment

- Windows 11, 64-bit Python 3.12.
- NVIDIA RTX 5080, 16 GB VRAM, with an existing CUDA-compatible driver.
- CuPy `14.2.0` (`cupy-cuda13x`) and the CUDA 13 packages pinned in `requirements.lock.txt`.
- A browser supporting canvas and WebGL. If WebGL is unavailable, the neural map cannot render, but the backend is a separate process.
- Git for pinned upstream source checkouts. Node.js 22 or newer is only needed for the JavaScript tests, not to serve the application.

These are observed working conditions, not a measured minimum hardware specification. There is no full-connectome CPU gameplay mode. Linux and other NVIDIA cards may require dependency/driver adjustments and have not been validated for the full experiment.

## Automated setup

```powershell
git clone https://github.com/KakaoXI/fly-brain-billiards.git
cd fly-brain-billiards
py -3.12 scripts/bootstrap.py
```

Setup performs these steps:

1. Fetches FastFly and Stonkfly into ignored `external/` folders at the exact revisions in `config/sources.lock.json`. Existing changed checkouts are rejected rather than overwritten.
2. Creates a local `.venv` and installs the pinned Python/CUDA packages.
3. Downloads three MaleCNS tables from the pinned public release URLs and verifies their byte sizes and SHA-256 values.
4. Runs the pinned upstream importer and retinal/graph preparation. The imported graph includes all connections retained by that importer, not a billiards-specific subset.
5. Runs a short GPU installation check on a new in-memory neural instance. No user game or checkpoint is loaded or changed by this check.

The raw tables total 1,109,008,094 bytes. Keep additional free disk space for the Python/CUDA environment, normalized tables, graph and local memories. Data hashes are compared with the upstream/project lock; those locks are reproducibility records, not publisher digital signatures.

You can inspect setup without starting it:

```powershell
py -3.12 scripts/bootstrap.py --help
```

`--sources-only` fetches/verifies only the two upstream Git repositories. `--skip-pip` reuses a prepared environment, while still verifying/preparing data and running the installation check.

## Launch and stop

```powershell
.\.venv\Scripts\python.exe -m biliardo.launcher
```

The launcher reuses an already running compatible local instance, or starts the service and opens `http://127.0.0.1:8766/`. `start.bat` is the Windows shortcut. Keep the service terminal open while playing.

Save with **Salva memoria** (“Save memory”) and wait for the saved filename. Ctrl+C requests an orderly service shutdown. Do not kill the process or power off while it is saving. Closing only the browser tab does not stop the backend.

Common Italian labels: **Pausa** = pause, **Riprendi** = resume, **Apprendimento** = learning, **Nuova partita** = new game, **Archivio** = saved-memory archive. The human uses solids; the fly uses stripes. A new table keeps the learned parameters.

## First run and existing memories

A clean checkout has no local memory. It creates a new neural experiment and saves under `biliardo/saves/`. Data, environments, generated logs, credentials and personal `.save` files are ignored by Git.

To migrate an existing compatible billiards experiment, stop both instances and copy the desired `.save` to the new installation's `biliardo/saves/latest.save`. Keep a backup. Model-source, configuration and graph hashes must match. Do not edit the hashed neural modules just to make an old memory pass its integrity check.

The original fingerprint includes raw source bytes from the upstream learning rule. Setup pins the upstream checkout's line-ending convention as well as its revision; manually cloning with a different convention can change this fingerprint. Application Python files use LF. Dataset rebuilding can also affect the recorded graph hash; a save will not silently load against another graph.

The retained server can import `checkpoints/latest.npz` if such a compatible file is deliberately present on its first start. The repository does not supply that file, and normally starts fresh. This preserves the original project's optional migration path without bundling its previous Roblox session.

## CPU-only development tests

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m unittest discover -s biliardo/tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check biliardo/dist/app.js
npm test
```

These tests use small synthetic graphs and do not require data downloads or a GPU. They cannot establish full-model throughput or learned skill. Installing only the test requirements is insufficient to run the full game.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Connectome missing or graph hash rejected | Complete setup; preserve any altered files before retrying. Do not bypass verification. |
| CUDA / NVRTC cannot load | Use the tested Python version and pinned environment; check that your existing NVIDIA driver supports it. Setup does not install a driver. |
| Browser cannot connect | Keep the backend terminal open and inspect `biliardo/logs/server.log`; verify port 8766 is free. |
| Fly is waiting | Check pause, whose turn it is, whether balls are still moving, and the body's status. No current descending spikes means no motor release. |
| A save is incompatible | Verify model, configuration and graph identity, including upstream source revision/line endings. Preserve the original installation and file. |
| Brain map is unavailable | Check WebGL support. Soma coordinates exist for 139,662 neurons; the remaining simulated neurons have no invented display positions. |

For read-only latency checks while the service is running, use `python -m biliardo.tests.stream_probe` or `python -m biliardo.tests.motor_probe`. The latter replays live spikes into a disposable copy of the motor body and never submits a game command.
