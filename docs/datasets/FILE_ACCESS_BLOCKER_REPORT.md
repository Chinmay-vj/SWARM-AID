# Phase 10I-A Windows file-access diagnosis

## Read-only findings

The current process identity is `MSI\Local User` (SID suffix `-1021`). Its
Windows token is at medium integrity; `BUILTIN\Administrators` is present as a
deny-only group, so this process is not elevated. No elevation, ownership
change, ACL change or permission bypass was attempted.

| Path | Existence | Read / ACL result | Owner result |
|---|---|---|---|
| `D:\SWARM-AID\datasets\processed\model2\pilot-1` | Directory exists. | Direct `icacls` and `Get-Acl` return access denied. Directory contents cannot be enumerated. | Target owner and DACL could not be read. The readable parent `...\processed\model2` is owned by `MSI\CodexSandboxOffline`. |
| `D:\SWARM-AID\runs\phase10g-alert-v2` | Directory exists. | Direct `icacls` and `Get-Acl` return access denied. | Target owner and DACL could not be read. The readable parent `D:\SWARM-AID\runs` is owned by `MSI\CodexSandboxOffline`. |
| `D:\SWARM-AID\runs\phase10g-alert-v2\matched.jsonl` | Indeterminate; the containing directory cannot be listed and direct lookup returns access denied. | File cannot be opened or hashed. | Unavailable. |
| `D:\SWARM-AID\runs\phase10g-alert-v2\summary.json` | Indeterminate; the containing directory cannot be listed and direct lookup returns access denied. | File cannot be opened or hashed. | Unavailable. |
| `D:\SWARM-AID\runs\phase10h-alert-v1` | Directory exists. | Direct `icacls` and `Get-Acl` return access denied. | Target owner and DACL could not be read. The readable parent `D:\SWARM-AID\runs` is owned by `MSI\CodexSandboxOffline`. |
| `D:\SWARM-AID\runs\phase10h-alert-v1\alert-review.jsonl` | Indeterminate; the containing directory cannot be listed and direct lookup returns access denied. | File cannot be opened or hashed. | Unavailable. |
| `D:\SWARM-AID\runs\pytest\cache` | Directory exists. | Current storage scan cannot enumerate it; `Get-Acl` is denied. | Target owner and DACL could not be read. This additional repository-run cache is not needed to complete the audit; it was left untouched. |

Read-only inspection of the two readable parent directories showed inherited
entries for `Authenticated Users` and `Users`; this does not establish the
effective DACL on the inaccessible child directories. The target security
descriptors themselves could not be obtained. Therefore the confirmed result
is a Windows effective-access denial for this process. Available evidence does
not distinguish a protected/explicit child DACL from a host-level access
boundary. It is not a missing `pilot-1` directory or a Python path-resolution
failure.

The Phase 10H alert summary and the 44-case review queue remain prior audit
evidence only. The alert-journal lineage was **not rerun** in Phase 10I-A;
no priority case was independently reclassified, and the queue was not changed.
Presence of a person in imagery is not treated as confirmed distress.

## Authorized owner action

An authorized data owner must either provide read-only access for the current
identity (`MSI\Local User`) to only the following directories and their
contents, or place read-only copies of the required audit artifacts in an
already-authorized D-drive review location:

- `D:\SWARM-AID\datasets\processed\model2\pilot-1`
- `D:\SWARM-AID\runs\phase10g-alert-v2`
- `D:\SWARM-AID\runs\phase10h-alert-v1`

Grant only list/read/execute access (`RX`) on those exact paths, if the owner
and data-governance policy authorize it. Do not grant Modify/Full Control, do
not change a parent ACL, do not take ownership, and do not elevate this process.
Once access is authorized, rerun the pilot storage/exclusion checks and the
existing alert verification against the original journals, preserving the
current review queue.

Until then, the protected pilot directory size and the alert-journal contents
remain unknown. The repository processed-storage measurement is partial, not
zero. The `runs\pytest\cache` measurement is also partial; Phase 10I-A checks
can direct their own test cache to the D-drive audit directory without
changing this protected path.
