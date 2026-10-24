export interface FieldEvidence<T> {
  status: "recognized" | "unknown" | "conflict" | "not_applicable";
  value?: T | null;
  [key: string]: unknown;
}

export interface PlayerEvidence {
  player_id: "p1" | "p2";
  side: "left" | "right";
  presence: "recognized" | "uncertain";
  fields: Record<string, FieldEvidence<string | number>>;
  [key: string]: unknown;
}

export interface TimelineSegment {
  start_seconds: number;
  end_seconds: number;
  stage: 1 | 2 | 3 | 4 | 5 | 6 | null;
  song: string | null;
  chart: string | null;
  players?: Partial<Record<"p1" | "p2", PlayerEvidence>>;
  results?: { players?: Partial<Record<"p1" | "p2", PlayerEvidence>>; [key: string]: unknown };
  [key: string]: unknown;
}

export interface TimelineDocument {
  method: "automatic_hud_ocr";
  segments: TimelineSegment[];
  [key: string]: unknown;
}

export function parseTimeline(value: unknown): TimelineDocument {
  if (typeof value !== "object" || value === null || !Array.isArray((value as TimelineDocument).segments)) {
    throw new Error("analysis JSON must contain a segments array");
  }
  const document = value as TimelineDocument;
  for (const [index, segment] of document.segments.entries()) {
    if (typeof segment !== "object" || segment === null ||
        !Number.isFinite(segment.start_seconds) || !Number.isFinite(segment.end_seconds) ||
        segment.start_seconds < 0 || segment.end_seconds <= segment.start_seconds ||
        !(segment.stage === null || Number.isInteger(segment.stage) && segment.stage >= 1 && segment.stage <= 6)) {
      throw new Error(`invalid segment ${index + 1}`);
    }
  }
  return document;
}

export function timestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) throw new Error("timestamp must be finite and non-negative");
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function songLabel(segment: TimelineSegment): string {
  return [segment.song ?? "Unknown song", segment.chart].filter(Boolean).join(" ");
}

export function onlyResultPlayer(segment: TimelineSegment): PlayerEvidence | undefined {
  const players = Object.values(segment.results?.players ?? {}).filter(
    (player): player is PlayerEvidence => player?.presence === "recognized",
  );
  return players.length === 1 ? players[0] : undefined;
}

export function field<T extends string | number>(player: PlayerEvidence | undefined, name: string): T | undefined {
  const evidence = player?.fields[name];
  return evidence?.status === "recognized" ? evidence.value as T : undefined;
}

function participantIds(segment: TimelineSegment): ("p1" | "p2")[] {
  return (["p1", "p2"] as const).filter(id =>
    segment.players?.[id]?.presence === "recognized" || segment.results?.players?.[id]?.presence === "recognized");
}

function participantField(segment: TimelineSegment, id: "p1" | "p2", name: string): string | undefined {
  const identity = segment.players?.[id];
  const result = segment.results?.players?.[id];
  return (identity?.presence === "recognized" ? field<string>(identity, name) : undefined)
    ?? (result?.presence === "recognized" ? field<string>(result, name) : undefined);
}

function accountParts(account: string): { nickname: string; discriminator?: string } {
  const match = account.trim().match(/^(.*?)\s*#(\d{4})$/);
  return match ? { nickname: match[1].trim(), discriminator: match[2] } : { nickname: account.trim() };
}

export function hasMultiplePlayers(document: TimelineDocument): boolean {
  const accounts = new Map<string, Set<string>>();
  for (const segment of document.segments) {
    const ids = participantIds(segment);
    if (ids.length > 1) return true;
    for (const id of ids) {
      const account = participantField(segment, id, "name");
      if (!account?.trim()) continue;
      const { nickname, discriminator } = accountParts(account);
      const discriminators = accounts.get(nickname) ?? new Set<string>();
      // An unreadable discriminator does not establish a different account.
      if (discriminator) discriminators.add(discriminator);
      accounts.set(nickname, discriminators);
    }
  }
  return accounts.size > 1 || [...accounts.values()].some(discriminators => discriminators.size > 1);
}

export interface SegmentLabelOptions {
  /** Auto adds names only for multiple accounts or simultaneous participants. */
  playerNames?: "auto" | "always" | "never";
  accountDiscriminators?: boolean;
}

function participantName(segment: TimelineSegment, id: "p1" | "p2", accountDiscriminators = false): string {
  const account = participantField(segment, id, "name");
  return account?.trim() ? (accountDiscriminators ? account.trim() : accountParts(account).nickname) : "Unknown player";
}

/** Names only; song and chart text belong to the segment label. */
export function playerNames(segment: TimelineSegment, options: { accountDiscriminators?: boolean } = {}): string {
  const ids = participantIds(segment);
  return ids.map(id => {
    const name = participantName(segment, id, options.accountDiscriminators);
    return ids.length > 1 ? `${id.toUpperCase()}: ${name}` : name;
  }).join(" / ") || "Unknown player";
}

/** Build once per recording so automatic name visibility is consistent across plays. */
export function createSegmentLabeler(document: TimelineDocument, options: SegmentLabelOptions = {}): (segment: TimelineSegment) => string {
  const showNames = options.playerNames === "always"
    || (options.playerNames !== "never" && hasMultiplePlayers(document));
  return segment => {
    const ids = participantIds(segment);
    if (ids.length <= 1) {
      return songLabel(segment) + (showNames ? ` [${playerNames(segment, options)}]` : "");
    }
    // Both charts remain visible even when a custom format explicitly hides names.
    const participants = ids.map(id => {
      return [id.toUpperCase() + ":", showNames ? participantName(segment, id, options.accountDiscriminators) : undefined,
        participantField(segment, id, "chart")].filter(Boolean).join(" ");
    });
    return `${segment.song ?? "Unknown song"} [${participants.join(" / ")}]`;
  };
}
