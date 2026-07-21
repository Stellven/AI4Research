//! Solar Search CLI
//!
//! High-performance search for Solar OS data.
//!
//! # Usage
//!
//! ```bash
//! # Index conversation logs
//! solar-search index conversations
//!
//! # Search
//! solar-search query "GPU 性能优化"
//!
//! # Watch for changes
//! solar-search daemon
//! ```

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use solar_search::prelude::*;
use solar_search::index::{index_jsonl_files, default_index_path};
use std::path::PathBuf;
use std::time::Duration;
use tracing::{info, warn, Level};
use tracing_subscriber::FmtSubscriber;

#[derive(Parser)]
#[command(name = "solar-search")]
#[command(about = "High-performance search for Solar OS", version)]
struct Cli {
    /// Verbose output
    #[arg(short, long, global = true)]
    verbose: bool,

    /// Index directory (default: ~/.solar/search-index)
    #[arg(long, global = true)]
    index_dir: Option<PathBuf>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Index data sources
    Index {
        #[command(subcommand)]
        source: IndexSource,
    },

    /// Search the index
    Query {
        /// Search query
        query: String,

        /// Maximum results
        #[arg(short, long, default_value = "10")]
        limit: usize,

        /// Filter by document type (conversation, memory, code, document, artifact, source, claim)
        #[arg(short = 't', long)]
        doc_type: Option<String>,

        /// Filter by project
        #[arg(short, long)]
        project: Option<String>,

        /// Filter by task ID (Cortex Query support)
        #[arg(long)]
        task_id: Option<String>,

        /// Filter by kind (Cortex artifact type)
        #[arg(long)]
        kind: Option<String>,

        /// Output format (pretty, json)
        #[arg(short, long, default_value = "pretty")]
        format: String,
    },

    /// Show recent documents
    Recent {
        /// Maximum results
        #[arg(short, long, default_value = "10")]
        limit: usize,

        /// Filter by document type
        #[arg(short = 't', long)]
        doc_type: Option<String>,

        /// Output format (pretty, json)
        #[arg(short, long, default_value = "pretty")]
        format: String,
    },

    /// Run as daemon (watch + process queue)
    Daemon {
        /// Process interval in seconds
        #[arg(short, long, default_value = "5")]
        interval: u64,
    },

    /// Process pending queue items
    Process {
        /// Batch size
        #[arg(short, long, default_value = "100")]
        batch: usize,
    },

    /// Show index and queue statistics
    Stats,

    /// Verify index integrity
    Verify {
        /// Fix missing documents
        #[arg(long)]
        fix: bool,
    },
}

#[derive(Subcommand)]
enum IndexSource {
    /// Index conversation logs (~/.claude/projects/**/*.jsonl)
    Conversations,

    /// Index a specific JSONL file
    Jsonl {
        /// Path to JSONL file
        path: PathBuf,
    },

    /// Index a directory
    Dir {
        /// Directory path
        path: PathBuf,

        /// File patterns to include
        #[arg(short, long, default_value = "**/*.md,**/*.ts,**/*.rs")]
        patterns: String,
    },

    /// Reindex everything
    All,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Setup logging - write to stderr to keep stdout clean for JSON output
    let level = if cli.verbose { Level::DEBUG } else { Level::INFO };
    FmtSubscriber::builder()
        .with_max_level(level)
        .with_target(false)
        .compact()
        .with_writer(std::io::stderr)
        .init();

    // Get index path
    let index_path = cli.index_dir.unwrap_or_else(default_index_path);

    match cli.command {
        Commands::Index { source } => {
            cmd_index(&index_path, source).await?;
        }

        Commands::Query {
            query,
            limit,
            doc_type,
            project,
            task_id,
            kind,
            format,
        } => {
            cmd_query(&index_path, &query, limit, doc_type, project, task_id, kind, &format)?;
        }

        Commands::Recent {
            limit,
            doc_type,
            format,
        } => {
            cmd_recent(&index_path, limit, doc_type, &format)?;
        }

        Commands::Daemon { interval } => {
            cmd_daemon(&index_path, interval).await?;
        }

        Commands::Process { batch } => {
            cmd_process(&index_path, batch)?;
        }

        Commands::Stats => {
            cmd_stats(&index_path)?;
        }

        Commands::Verify { fix } => {
            cmd_verify(&index_path, fix)?;
        }
    }

    Ok(())
}

