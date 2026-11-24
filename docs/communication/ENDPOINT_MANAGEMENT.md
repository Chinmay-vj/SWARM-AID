# ENDPOINT MANAGEMENT

register binds name, role, mission, session and registration tick. Duplicate active IDs and previously used sessions are rejected. Deregistration invalidates scoped ports. Queued attempts check both sender and recipient session before delivery. Permissions are shared by role pair and payload discriminator. Phase 4 uses fixed registered participants per mission; registration messages announce those participants to the mock server. Enrollment is a trusted harness operation.
