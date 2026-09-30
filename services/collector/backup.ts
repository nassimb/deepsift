/** Consistent online backup of the collector store (safe while the collector runs): SQLite `VACUUM INTO`.
 *    node services/collector/backup.ts                    # → <db dir>/backups/observatory-YYYYMMDDTHHMM.sqlite, keeps 7
 *  env: COLLECTOR_DB, COLLECTOR_BACKUP_DIR, COLLECTOR_BACKUP_KEEP (7) */
import { mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { DatabaseSync } from "node:sqlite";

const db = process.env.COLLECTOR_DB ?? join(import.meta.dirname, "../../live_observatory/data/observatory.sqlite");
const dir = process.env.COLLECTOR_BACKUP_DIR ?? join(dirname(db), "backups");
const keep = Number(process.env.COLLECTOR_BACKUP_KEEP ?? 7);
mkdirSync(dir, { recursive: true });
const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 13);
const out = join(dir, `observatory-${stamp}.sqlite`);
rmSync(out, { force: true });
const src = new DatabaseSync(db, { readOnly: true });
src.exec("PRAGMA busy_timeout=10000");
src.prepare("VACUUM INTO ?").run(out);
src.close();
const check = new DatabaseSync(out, { readOnly: true });
const ok = (check.prepare("PRAGMA integrity_check").get() as { integrity_check: string }).integrity_check;
const events = (check.prepare("SELECT COUNT(*) AS n FROM events").get() as { n: number }).n;
check.close();
if (ok !== "ok") { console.error(`backup integrity check FAILED: ${ok}`); process.exit(1); }
const old = readdirSync(dir).filter((f) => /^observatory-\d{8}T\d{4}\.sqlite$/.test(f)).sort().reverse().slice(keep);
for (const f of old) rmSync(join(dir, f));
console.log(`backup ok → ${out} (${(statSync(out).size / 1e6).toFixed(1)} MB, ${events} events, integrity ok); pruned ${old.length}`);
