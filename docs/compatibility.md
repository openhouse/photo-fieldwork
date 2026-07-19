# Compatibility

Photo Fieldwork versions seven contracts independently.

| Contract | Current | Compatibility rule |
| --- | ---: | --- |
| Core CLI | 0.2.x | Minor releases may add commands; breaking flags require a major release. |
| Selection config | 1 | Unknown schema versions fail before selection. |
| Machine profile | 1 | Populated profiles remain outside Git. |
| Core catalog plans | 2 | Plans require source, master, final-evaluation, validation, and content identities. |
| Apple helper plans and receipts | 1 | Writers reject unknown plan versions. |
| Helper capability | 2 | Operational probe must report capability 2 before whole-library or cache-aware production work. |
| Run receipts | 1 | Historical receipts are append-only and are never rewritten during migration. |

An installed macOS helper has a stable permission identity. Rebuilding or changing its bundle identifier is an explicit operator action and may require Photos authorization again.
