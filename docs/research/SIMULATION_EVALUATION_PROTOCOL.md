# Prospective field comparisons

The command and coordination plans use matched development seeds 1801 and 1802, outside the expansion matrix. The former compares direct forwarding, individual rules and multi-agent fusion with the same shared-information fleet. The latter compares independent, fixed-sector and shared-information drones, with transport but without Model 2. The PettingZoo parallel wrapper accepts external actions and returns private observation vectors and zero rewards. For integrated command experiments use the fleet runner. [Coordination plan](../../configs/experiments/field_coordination.json) · [Command plan](../../configs/experiments/phase6_field_command.json)

```powershell
.tools\phase10a-check\python.exe -m evaluation.experiment_runner --config configs/experiments/field_coordination.json --output D:\SWARM-AID-DATA\experiments\field-coordination
.tools\phase10a-check\python.exe -m evaluation.command_agent_experiments --config configs/experiments/phase6_field_command.json --output D:\SWARM-AID-DATA\experiments\field-command
```

Compute unique cells observed per reachable grid and unique source observations per delivered report. Compare delivery, loss, recovery, capture-to-receipt age and citation validity by episode, family and fleet size. Score independent evidence handling using original evidence lineage. Measure contradiction precision and recall against independently reviewed examples. False escalation and missed incident rates require adjudicated decision opportunities with a defined denominator. The evaluator's same-cell reference concerns visible presence only. Count schema, expiry and incident-revision violations separately from human-rated appropriateness. For reviewer agreement collect independent first judgments before adjudication. Report episode-level uncertainty and small strata.

The current train/validation partition holds out whole scenario families. Future independent evaluation needs unseen layouts, hazards and review labels, grouped derivative cases and a frozen protocol before unlocking protected seeds. Compare any learned assessor against the same information cutoff and baseline reports. Current measurements concern data and execution only.
