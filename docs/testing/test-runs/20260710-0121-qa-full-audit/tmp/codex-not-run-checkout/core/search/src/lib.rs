//! Solar Search - High-performance search engine for Solar OS
//!
//! Built on Tantivy with Chinese tokenization support (jieba-rs).
//!
//! # Features
//!
//! - Full-text search with Chinese support
//! - Incremental indexing via queue
//! - File watching for automatic updates
//! - SQLite integration for queue persistence
//!
//! # Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────┐
//! │               Solar Search                   │
//! ├─────────────────────────────────────────────┤
//! │  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
//! │  │ Watcher │→ │  Queue  │→ │  Index  │    │
//! │  └─────────┘  └─────────┘  └─────────┘    │
//! │       ↓                          ↓         │
//! │  File System              Tantivy Index    │
//! │  SQLite DB                                 │
//! └─────────────────────────────────────────────┘
//! ```

pub mod schema;
pub mod tokenizer;
pub mod index;
pub mod search;
pub mod queue;
pub mod watcher;

pub use schema::{DocType, SchemaFields, build_schema};
pub use tokenizer::JiebaTokenizer;
pub use index::{SolarIndex, default_index_path};
pub use search::{SearchResult, SearchOptions, search, recent};
pub use queue::{IndexQueue, QueueItem, QueueStats};
pub use watcher::{FileWatcher, WatchConfig};

/// Re-export commonly used types
pub mod prelude {
    pub use crate::{
        DocType,
        SolarIndex,
        SearchOptions,
        SearchResult,
        IndexQueue,
        FileWatcher,
        WatchConfig,
        search,
        recent,
    };
}
