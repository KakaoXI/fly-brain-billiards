# Architecture

## Four separate responsibilities

The environment decides what physically happened. The neural simulation responds to pixels. The artificial body translates neural signals into a cue action. The reward system changes the learning signals after the outcome. These responsibilities are kept distinct so a successful shot cannot be silently supplied by a geometric solver.

### Environment and human input

`Game` owns a 1000 × 500 table, sixteen balls of radius 11, six pockets, collision response, friction and the simplified rules. The server accepts only a human angle/power command or cue placement when allowed. Reward values cannot be submitted by the browser.

Human input is continuous: hover to aim, press and pull backward along the cue direction, then release. A simple click does not shoot; Escape cancels. The aiming guide intersects the first ball or rail and estimates the struck ball's outgoing direction. This guide is a human interface feature, excluded from `render_eye()`.

### Sensory input and neural computation

`render_eye()` produces an artificial overhead table image. `Retina.transform()` resizes it to 160 × 90, converts image luminance/color and samples the imported receptive-field coordinates. Its previews include per-eye retinal samples and a temporal-contrast image. Temporal contrast is a motion proxy, not semantic object detection.

The installed projection selects 3,335 R1–R6 receptors and 811 R8 receptors. Their projection is inferred from connectome annotations and contacts; it is not a measured living fly eye camera calibration.

The GPU runtime simulates the whole **retained imported graph**, with no gameplay-specific neuron pruning. Each outer update advances 40 neural ms using an internal 0.5 ms integration step. Leaky integrate-and-fire neurons, fixed synaptic delays, selected adaptation, transmitter sign assumptions and current-based input form an approximation to biological dynamics. The model is not a conductance-complete reconstruction of every cell or synapse.

`graph.npz` is verified against `config/graph.lock.json`. Source-file and configuration hashes are recorded with memories. Changing those inputs can make old saves incompatible by design.

### Motor interface

The cue body receives neural spike features, not game coordinates. It combines:

- 32 coarse spatial retinal rate bins;
- eight descending/motor population channels;
- KC, PAM and PPL population channels;
- a constant bias.

The resulting 44-dimensional vector feeds a 2 × 44 weight matrix. Its two outputs parameterize cue angle and bounded power. Exploration samples an action, which is retained until the shot outcome. The motors rotate and load the cue toward those targets only when the descending populations emit spikes.

A shot is released when the cue has settled, at least 80 descending spikes have accumulated and the current observation also contains descending spikes. Silence cannot trigger a timeout shot. There is no additional fixed delay once the cue is ready. This is an artificial actuator contract, not an identified anatomical “play billiards” pathway.

The motor clock counts the complete active update interval. Pausing, loading, saving or changing turns invalidates inappropriate old observations; time spent paused or in another turn is not converted into a sudden motor jump.

### Learning and reward

The physics worker queues completed outcomes. The neural worker processes the queue, updates the adaptive body and schedules a PAM current pulse when eligible. The pulse lasts a bounded number of **neural milliseconds**. The body readout and native KC→MBON learning are described in [LEARNING.md](LEARNING.md).

## Concurrency and smoothness

- The neural worker owns the GPU, retinal processing, plasticity and cue-policy updates.
- The physics worker advances fixed 1/240-second steps using accumulated real elapsed time.
- An HTTP event stream sends batches of recent physics samples.
- The browser renders independently through `requestAnimationFrame`, interpolating a short buffer of authoritative samples.
- Detailed neural telemetry is refreshed less frequently than the rendered table.

Physics continues during neural computation and disk compression. The simulation uses a bounded catch-up interval to avoid extreme catch-up after a long stall; 240 Hz is a numerical step size, not a guaranteed real-time throughput on every computer.

The HTTP guard is direct ASGI middleware: host/origin/token checks run without routing every streamed frame through intermediate task queues. Stream disconnection is handled by `StreamingResponse`. On Windows the server requests a 1 ms timer period during its lifetime; Python's thread-switch interval is also shortened. Neither modifies the model's neural timestep or the computer's GPU driver.

Each restart or memory load generates a new stream epoch. The browser discards samples from an old epoch instead of interpolating across unrelated positions.

## Persistence and shutdown

`save_archive()` writes `brain.npz`, `state.json` and `manifest.json` into a temporary ZIP and atomically replaces the final file. The manifest checksums both payloads and identifies the graph/model. The previous successful autosave is retained separately.

Pending shot outcomes are committed before snapshot creation, so a restored cue cannot remain stuck believing it has fired while the game is already waiting for a new shot. Neural/body state remains owned by the saving worker; a detached game snapshot allows the independent physics worker to continue while compression and I/O run.

Loading validates archive membership, size, hashes, array shapes and numeric state before applying neural arrays. Saves do not use pickle. Loading a save is an explicit local operation; files are not executable plugins.

The server binds to localhost and checks a per-session token on mutation requests. This is a local single-user application, not a hardened public multiplayer service. Do not expose port 8766 as an Internet endpoint without designing authentication and resource controls for that new use case.

## Scientific boundaries

Anatomical connectivity constrains the neural computation, but it does not supply a billiards-specific sensory representation, the missing biological body or a measured learning objective. The camera projection, motor pooling, action readout, reward mapping and many cell dynamics are artificial. Neuron activity in the visualizer is actual simulated activity; it is not evidence of consciousness or a report of an animal's experiences.
