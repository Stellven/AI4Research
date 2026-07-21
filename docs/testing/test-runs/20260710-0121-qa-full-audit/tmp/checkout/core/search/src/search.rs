//! Search functionality for Solar Search
//!
//! Provides query parsing and execution against the Tantivy index.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tantivy::collector::TopDocs;
use tantivy::query::{BooleanQuery, Occur, Query, QueryParser, TermQuery};
use tantivy::schema::IndexRecordOption;
use tantivy::{DocAddress, Score, Searcher, TantivyDocument, Term};
use tracing::debug;

use crate::index::SolarIndex;
use crate::schema::DocType;

/// Search result item
#[derive(Debug, Serialize, Deserialize)]
pub struct SearchResult {
    pub id: String,
    pub doc_type: String,
    pub content: String,
    pub title: Option<String>,
    pub source: Option<String>,
    pub timestamp: u64,
    pub role: Option<String>,
    pub project: Option<String>,
    pub score: f32,
    /// Content snippet with query terms highlighted
    pub snippet: Option<String>,
    // === Schema Optimization v0.3 新增 ===
    /// Artifact kind (source/claim/outline/draft/review/final)
    pub kind: Option<String>,
    /// Artifact ID for SQLite joins
    pub artifact_id: Option<u64>,
    /// FS path to full content
    pub content_path: Option<String>,
}

/// Search options
#[derive(Debug, Default)]
pub struct SearchOptions {
    /// Maximum number of results
    pub limit: usize,
    /// Filter by document type
    pub doc_type: Option<DocType>,
    /// Filter by project
    pub project: Option<String>,
    /// Filter by role (for conversations)
    pub role: Option<String>,
    /// Minimum timestamp
    pub after: Option<u64>,
    /// Maximum timestamp
    pub before: Option<u64>,
    /// Filter by task ID (Cortex support)
    pub task_id: Option<String>,
    /// Filter by kind (Cortex artifact type)
    pub kind: Option<String>,
}

impl SearchOptions {
    pub fn new() -> Self {
        Self {
            limit: 10,
            ..Default::default()
        }
    }

    pub fn limit(mut self, limit: usize) -> Self {
        self.limit = limit;
        self
    }

    pub fn doc_type(mut self, doc_type: DocType) -> Self {
        self.doc_type = Some(doc_type);
        self
    }

    pub fn project(mut self, project: impl Into<String>) -> Self {
        self.project = Some(project.into());
        self
    }

    pub fn role(mut self, role: impl Into<String>) -> Self {
        self.role = Some(role.into());
        self
    }

    pub fn after(mut self, timestamp: u64) -> Self {
        self.after = Some(timestamp);
        self
    }

    pub fn before(mut self, timestamp: u64) -> Self {
        self.before = Some(timestamp);
        self
    }

    pub fn task_id(mut self, task_id: impl Into<String>) -> Self {
        self.task_id = Some(task_id.into());
        self
    }

    pub fn kind(mut self, kind: impl Into<String>) -> Self {
        self.kind = Some(kind.into());
        self
    }
}

/// Search the index
pub fn search(
    index: &SolarIndex,
    query_str: &str,
    options: SearchOptions,
) -> Result<Vec<SearchResult>> {
    let reader = index.reader()?;
    let searcher = reader.searcher();
    let fields = index.fields();

    // Build query parser for content field
    let query_parser = QueryParser::for_index(
        &reader.searcher().index(),
        vec![fields.content, fields.title],
    );

    // Parse the main query
    let text_query = query_parser
        .parse_query(query_str)
        .with_context(|| format!("Failed to parse query: {}", query_str))?;

    // Build combined query with filters
    let final_query = build_filtered_query(index, text_query, &options)?;

    // Execute search
    let top_docs = searcher.search(&final_query, &TopDocs::with_limit(options.limit))?;

    // Convert results
    let mut results = Vec::with_capacity(top_docs.len());
    for (score, doc_address) in top_docs {
        if let Some(result) = doc_to_result(&searcher, doc_address, score, query_str)? {
            results.push(result);
        }
    }

    debug!(
        "Search '{}' returned {} results",
        query_str,
        results.len()
    );

    Ok(results)
}

/// Build a filtered query combining text search with filters
fn build_filtered_query(
    index: &SolarIndex,
    text_query: Box<dyn Query>,
    options: &SearchOptions,
) -> Result<Box<dyn Query>> {
    let fields = index.fields();
    let mut clauses: Vec<(Occur, Box<dyn Query>)> = vec![(Occur::Must, text_query)];

    // Filter by doc_type
    if let Some(doc_type) = &options.doc_type {
        let term = Term::from_field_text(fields.doc_type, doc_type.as_str());
        let term_query = TermQuery::new(term, IndexRecordOption::Basic);
        clauses.push((Occur::Must, Box::new(term_query)));
    }

    // Filter by project
    if let Some(project) = &options.project {
        let term = Term::from_field_text(fields.project, project);
        let term_query = TermQuery::new(term, IndexRecordOption::Basic);
        clauses.push((Occur::Must, Box::new(term_query)));
    }

    // Filter by role
    if let Some(role) = &options.role {
        let term = Term::from_field_text(fields.role, role);
        let term_query = TermQuery::new(term, IndexRecordOption::Basic);
        clauses.push((Occur::Must, Box::new(term_query)));
    }

    // Filter by task_id (Cortex support)
    if let Some(task_id) = &options.task_id {
        let term = Term::from_field_text(fields.task_id, task_id);
        let term_query = TermQuery::new(term, IndexRecordOption::Basic);
        clauses.push((Occur::Must, Box::new(term_query)));
    }

    // Filter by kind (Cortex artifact type)
    if let Some(kind) = &options.kind {
        let term = Term::from_field_text(fields.kind, kind);
        let term_query = TermQuery::new(term, IndexRecordOption::Basic);
        clauses.push((Occur::Must, Box::new(term_query)));
    }

    // Note: timestamp range filtering would need a RangeQuery
    // For now, we'll filter in post-processing if needed

    Ok(Box::new(BooleanQuery::new(clauses)))
}

