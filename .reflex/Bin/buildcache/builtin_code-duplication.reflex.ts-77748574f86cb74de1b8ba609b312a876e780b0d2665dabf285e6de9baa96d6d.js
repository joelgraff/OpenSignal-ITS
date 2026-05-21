const PHRASE_TOKEN_COUNT = 10;
const REPEATED_CHAR_THRESHOLD = 4;
const MATCH_MUST_START_BEFORE_LINE_FRACTION = 0.75;
const MIN_TRACKER_RATIO = 0.5;
const MIN_TOKENS_AT_HIGH_RATIO = 50;
const MIN_TOKENS_AT_LOW_RATIO = 300;
function md5(input) {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
  }
  const hexHash = (hash >>> 0).toString(16).padStart(8, "0");
  return hexHash + hexHash + hexHash + hexHash;
}
function getFileExtension(filePath) {
  const lastDot = filePath.lastIndexOf(".");
  const lastSlash = Math.max(filePath.lastIndexOf("/"), filePath.lastIndexOf("\\"));
  if (lastDot > lastSlash) {
    return filePath.substring(lastDot).toLowerCase();
  }
  return "";
}
function normalizePathSeparators(filePath) {
  return filePath.replace(/\\/g, "/");
}
const excludedDirectoryPatterns = [
  "node_modules",
  "bower_components",
  "__pycache__",
  ".venv",
  "venv",
  ".env",
  "site-packages",
  "bin",
  "obj",
  "packages",
  "target",
  "dist",
  "build",
  "out",
  ".build",
  ".git",
  ".svn",
  ".hg",
  ".vs",
  ".idea",
  "vendor",
  "third_party",
  "external",
  "deps",
  "lib",
  "libs"
];
function isExcludedPath(filePath) {
  const normalizedPath = normalizePathSeparators(filePath).toLowerCase();
  for (const pattern of excludedDirectoryPatterns) {
    if (normalizedPath.includes(`/${pattern.toLowerCase()}/`)) {
      return true;
    }
  }
  return false;
}
const supportedExtensions = [
  ".cs",
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".py",
  ".go",
  ".rs",
  ".java",
  ".c",
  ".cpp",
  ".h",
  ".hpp",
  ".css",
  ".scss",
  ".less",
  ".rb",
  ".html",
  ".htm"
];
function isSupportedFile(filePath) {
  const ext = getFileExtension(filePath);
  return supportedExtensions.includes(ext);
}
function tokenizeLineWithPositions(line) {
  const tokensWithPositions = [];
  const pattern = /(\s+|[{}()\[\];,.<>!&|=+\-*/])/g;
  let lastIndex = 0;
  let match;
  while ((match = pattern.exec(line)) !== null) {
    if (match.index > lastIndex) {
      const wordToken = line.substring(lastIndex, match.index);
      tokensWithPositions.push({
        token: wordToken,
        oneBasedColumn: lastIndex + 1
        // Convert 0-based to 1-based
      });
    }
    if (match[0].trim() === "") {
      tokensWithPositions.push({
        token: " ",
        // Unified whitespace
        oneBasedColumn: match.index + 1
        // Convert 0-based to 1-based
      });
    } else {
      tokensWithPositions.push({
        token: match[0],
        // Punctuation
        oneBasedColumn: match.index + 1
        // Convert 0-based to 1-based
      });
    }
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < line.length) {
    const finalToken = line.substring(lastIndex);
    tokensWithPositions.push({
      token: finalToken,
      oneBasedColumn: lastIndex + 1
      // Convert 0-based to 1-based
    });
  }
  return tokensWithPositions;
}
function computePhraseHash(tokens) {
  const combined = tokens.join("");
  return md5(combined);
}
function phraseContainsRepeatedChars(tokens) {
  if (tokens.length < REPEATED_CHAR_THRESHOLD) return false;
  let repeatCount = 1;
  let lastToken = null;
  for (const token of tokens) {
    if (token.length === 1) {
      if (token === lastToken) {
        repeatCount++;
        if (repeatCount >= REPEATED_CHAR_THRESHOLD) {
          return true;
        }
      } else {
        repeatCount = 1;
        lastToken = token;
      }
    } else {
      repeatCount = 1;
      lastToken = null;
    }
  }
  return false;
}
function getMinTokensForRatio(hitRatio) {
  const clampedRatio = Math.max(MIN_TRACKER_RATIO, Math.min(1, hitRatio));
  const ratioRange = 1 - MIN_TRACKER_RATIO;
  const normalizedRatio = (clampedRatio - MIN_TRACKER_RATIO) / ratioRange;
  const tokenRange = MIN_TOKENS_AT_LOW_RATIO - MIN_TOKENS_AT_HIGH_RATIO;
  return MIN_TOKENS_AT_HIGH_RATIO + Math.floor((1 - normalizedRatio) * tokenRange);
}
function trackerMeetsThreshold(hits, misses) {
  const totalTokens = hits + misses;
  if (totalTokens === 0) return false;
  const hitRatio = hits / totalTokens;
  if (hitRatio < MIN_TRACKER_RATIO) return false;
  const minTokensRequired = getMinTokensForRatio(hitRatio);
  return hits >= minTokensRequired;
}
const ContentFilterPatterns = {
  // Comments
  cStyleBlockComment: /\/\*.*?\*\//gs,
  cStyleLineComment: /\/\/[^\r\n]*/g,
  hashComment: /#[^\r\n]*/g,
  pythonDocstring: /(""".*?"""|'''.*?''')/gs,
  rubyBlockComment: /=begin.*?=end/gs,
  // Imports/Using
  csharpUsing: /^\s*using\s+[^;]+;/gm,
  tsImportExport: /^\s*(import|export)\s+.*?(?:from\s+['"][^'"]+['"])?;?/gm,
  pythonImport: /^\s*(import\s+\S+|from\s+\S+\s+import\s+[^\r\n]+)/gm,
  goImportSingle: /import\s+"[^"]+"/g,
  goImportGroup: /import\s*\([^)]*\)/gs,
  rustUse: /use\s+[\w:]+(\s*::\s*\{[^}]*\})?;/g,
  javaImport: /import\s+(static\s+)?[\w.]+(\.\*)?;/g,
  javaPackage: /package\s+[\w.]+;/g,
  cssImport: /@import\s+[^;]+;/g,
  cppInclude: /#include\s*[<"][^>"]+[>"]/g,
  cppDefine: /#define\s+\w+[^\r\n]*/g,
  rubyRequire: /require(_relative)?\s+['"][^'"]+['"]/g,
  // Method/Function signatures
  csharpMethodSignature: /(public|private|protected|internal)\s+[\w<>\[\],\?\(\)\s]+\w+\s*\([^)]*\)/g,
  pythonDefinition: /^\s*(def|class)\s+\w+\s*\([^)]*\)\s*:/gm,
  tsFunctionDeclaration: /(async\s+)?function\s+\w+\s*\([^)]*\)\s*(:\s*[\w<>\[\]|&\s]+)?/g,
  tsMethodSignature: /(public|private|protected)\s+(async\s+)?\w+\s*\([^)]*\)\s*(:\s*[\w<>\[\]|&\s]+)?/g,
  goFunction: /func\s+(\([^)]+\)\s*)?\w+\s*\([^)]*\)/g,
  rustFunction: /(pub\s+)?fn\s+\w+\s*(<[^>]*>)?\s*\([^)]*\)/g,
  rubyDef: /def\s+\w+(\s*\([^)]*\))?/g,
  rubyClass: /class\s+\w+(\s*<\s*\w+)?/g,
  // HTML/JSX inline data
  inlineSvg_v1: /<svg\b.*<\/svg>/gs,
  inlineSvg_v2: /<svg\b[\s\S]*?<\/svg>/g,
  inlineSvg_v3: /<svg.*?<\/svg>/gs,
  cdataSection: /<!\[CDATA\[.*?\]\]>/gs
};
const languageConfigs = [
  {
    displayTag: "cs",
    extensions: [".cs"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.csharpUsing,
      ContentFilterPatterns.csharpMethodSignature
    ]
  },
  {
    displayTag: "ts",
    extensions: [".ts"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.tsImportExport,
      ContentFilterPatterns.inlineSvg_v1,
      ContentFilterPatterns.inlineSvg_v2,
      ContentFilterPatterns.inlineSvg_v3,
      ContentFilterPatterns.tsFunctionDeclaration,
      ContentFilterPatterns.tsMethodSignature,
      ContentFilterPatterns.cdataSection
    ]
  },
  {
    displayTag: "tsx",
    extensions: [".tsx"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.tsImportExport,
      ContentFilterPatterns.inlineSvg_v1,
      ContentFilterPatterns.inlineSvg_v2,
      ContentFilterPatterns.inlineSvg_v3,
      ContentFilterPatterns.tsFunctionDeclaration,
      ContentFilterPatterns.tsMethodSignature,
      ContentFilterPatterns.cdataSection
    ]
  },
  {
    displayTag: "js",
    extensions: [".js"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.tsImportExport,
      ContentFilterPatterns.inlineSvg_v1,
      ContentFilterPatterns.inlineSvg_v2,
      ContentFilterPatterns.inlineSvg_v3,
      ContentFilterPatterns.tsFunctionDeclaration,
      ContentFilterPatterns.tsMethodSignature,
      ContentFilterPatterns.cdataSection
    ]
  },
  {
    displayTag: "jsx",
    extensions: [".jsx"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.tsImportExport,
      ContentFilterPatterns.inlineSvg_v1,
      ContentFilterPatterns.inlineSvg_v2,
      ContentFilterPatterns.inlineSvg_v3,
      ContentFilterPatterns.tsFunctionDeclaration,
      ContentFilterPatterns.tsMethodSignature,
      ContentFilterPatterns.cdataSection
    ]
  },
  {
    displayTag: "htm",
    extensions: [".html", ".htm"],
    patternsToBlank: [
      ContentFilterPatterns.inlineSvg_v1,
      ContentFilterPatterns.inlineSvg_v2,
      ContentFilterPatterns.inlineSvg_v3,
      ContentFilterPatterns.cdataSection
    ]
  },
  {
    displayTag: "py",
    extensions: [".py"],
    patternsToBlank: [
      ContentFilterPatterns.pythonDocstring,
      ContentFilterPatterns.hashComment,
      ContentFilterPatterns.pythonImport,
      ContentFilterPatterns.pythonDefinition
    ]
  },
  {
    displayTag: "go",
    extensions: [".go"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.goImportSingle,
      ContentFilterPatterns.goImportGroup,
      ContentFilterPatterns.goFunction
    ]
  },
  {
    displayTag: "rs",
    extensions: [".rs"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.rustUse,
      ContentFilterPatterns.rustFunction
    ]
  },
  {
    displayTag: "jav",
    extensions: [".java"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.javaPackage,
      ContentFilterPatterns.javaImport,
      ContentFilterPatterns.csharpMethodSignature
    ]
  },
  {
    displayTag: "c",
    extensions: [".c", ".h"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.cppInclude,
      ContentFilterPatterns.cppDefine
    ]
  },
  {
    displayTag: "cpp",
    extensions: [".cpp", ".hpp"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cStyleLineComment,
      ContentFilterPatterns.cppInclude,
      ContentFilterPatterns.cppDefine
    ]
  },
  {
    displayTag: "css",
    extensions: [".css", ".scss", ".less"],
    patternsToBlank: [
      ContentFilterPatterns.cStyleBlockComment,
      ContentFilterPatterns.cssImport
    ]
  },
  {
    displayTag: "rb",
    extensions: [".rb"],
    patternsToBlank: [
      ContentFilterPatterns.rubyBlockComment,
      ContentFilterPatterns.hashComment,
      ContentFilterPatterns.rubyRequire,
      ContentFilterPatterns.rubyDef,
      ContentFilterPatterns.rubyClass
    ]
  }
];
function blankMatches(content, pattern) {
  return content.replace(pattern, (match) => {
    let blanked = "";
    for (let i = 0; i < match.length; i++) {
      const char = match[i];
      blanked += char === "\n" || char === "\r" ? char : " ";
    }
    return blanked;
  });
}
function applyContentFilter(content, filePath) {
  const extension = getFileExtension(filePath);
  for (const config of languageConfigs) {
    if (config.extensions.includes(extension)) {
      let filtered = content;
      for (const pattern of config.patternsToBlank) {
        filtered = blankMatches(filtered, pattern);
      }
      return { filteredContent: filtered, displayTag: config.displayTag };
    }
  }
  return { filteredContent: content, displayTag: null };
}
let persistentDb = {
  hashLocationMap: {},
  fileHashMap: {},
  processedFiles: /* @__PURE__ */ new Set()
};
function removeHashesForFile(filePath) {
  const normalizedPath = normalizePathSeparators(filePath);
  const hashesFromFile = persistentDb.fileHashMap[normalizedPath];
  if (!hashesFromFile) {
    return;
  }
  for (const hash of hashesFromFile) {
    const locations = persistentDb.hashLocationMap[hash];
    if (locations) {
      persistentDb.hashLocationMap[hash] = locations.filter(
        (loc) => normalizePathSeparators(loc.filePath) !== normalizedPath
      );
      if (persistentDb.hashLocationMap[hash].length === 0) {
        delete persistentDb.hashLocationMap[hash];
      }
    }
  }
  delete persistentDb.fileHashMap[normalizedPath];
  persistentDb.processedFiles.delete(normalizedPath);
}
function processFileDuplicationDetection(filePath, fileContent) {
  const normalizedPath = normalizePathSeparators(filePath);
  const { filteredContent, displayTag } = applyContentFilter(fileContent, filePath);
  const lines = filteredContent.split(/\r?\n/);
  const allTokens = [];
  for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
    const line = lines[lineIdx];
    const lineTokensWithPositions = tokenizeLineWithPositions(line);
    for (const { token, oneBasedColumn } of lineTokensWithPositions) {
      allTokens.push({
        token,
        lineNum: lineIdx + 1,
        colNum: oneBasedColumn
      });
    }
  }
  const activeTrackersPerTargetFile = /* @__PURE__ */ new Map();
  const trackersHitThisIteration = /* @__PURE__ */ new Set();
  const reportedFragments = [];
  const processedFragmentKeys = /* @__PURE__ */ new Set();
  const hashesFromThisFile = [];
  for (let tokenIdx = 0; tokenIdx <= allTokens.length - PHRASE_TOKEN_COUNT; tokenIdx++) {
    const phraseTokens = allTokens.slice(tokenIdx, tokenIdx + PHRASE_TOKEN_COUNT).map((t) => t.token);
    const windowStartLine = allTokens[tokenIdx].lineNum;
    const windowStartCol = allTokens[tokenIdx].colNum;
    if (phraseContainsRepeatedChars(phraseTokens)) {
      for (const trackerList of activeTrackersPerTargetFile.values()) {
        for (const tracker of trackerList) {
          tracker.consecutiveMisses++;
          tracker.lastTargetSequence++;
        }
      }
      continue;
    }
    const hash = computePhraseHash(phraseTokens);
    trackersHitThisIteration.clear();
    const matchingLocations = persistentDb.hashLocationMap[hash];
    if (matchingLocations && matchingLocations.length > 0) {
      for (const targetLoc of matchingLocations) {
        let trackersForFile = activeTrackersPerTargetFile.get(targetLoc.filePath);
        if (!trackersForFile) {
          trackersForFile = [];
          activeTrackersPerTargetFile.set(targetLoc.filePath, trackersForFile);
        }
        let matchingTracker = null;
        for (const tracker of trackersForFile) {
          if (targetLoc.tokenSequence === tracker.lastTargetSequence + 1) {
            matchingTracker = tracker;
            break;
          }
        }
        if (matchingTracker) {
          if (matchingTracker.consecutiveMisses > 0) {
            matchingTracker.misses += matchingTracker.consecutiveMisses;
            matchingTracker.consecutiveMisses = 0;
          }
          matchingTracker.hits++;
          matchingTracker.lastTargetSequence = targetLoc.tokenSequence;
          matchingTracker.lastMatchLine = targetLoc.lineNumber;
          trackersHitThisIteration.add(matchingTracker);
        } else {
          const sourceLine = lines[windowStartLine - 1];
          const sourceLineLength = sourceLine ? sourceLine.length : 0;
          let sourceIsTooLate = false;
          if (sourceLineLength > 0) {
            const sourceLineFraction = (windowStartCol - 1) / sourceLineLength;
            sourceIsTooLate = sourceLineFraction > MATCH_MUST_START_BEFORE_LINE_FRACTION;
          }
          if (sourceIsTooLate) {
            continue;
          }
          const newTracker = {
            targetFilePath: targetLoc.filePath,
            firstMatchLine: targetLoc.lineNumber,
            firstMatchCol: targetLoc.columnNumber,
            firstSourceTokenIdx: tokenIdx,
            firstSourceLine: windowStartLine,
            firstSourceCol: windowStartCol,
            lastMatchLine: targetLoc.lineNumber,
            lastTargetSequence: targetLoc.tokenSequence,
            hits: 1,
            misses: 0,
            consecutiveMisses: 0
          };
          trackersForFile.push(newTracker);
          trackersHitThisIteration.add(newTracker);
        }
      }
    }
    for (const trackerList of activeTrackersPerTargetFile.values()) {
      for (const tracker of trackerList) {
        if (!trackersHitThisIteration.has(tracker)) {
          tracker.consecutiveMisses++;
          tracker.lastTargetSequence++;
        }
      }
    }
    if (!persistentDb.hashLocationMap[hash]) {
      persistentDb.hashLocationMap[hash] = [];
    }
    persistentDb.hashLocationMap[hash].push({
      filePath: normalizedPath,
      lineNumber: windowStartLine,
      columnNumber: windowStartCol,
      tokenSequence: tokenIdx
    });
    hashesFromThisFile.push(hash);
  }
  persistentDb.fileHashMap[normalizedPath] = hashesFromThisFile;
  persistentDb.processedFiles.add(normalizedPath);
  for (const trackerList of activeTrackersPerTargetFile.values()) {
    for (const tracker of trackerList) {
      if (!trackerMeetsThreshold(tracker.hits, tracker.misses)) {
        continue;
      }
      const fragKey = `${normalizedPath}:${tracker.firstSourceLine}\u2192${tracker.targetFilePath}:${tracker.firstMatchLine}`;
      if (!processedFragmentKeys.has(fragKey)) {
        const fragment = {
          sourceLocation: {
            filePath: normalizedPath,
            lineNumber: tracker.firstSourceLine,
            columnNumber: tracker.firstSourceCol,
            tokenSequence: tracker.firstSourceTokenIdx
          },
          totalHits: tracker.hits,
          totalMisses: tracker.misses,
          matchLocations: [{
            filePath: tracker.targetFilePath,
            lineNumber: tracker.firstMatchLine,
            columnNumber: tracker.firstMatchCol,
            tokenSequence: 0
          }]
        };
        reportedFragments.push(fragment);
        processedFragmentKeys.add(fragKey);
      }
    }
  }
  return reportedFragments;
}
function rescanFile(filePath, fileContent) {
  removeHashesForFile(filePath);
  return processFileDuplicationDetection(filePath, fileContent);
}
function writeDebugLog(fragments, currentFilePath) {
  const debugLines = [];
  debugLines.push("=== CODE DUPLICATION DETECTION RESULTS ===");
  debugLines.push(`Current file: ${currentFilePath}`);
  debugLines.push(`Total fragments found: ${fragments.length}`);
  debugLines.push("");
  for (const frag of fragments) {
    const ratio = frag.totalHits / (frag.totalHits + frag.totalMisses);
    const effectiveLength = frag.totalHits;
    debugLines.push(`Fragment: ${frag.sourceLocation.filePath}:${frag.sourceLocation.lineNumber} (1-based)`);
    debugLines.push(`  Tokens: ${effectiveLength}, Ratio: ${(ratio * 100).toFixed(1)}%`);
    debugLines.push(`  Matches:`);
    for (const matchLoc of frag.matchLocations) {
      const isSelfMatch = normalizePathSeparators(frag.sourceLocation.filePath) === normalizePathSeparators(matchLoc.filePath);
      debugLines.push(`    - ${matchLoc.filePath}:${matchLoc.lineNumber} (1-based)${isSelfMatch ? " [SELF-MATCH]" : ""}`);
    }
    debugLines.push("");
  }
  log("===== DEBUG LOG START =====");
  for (const line of debugLines) {
    log(line);
  }
  log("===== DEBUG LOG END =====");
}
function reportDuplicateFragments(fragments, currentFilePath) {
  writeDebugLog(fragments, currentFilePath);
  for (const frag of fragments) {
    const ratio = frag.totalHits / (frag.totalHits + frag.totalMisses);
    const effectiveLength = frag.totalHits;
    for (const matchLoc of frag.matchLocations) {
      if (normalizePathSeparators(frag.sourceLocation.filePath) === normalizePathSeparators(matchLoc.filePath)) {
        continue;
      }
      report({
        line: frag.sourceLocation.lineNumber,
        column: frag.sourceLocation.columnNumber,
        message: `Code duplication detected (${effectiveLength} tokens, ${(ratio * 100).toFixed(1)}% similar). Matches: ${matchLoc.filePath}:${matchLoc.lineNumber}:${matchLoc.columnNumber}`,
        severity: "warning",
        ruleId: "DUP001"
      });
    }
  }
}
let totalDuplicateFragments = 0;
let totalFilesProcessed = 0;
function updateGlobalInfo() {
  const totalHashes = Object.keys(persistentDb.hashLocationMap).length;
  const duplicatedHashes = Object.values(persistentDb.hashLocationMap).filter((locs) => locs.length > 1).length;
  const infoLines = [
    `Files processed: ${totalFilesProcessed}`,
    `Phrase hashes: ${totalHashes.toLocaleString()} (${duplicatedHashes.toLocaleString()} duplicated)`,
    `Duplicate fragments: ${totalDuplicateFragments}`
  ];
  setGlobalInfoLines(infoLines);
}
registerSaveCallback(() => {
  return {
    hashLocationMap: persistentDb.hashLocationMap,
    fileHashMap: persistentDb.fileHashMap,
    processedFiles: Array.from(persistentDb.processedFiles),
    totalDuplicateFragments,
    totalFilesProcessed
  };
});
registerRestoreCallback((data) => {
  if (data) {
    persistentDb.hashLocationMap = data.hashLocationMap || {};
    persistentDb.fileHashMap = data.fileHashMap || {};
    persistentDb.processedFiles = new Set(data.processedFiles || []);
    totalDuplicateFragments = data.totalDuplicateFragments || 0;
    totalFilesProcessed = data.totalFilesProcessed || 0;
    updateGlobalInfo();
    log(`Restored database: ${Object.keys(persistentDb.hashLocationMap).length} hashes, ${persistentDb.processedFiles.size} files`);
  }
});
registerFileSaveHandler((file) => {
  const filePath = file.fileName;
  if (isExcludedPath(filePath)) {
    return;
  }
  if (!isSupportedFile(filePath)) {
    return;
  }
  const fragments = rescanFile(filePath, file.fileContent);
  totalFilesProcessed++;
  totalDuplicateFragments += fragments.length;
  reportDuplicateFragments(fragments, filePath);
  updateGlobalInfo();
  if (fragments.length > 0) {
    log(`File: ${file.fileBaseName} - Found ${fragments.length} duplicate fragments`);
  }
});
requestPersistentContext({ preRunAllFiles: true });
log("Code duplication detector initialized - ONE-PASS algorithm active");
log("Persistence enabled: database preserved across file saves");
log("Pre-run enabled: will scan all workspace files on startup");
