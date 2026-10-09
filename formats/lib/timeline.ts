export interface FieldEvidence<T> {
  status: "recognized" | "unknown" | "conflict" | "not_applicable";
  value?: T | null;
  [key: string]: unknown;
}

export interface ResultPlayer {
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
  players?: Partial<Record<"p1" | "p2", ResultPlayer>>;
  results?: { players?: Partial<Record<"p1" | "p2", ResultPlayer>>; [key: string]: unknown };
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

export function label(segment: TimelineSegment): string {
  return [segment.song ?? "Unknown song", segment.chart].filter(Boolean).join(" ");
}

export function onlyPlayer(segment: TimelineSegment): ResultPlayer | undefined {
  const players = Object.values(segment.results?.players ?? {}).filter(
    (player): player is ResultPlayer => player?.presence === "recognized",
  );
  return players.length === 1 ? players[0] : undefined;
}

export function field<T extends string | number>(player: ResultPlayer | undefined, name: string): T | undefined {
  const evidence = player?.fields[name];
  return evidence?.status === "recognized" ? evidence.value as T : undefined;
}


export function hasDifferentPlayers(document: TimelineDocument): boolean {
  const names = new Set(document.segments.flatMap(segment =>
    Object.values(segment.players ?? {}).map(player => field<string>(player, "name")).filter(Boolean)));
  return names.size > 1 || document.segments.some(segment =>
    Object.values(segment.results?.players ?? {}).filter(p => p?.presence === "recognized").length > 1 ||
    Object.values(segment.players ?? {}).filter(p => p?.presence === "recognized").length > 1);
}

export function playerLabel(segment: TimelineSegment, includeNames: boolean): string {
  if (!includeNames) return label(segment);
  const ids = (["p1", "p2"] as const).filter(id =>
    segment.players?.[id]?.presence === "recognized" || segment.results?.players?.[id]?.presence === "recognized");
  const names = ids.map(id => {
    const name = field<string>(segment.players?.[id], "name") ?? "Unknown player";
    const chart = field<string>(segment.players?.[id], "chart") ?? field<string>(segment.results?.players?.[id], "chart");
    return ids.length > 1 ? [id.toUpperCase() + ":", name, chart].filter(Boolean).join(" ") : name;
  });
  const title = ids.length > 1 ? segment.song ?? "Unknown song" : label(segment);
  return `${title} [${names.length ? names.join(" / ") : "Unknown player"}]`;
}
