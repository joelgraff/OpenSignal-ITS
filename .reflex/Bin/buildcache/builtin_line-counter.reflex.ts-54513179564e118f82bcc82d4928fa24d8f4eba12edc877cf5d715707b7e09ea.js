let BIG_FILE_WARNING_THRESHOLD = 1200;
let fileDatabase = {};
requestPersistentContext({ preRunAllFiles: true });
registerSaveCallback(() => {
  return fileDatabase;
});
registerRestoreCallback((savedData) => {
  fileDatabase = savedData;
  log(`Restored line counts for ${Object.keys(fileDatabase).length} files`);
  updateGlobalInfo();
});
registerFileSaveHandler((file) => {
  const language = file.languageId || "plaintext";
  fileDatabase[file.fileName] = {
    language,
    lineCount: file.lineCount
  };
  if (file.lineCount > BIG_FILE_WARNING_THRESHOLD) {
    report({
      line: 1,
      message: `Large file is ${file.lineCount.toLocaleString()} lines of ${language} - consider refactoring`,
      severity: "warning",
      ruleId: "large-file"
    });
  }
  updateGlobalInfo();
});
function updateGlobalInfo() {
  const lineCountsByLanguage = {};
  let totalLines = 0;
  for (const fileData of Object.values(fileDatabase)) {
    if (!fileData || typeof fileData.lineCount !== "number" || !fileData.language) {
      continue;
    }
    const lang = fileData.language;
    const count = fileData.lineCount;
    if (!lineCountsByLanguage[lang]) {
      lineCountsByLanguage[lang] = 0;
    }
    lineCountsByLanguage[lang] += count;
    totalLines += count;
  }
  const sortedLanguages = Object.entries(lineCountsByLanguage).filter(([_lang, count]) => count > 0).sort((a, b) => b[1] - a[1]);
  const infoLines = [];
  for (const [language, count] of sortedLanguages) {
    const percentage = (count / totalLines * 100).toFixed(1);
    infoLines.push(`  ${language}: ${count.toLocaleString()} lines (${percentage}%)`);
  }
  infoLines.push(`  Total: ${totalLines.toLocaleString()} lines in ${Object.keys(fileDatabase).length} files`);
  setGlobalInfoLines(infoLines);
}
log("Line counter initialized with persistent context");
