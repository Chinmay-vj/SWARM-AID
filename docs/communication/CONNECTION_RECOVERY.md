# CONNECTION RECOVERY

Availability sampling distinguishes simulated link silence from agent health. Heartbeat age can mark an endpoint degraded. The drone also checks the age of acknowledged heartbeat creation time. At loss the adapter clears cached authority, records a lifecycle hold when applicable and supplies the local offline signal to the safety controller. Incoming valid retained packets may be processed when the link reopens. Expired commands cannot execute. Restarting a process requires a fresh mission session; persistent cursor reconciliation remains future work.

```mermaid
stateDiagram-v2
connected --> degraded: heartbeat stale
degraded --> connected: fresh heartbeat
connected --> disconnected: outage
disconnected --> reconnecting: link available
reconnecting --> connected: same session
```

```mermaid
sequenceDiagram
participant D as Drone
participant R as Router
participant C as Mock command
R-->>D: Offline status
D->>D: Clear lease
D->>R: Buffer reports
R->>C: Restore and deliver unexpired reports
C->>R: ACK
```