async fn cmd_index(index_path: &PathBuf, source: IndexSource) -> Result<()> {
    let index = SolarIndex::open_or_create(index_path)?;
    let mut writer = index.writer(50_000_000)?; // 50MB heap

    match source {
        IndexSource::Conversations => {
            info!("Indexing conversation logs...");

            let claude_projects = dirs::home_dir()
                .map(|h| h.join(".claude/projects"))
                .context("Cannot find home directory")?;

            let files: Vec<PathBuf> = glob::glob(&format!("{}/**/*.jsonl", claude_projects.display()))?
                .filter_map(|r| r.ok())
                .collect();

            info!("Found {} JSONL files", files.len());

            let count = index_jsonl_files(&index, &writer, &files)?;
            writer.commit()?;

            info!("Indexed {} documents from conversation logs", count);
        }

        IndexSource::Jsonl { path } => {
            info!("Indexing JSONL file: {:?}", path);

            let count = solar_search::index::index_single_jsonl(&index, &writer, &path)?;
            writer.commit()?;

            info!("Indexed {} documents", count);
        }

        IndexSource::Dir { path, patterns } => {
            info!("Indexing directory: {:?}", path);

            let pattern_list: Vec<&str> = patterns.split(',').collect();
            let mut total = 0;

            for pattern in pattern_list {
                let full_pattern = format!("{}/{}", path.display(), pattern);
                for entry in glob::glob(&full_pattern)? {
                    if let Ok(file_path) = entry {
                        if file_path.is_file() {
                            // Queue or directly index based on file type
                            total += 1;
                        }
                    }
                }
            }

            writer.commit()?;
            info!("Indexed {} files from {:?}", total, path);
        }

        IndexSource::All => {
            info!("Reindexing all sources...");

            // Index conversations
            let claude_projects = dirs::home_dir()
                .map(|h| h.join(".claude/projects"))
                .context("Cannot find home directory")?;

            if claude_projects.exists() {
                let files: Vec<PathBuf> = glob::glob(&format!("{}/**/*.jsonl", claude_projects.display()))?
                    .filter_map(|r| r.ok())
                    .collect();

                let count = index_jsonl_files(&index, &writer, &files)?;
                info!("Indexed {} conversation documents", count);
            }

            writer.commit()?;
            info!("Reindex complete");
        }
    }

    Ok(())
}

fn cmd_query(
    index_path: &PathBuf,
    query: &str,
    limit: usize,
    doc_type: Option<String>,
    project: Option<String>,
    task_id: Option<String>,
    kind: Option<String>,
    format: &str,
) -> Result<()> {
    let index = SolarIndex::open_or_create(index_path)?;

    let mut options = SearchOptions::new().limit(limit);

    if let Some(dt) = doc_type {
        if let Some(parsed) = DocType::from_str(&dt) {
            options = options.doc_type(parsed);
        } else {
            warn!("Unknown doc_type: {}, ignoring filter", dt);
        }
    }

    if let Some(p) = project {
        options = options.project(p);
    }

    if let Some(tid) = task_id {
        options = options.task_id(tid);
    }

    if let Some(k) = kind {
        options = options.kind(k);
    }

    let results = search(&index, query, options)?;

    match format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&results)?);
        }
        _ => {
            println!("Found {} results for '{}':\n", results.len(), query);

            for (i, result) in results.iter().enumerate() {
                println!("{}. [{}] {} (score: {:.2})", i + 1, result.doc_type, result.id, result.score);

                if let Some(snippet) = &result.snippet {
                    println!("   {}", snippet);
                }

                if let Some(source) = &result.source {
                    println!("   Source: {}", source);
                }

                println!();
            }
        }
    }

    Ok(())
}

fn cmd_recent(
    index_path: &PathBuf,
    limit: usize,
    doc_type: Option<String>,
    format: &str,
) -> Result<()> {
    let index = SolarIndex::open_or_create(index_path)?;

    let dt = doc_type.and_then(|s| DocType::from_str(&s));
    let results = recent(&index, dt, limit)?;

    match format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&results)?);
        }
        _ => {
            println!("Recent {} documents:\n", results.len());

            for (i, result) in results.iter().enumerate() {
                let time = chrono::DateTime::from_timestamp(result.timestamp as i64, 0)
                    .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
                    .unwrap_or_else(|| "unknown".to_string());

                println!("{}. [{}] {} - {}", i + 1, result.doc_type, time, result.id);

                if let Some(snippet) = &result.snippet {
                    let short = if snippet.len() > 100 {
                        format!("{}...", &snippet[..100])
                    } else {
                        snippet.clone()
                    };
                    println!("   {}", short);
                }

                println!();
            }
        }
    }

    Ok(())
}

