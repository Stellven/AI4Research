//! Document schema for Solar Search
//!
//! Defines the structure of indexed documents across all data sources.

use tantivy::schema::{Schema, STORED, TEXT, STRING, FAST};
use tantivy::schema::{TextFieldIndexing, TextOptions, IndexRecordOption};

/// Document types in Solar
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DocType {
    /// Conversation messages from .jsonl
    Conversation,
    /// Semantic/episodic/procedural memories
    Memory,
    /// Source code files
    Code,
    /// Documentation and markdown
    Document,
    /// System registry entries (skills, agents, etc.)
    Registry,
    /// Statistics and logs
    Stats,
    // === Cortex Query v0.2 新增 ===
    /// Cortex artifacts (prompts, outlines, drafts, reports)
    Artifact,
    /// Cortex reference sources
    Source,
    /// Cortex claims/conclusions
    Claim,
    /// Knowledge network entities
    Knowledge,
}

impl DocType {
    pub fn as_str(&self) -> &'static str {
        match self {
            DocType::Conversation => "conversation",
            DocType::Memory => "memory",
            DocType::Code => "code",
            DocType::Document => "document",
            DocType::Registry => "registry",
            DocType::Stats => "stats",
            DocType::Artifact => "artifact",
            DocType::Source => "source",
            DocType::Claim => "claim",
            DocType::Knowledge => "knowledge",
        }
    }

    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "conversation" => Some(DocType::Conversation),
            "memory" => Some(DocType::Memory),
            "code" => Some(DocType::Code),
            "document" => Some(DocType::Document),
            "registry" => Some(DocType::Registry),
            "stats" => Some(DocType::Stats),
            "artifact" => Some(DocType::Artifact),
            "source" => Some(DocType::Source),
            "claim" => Some(DocType::Claim),
            "knowledge" => Some(DocType::Knowledge),
            _ => None,
        }
    }
}

/// Build the Tantivy schema for Solar documents
pub fn build_schema() -> Schema {
    let mut schema_builder = Schema::builder();

    // Unique identifier
    schema_builder.add_text_field("id", STRING | STORED);

    // Document type (conversation, memory, code, etc.)
    schema_builder.add_text_field("doc_type", STRING | STORED | FAST);

    // Main content - full-text indexed with Chinese support
    let text_indexing = TextFieldIndexing::default()
        .set_tokenizer("jieba")
        .set_index_option(IndexRecordOption::WithFreqsAndPositions);
    let text_options = TextOptions::default()
        .set_indexing_options(text_indexing)
        .set_stored();
    schema_builder.add_text_field("content", text_options);

    // Title/subject (for conversations, memory titles, etc.)
    schema_builder.add_text_field("title", TEXT | STORED);

    // Source file path
    schema_builder.add_text_field("source", STRING | STORED);

    // Timestamp (Unix timestamp in seconds)
    schema_builder.add_u64_field("timestamp", STORED | FAST);

    // Role (for conversations: user/assistant/system)
    schema_builder.add_text_field("role", STRING | STORED);

    // Project context
    schema_builder.add_text_field("project", STRING | STORED);

    // Additional metadata as JSON string
    schema_builder.add_text_field("metadata", STORED);

    // === Cortex Query v0.2 新增字段 ===

    // Credibility score (0.0 - 1.0) for artifacts/sources/claims
    schema_builder.add_f64_field("score", STORED | FAST);

    // Artifact kind: 'source' | 'claim' | 'outline' | 'draft' | 'review' | 'final'
    schema_builder.add_text_field("kind", STRING | STORED);

    // Tags (comma-separated, searchable)
    schema_builder.add_text_field("tags", TEXT | STORED);

    // Explicit task_id for Cortex artifacts
    schema_builder.add_text_field("task_id", STRING | STORED);

    // Citation key for references
    schema_builder.add_text_field("citation_key", STRING | STORED);

    // === Schema Optimization v0.3 ===

    // Numeric artifact ID for efficient SQLite joins (extracted from id string)
    schema_builder.add_u64_field("artifact_id", STORED | FAST);

    // FS path to full content (for "装配" phase)
    schema_builder.add_text_field("content_path", STRING | STORED);

    schema_builder.build()
}

/// Field accessors for the schema
pub struct SchemaFields {
    pub id: tantivy::schema::Field,
    pub doc_type: tantivy::schema::Field,
    pub content: tantivy::schema::Field,
    pub title: tantivy::schema::Field,
    pub source: tantivy::schema::Field,
    pub timestamp: tantivy::schema::Field,
    pub role: tantivy::schema::Field,
    pub project: tantivy::schema::Field,
    pub metadata: tantivy::schema::Field,
    // Cortex Query v0.2 新增
    pub score: tantivy::schema::Field,
    pub kind: tantivy::schema::Field,
    pub tags: tantivy::schema::Field,
    pub task_id: tantivy::schema::Field,
    pub citation_key: tantivy::schema::Field,
    // Schema Optimization v0.3 新增
    pub artifact_id: tantivy::schema::Field,
    pub content_path: tantivy::schema::Field,
}

impl SchemaFields {
    pub fn new(schema: &Schema) -> Self {
        Self {
            id: schema.get_field("id").unwrap(),
            doc_type: schema.get_field("doc_type").unwrap(),
            content: schema.get_field("content").unwrap(),
            title: schema.get_field("title").unwrap(),
            source: schema.get_field("source").unwrap(),
            timestamp: schema.get_field("timestamp").unwrap(),
            role: schema.get_field("role").unwrap(),
            project: schema.get_field("project").unwrap(),
            metadata: schema.get_field("metadata").unwrap(),
            // Cortex Query v0.2 新增
            score: schema.get_field("score").unwrap(),
            kind: schema.get_field("kind").unwrap(),
            tags: schema.get_field("tags").unwrap(),
            task_id: schema.get_field("task_id").unwrap(),
            citation_key: schema.get_field("citation_key").unwrap(),
            // Schema Optimization v0.3 新增
            artifact_id: schema.get_field("artifact_id").unwrap(),
            content_path: schema.get_field("content_path").unwrap(),
        }
    }
}
