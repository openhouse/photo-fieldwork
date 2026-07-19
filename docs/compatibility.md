# Compatibility

Photo Fieldwork versions seven contracts independently.

| Contract | Current | Compatibility rule |
| --- | ---: | --- |
| Core CLI | 0.2.x | Minor releases may add commands; breaking flags require a major release. |
| Selection config | 1 | Unknown schema versions fail before selection. |
| Machine profile | 1 | Populated profiles remain outside Git. |
| Core catalog plans | 2 | Plans require source, master, config, feedback, final-evaluation, validation, release-class, and content identities. |
| Apple helper snapshot plans and receipts | 2 | Writers reject unknown plan versions and receipts echo the attempt and release binding. |
| Helper capability | 3 | Production receipts require capability 3; operational probes remain backward-compatible with capability 2. |
| Run receipts | 1 | Historical receipts are append-only and are never rewritten during migration. |

An installed macOS helper has a stable permission identity. Rebuilding or changing its bundle identifier is an explicit operator action and may require Photos authorization again.
