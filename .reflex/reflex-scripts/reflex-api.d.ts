/**
 * AstroDev Reflex Script API Type Definitions
 * 
 * This file provides TypeScript types and documentation for writing reflex scripts.
 * Reflex scripts are JavaScript/TypeScript files that analyze source code and report diagnostics.
 * 
 * @version 1.0.0
 * @see https://github.com/ArtificialNecessity/ArtificialNecessitySupport/wiki/AstroDevAssistant
 */

// ===== Core Types =====

/**
 * Context about the current scan invocation
 */
declare type ScanContext = {
    /** True if this is a full workspace scan (startup/button click), false for incremental (file open/save) */
    isFullWorkspaceScan: boolean;
};

/**
 * File analysis context passed to your file save handler
 */
declare type FileAnalysisContext = {
    /** Full path to the file being analyzed */
    fileName: string;
    /** Just the file name (no path) */
    fileBaseName: string;
    /** The content of the file */
    fileContent: string;
    /** VSCode language ID (e.g., 'typescript', 'javascript', 'python') */
    languageId: string;
    /** File content split by lines for convenience */
    lines: string[];
    /** Number of lines in the file */
    lineCount: number;
    /** Context about this scan invocation */
    scanContext: ScanContext;
};

/**
 * Options for reporting a diagnostic from a reflex script
 */
declare type ReportOptions = {
    /** 1-based line number where the issue occurs */
    line: number;
    /** 1-based column number (optional, defaults to 1) */
    column?: number;
    /** End line for multi-line diagnostics (optional) */
    endLine?: number;
    /** End column for multi-line diagnostics (optional) */
    endColumn?: number;
    /** The diagnostic message to display */
    message: string;
    /** Severity level: 'error' | 'warning' | 'info' | 'hint' */
    severity: 'error' | 'warning' | 'info' | 'hint';
    /** Optional rule ID for this diagnostic */
    ruleId?: string;
};

// ===== Global Functions =====

/**
 * Log a message to the AstroDev output channel
 * @param message The message to log
 */
declare function log(message: string): void;

/**
 * Report a diagnostic issue in the current file
 * @param options Diagnostic options including line, message, and severity
 */
declare function report(options: ReportOptions): void;

/**
 * Register your file save handler (REQUIRED)
 * This function will be called every time a file is saved or opened.
 * You MUST call this in your script's initialization phase.
 * 
 * @param handler Function that analyzes a file and reports issues
 * 
 * @example
 * registerFileSaveHandler((file: FileAnalysisContext) => {
 *     // Analyze file.fileContent and call report() for any issues found
 * });
 */
declare function registerFileSaveHandler(handler: (file: FileAnalysisContext) => void): void;

/**
 * Request a persistent VM context for this script (optional)
 * 
 * By default, scripts run in a fresh VM each time. Calling this function
 * creates a persistent VM that survives across multiple file saves, allowing
 * you to maintain state between invocations.
 * 
 * @param options Configuration options
 * @param options.preRunAllFiles If true, requests a full workspace scan on startup
 * 
 * @example
 * requestPersistentContext({ preRunAllFiles: true });
 */
declare function requestPersistentContext(options?: { preRunAllFiles?: boolean }): void;

/**
 * Register a save callback for persistent data (optional)
 * 
 * This function will be called periodically (debounced) to save your script's state.
 * Only works with persistent VM contexts.
 * 
 * @param saveCallback Function that returns data to save (must be JSON-serializable)
 * 
 * @example
 * const myData = { lastSeen: new Date().toISOString() };
 * registerSaveCallback(() => myData);
 */
declare function registerSaveCallback(saveCallback: () => any): void;

/**
 * Register a restore callback for persistent data (optional)
 * 
 * This function will be called on startup if saved data exists.
 * Only works with persistent VM contexts.
 * 
 * @param restoreCallback Function that receives saved data
 * 
 * @example
 * let myData: any = {};
 * registerRestoreCallback((savedData) => {
 *     myData = savedData;
 * });
 */
declare function registerRestoreCallback(restoreCallback: (savedData: any) => void): void;

/**
 * Set global info lines for Command Deck tooltip (optional)
 * 
 * These lines appear in the Command Deck when hovering over your script.
 * Useful for showing aggregate statistics or status information.
 * Only works with persistent VM contexts.
 * 
 * @param lines Array of strings to display in tooltip
 * 
 * @example
 * setGlobalInfoLines([
 *     'Files analyzed: 142',
 *     'Issues found: 7'
 * ]);
 */
declare function setGlobalInfoLines(lines: string[]): void;

// ===== Console Object =====

declare const console: {
    /** Log an info message */
    log(message: string): void;
    /** Log a warning message */
    warn(message: string): void;
    /** Log an error message */
    error(message: string): void;
};

// ===== Safe Globals =====

declare const JSON: typeof globalThis.JSON;
declare const Math: typeof globalThis.Math;
declare const Date: typeof globalThis.Date;
declare const RegExp: typeof globalThis.RegExp;
declare const String: typeof globalThis.String;
declare const Number: typeof globalThis.Number;
declare const Boolean: typeof globalThis.Boolean;
declare const Array: typeof globalThis.Array;
declare const Object: typeof globalThis.Object;
declare const parseInt: typeof globalThis.parseInt;
declare const parseFloat: typeof globalThis.parseFloat;
declare const isNaN: typeof globalThis.isNaN;
declare const isFinite: typeof globalThis.isFinite;