"use strict";
/**
 * ecom-toon VS Code Extension
 * ============================
 * Full TOON conversion logic built directly in TypeScript.
 * NO Python dependency. NO CLI path configuration needed.
 * Just install and use.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
// ═══════════════════════════════════════════════════════════════════════════
// TOON WRITER  (JSON → TOON)
// ═══════════════════════════════════════════════════════════════════════════
function isUniformObjectArray(lst) {
    if (!lst.length || typeof lst[0] !== "object" || lst[0] === null || Array.isArray(lst[0])) {
        return false;
    }
    const firstKeys = Object.keys(lst[0]).join(",");
    return lst.every((item) => typeof item === "object" &&
        item !== null &&
        !Array.isArray(item) &&
        Object.keys(item).join(",") === firstKeys);
}
function escapeValue(value) {
    if (value === null || value === undefined) {
        return "null";
    }
    if (typeof value === "boolean") {
        return value ? "true" : "false";
    }
    if (typeof value === "number") {
        return String(value);
    }
    const s = String(value);
    if (/^\d{4}-\d{2}-\d{2}T[\d:]+Z$/.test(s)) {
        return s;
    }
    if (s.startsWith("https://")) {
        return "https~/" + s.slice(8);
    }
    if (s.startsWith("http://")) {
        return "http~/" + s.slice(7);
    }
    if (/^-?\d+(\.\d+)?$/.test(s)) {
        return `"${s}"`;
    }
    const cleaned = s.replace(/[\n\r\t]/g, " ");
    if (cleaned.includes(",")) {
        return `"${cleaned.replace(/"/g, '\\"')}"`;
    }
    return cleaned;
}
function hasComplexField(arr, fields) {
    return arr.some((item) => fields.some((f) => {
        const v = item[f];
        return Array.isArray(v) || (typeof v === "object" && v !== null);
    }));
}
function writeMixedObjectArray(key, lst, lines, indent) {
    lines.push(`${indent}${key}[${lst.length}],`);
    for (const item of lst) {
        lines.push(`${indent}  -`);
        if (typeof item === "object" && item !== null && !Array.isArray(item)) {
            writeDict(item, lines, indent + "    ");
        }
        else {
            lines.push(`${indent}    ${escapeValue(item)}`);
        }
    }
}
function writeKeyValue(key, value, lines, indent) {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        lines.push(`${indent}${key},`);
        writeDict(value, lines, indent + "  ");
    }
    else if (Array.isArray(value)) {
        const n = value.length;
        if (n === 0) {
            lines.push(`${indent}${key}[0],`);
        }
        else if (isUniformObjectArray(value)) {
            const fields = Object.keys(value[0]);
            if (hasComplexField(value, fields)) {
                writeMixedObjectArray(key, value, lines, indent);
            }
            else {
                lines.push(`${indent}${key}[${n}]{${fields.join(",")}},`);
                for (const item of value) {
                    const row = fields.map((f) => escapeValue(item[f])).join(",");
                    lines.push(`${indent}  ${row}`);
                }
            }
        }
        else if (value.every((x) => !Array.isArray(x) && (typeof x !== "object" || x === null))) {
            lines.push(`${indent}${key}[${n}],${value.map(escapeValue).join(",")}`);
        }
        else {
            writeMixedObjectArray(key, value, lines, indent);
        }
    }
    else {
        lines.push(`${indent}${key},${escapeValue(value)}`);
    }
}
function writeDict(d, lines, indent) {
    for (const [k, v] of Object.entries(d)) {
        writeKeyValue(k, v, lines, indent);
    }
}
function jsonToToon(obj) {
    const lines = [];
    writeDict(obj, lines, "");
    return lines.join("\n");
}
// ═══════════════════════════════════════════════════════════════════════════
// TOON PARSER  (TOON → JSON)
// ═══════════════════════════════════════════════════════════════════════════
function unescapeValue(v) {
    v = v.trimStart();
    if (v.length >= 2 && v[0] === '"' && v[v.length - 1] === '"') {
        return v.slice(1, -1).replace(/\\"/g, '"');
    }
    if (v.startsWith("https~/")) {
        return "https://" + v.slice(7);
    }
    if (v.startsWith("http~/")) {
        return "http://" + v.slice(6);
    }
    if (/^\d{4}-\d{2}-\d{2}T[\d:]+Z$/.test(v)) {
        return v;
    }
    if (v.toLowerCase() === "true") {
        return true;
    }
    if (v.toLowerCase() === "false") {
        return false;
    }
    if (v.toLowerCase() === "null") {
        return null;
    }
    if (/^-?\d+$/.test(v)) {
        return parseInt(v, 10);
    }
    if (/^-?\d+\.\d+$/.test(v)) {
        return parseFloat(v);
    }
    return v;
}
function splitCsv(line, nFields) {
    const parts = [];
    let current = "";
    let inQuote = false;
    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"' && !inQuote) {
            inQuote = true;
            current += ch;
        }
        else if (ch === '"' && inQuote) {
            if (i + 1 < line.length && line[i + 1] === '"') {
                current += '"';
                i++;
            }
            else {
                inQuote = false;
                current += ch;
            }
        }
        else if (ch === "," && !inQuote) {
            parts.push(current);
            current = "";
        }
        else {
            current += ch;
        }
    }
    parts.push(current);
    while (parts.length < nFields) {
        parts.push("");
    }
    if (parts.length > nFields) {
        return [...parts.slice(0, nFields - 1), parts.slice(nFields - 1).join(",")];
    }
    return parts;
}
function getIndent(line) { return line.length - line.trimStart().length; }
function parseBlock(lines, start, baseIndent) {
    const result = {};
    let i = start;
    while (i < lines.length) {
        const raw = lines[i];
        if (!raw.trim()) {
            i++;
            continue;
        }
        const indentLen = getIndent(raw);
        if (indentLen < baseIndent) {
            break;
        }
        if (indentLen > baseIndent) {
            i++;
            continue;
        }
        const line = raw.trim();
        const m1 = line.match(/^(\w+)\[(\d+)\]\{([^}]*)\},\s*$/);
        if (m1) {
            const key = m1[1];
            const n = parseInt(m1[2], 10);
            const fields = m1[3].split(",").map((f) => f.trim());
            i++;
            const items = [];
            for (let _r = 0; _r < n; _r++) {
                while (i < lines.length && !lines[i].trim()) {
                    i++;
                }
                if (i >= lines.length) {
                    break;
                }
                const rowLine = lines[i].trimStart();
                const rawVals = splitCsv(rowLine, fields.length);
                const item = {};
                fields.forEach((f, j) => { item[f] = j < rawVals.length ? unescapeValue(rawVals[j]) : null; });
                items.push(item);
                i++;
            }
            result[key] = items;
            continue;
        }
        const m2 = line.match(/^(\w+)\[(\d+)\],\s*$/);
        if (m2) {
            const key = m2[1];
            const n = parseInt(m2[2], 10);
            i++;
            const [items, nextI] = parseMixedArray(lines, i, baseIndent + 2, n);
            result[key] = items;
            i = nextI;
            continue;
        }
        const m3 = line.match(/^(\w+)\[(\d+)\],(.+)$/);
        if (m3) {
            result[m3[1]] = m3[3].split(",").map((v) => unescapeValue(v));
            i++;
            continue;
        }
        const m4 = line.match(/^([\w]+),\s*$/);
        if (m4) {
            const key = m4[1];
            i++;
            const [child, nextI] = parseBlock(lines, i, baseIndent + 2);
            result[key] = child;
            i = nextI;
            continue;
        }
        if (line.includes(",")) {
            const commaIdx = line.indexOf(",");
            const key = line.slice(0, commaIdx).trim();
            const rawTrimmed = raw.trimStart();
            const rawCommaIdx = rawTrimmed.indexOf(",");
            const rest = rawTrimmed.slice(rawCommaIdx + 1);
            result[key] = unescapeValue(rest);
            i++;
            continue;
        }
        i++;
    }
    return [result, i];
}
function parseMixedArray(lines, start, itemIndent, count) {
    const items = [];
    let i = start;
    while (i < lines.length && items.length < count) {
        const raw = lines[i];
        if (!raw.trim()) {
            i++;
            continue;
        }
        if (getIndent(raw) < itemIndent) {
            break;
        }
        if (raw.trim() === "-") {
            i++;
            const [item, nextI] = parseBlock(lines, i, itemIndent + 2);
            items.push(item);
            i = nextI;
        }
        else {
            break;
        }
    }
    return [items, i];
}
function toonToJson(toonText) {
    const [result] = parseBlock(toonText.split("\n"), 0, 0);
    return result;
}
// ═══════════════════════════════════════════════════════════════════════════
// TOKEN COUNTER
// ═══════════════════════════════════════════════════════════════════════════
function countTokens(text) {
    const tokens = text.match(/[a-zA-Z0-9_\-\.]+|[^a-zA-Z0-9_\-\.\s]|\s+/g) || [];
    return tokens.reduce((sum, t) => {
        if (/^[a-zA-Z0-9]/.test(t)) {
            return sum + Math.max(1, Math.round(t.length / 3.5));
        }
        return sum + 1;
    }, 0);
}
function getProducts(data) {
    for (const key of ["products", "items", "catalog", "data"]) {
        if (Array.isArray(data[key])) {
            return data[key];
        }
    }
    return [data];
}
function runPreflight(data, rawText) {
    const products = getProducts(data);
    const n = products.length;
    const sample = products.slice(0, Math.min(5, n));
    const t0 = performance.now();
    const sampleToon = sample.map((p) => jsonToToon(p));
    const msPerProduct = (performance.now() - t0) / sample.length;
    const savingsList = sample.map((p, i) => {
        const jTok = countTokens(JSON.stringify(p, null, 2));
        const tTok = countTokens(sampleToon[i]);
        return jTok > 0 ? (jTok - tTok) / jTok : 0.40;
    });
    const avgSavings = savingsList.reduce((a, b) => a + b, 0) / savingsList.length;
    const fileSizeKb = rawText.length / 1024;
    const estMemLoadMb = (fileSizeKb * 3.2) / 1024;
    const fullJsonTokens = countTokens(rawText);
    const estToonTokens = Math.round(fullJsonTokens * (1 - avgSavings));
    return {
        nProducts: n, sampleSize: sample.length,
        fileSizeKb: Math.round(fileSizeKb * 10) / 10,
        estMemoryLoadMb: Math.round(estMemLoadMb * 10) / 10,
        estMemoryPeakMb: Math.round(estMemLoadMb * 1.4 * 10) / 10,
        estTimeMs: Math.round(msPerProduct * n * 10) / 10,
        jsonTokens: fullJsonTokens, estToonTokens,
        estSavingsPct: Math.round(avgSavings * 1000) / 10,
        estTokensSaved: fullJsonTokens - estToonTokens,
    };
}
function fmtTime(ms) {
    if (ms < 1000) {
        return `${ms.toFixed(1)} ms`;
    }
    if (ms < 60000) {
        return `${(ms / 1000).toFixed(1)} sec`;
    }
    return `${Math.floor(ms / 60000)} min ${Math.floor((ms % 60000) / 1000)} sec`;
}
// ═══════════════════════════════════════════════════════════════════════════
// COMMANDS
// ═══════════════════════════════════════════════════════════════════════════
async function convertToToon(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath?.endsWith(".json")) {
        vscode.window.showWarningMessage("ecom-toon: Please right-click a .json file.");
        return;
    }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
        title: `ecom-toon: Converting ${path.basename(filePath)}...`, cancellable: false }, async (progress) => {
        try {
            progress.report({ message: "Reading file..." });
            const rawText = fs.readFileSync(filePath, "utf-8");
            const data = JSON.parse(rawText);
            progress.report({ message: "Running pre-flight estimate..." });
            const pf = runPreflight(data, rawText);
            progress.report({ message: "Converting to TOON..." });
            const t0 = performance.now();
            const toonText = jsonToToon(data);
            const elapsed = performance.now() - t0;
            const jTok = countTokens(rawText);
            const tTok = countTokens(toonText);
            const savings = Math.round((jTok - tTok) / jTok * 1000) / 10;
            const outPath = filePath.replace(/\.json$/, ".toon");
            fs.writeFileSync(outPath, toonText, "utf-8");
            const out = vscode.window.createOutputChannel("ecom-toon");
            out.clear();
            out.appendLine("━".repeat(55));
            out.appendLine("  ecom-toon Conversion Report");
            out.appendLine("━".repeat(55));
            out.appendLine(`  Input  : ${path.basename(filePath)}`);
            out.appendLine(`  Output : ${path.basename(outPath)}`);
            out.appendLine("");
            out.appendLine("  PRE-FLIGHT ESTIMATES (before conversion)");
            out.appendLine("  " + "─".repeat(45));
            out.appendLine(`  Products detected  : ${pf.nProducts}`);
            out.appendLine(`  Est. memory load   : ~${pf.estMemoryLoadMb} MB`);
            out.appendLine(`  Est. peak memory   : ~${pf.estMemoryPeakMb} MB`);
            out.appendLine(`  Est. time          : ~${fmtTime(pf.estTimeMs)}`);
            out.appendLine(`  Est. token savings : ~${pf.estSavingsPct}%`);
            out.appendLine("");
            out.appendLine("  ACTUAL RESULTS");
            out.appendLine("  " + "─".repeat(45));
            out.appendLine(`  Actual time        : ${elapsed.toFixed(2)} ms`);
            out.appendLine(`  JSON tokens        : ${jTok.toLocaleString()}`);
            out.appendLine(`  TOON tokens        : ${tTok.toLocaleString()}`);
            out.appendLine(`  Tokens saved       : ${(jTok - tTok).toLocaleString()}`);
            out.appendLine(`  Token savings      : ${savings}%`);
            out.appendLine(`  JSON chars         : ${rawText.length.toLocaleString()}`);
            out.appendLine(`  TOON chars         : ${toonText.length.toLocaleString()}`);
            out.appendLine("");
            out.appendLine("  TOON PREVIEW (first 10 lines)");
            out.appendLine("  " + "─".repeat(45));
            toonText.split("\n").slice(0, 10).forEach((l) => out.appendLine(`  ${l}`));
            if (toonText.split("\n").length > 10) {
                out.appendLine("  ...");
            }
            out.appendLine("━".repeat(55));
            out.show();
            const choice = await vscode.window.showInformationMessage(`[OK] Converted to ${path.basename(outPath)} — ${savings}% token savings`, "Open TOON File");
            if (choice === "Open TOON File") {
                const doc = await vscode.workspace.openTextDocument(outPath);
                vscode.window.showTextDocument(doc);
            }
        }
        catch (e) {
            const msg = e instanceof SyntaxError ? "Invalid JSON: " + e.message : String(e);
            vscode.window.showErrorMessage(`ecom-toon: ${msg}`);
        }
    });
}
async function convertToJson(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath?.endsWith(".toon")) {
        vscode.window.showWarningMessage("ecom-toon: Please right-click a .toon file.");
        return;
    }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
        title: `ecom-toon: Converting to JSON...`, cancellable: false }, async () => {
        try {
            const toonText = fs.readFileSync(filePath, "utf-8");
            const data = toonToJson(toonText);
            const outPath = filePath.replace(/\.toon$/, "-tojson.json");
            fs.writeFileSync(outPath, JSON.stringify(data, null, 2), "utf-8");
            const choice = await vscode.window.showInformationMessage(`[OK] Converted to ${path.basename(outPath)}`, "Open File");
            if (choice === "Open File") {
                const doc = await vscode.workspace.openTextDocument(outPath);
                vscode.window.showTextDocument(doc);
            }
        }
        catch (e) {
            vscode.window.showErrorMessage(`ecom-toon: ${String(e)}`);
        }
    });
}
async function showStats(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath?.endsWith(".json")) {
        vscode.window.showWarningMessage("ecom-toon: Please right-click a .json file.");
        return;
    }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
        title: "ecom-toon: Calculating token savings...", cancellable: false }, async () => {
        try {
            const rawText = fs.readFileSync(filePath, "utf-8");
            const data = JSON.parse(rawText);
            const toonText = jsonToToon(data);
            const pf = runPreflight(data, rawText);
            const jTok = countTokens(rawText);
            const cTok = countTokens(JSON.stringify(data));
            const tTok = countTokens(toonText);
            const savPretty = Math.round((jTok - tTok) / jTok * 1000) / 10;
            const savCompact = Math.round((cTok - tTok) / cTok * 1000) / 10;
            const out = vscode.window.createOutputChannel("ecom-toon");
            out.clear();
            out.appendLine("━".repeat(55));
            out.appendLine("  ecom-toon Token Report");
            out.appendLine("━".repeat(55));
            out.appendLine(`  File     : ${path.basename(filePath)}`);
            out.appendLine(`  Size     : ${(rawText.length / 1024).toFixed(1)} KB`);
            out.appendLine(`  Products : ${pf.nProducts} detected`);
            out.appendLine("");
            out.appendLine("  PRE-FLIGHT ESTIMATES");
            out.appendLine("  " + "─".repeat(45));
            out.appendLine(`  Est. memory (load) : ~${pf.estMemoryLoadMb} MB`);
            out.appendLine(`  Est. memory (peak) : ~${pf.estMemoryPeakMb} MB`);
            out.appendLine(`  Est. conv. time    : ~${fmtTime(pf.estTimeMs)}`);
            out.appendLine("");
            out.appendLine("  TOKEN COUNTS");
            out.appendLine("  " + "─".repeat(45));
            out.appendLine(`  Pretty JSON tokens  : ${jTok.toLocaleString()}`);
            out.appendLine(`  Compact JSON tokens : ${cTok.toLocaleString()}`);
            out.appendLine(`  TOON tokens         : ${tTok.toLocaleString()}`);
            out.appendLine("");
            out.appendLine("  SAVINGS");
            out.appendLine("  " + "─".repeat(45));
            out.appendLine(`  vs Pretty JSON  : ${savPretty}%  (${(jTok - tTok).toLocaleString()} tokens saved)`);
            out.appendLine(`  vs Compact JSON : ${savCompact}%`);
            out.appendLine(`  Char savings    : ${Math.round((rawText.length - toonText.length) / rawText.length * 1000) / 10}%`);
            out.appendLine("━".repeat(55));
            out.show();
            vscode.window.showInformationMessage(`ecom-toon: ${path.basename(filePath)} — ${savPretty}% token savings`);
        }
        catch (e) {
            vscode.window.showErrorMessage(`ecom-toon: ${String(e)}`);
        }
    });
}
async function validateRoundtrip(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath?.endsWith(".json")) {
        vscode.window.showWarningMessage("ecom-toon: Please right-click a .json file.");
        return;
    }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
        title: "ecom-toon: Validating roundtrip...", cancellable: false }, async () => {
        try {
            const rawText = fs.readFileSync(filePath, "utf-8");
            const data = JSON.parse(rawText);
            const toonText = jsonToToon(data);
            const restored = toonToJson(toonText);
            const orig = JSON.stringify(data, null, 2);
            const got = JSON.stringify(restored, null, 2);
            if (orig === got) {
                vscode.window.showInformationMessage(`[OK] Roundtrip PASS — ${path.basename(filePath)} converts with zero data loss`);
            }
            else {
                const origLines = orig.split("\n");
                const gotLines = got.split("\n");
                let diffMsg = "";
                for (let i = 0; i < Math.min(origLines.length, gotLines.length); i++) {
                    if (origLines[i] !== gotLines[i]) {
                        diffMsg = `Line ${i + 1}:\n  Expected: ${origLines[i]}\n  Got:      ${gotLines[i]}`;
                        break;
                    }
                }
                const out = vscode.window.createOutputChannel("ecom-toon");
                out.clear();
                out.appendLine("[FAIL] Roundtrip FAIL — Data mismatch detected");
                out.appendLine(diffMsg);
                out.show();
                vscode.window.showErrorMessage("ecom-toon: Roundtrip FAIL — see Output panel");
            }
        }
        catch (e) {
            vscode.window.showErrorMessage(`ecom-toon: ${String(e)}`);
        }
    });
}
async function batchConvert(uri) {
    let folderPath;
    if (uri?.fsPath) {
        folderPath = fs.statSync(uri.fsPath).isDirectory() ? uri.fsPath : path.dirname(uri.fsPath);
    }
    else {
        const picked = await vscode.window.showOpenDialog({
            canSelectFolders: true, canSelectFiles: false, canSelectMany: false,
            openLabel: "Select folder to batch convert",
        });
        folderPath = picked?.[0]?.fsPath;
    }
    if (!folderPath) {
        return;
    }
    const jsonFiles = fs.readdirSync(folderPath).filter((f) => f.endsWith(".json"));
    if (!jsonFiles.length) {
        vscode.window.showWarningMessage(`ecom-toon: No .json files in ${path.basename(folderPath)}`);
        return;
    }
    const confirm = await vscode.window.showInformationMessage(`ecom-toon: Convert ${jsonFiles.length} JSON file(s) in "${path.basename(folderPath)}" to TOON?`, "Convert All", "Cancel");
    if (confirm !== "Convert All") {
        return;
    }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification,
        title: `ecom-toon: Batch converting ${jsonFiles.length} files...`, cancellable: false }, async () => {
        let totalJTok = 0;
        let totalTTok = 0;
        let converted = 0;
        let failed = 0;
        for (const file of jsonFiles) {
            try {
                const fullPath = path.join(folderPath, file);
                const rawText = fs.readFileSync(fullPath, "utf-8");
                const data = JSON.parse(rawText);
                const toonText = jsonToToon(data);
                fs.writeFileSync(fullPath.replace(/\.json$/, ".toon"), toonText, "utf-8");
                totalJTok += countTokens(rawText);
                totalTTok += countTokens(toonText);
                converted++;
            }
            catch {
                failed++;
            }
        }
        const savings = Math.round((totalJTok - totalTTok) / totalJTok * 1000) / 10;
        vscode.window.showInformationMessage(`[OK] ${converted}/${jsonFiles.length} files converted — ` +
            `${(totalJTok - totalTTok).toLocaleString()} tokens saved (${savings}%)` +
            (failed ? ` — ${failed} failed` : ""));
    });
}
// ═══════════════════════════════════════════════════════════════════════════
// STATUS BAR + ACTIVATE
// ═══════════════════════════════════════════════════════════════════════════
function updateStatusBar(item, editor) {
    if (!editor) {
        item.hide();
        return;
    }
    const ext = path.extname(editor.document.uri.fsPath);
    if (ext === ".json") {
        item.text = "$(arrow-right) JSON→TOON";
        item.command = "ecom-toon.convertToToon";
        item.tooltip = "ecom-toon: Convert this JSON file to TOON";
        item.show();
    }
    else if (ext === ".toon") {
        item.text = "$(arrow-left) TOON→JSON";
        item.command = "ecom-toon.convertToJson";
        item.tooltip = "ecom-toon: Convert this TOON file back to JSON";
        item.show();
    }
    else {
        item.hide();
    }
}
function activate(context) {
    context.subscriptions.push(vscode.commands.registerCommand("ecom-toon.convertToToon", convertToToon), vscode.commands.registerCommand("ecom-toon.convertToJson", convertToJson), vscode.commands.registerCommand("ecom-toon.showStats", showStats), vscode.commands.registerCommand("ecom-toon.batchConvert", batchConvert), vscode.commands.registerCommand("ecom-toon.validateRoundtrip", validateRoundtrip));
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    context.subscriptions.push(statusBar);
    context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor((e) => updateStatusBar(statusBar, e)));
    updateStatusBar(statusBar, vscode.window.activeTextEditor);
    if (!context.globalState.get("ecom-toon.installed")) {
        context.globalState.update("ecom-toon.installed", true);
        vscode.window.showInformationMessage("[OK] ecom-toon installed! Right-click any .json file to convert. No setup needed.");
    }
}
function deactivate() { }
//# sourceMappingURL=extension.js.map