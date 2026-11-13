import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";

export function save(path: string, library: unknown): void {
  const temporary = path + ".tmp";
  writeFileSync(temporary, JSON.stringify(library, null, 2));
  renameSync(temporary, path);
}

export function load<T>(path: string, fallback: T): T {
  return existsSync(path) ? (JSON.parse(readFileSync(path, "utf8")) as T) : fallback;
}
