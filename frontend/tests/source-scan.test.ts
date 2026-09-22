import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "fs";
import { join, resolve } from "path";

/**
 * Source scan: the frontend must never open a database connection,
 * never contain SQL strings, and never contain credentials.
 *
 * This test scans all source files under src/ for forbidden patterns.
 */
function getAllSourceFiles(dir: string): string[] {
  const files: string[] = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...getAllSourceFiles(fullPath));
    } else if (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) {
      files.push(fullPath);
    }
  }
  return files;
}

const srcDir = resolve(__dirname, "..", "src");

describe("source scan — no database, no SQL, no credentials", () => {
  const files = getAllSourceFiles(srcDir);

  it("found source files to scan", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  for (const file of files) {
    const content = readFileSync(file, "utf-8");
    const relPath = file.replace(srcDir + "/", "");

    it(`${relPath} contains no fetch to a database`, () => {
      // No direct PostgreSQL / MySQL connection strings
      expect(content).not.toMatch(/postgres(ql)?:\/\//i);
      expect(content).not.toMatch(/mysql:\/\//i);
      expect(content).not.toMatch(/mongodb(\+srv)?:\/\//i);
    });

    it(`${relPath} contains no SQL strings`, () => {
      // No SQL keywords that would indicate a query string
      expect(content).not.toMatch(/SELECT\s+.*\s+FROM/i);
      expect(content).not.toMatch(/INSERT\s+INTO/i);
      expect(content).not.toMatch(/UPDATE\s+.*\s+SET/i);
      expect(content).not.toMatch(/DELETE\s+FROM/i);
      expect(content).not.toMatch(/CREATE\s+TABLE/i);
    });

    it(`${relPath} contains no credential patterns`, () => {
      // No API keys, passwords, tokens in source
      expect(content).not.toMatch(/(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*["'][^"']{8,}/i);
      expect(content).not.toMatch(/AKIA[0-9A-Z]{16}/);
      expect(content).not.toMatch(/gh[pousr]_[A-Za-z0-9]{20,}/);
      expect(content).not.toMatch(/sk-[A-Za-z0-9]{20,}/);
      expect(content).not.toMatch(/-----BEGIN [A-Z ]*PRIVATE KEY-----/);
    });
  }
});
