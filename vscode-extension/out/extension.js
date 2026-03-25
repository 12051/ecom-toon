"use strict";
/**
 * ecom-toon VS Code Extension
 * Converts eCommerce JSON ↔ TOON format via the Python CLI.
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
const cp = __importStar(require("child_process"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
// ── Helpers ───────────────────────────────────────────────────────────────────
/**
 * Get Python path from settings (default: "python").
 */
function getPythonPath() {
    const config = vscode.workspace.getConfiguration("ecom-toon");
    return config.get("pythonPath") || "python";
}
/**
 * Find the ecom-toon CLI path.
 * Tries: settings → workspace root → walks up from active file.
 */
function getCliPath() {
    const config = vscode.workspace.getConfiguration("ecom-toon");
    const configured = config.get("cliPath");
    if (configured && configured.trim() !== "") {
        return path.join(configured, "cli", "main.py");
    }
    // Try workspace root
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders) {
        for (const folder of workspaceFolders) {
            const candidate = path.join(folder.uri.fsPath, "cli", "main.py");
            if (fs.existsSync(candidate)) {
                return candidate;
            }
        }
    }
    // Try active file's directory and its parents
    const activeFile = vscode.window.activeTextEditor?.document.uri.fsPath;
    if (activeFile) {
        let dir = path.dirname(activeFile);
        for (let i = 0; i < 5; i++) {
            const candidate = path.join(dir, "cli", "main.py");
            if (fs.existsSync(candidate)) {
                return candidate;
            }
            const parent = path.dirname(dir);
            if (parent === dir) {
                break;
            }
            dir = parent;
        }
    }
    return "";
}
/**
 * Run the ecom-toon CLI and return { stdout, stderr, exitCode }.
 */
function runCli(args) {
    return new Promise((resolve) => {
        const python = getPythonPath();
        const cli = getCliPath();
        if (!cli) {
            resolve({
                stdout: "",
                stderr: "Could not find cli/main.py. Please set ecom-toon.cliPath in Settings " +
                    "(File → Preferences → Settings → search 'ecom-toon').",
                exitCode: 1,
            });
            return;
        }
        const fullArgs = [cli, ...args];
        const proc = cp.spawn(python, fullArgs, { shell: true });
        let stdout = "";
        let stderr = "";
        proc.stdout.on("data", (d) => (stdout += d.toString()));
        proc.stderr.on("data", (d) => (stderr += d.toString()));
        proc.on("close", (code) => {
            resolve({ stdout, stderr, exitCode: code ?? 0 });
        });
        proc.on("error", (err) => {
            resolve({
                stdout: "",
                stderr: `Failed to start Python: ${err.message}\nMake sure Python is installed and ecom-toon.pythonPath is correct.`,
                exitCode: 1,
            });
        });
    });
}
/**
 * Parse token savings % from CLI stats output.
 * Looks for "Savings vs pretty JSON :  38.6%"
 */
function parseSavings(output) {
    const match = output.match(/Savings vs pretty JSON\s*:\s*([\d.]+)%/);
    return match ? match[1] : null;
}
/**
 * Show an error message with a "Open Settings" button.
 */
async function showError(message, detail) {
    const fullMsg = detail ? `${message}\n${detail}` : message;
    const choice = await vscode.window.showErrorMessage(`ecom-toon: ${fullMsg}`, "Open Settings");
    if (choice === "Open Settings") {
        vscode.commands.executeCommand("workbench.action.openSettings", "ecom-toon");
    }
}
// ── Commands ──────────────────────────────────────────────────────────────────
/**
 * Convert a .json file → .toon file.
 */
