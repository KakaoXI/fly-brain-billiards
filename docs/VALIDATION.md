# Validation and the learning question

## What has been checked

The application suite has 39 Python tests and 11 JavaScript tests. Python tests cover ball collisions, pockets, legal/illegal targets, turn changes, reward shaping, cue release, silence, pause/resume timing, memory restoration, concurrent saving, HTTP request guards and stream cleanup. JavaScript tests exercise the real input handlers in a small DOM/canvas test double and separately test aiming geometry and sample interpolation.

Repository packaging checks additionally verify that the source tree contains the required runtime modules, that local documentation links resolve, and that altered upstream checkouts are rejected. CI runs CPU/interface checks only; it does not have the full dataset or an NVIDIA GPU.

The [recorded GPU validation](../evidence/gpu-validation-2026-09-13.json) used the installed full graph and a disposable copy of a saved experiment. It recorded:

- 166,700 neurons and 25,582,938 connections;
- +10 / 2,000 neural ms, +2 / 350 ms, +0.5 / 120 ms and wrong-group 0 / no pulse;
- mean selected PAM activity of 2.5 Hz before and approximately 91.3 Hz after the high reward pulse;
- changes in the model's native plasticity and the artificial readout;
- frozen native weights in evaluation mode;
- exact restoration of the full saved state.

Those numbers verify wiring and persistence for that run. They are not a population-level neuroscience result or a billiards learning curve. The private game history is not distributed, and no pocket-success percentage is presented as a benchmark.

The standalone repository was also checked with fresh pinned upstream source clones, local copies of the already verified prepared data and the existing pinned Python environment. Its short GPU update reproduced the original graph/model hashes; all 52 application/setup/interface tests passed. This was not a fresh multi-GB dependency/data installation. The exact scope is recorded in [export smoke evidence](../evidence/export-smoke-2026-09-14.json).

## Limits of performance measurements

Physics has a 1/240-second integration step and is independent of GPU updates. Rendering, network batch frequency, wall-clock simulation speed and neural simulation speed are different measurements. A smooth table does not mean the brain runs in biological real time; a 240 Hz physics step does not mean the browser receives or draws 240 frames each second.

The motor timing regression checks that slow neural windows do not artificially stretch a ready shot's minimum wait. A cue still needs a valid action, settled joints and current motor spikes. Tests with a copy of the body measure that interface, not a guarantee on every real-game turn.

## Proposed learning evaluation — not yet implemented

Before claiming that the fly learned to play better:

1. Prepare a held-out set of reproducible table states and seeds. Keep training and evaluation states separate.
2. Compare a random action baseline, a frozen initial readout and saved trained checkpoints under the same rules and shot limits.
3. Disable learning during evaluation. Account for the remaining evaluation-time action noise, or explicitly implement a deterministic evaluation option and document that change.
4. Measure correct first-contact rate, legal own-group pocket rate, scratches, wrong-group pots, fouls and wins. Report reward alongside those metrics, since shaping reward can increase without useful pocketing.
5. Repeat across multiple seeds and training runs. Report variation and uncertainty, not just the most successful game.
6. Separate changes caused by the artificial readout from native plasticity through controlled ablations. Compare high-only, contact-plus-high and the full reward schedule.
7. Keep the same sensory interface and reject any evaluation that supplies hidden ball coordinates or a geometric shot solver to the neural policy.

Until that work is done, the accurate claim is: **the experiment connects a full retained fly connectome to a playable billiards environment with functioning reward pathways, adaptive parameters and persistent state. It has not established improved playing skill, understanding or consciousness.**