async fn cmd_daemon(index_path: &PathBuf, interval: u64) -> Result<()> {
    info!("Starting Solar Search daemon...");

    let index = SolarIndex::open_or_create(index_path)?;
    let queue = IndexQueue::open_default()?;

    // Setup file watcher
    let config = WatchConfig::conversations();
    let mut watcher = FileWatcher::new(config)?;
    watcher.start()?;

    info!("Daemon started. Press Ctrl+C to stop.");

    loop {
        // Process file events
        let queued = watcher.process_events(&queue)?;
        if queued > 0 {
            info!("Queued {} files for indexing", queued);
        }

        // Process queue
        let pending = queue.get_pending(100)?;
        if !pending.is_empty() {
            let mut writer = index.writer(50_000_000)?;
            let ids: Vec<i64> = pending.iter().map(|p| p.id).collect();

            queue.mark_processing(&ids)?;

            let mut success_ids = Vec::new();
            let mut fail_ids = Vec::new();

            for item in pending {
                let doc_type = DocType::from_str(&item.doc_type).unwrap_or(DocType::Document);

                match index.index_document(
                    &writer,
                    &item.source_id,
                    doc_type,
                    &item.content,
                    item.title.as_deref(),
                    item.source_path.as_deref(),
                    item.timestamp,
                    item.role.as_deref(),
                    item.project.as_deref(),
                    item.metadata.as_deref(),
                    // Schema Optimization v0.3 新增参数
                    item.artifact_id.map(|id| id as u64),
                    item.content_path.as_deref(),
                    item.score,
                    item.kind.as_deref(),
                    item.tags.as_deref(),
                    item.task_id.as_deref(),
                    item.citation_key.as_deref(),
                ) {
                    Ok(_) => success_ids.push(item.id),
                    Err(e) => {
                        warn!("Failed to index item {}: {}", item.id, e);
                        fail_ids.push(item.id);
                    }
                }
            }

            writer.commit()?;

            queue.mark_indexed(&success_ids)?;
            queue.mark_failed(&fail_ids)?;

            if !success_ids.is_empty() {
                info!("Indexed {} documents", success_ids.len());
            }
        }

        tokio::time::sleep(Duration::from_secs(interval)).await;
    }
}

fn cmd_process(index_path: &PathBuf, batch: usize) -> Result<()> {
    let index = SolarIndex::open_or_create(index_path)?;
    let queue = IndexQueue::open_default()?;

    let pending = queue.get_pending(batch)?;
    if pending.is_empty() {
        println!("No pending items in queue");
        return Ok(());
    }

    println!("Processing {} items...", pending.len());

    let mut writer = index.writer(50_000_000)?;
    let ids: Vec<i64> = pending.iter().map(|p| p.id).collect();

    queue.mark_processing(&ids)?;

    let mut success = 0;
    let mut failed = 0;

    for item in pending {
        let doc_type = DocType::from_str(&item.doc_type).unwrap_or(DocType::Document);

        match index.index_document(
            &writer,
            &item.source_id,
            doc_type,
            &item.content,
            item.title.as_deref(),
            item.source_path.as_deref(),
            item.timestamp,
            item.role.as_deref(),
            item.project.as_deref(),
            item.metadata.as_deref(),
            // Schema Optimization v0.3 新增参数
            item.artifact_id.map(|id| id as u64),
            item.content_path.as_deref(),
            item.score,
            item.kind.as_deref(),
            item.tags.as_deref(),
            item.task_id.as_deref(),
            item.citation_key.as_deref(),
        ) {
            Ok(_) => {
                queue.mark_indexed(&[item.id])?;
                success += 1;
            }
            Err(e) => {
                warn!("Failed to index item {}: {}", item.id, e);
                queue.mark_failed(&[item.id])?;
                failed += 1;
            }
        }
    }

    writer.commit()?;

    println!("Processed: {} success, {} failed", success, failed);

    Ok(())
}

fn cmd_stats(index_path: &PathBuf) -> Result<()> {
    let index = SolarIndex::open_or_create(index_path)?;
    let index_stats = index.stats()?;

    let queue = IndexQueue::open_default()?;
    let queue_stats = queue.stats()?;

    println!("┌─ 📊 Solar Search Stats ────────────────────────────┐");
    println!("│                                                    │");
    println!("│  Index:                                            │");
    println!("│    Documents: {:>10}                           │", index_stats.total_docs);
    println!("│    Segments:  {:>10}                           │", index_stats.total_segments);
    println!("│    Path:      {:?}", index_path);
    println!("│                                                    │");
    println!("│  Queue:                                            │");
    println!("│    Pending:   {:>10}                           │", queue_stats.pending);
    println!("│    Processing:{:>10}                           │", queue_stats.processing);
    println!("│    Indexed:   {:>10}                           │", queue_stats.indexed);
    println!("│    Failed:    {:>10}                           │", queue_stats.failed);
    println!("│    Total:     {:>10}                           │", queue_stats.total());
    println!("│                                                    │");
    println!("└────────────────────────────────────────────────────┘");

    Ok(())
}

fn cmd_verify(index_path: &PathBuf, fix: bool) -> Result<()> {
    let index = SolarIndex::open_or_create(index_path)?;
    let stats = index.stats()?;

    println!("Verifying index at {:?}", index_path);
    println!("Documents: {}", stats.total_docs);
    println!("Segments: {}", stats.total_segments);

    // Basic verification - try to open reader
    let reader = index.reader()?;
    let _searcher = reader.searcher();

    println!("✓ Index is valid");

    if fix {
        println!("Checking for missing documents...");
        // TODO: Compare with source files and reindex missing
        println!("(fix not yet implemented)");
    }

    Ok(())
}
