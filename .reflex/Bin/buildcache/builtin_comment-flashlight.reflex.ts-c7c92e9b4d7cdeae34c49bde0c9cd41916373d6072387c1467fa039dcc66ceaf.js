const codeFileExtensions = [
  // C family
  ".c",
  ".cpp",
  ".cc",
  ".cxx",
  ".h",
  ".hpp",
  ".hxx",
  // C#
  ".cs",
  ".csx",
  // Java
  ".java",
  ".kt",
  ".kts",
  // JavaScript/TypeScript
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".mjs",
  ".cjs",
  // Python
  ".py",
  ".pyw",
  // Ruby
  ".rb",
  ".rbw",
  // Go
  ".go",
  // Rust
  ".rs",
  // PHP
  ".php",
  ".phtml",
  // Swift
  ".swift",
  // Objective-C
  ".m",
  ".mm",
  // Shell scripts
  ".sh",
  ".bash",
  ".zsh",
  ".fish",
  ".bat",
  ".ps1",
  ".psm1",
  ".psd1",
  ".ps1xml",
  // Other common
  ".scala",
  ".clj",
  ".cljs",
  ".erl",
  ".ex",
  ".exs",
  ".elm",
  ".hs",
  ".lua",
  ".r"
];
const activeCommentPatterns = [
  { keyword: "TODO", emoji: "\u{1F4CB}", ruleId: "FLASHLIGHT_TODO", defaultMessage: "TODO item found" },
  { keyword: "CRITICAL", emoji: "\u{1F525}", ruleId: "FLASHLIGHT_CRITICAL", defaultMessage: "Critical issue marked" },
  { keyword: "WARNING", emoji: "\u26A0\uFE0F", ruleId: "FLASHLIGHT_WARNING", defaultMessage: "Warning noted" },
  { keyword: "REMEMBER", emoji: "\u{1F4A1}", ruleId: "FLASHLIGHT_REMEMBER", defaultMessage: "Remember this context" }
];
registerFileSaveHandler((file) => {
  const fileExtension = file.fileName.slice(file.fileName.lastIndexOf(".")).toLowerCase();
  if (!codeFileExtensions.includes(fileExtension)) {
    return;
  }
  const processedLineIndices = /* @__PURE__ */ new Set();
  function accumulateAdjacentCommentLines(startLineIndex, initialMessage) {
    let accumulatedMessage = initialMessage;
    for (let nextLineIndex = startLineIndex + 1; nextLineIndex < file.lines.length; nextLineIndex++) {
      const nextLine = file.lines[nextLineIndex];
      const continuationMatch = nextLine.match(/^\s*(\/\/|#)\s*(.*)$/);
      if (!continuationMatch) {
        break;
      }
      const commentContent = continuationMatch[2].trim();
      if (commentContent === "") {
        break;
      }
      const hasKeyword = activeCommentPatterns.some(
        (p) => new RegExp(`^${p.keyword}\\s*:`, "i").test(commentContent)
      );
      if (hasKeyword) {
        break;
      }
      accumulatedMessage += " " + commentContent;
      processedLineIndices.add(nextLineIndex);
    }
    return accumulatedMessage;
  }
  for (let lineIndex = 0; lineIndex < file.lines.length; lineIndex++) {
    if (processedLineIndices.has(lineIndex)) {
      continue;
    }
    const lineText = file.lines[lineIndex];
    const lineNumber = lineIndex + 1;
    for (const pattern of activeCommentPatterns) {
      const regex = new RegExp(`(//|#)\\s*${pattern.keyword}\\s*:?\\s*(.*)`, "i");
      const match = lineText.match(regex);
      if (match) {
        const initialMessage = match[2].trim() || pattern.defaultMessage;
        const commentStartColumn = lineText.indexOf(match[0]) + 1;
        const fullMessage = accumulateAdjacentCommentLines(lineIndex, initialMessage);
        report({
          line: lineNumber,
          column: commentStartColumn,
          message: `${pattern.emoji} ${pattern.keyword}: ${fullMessage}`,
          severity: "error",
          ruleId: pattern.ruleId
        });
        break;
      }
    }
  }
  log(`Flashlight scanned ${file.fileBaseName}`);
});
log("Comment Flashlight reflex initialized [ephemeral]");
