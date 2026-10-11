// Wire types for the porch-ledger MCP tool outputs (snake_case on the wire).

export interface Resident {
  id: string;
  display_name: string;
}

export interface VisitCard {
  id: string;
  kind: string;
  start_ms: number;
  end_ms: number;
  title: string;
  span: string;
  facts: string[];
  description: string;
  hero_url: string | null;
  clip_url: string | null;
  recipient_id: string | null;
  blocks_door: boolean | null;
  claimed_by: string | null;
  provenance: string;
  version: number;
}

export interface Inbox {
  spoken: string;
  items: VisitCard[];
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isString = (value: unknown): value is string => typeof value === 'string';

const isStringOrNull = (value: unknown): value is string | null =>
  value === null || typeof value === 'string';

const isNumber = (value: unknown): value is number => typeof value === 'number';

export const isVisitCard = (value: unknown): value is VisitCard =>
  isRecord(value) &&
  isString(value.id) &&
  isString(value.kind) &&
  isNumber(value.start_ms) &&
  isNumber(value.end_ms) &&
  isString(value.title) &&
  isString(value.span) &&
  Array.isArray(value.facts) &&
  value.facts.every(isString) &&
  isString(value.description) &&
  isStringOrNull(value.hero_url) &&
  isStringOrNull(value.clip_url) &&
  isStringOrNull(value.recipient_id) &&
  (value.blocks_door === null || typeof value.blocks_door === 'boolean') &&
  isStringOrNull(value.claimed_by) &&
  isString(value.provenance) &&
  isNumber(value.version);

export const isInbox = (value: unknown): value is Inbox =>
  isRecord(value) &&
  isString(value.spoken) &&
  Array.isArray(value.items) &&
  value.items.every(isVisitCard);

export const isResidentList = (value: unknown): value is Resident[] =>
  Array.isArray(value) &&
  value.every((item) => isRecord(item) && isString(item.id) && isString(item.display_name));
