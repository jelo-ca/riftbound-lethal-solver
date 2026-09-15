// Derives the web layer's display map from the shared card cache at
// <repo>/data/cards-ogn.json, trimmed to the cards the puzzles actually
// reference, and writes src/data/card-names.json.
//
// This used to call the Riftcodex API directly, once per referenced card.
// It now reads the cache that `python -m solver.fetch_cards` produces —
// one bulk pull of the whole Origins set, committed to the repo, shared
// with the solver (see solver/engine/card_names.py). No network access
// here at all, so it is safe to run at any time, including in CI or on a
// plane. See design/01-data-sources.md.
//
// The trim matters: the cache holds the full set (~350 printings) because
// pool expansion needs to browse it, but the browser only ever needs the
// dozen-odd cards a puzzle shows. Re-run this whenever a new puzzle
// introduces a card, and re-run the Python ingestion only when the SET
// gains printings.
//
// solver/ is off-limits to write (a generation batch may be running
// against it in another session); this only reads puzzles/*.json and
// data/, both read-only contracts.

import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, "..", "..");
const PUZZLES_DIR = path.join(REPO_ROOT, "puzzles");
const CACHE_PATH = path.join(REPO_ROOT, "data", "cards-ogn.json");
const OUTPUT_PATH = path.join(__dirname, "..", "src", "data", "card-names.json");

// Ids the engine invents that have no printing behind them. Kept in step
// with PLACEHOLDER_NAMES in solver/engine/card_names.py.
const PLACEHOLDERS = {
	"generic-opponent": { name: "Opponent Unit", text: null, type: null, placeholder: true },
};

function collectCardIds(node, ids) {
	for (const player of node.players) {
		for (const unit of player.base_units) ids.add(unit.card_id);
		for (const cardId of player.hand) ids.add(cardId);
		if (player.legend) ids.add(player.legend.card_id);
	}
	for (const bf of node.battlefields) {
		for (const unit of bf.units) ids.add(unit.card_id);
		if (bf.effect_id) ids.add(bf.effect_id);
	}
}

async function findCardIds() {
	const ids = new Set();
	const files = (await readdir(PUZZLES_DIR)).filter(
		(f) => f.startsWith("puzzle-") && f.endsWith(".json"),
	);
	for (const file of files) {
		const puzzle = JSON.parse(await readFile(path.join(PUZZLES_DIR, file), "utf-8"));
		for (const node of Object.values(puzzle.nodes)) collectCardIds(node, ids);
	}
	return [...ids].sort();
}

async function loadCache() {
	try {
		return JSON.parse(await readFile(CACHE_PATH, "utf-8"));
	} catch (err) {
		if (err.code !== "ENOENT") throw err;
		return null;
	}
}

async function main() {
	const cardIds = await findCardIds();
	console.log(`Found ${cardIds.length} referenced card/effect ids.`);

	const cache = await loadCache();
	if (cache === null) {
		// Not fatal. The cache is a committed network artifact that can be
		// absent on a fresh clone, and every consumer falls back to showing
		// the raw card id, so the site still builds — it just reads badly.
		console.warn(
			`No card cache at ${CACHE_PATH}.\n` +
				"Run `python -m solver.fetch_cards` to populate it, then re-run this.\n" +
				"Writing a map of id -> id so the build still works.",
		);
	}

	const result = {};
	const missing = [];
	for (const cardId of cardIds) {
		if (PLACEHOLDERS[cardId]) {
			result[cardId] = PLACEHOLDERS[cardId];
			continue;
		}
		const card = cache?.[cardId];
		if (!card) {
			missing.push(cardId);
			result[cardId] = { name: cardId, text: null, type: null, unresolved: true };
			continue;
		}
		result[cardId] = {
			name: card.name ?? cardId,
			text: card.text?.plain ?? null,
			type: card.classification?.type ?? null,
		};
	}

	if (cache !== null && missing.length > 0) {
		console.warn(
			`${missing.length} id(s) not in the cache: ${missing.join(", ")}\n` +
				"Either the set gained printings (re-run the Python ingestion) or these " +
				"are engine-invented ids that need a PLACEHOLDERS entry.",
		);
	}

	await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
	await writeFile(OUTPUT_PATH, `${JSON.stringify(result, null, 2)}\n`);
	console.log(`Wrote ${Object.keys(result).length} entries to ${OUTPUT_PATH}`);
}

main().catch((err) => {
	console.error(err);
	process.exitCode = 1;
});
