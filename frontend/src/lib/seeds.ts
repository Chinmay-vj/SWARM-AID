/**
 * Missions created from the dashboard are development runs. The seed must be chosen explicitly:
 * scenario defaults are historical values and are never filled in.
 */
export function developmentSeedError(value: string): string | null {
  const seed = Number(value);
  if (!value.trim() || !Number.isInteger(seed) || seed < 12000 || seed > 12999)
    return "Seed: enter a development seed from 12000 to 12999.";
  return null;
}
