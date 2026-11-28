"""Bind owner-confirmed external WiSARD permission to the two prepared releases."""
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.model2 import digest
from evaluation.data.release_authorization import (
    AuthorizationBundle,
    AuthorizationRecord,
    WiSARDProjectPermission,
    manifest_sha256,
)


def generate(root: Path) -> None:
    evidence = root / 'runs/phase11g8'
    permission = json.loads((evidence / 'publisher_permission.json').read_bytes())
    privacy = json.loads((evidence / 'privacy_review.completed.json').read_bytes())
    review = evidence / 'visual_review/completed_review.json'
    if privacy['annotation_review_sha256'] != digest(review):
        raise ValueError('review checksum mismatch')
    if privacy['decision'] != 'PROJECT_OWNER_PRIVACY_CONDITIONS_ACCEPTED':
        raise ValueError('privacy approval missing')
    if permission['evidence_status'] != 'Project-owner-reported publisher permission':
        raise ValueError('publisher permission confirmation missing')
    owner = privacy['reviewer']
    now = datetime.now(UTC)
    confirmation = WiSARDProjectPermission(project='SWARM-AID', owner_identity=owner,
        external_reference='Externally held publisher reply: ' + permission['sender'] + ' / ' + permission['reply_date'],
        confirmed_at=now, publisher_permission_confirmed=True, imagery_and_annotations_covered=True,
        scope='local_noncommercial_training_and_evaluation')
    for modality in ('visual', 'thermal'):
        release = evidence / 'prepared-v1' / modality
        registry = Registry.model_validate_json((release / 'registry.json').read_bytes())
        inputs = Manifest.model_validate_json((release / 'operational.json').read_bytes())
        targets = Manifest.model_validate_json((release / 'targets.json').read_bytes())
        candidate = json.loads((release / 'candidate.json').read_bytes())
        entry = registry.datasets[0].model_copy(update={'privacy_status': 'approved', 'verification': 'verified'})
        updated = registry.model_copy(update={'datasets': (entry,)})
        refs = tuple(f'sha256:{digest(evidence / name)}' for name in (
            'publisher_permission.json', 'privacy_review.completed.json', 'project_policy_approval.json'))
        auth = AuthorizationRecord(schema_version='phase10i-authorization-1.1',
            authorization_id=f'wisard-{modality}-external-permission-v1', dataset_id='wisard',
            dataset_version=inputs.dataset_version, task_id=candidate['task'],
            candidate_manifest_sha256=digest(release / 'candidate.json'),
            training_manifest_sha256=manifest_sha256(inputs),
            training_targets_manifest_sha256=manifest_sha256(targets),
            approved_usage_scopes=('local_training', 'local_evaluation'), governance_decision='approved',
            governance_evidence_refs=refs, privacy_decision='approved',
            cloud_processing_decision='not_authorized', redistribution_decision='not_authorized',
            human_review_evidence_refs=(f'sha256:{digest(review)}',),
            authorizing_owner_identity=owner, owner_authorization_ref='Current owner instruction: approve it; external publisher permission workflow',
            reviewer_identity=owner, authorized_at=now, decision='APPROVE',
            decision_rationale='Owner-confirmed externally held project-specific publisher permission; general licence remains unverified. Existing sampled review and integrity evidence reused.',
            restrictions=('Local D-drive non-commercial civilian academic research only',
                'Attribution required; no cloud uploads or raw redistribution',
                'No facial recognition or personal identification; aggregate publication only',
                'Retention: project completion plus 12 months, subject to review',
                'Reserved test protected; separate training-start decision required'),
            wisard_project_permission=confirmation)
        bundle = AuthorizationBundle(schema_version='phase10i-authorization-bundle-1.1', records=(auth,))
        (release / 'registry.json').write_text(updated.model_dump_json(indent=2), encoding='utf8')
        (release / 'authorization_bundle.json').write_text(bundle.model_dump_json(indent=2), encoding='utf8')
        print(f'{modality}: authorization generated; general licence unverified; start approval separate', flush=True)


if __name__ == '__main__':
    generate(Path('D:/SWARM-AID-DATA'))
