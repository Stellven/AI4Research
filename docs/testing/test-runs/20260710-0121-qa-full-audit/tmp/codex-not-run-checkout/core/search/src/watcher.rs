//! File watcher for automatic indexing
//!
//! Monitors specified directories and files for changes,
//! automatically queuing them for indexing.

use anyhow::{Context, Result};
use notify::{RecommendedWatcher, RecursiveMode};
use notify_debouncer_mini::{new_debouncer, DebouncedEvent, Debouncer};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{channel, Receiver};
use std::time::Duration;
use tracing::{debug, info, warn};

use crate::queue::IndexQueue;
use crate::schema::DocType;

/// Configuration for the file watcher
#[derive(Debug, Clone)]
pub struct WatchConfig {
    /// Directories to watch
    pub watch_paths: Vec<PathBuf>,
    /// File patterns to include (glob patterns)
    pub include_patterns: Vec<String>,
    /// File patterns to exclude
    pub exclude_patterns: Vec<String>,
    /// Debounce duration for batching changes
    pub debounce_duration: Duration,
}

impl Default for WatchConfig {
    fn default() -> Self {
        Self {
            watch_paths: vec![],
            include_patterns: vec![
                "**/*.jsonl".to_string(),  // Conversation logs
                "**/*.md".to_string(),     // Documentation
                "**/*.ts".to_string(),     // TypeScript
                "**/*.rs".to_string(),     // Rust
            ],
            exclude_patterns: vec![
                "**/node_modules/**".to_string(),
                "**/target/**".to_string(),
                "**/.git/**".to_string(),
            ],
            debounce_duration: Duration::from_secs(2),
        }
    }
}

impl WatchConfig {
    /// Create config for conversation log watching
    pub fn conversations() -> Self {
        let mut config = Self::default();
        config.watch_paths = vec![
            dirs::home_dir()
                .map(|h| h.join(".claude/projects"))
                .unwrap_or_default(),
        ];
        config.include_patterns = vec!["**/*.jsonl".to_string()];
        config
    }

    /// Create config for Solar state files
    pub fn solar_state() -> Self {
        let mut config = Self::default();
        config.watch_paths = vec![
            dirs::home_dir()
                .map(|h| h.join(".solar"))
                .unwrap_or_default(),
        ];
        config.include_patterns = vec![
            "**/*.md".to_string(),
            "**/*.json".to_string(),
        ];
        config.exclude_patterns = vec![
            "**/search-index/**".to_string(),
        ];
        config
    }

    /// Add a watch path
    pub fn add_path(mut self, path: impl Into<PathBuf>) -> Self {
        self.watch_paths.push(path.into());
        self
    }
}

/// File watcher that queues changes for indexing
pub struct FileWatcher {
    config: WatchConfig,
    debouncer: Debouncer<RecommendedWatcher>,
    receiver: Receiver<Result<Vec<DebouncedEvent>, notify::Error>>,
}

impl FileWatcher {
    /// Create a new file watcher
    pub fn new(config: WatchConfig) -> Result<Self> {
        let (tx, rx) = channel();

        let debouncer = new_debouncer(config.debounce_duration, tx)
            .context("Failed to create debouncer")?;

        Ok(Self {
            config,
            debouncer,
            receiver: rx,
        })
    }

    /// Start watching configured paths
    pub fn start(&mut self) -> Result<()> {
        for path in &self.config.watch_paths {
            if path.exists() {
                info!("Watching: {:?}", path);
                self.debouncer
                    .watcher()
                    .watch(path, RecursiveMode::Recursive)
                    .with_context(|| format!("Failed to watch: {:?}", path))?;
            } else {
                warn!("Watch path does not exist: {:?}", path);
            }
        }

        Ok(())
    }

    /// Process events and queue for indexing
    pub fn process_events(&self, queue: &IndexQueue) -> Result<usize> {
        let mut processed = 0;

        // Non-blocking receive
        while let Ok(result) = self.receiver.try_recv() {
            match result {
                Ok(events) => {
                    for event in events {
                        if self.should_process(&event.path) {
                            if let Err(e) = self.queue_file(queue, &event.path) {
                                warn!("Failed to queue file {:?}: {}", event.path, e);
                            } else {
                                processed += 1;
                            }
                        }
                    }
                }
                Err(e) => {
                    warn!("Watch error: {:?}", e);
                }
            }
        }

        if processed > 0 {
            debug!("Queued {} files for indexing", processed);
        }

        Ok(processed)
    }

