# Dashboard read model

The .command.json snapshot has schema_version 1, mission UUID, last message time, lifecycle state, review_queue, world, priorities, operator priorities, health, task reports, findings, incidents, revisions, decisions and events. The queue combines current recommendations, dispositions and supporting priority reasons. A client must bind a decision to the displayed recommendation ID and incident revision. Mission milliseconds and exclusive deadlines use simulator time; delivery history is exported separately.
