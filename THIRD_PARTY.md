# Sources, attribution and redistribution

This repository contains the billiards application and the shared runtime files needed by it. Large data files and upstream code checkouts are downloaded separately during setup. All revisions and raw-data checksums are recorded in `config/sources.lock.json`.

| Source | Role | Pinned revision / terms |
| --- | --- | --- |
| [MaleCNS v1.0](https://male-cns.janelia.org/download/) — MaleCNS collaboration, Janelia FlyEM and collaborators | Anatomical tables, connectivity, cell types and soma annotations | The official download page specifies [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Downloaded separately; source attribution is retained. |
| [Stonkfly](https://github.com/nftechie/stonkfly) | Neural importer, graph/retinal preparation, circuit identification and centered plasticity rule | `78ef3e05ab0fa086032098558d893667068944a0`; MIT. [License notice](docs/STONKFLY-LICENSE.txt). Only its neural modules are used; no trading actions are installed or called. |
| [FastFly](https://github.com/eonfathom/FastFly) | Runtime-compiled spike-compaction kernel imported by the CuPy runtime | `c84458b4a500a3101836a4535aaef4fa8a2566cc`. Its README says MIT; the examined revision has no separate LICENSE file. Its code is fetched from upstream, not vendored in this repository. |
| [DOOMFLY](https://github.com/nftechie/doomfly) | Preceding architecture/source reference for components adapted upstream | `71ecf53d78eaffaf1a57ed7b0ccf5d458abc9f33`; MIT. Not needed by the billiards setup. |
| [Fly64](https://github.com/ornata/fly) | Historical visual/body reference only | `f2f4114e53eaa326e54129f27a5383f93c6957af`. No code or game assets are used in billiards. |

The Python/CUDA dependencies listed in `requirements.lock.txt` retain their own licenses. CUDA libraries are NVIDIA packages; the project does not redistribute or modify the installed GPU driver.

The `flyblox` modules are the local project's adaptation layer. The novel cue body, pool rules, browser interface and reward mapping are artificial components built around the anatomical simulation. None should be attributed to the dataset authors as a validated biological result.

No Roblox, Doom or Mario commercial game assets, trading credentials, local runtime environments or personal experiment memories are included. The simulated pool table and balls are drawn by application code.

Public visibility does not assign a new license to every component. No repository-wide license has been selected for the original application code; the notices above preserve upstream attribution and do not replace upstream terms.
