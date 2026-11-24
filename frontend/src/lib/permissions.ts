/**
 * Client copy of the backend permission matrix (backend/core/permissions.py). Used only to hide
 * or disable controls; the backend remains the authority and every action is re-checked there.
 */
import type { GlobalRole, Me, MissionRole } from "../contracts/api";

export type Permission =
  | "mission.read"
  | "mission.update"
  | "mission.control"
  | "mission.override"
  | "membership.manage"
  | "incident.acknowledge"
  | "incident.request_review"
  | "incident.resolution_report"
  | "incident.close"
  | "recommendation.decide"
  | "recommendation.confirm"
  | "alert.acknowledge"
  | "feedback.correct"
  | "metrics.read"
  | "export.operational"
  | "export.research"
  | "audit.read";

const READ: Permission[] = ["mission.read"];
export const MISSION_MATRIX: Record<MissionRole, ReadonlySet<Permission>> = {
  coordinator: new Set<Permission>([
    ...READ,
    "mission.update",
    "mission.control",
    "mission.override",
    "membership.manage",
    "incident.acknowledge",
    "incident.request_review",
    "incident.resolution_report",
    "incident.close",
    "recommendation.decide",
    "recommendation.confirm",
    "alert.acknowledge",
    "feedback.correct",
    "metrics.read",
    "export.operational",
    "audit.read",
  ]),
  operator: new Set<Permission>([
    ...READ,
    "incident.acknowledge",
    "incident.request_review",
    "incident.resolution_report",
    "alert.acknowledge",
    "feedback.correct",
  ]),
  researcher: new Set<Permission>([...READ, "metrics.read", "export.operational", "export.research"]),
  observer: new Set<Permission>(READ),
};
export const ADMIN_MISSION_PERMISSIONS: ReadonlySet<Permission> = new Set<Permission>([
  "mission.read",
  "membership.manage",
  "audit.read",
]);

export interface Identity {
  global_role: GlobalRole | null;
  memberships: { mission_id: string; role: MissionRole }[];
}

export function missionRole(me: Identity | null, missionId: string | undefined): MissionRole | null {
  if (!me || !missionId) return null;
  return me.memberships.find((m) => m.mission_id === missionId)?.role ?? null;
}

export function permissionsFor(me: Identity | null, missionId: string | undefined): Set<Permission> {
  const out = new Set<Permission>();
  if (!me) return out;
  const role = missionRole(me, missionId);
  if (role) MISSION_MATRIX[role].forEach((p) => out.add(p));
  if (me.global_role === "administrator") ADMIN_MISSION_PERMISSIONS.forEach((p) => out.add(p));
  return out;
}

export function can(me: Identity | null, permission: Permission, missionId: string | undefined): boolean {
  return permissionsFor(me, missionId).has(permission);
}

export function canCreateMissions(me: Pick<Me, "global_role"> | null): boolean {
  return me?.global_role === "administrator" || me?.global_role === "coordinator";
}

export function canReadSystemHealth(me: Pick<Me, "global_role"> | null): boolean {
  return me?.global_role === "administrator";
}

export function canReadExperiments(me: Pick<Me, "global_role"> | null): boolean {
  return me?.global_role === "administrator" || me?.global_role === "researcher";
}

/** Short explanation used next to disabled controls. */
export function deniedReason(permission: Permission): string {
  return `Your mission role does not include “${permission}”. The backend enforces this permission.`;
}
