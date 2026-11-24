# Model 2 integration

AssignmentFixture.command_snapshot returns copied command-visible mission, availability, reported cells, observation evidence, task dispositions and conflict records. The fixture also retains original envelopes in SimulationNetwork.history. A future consumer must resolve revisions and human authority before consequential decisions. The current snapshot is an in-process interface.

```mermaid
flowchart LR
  Reports --> CommandHistory --> Snapshot --> FutureModel2
  FutureModel2 --> HumanReview
```