async function convertToToon(uri) {
    // Get the file path — either from right-click or active editor
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath || !filePath.endsWith(".json")) {
        vscode.window.showWarningMessage("ecom-toon: Please open or right-click a .json file first.");
        return;
    }
    const config = vscode.workspace.getConfiguration("ecom-toon");
    const outputFolder = config.get("outputFolder") || "";
    const showSavings = config.get("showSavingsOnConvert") ?? true;
    // Determine output path
    let outputPath;
    if (outputFolder.trim() !== "") {
        const fileName = path.basename(filePath, ".json") + ".toon";
        outputPath = path.join(outputFolder, fileName);
        // Create output folder if it doesn't exist
        fs.mkdirSync(outputFolder, { recursive: true });
    }
    else {
        outputPath = filePath.replace(/\.json$/, ".toon");
    }
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `ecom-toon: Converting ${path.basename(filePath)}...`,
        cancellable: false,
    }, async () => {
        const result = await runCli(["convert", filePath, "-o", outputPath]);
        if (result.exitCode !== 0) {
            await showError("Conversion failed.", result.stderr);
            return;
        }
        if (showSavings) {
            // Run stats to get token savings
            const statsResult = await runCli(["stats", filePath]);
            const savings = parseSavings(statsResult.stdout);
            const savingsMsg = savings ? ` (${savings}% token savings)` : "";
            vscode.window
                .showInformationMessage(`✅ Converted to ${path.basename(outputPath)}${savingsMsg}`, "Open File")
                .then((choice) => {
                if (choice === "Open File") {
                    vscode.workspace
                        .openTextDocument(outputPath)
                        .then((doc) => vscode.window.showTextDocument(doc));
                }
            });
        }
        else {
            vscode.window.showInformationMessage(`✅ Converted to ${path.basename(outputPath)}`);
        }
    });
}
/**
 * Convert a .toon file → -tojson.json file.
 */
async function convertToJson(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath || !filePath.endsWith(".toon")) {
        vscode.window.showWarningMessage("ecom-toon: Please open or right-click a .toon file first.");
        return;
    }
    const config = vscode.workspace.getConfiguration("ecom-toon");
    const outputFolder = config.get("outputFolder") || "";
    let outputPath;
    if (outputFolder.trim() !== "") {
        const fileName = path.basename(filePath, ".toon") + "-tojson.json";
        outputPath = path.join(outputFolder, fileName);
        fs.mkdirSync(outputFolder, { recursive: true });
    }
    else {
        outputPath = filePath.replace(/\.toon$/, "-tojson.json");
    }
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `ecom-toon: Converting ${path.basename(filePath)} to JSON...`,
        cancellable: false,
    }, async () => {
        const result = await runCli(["to-json", filePath, "-o", outputPath]);
        if (result.exitCode !== 0) {
            await showError("Conversion failed.", result.stderr);
            return;
        }
        vscode.window
            .showInformationMessage(`✅ Converted to ${path.basename(outputPath)}`, "Open File")
            .then((choice) => {
            if (choice === "Open File") {
                vscode.workspace
                    .openTextDocument(outputPath)
                    .then((doc) => vscode.window.showTextDocument(doc));
            }
        });
    });
}
/**
 * Show token savings stats report for a .json file.
 */
async function showStats(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath || !filePath.endsWith(".json")) {
        vscode.window.showWarningMessage("ecom-toon: Please open or right-click a .json file first.");
        return;
    }
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "ecom-toon: Calculating token savings...",
        cancellable: false,
    }, async () => {
        const result = await runCli(["stats", filePath]);
        if (result.exitCode !== 0) {
            await showError("Stats failed.", result.stderr);
            return;
        }
        // Parse the stats output
        const lines = result.stdout
            .split("\n")
            .map((l) => l.replace(/\x1b\[[0-9;]*m/g, "").trim()) // strip ANSI codes
            .filter((l) => l.length > 0);
        // Show in output panel
        const outputChannel = vscode.window.createOutputChannel("ecom-toon Stats");
        outputChannel.clear();
        outputChannel.appendLine(`📊 Token Report — ${path.basename(filePath)}`);
        outputChannel.appendLine("─".repeat(50));
        for (const line of lines) {
            outputChannel.appendLine(line);
        }
        outputChannel.show();
        // Also show a quick notification with the headline number
        const savings = parseSavings(result.stdout);
        if (savings) {
            vscode.window.showInformationMessage(`📊 ${path.basename(filePath)}: ${savings}% token savings vs pretty JSON`);
        }
    });
}
/**
 * Batch convert all .json files in a folder → .toon files.
 */
