# Mission memory

Findings use an injectable MutableMapping. Incidents, review decisions and evidence references are mission scoped. History and replay journal lengths use the configured capacity. When the finding store fills, subsequent new observations produce capacity events. A trusted checkpoint serializes the scoped input journal and application history. Restore requires the same mission, roster and provider behavior. Checkpoint creation fails after journal truncation. A fresh CommandAgent resets a mission. Router queues and sessions require separate recovery.