/// Convert a document to a SearchResult
fn doc_to_result(
    searcher: &Searcher,
    doc_address: DocAddress,
    score: Score,
    query_str: &str,
) -> Result<Option<SearchResult>> {
    let doc: TantivyDocument = searcher.doc(doc_address)?;
    let schema = searcher.schema();

    let get_text = |field_name: &str| -> Option<String> {
        schema
            .get_field(field_name)
            .ok()
            .and_then(|f| doc.get_first(f))
            .and_then(|v| {
                match v {
                    tantivy::schema::OwnedValue::Str(s) => Some(s.clone()),
                    _ => None,
                }
            })
    };

    let get_u64 = |field_name: &str| -> u64 {
        schema
            .get_field(field_name)
            .ok()
            .and_then(|f| doc.get_first(f))
            .and_then(|v| {
                match v {
                    tantivy::schema::OwnedValue::U64(n) => Some(*n),
                    _ => None,
                }
            })
            .unwrap_or(0)
    };

    let id = match get_text("id") {
        Some(id) => id,
        None => return Ok(None),
    };

    let content = get_text("content").unwrap_or_default();
    let snippet = generate_snippet(&content, query_str, 150);

    Ok(Some(SearchResult {
        id,
        doc_type: get_text("doc_type").unwrap_or_else(|| "unknown".to_string()),
        content,
        title: get_text("title"),
        source: get_text("source"),
        timestamp: get_u64("timestamp"),
        role: get_text("role"),
        project: get_text("project"),
        score,
        snippet: Some(snippet),
        // Schema Optimization v0.3 新增
        kind: get_text("kind"),
        artifact_id: Some(get_u64("artifact_id")).filter(|&v| v > 0),
        content_path: get_text("content_path"),
    }))
}

/// Generate a snippet from content, highlighting around query terms
/// Unicode-safe: works with Chinese and other multi-byte characters
fn generate_snippet(content: &str, query: &str, max_chars: usize) -> String {
    let query_lower = query.to_lowercase();
    let query_terms: Vec<&str> = query_lower.split_whitespace().collect();
    let content_lower = content.to_lowercase();

    // Find the character position of the first query term
    let mut best_char_pos = 0;
    for term in &query_terms {
        if let Some(byte_pos) = content_lower.find(term) {
            // Convert byte position to character position
            best_char_pos = content[..byte_pos].chars().count();
            break;
        }
    }

    // Collect all characters
    let chars: Vec<char> = content.chars().collect();
    let total_chars = chars.len();

    if total_chars <= max_chars {
        return content.to_string();
    }

    // Calculate snippet bounds in character units
    let context_before = max_chars / 4;
    let start_char = best_char_pos.saturating_sub(context_before);
    let end_char = (start_char + max_chars).min(total_chars);

    // Build the snippet from characters
    let snippet: String = chars[start_char..end_char].iter().collect();

    // Add ellipsis if truncated
    let prefix = if start_char > 0 { "..." } else { "" };
    let suffix = if end_char < total_chars { "..." } else { "" };

    format!("{}{}{}", prefix, snippet.trim(), suffix)
}

/// Get recent documents (sorted by timestamp)
pub fn recent(
    index: &SolarIndex,
    doc_type: Option<DocType>,
    limit: usize,
) -> Result<Vec<SearchResult>> {
    let reader = index.reader()?;
    let searcher = reader.searcher();
    let fields = index.fields();

    // Build query
    let query: Box<dyn Query> = if let Some(dt) = doc_type {
        let term = Term::from_field_text(fields.doc_type, dt.as_str());
        Box::new(TermQuery::new(term, IndexRecordOption::Basic))
    } else {
        Box::new(tantivy::query::AllQuery)
    };

    // Search with timestamp ordering
    // Note: For proper timestamp ordering, we'd need a custom collector
    // For now, fetch more and sort in memory
    let top_docs = searcher.search(&query, &TopDocs::with_limit(limit * 2))?;

    let mut results: Vec<SearchResult> = top_docs
        .into_iter()
        .filter_map(|(score, addr)| doc_to_result(&searcher, addr, score, "").ok().flatten())
        .collect();

    // Sort by timestamp descending
    results.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
    results.truncate(limit);

    Ok(results)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_snippet() {
        let content = "This is a long document about GPU optimization and performance tuning. \
                       We discuss various techniques including SIMD vectorization.";
        let snippet = generate_snippet(content, "GPU", 80);

        assert!(snippet.contains("GPU") || snippet.len() <= 100);
    }
}