async function batchConvert(uri) {
    // Get the folder path
    let folderPath;
    if (uri?.fsPath) {
        const stat = fs.statSync(uri.fsPath);
        folderPath = stat.isDirectory() ? uri.fsPath : path.dirname(uri.fsPath);
    }
    else {
        // Ask user to pick a folder
        const picked = await vscode.window.showOpenDialog({
            canSelectFolders: true,
            canSelectFiles: false,
            canSelectMany: false,
            openLabel: "Select folder to batch convert",
        });
        folderPath = picked?.[0]?.fsPath;
    }
    if (!folderPath) {
        return;
    }
    // Count JSON files
    const jsonFiles = fs
        .readdirSync(folderPath)
        .filter((f) => f.endsWith(".json"));
    if (jsonFiles.length === 0) {
        vscode.window.showWarningMessage(`ecom-toon: No .json files found in ${path.basename(folderPath)}`);
        return;
    }
    const confirm = await vscode.window.showInformationMessage(`ecom-toon: Convert ${jsonFiles.length} JSON file(s) in "${path.basename(folderPath)}" to TOON?`, "Convert All", "Cancel");
    if (confirm !== "Convert All") {
        return;
    }
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `ecom-toon: Batch converting ${jsonFiles.length} files...`,
        cancellable: false,
    }, async () => {
        const globPattern = path.join(folderPath, "*.json");
        const result = await runCli([
            "batch",
            globPattern,
            "--concurrency",
            "4",
        ]);
        if (result.exitCode !== 0) {
            await showError("Batch conversion failed.", result.stderr);
            return;
        }
        // Parse total saved from output
        const savedMatch = result.stdout.match(/Total saved:\s*([\d,]+)\s*tokens.*avg\s*([\d.]+)%/);
        const savedTokens = savedMatch ? savedMatch[1] : "?";
        const avgSavings = savedMatch ? savedMatch[2] : "?";
        vscode.window.showInformationMessage(`✅ Converted ${jsonFiles.length} files — saved ${savedTokens} tokens (avg ${avgSavings}%)`);
    });
}
/**
 * Validate roundtrip for a .json file (JSON → TOON → JSON = identical).
 */
async function validateRoundtrip(uri) {
    const filePath = uri?.fsPath ?? vscode.window.activeTextEditor?.document.uri.fsPath;
    if (!filePath || !filePath.endsWith(".json")) {
        vscode.window.showWarningMessage("ecom-toon: Please open or right-click a .json file first.");
        return;
    }
    await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "ecom-toon: Validating roundtrip...",
        cancellable: false,
    }, async () => {
        const result = await runCli(["roundtrip", filePath]);
        const output = (result.stdout + result.stderr).trim();
        if (output.includes("PASS")) {
            vscode.window.showInformationMessage(`✅ Roundtrip PASS — ${path.basename(filePath)} converts with zero data loss`);
        }
        else if (output.includes("FAIL")) {
            vscode.window.showErrorMessage(`❌ Roundtrip FAIL — ${path.basename(filePath)} has data loss during conversion. Check the output panel.`);
            const outputChannel = vscode.window.createOutputChannel("ecom-toon");
            outputChannel.appendLine(output);
            outputChannel.show();
        }
        else {
            await showError("Roundtrip check failed.", output);
        }
    });
}
// ── Status Bar ────────────────────────────────────────────────────────────────
function createStatusBarItem() {
    const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    item.text = "$(arrow-right) TOON";
    item.tooltip = "ecom-toon: Click to convert active file";
    item.command = "ecom-toon.convertToToon";
    return item;
}
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
        item.tooltip = "ecom-toon: Convert this TOON file to JSON";
        item.show();
    }
    else {
        item.hide();
    }
}
// ── Extension Entry Points ────────────────────────────────────────────────────
function activate(context) {
    console.log("ecom-toon extension activated");
    // Register all commands
    context.subscriptions.push(vscode.commands.registerCommand("ecom-toon.convertToToon", convertToToon), vscode.commands.registerCommand("ecom-toon.convertToJson", convertToJson), vscode.commands.registerCommand("ecom-toon.showStats", showStats), vscode.commands.registerCommand("ecom-toon.batchConvert", batchConvert), vscode.commands.registerCommand("ecom-toon.validateRoundtrip", validateRoundtrip));
    // Status bar
    const statusBar = createStatusBarItem();
    context.subscriptions.push(statusBar);
    // Update status bar when active editor changes
    context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor((editor) => {
        updateStatusBar(statusBar, editor);
    }));
    // Initial status bar update
    updateStatusBar(statusBar, vscode.window.activeTextEditor);
    // Welcome message on first install
    const isFirstInstall = !context.globalState.get("ecom-toon.installed");
    if (isFirstInstall) {
        context.globalState.update("ecom-toon.installed", true);
        vscode.window
            .showInformationMessage("✅ ecom-toon installed! Right-click any .json file to convert to TOON.", "Open Settings", "View README")
            .then((choice) => {
            if (choice === "Open Settings") {
                vscode.commands.executeCommand("workbench.action.openSettings", "ecom-toon");
            }
        });
    }
}
function deactivate() {
    // Clean up if needed
}
//# sourceMappingURL=extension.js.map