    /// Check if a path should be processed
    fn should_process(&self, path: &Path) -> bool {
        let path_str = path.to_string_lossy();

        // Check exclusions first
        for pattern in &self.config.exclude_patterns {
            if glob::Pattern::new(pattern)
                .map(|p| p.matches(&path_str))
                .unwrap_or(false)
            {
                return false;
            }
        }

        // Check inclusions
        for pattern in &self.config.include_patterns {
            if glob::Pattern::new(pattern)
                .map(|p| p.matches(&path_str))
                .unwrap_or(false)
            {
                return true;
            }
        }

        false
    }

    /// Queue a file for indexing
    fn queue_file(&self, queue: &IndexQueue, path: &Path) -> Result<()> {
        // Determine document type from path
        let doc_type = detect_doc_type(path);

        // For JSONL files, we need special handling (each line is a doc)
        if path.extension().map(|e| e == "jsonl").unwrap_or(false) {
            return queue_jsonl_file(queue, path);
        }

        // For other files, read content and queue
        let content = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read file: {:?}", path))?;

        let source_id = format!("file:{}", path.to_string_lossy());
        let timestamp = std::fs::metadata(path)
            .and_then(|m| m.modified())
            .map(|t| t.duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs())
            .unwrap_or(0);

        let title = path.file_name().map(|n| n.to_string_lossy().to_string());

        queue.enqueue(
            doc_type,
            &source_id,
            &content,
            title.as_deref(),
            Some(&path.to_string_lossy()),
            timestamp,
            None,
            detect_project(path).as_deref(),
            None,
        )?;

        Ok(())
    }
}

/// Detect document type from file path
fn detect_doc_type(path: &Path) -> DocType {
    let path_str = path.to_string_lossy();

    if path_str.contains(".claude/projects") && path_str.ends_with(".jsonl") {
        DocType::Conversation
    } else if path_str.contains(".solar") {
        if path_str.contains("ont_") {
            DocType::Memory
        } else if path_str.contains("sys_") {
            DocType::Registry
        } else {
            DocType::Document
        }
    } else if matches!(path.extension().and_then(|e| e.to_str()), Some("ts" | "rs" | "py" | "js" | "cpp" | "h")) {
        DocType::Code
    } else if matches!(path.extension().and_then(|e| e.to_str()), Some("md" | "txt" | "html")) {
        DocType::Document
    } else {
        DocType::Document
    }
}

/// Detect project from file path
fn detect_project(path: &Path) -> Option<String> {
    let path_str = path.to_string_lossy();

    // Check for .claude/projects/{hash}
    if path_str.contains(".claude/projects/") {
        return path.ancestors()
            .find(|p| p.parent().map(|pp| pp.ends_with("projects")).unwrap_or(false))
            .and_then(|p| p.file_name())
            .map(|n| n.to_string_lossy().to_string());
    }

    // Check for ~/Solar, ~/ThunderDuck, etc.
    if let Some(home) = dirs::home_dir() {
        if path.starts_with(&home) {
            let relative = path.strip_prefix(&home).ok()?;
            return relative.components().next()
                .and_then(|c| c.as_os_str().to_str())
                .map(|s| s.to_string());
        }
    }

    None
}

/// Queue a JSONL file (each line is a separate document)
fn queue_jsonl_file(queue: &IndexQueue, path: &Path) -> Result<()> {
    use std::io::{BufRead, BufReader};

    let file = std::fs::File::open(path)?;
    let reader = BufReader::new(file);

    let source_path = path.to_string_lossy().to_string();
    let project = detect_project(path);

    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }

        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            if let Some(uuid) = json.get("uuid").and_then(|v| v.as_str()) {
                let content = json.get("content")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");

                if content.trim().is_empty() {
                    continue;
                }

                let role = json.get("type").and_then(|v| v.as_str());
                let timestamp = json.get("timestamp")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);

                // Use INSERT OR IGNORE to handle duplicates
                let _ = queue.enqueue(
                    DocType::Conversation,
                    uuid,
                    content,
                    None,
                    Some(&source_path),
                    timestamp,
                    role,
                    project.as_deref(),
                    Some(&line),
                );
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_doc_type() {
        assert_eq!(detect_doc_type(Path::new("/home/.claude/projects/abc/123.jsonl")), DocType::Conversation);
        assert_eq!(detect_doc_type(Path::new("/src/main.rs")), DocType::Code);
        assert_eq!(detect_doc_type(Path::new("/docs/README.md")), DocType::Document);
    }
}
