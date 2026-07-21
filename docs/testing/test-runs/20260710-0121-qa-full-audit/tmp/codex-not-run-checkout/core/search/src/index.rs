//! Index management for Solar Search
//!
//! Handles creating, writing, and maintaining the Tantivy index.

use anyhow::{Context, Result};
use std::path::{Path, PathBuf};
use tantivy::{Index, IndexWriter, TantivyDocument};
use tantivy::directory::MmapDirectory;
use tracing::{info, debug};

use crate::schema::{build_schema, SchemaFields, DocType};
use crate::tokenizer::JiebaTokenizer;

/// Default index location
pub fn default_index_path() -> PathBuf {
    dirs::home_dir()
        .map(|h| h.join(".solar").join("search-index"))
        .unwrap_or_else(|| PathBuf::from("/tmp/solar-search-index"))
}

/// Solar Search Index manager
pub struct SolarIndex {
    index: Index,
    schema: tantivy::schema::Schema,
    fields: SchemaFields,
}

impl SolarIndex {
    /// Open or create index at the specified path
    pub fn open_or_create(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        std::fs::create_dir_all(path)
            .with_context(|| format!("Failed to create index directory: {:?}", path))?;

        let schema = build_schema();
        let fields = SchemaFields::new(&schema);

        let index = if path.join("meta.json").exists() {
            info!("Opening existing index at {:?}", path);
            let dir = MmapDirectory::open(path)?;
            Index::open(dir)?
        } else {
            info!("Creating new index at {:?}", path);
            let dir = MmapDirectory::open(path)?;
            Index::create(dir, schema.clone(), tantivy::IndexSettings::default())?
        };

        // Register Chinese tokenizer
        let tokenizers = index.tokenizers();
        tokenizers.register("jieba", JiebaTokenizer::new());

        Ok(Self {
            index,
            schema,
            fields,
        })
    }

    /// Get an index writer with the specified heap size (in bytes)
    pub fn writer(&self, heap_size: usize) -> Result<IndexWriter> {
        self.index
            .writer(heap_size)
            .context("Failed to create index writer")
    }

    /// Get a reader for searching
    pub fn reader(&self) -> Result<tantivy::IndexReader> {
        self.index
            .reader_builder()
            .reload_policy(tantivy::ReloadPolicy::OnCommitWithDelay)
            .try_into()
            .context("Failed to create index reader")
    }

    /// Get schema and fields
    pub fn schema(&self) -> &tantivy::schema::Schema {
        &self.schema
    }

    pub fn fields(&self) -> &SchemaFields {
        &self.fields
    }

    /// Index a single document
    pub fn index_document(
        &self,
        writer: &IndexWriter,
        id: &str,
        doc_type: DocType,
        content: &str,
        title: Option<&str>,
        source: Option<&str>,
        timestamp: u64,
        role: Option<&str>,
        project: Option<&str>,
        metadata: Option<&str>,
        // Schema Optimization v0.3 新增参数
        artifact_id: Option<u64>,
        content_path: Option<&str>,
        score: Option<f64>,
        kind: Option<&str>,
        tags: Option<&str>,
        task_id: Option<&str>,
        citation_key: Option<&str>,
    ) -> Result<()> {
        let mut doc = TantivyDocument::new();

        doc.add_text(self.fields.id, id);
        doc.add_text(self.fields.doc_type, doc_type.as_str());
        doc.add_text(self.fields.content, content);

        if let Some(t) = title {
            doc.add_text(self.fields.title, t);
        }
        if let Some(s) = source {
            doc.add_text(self.fields.source, s);
        }

        doc.add_u64(self.fields.timestamp, timestamp);

        if let Some(r) = role {
            doc.add_text(self.fields.role, r);
        }
        if let Some(p) = project {
            doc.add_text(self.fields.project, p);
        }
        if let Some(m) = metadata {
            doc.add_text(self.fields.metadata, m);
        }

        // Schema Optimization v0.3 新增字段
        if let Some(aid) = artifact_id {
            doc.add_u64(self.fields.artifact_id, aid);
        }
        if let Some(cp) = content_path {
            doc.add_text(self.fields.content_path, cp);
        }
        if let Some(s) = score {
            doc.add_f64(self.fields.score, s);
        }
        if let Some(k) = kind {
            doc.add_text(self.fields.kind, k);
        }
        if let Some(t) = tags {
            doc.add_text(self.fields.tags, t);
        }
        if let Some(tid) = task_id {
            doc.add_text(self.fields.task_id, tid);
        }
        if let Some(ck) = citation_key {
            doc.add_text(self.fields.citation_key, ck);
        }

        writer.add_document(doc)?;
        debug!("Indexed document: id={}, type={:?}", id, doc_type);

        Ok(())
    }

    /// Delete a document by ID
    pub fn delete_document(&self, writer: &IndexWriter, id: &str) -> Result<()> {
        let term = tantivy::Term::from_field_text(self.fields.id, id);
        writer.delete_term(term);
        debug!("Deleted document: id={}", id);
        Ok(())
    }

    /// Get index statistics
    pub fn stats(&self) -> Result<IndexStats> {
        let reader = self.reader()?;
        let searcher = reader.searcher();

        let mut total_docs = 0;
        let mut total_segments = 0;

        for segment_reader in searcher.segment_readers() {
            total_docs += segment_reader.num_docs() as u64;
            total_segments += 1;
        }

        Ok(IndexStats {
            total_docs,
            total_segments,
        })
    }
}

#[derive(Debug)]
pub struct IndexStats {
    pub total_docs: u64,
    pub total_segments: u64,
}

/// Index multiple JSONL conversation files
pub fn index_jsonl_files(
    index: &SolarIndex,
    writer: &IndexWriter,
    files: &[PathBuf],
) -> Result<usize> {
    let mut count = 0;

    for file in files {
        count += index_single_jsonl(index, writer, file)?;
    }

    Ok(count)
}

/// Index a single JSONL file
pub fn index_single_jsonl(
    index: &SolarIndex,
    writer: &IndexWriter,
    path: &Path,
) -> Result<usize> {
    use std::io::{BufRead, BufReader};

    let file = std::fs::File::open(path)
        .with_context(|| format!("Failed to open JSONL file: {:?}", path))?;
    let reader = BufReader::new(file);

    let source = path.to_string_lossy().to_string();
    let project = extract_project_from_path(path);

    let mut count = 0;

    for (line_num, line) in reader.lines().enumerate() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }

        match serde_json::from_str::<serde_json::Value>(&line) {
            Ok(json) => {
                if let Some(doc_id) = json.get("uuid").and_then(|v| v.as_str()) {
                    // Claude Code JSONL format: message.content (for user/assistant)
                    // or .summary (for summary entries)
                    let content = json
                        .get("message")
                        .and_then(|m| m.get("content"))
                        .and_then(|v| {
                            // content can be string or array of content blocks
                            if let Some(s) = v.as_str() {
                                Some(s.to_string())
                            } else if let Some(arr) = v.as_array() {
                                // Extract text from content blocks
                                let texts: Vec<String> = arr.iter()
                                    .filter_map(|block| {
                                        block.get("text").and_then(|t| t.as_str()).map(|s| s.to_string())
                                    })
                                    .collect();
                                if texts.is_empty() { None } else { Some(texts.join("\n")) }
                            } else {
                                None
                            }
                        })
                        .or_else(|| {
                            // Fallback to .summary for summary entries
                            json.get("summary").and_then(|v| v.as_str()).map(|s| s.to_string())
                        })
                        .unwrap_or_default();

                    // Skip empty content
                    if content.trim().is_empty() {
                        continue;
                    }

                    let role = json.get("type").and_then(|v| v.as_str());

                    let timestamp = json
                        .get("timestamp")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);

                    index.index_document(
                        writer,
                        doc_id,
                        DocType::Conversation,
                        &content,
                        None, // title
                        Some(&source),
                        timestamp,
                        role,
                        project.as_deref(),
                        Some(&line), // Store full JSON as metadata
                        // Schema Optimization v0.3: 新增参数 (JSONL 无这些字段)
                        None, // artifact_id
                        None, // content_path
                        None, // score
                        None, // kind
                        None, // tags
                        None, // task_id
                        None, // citation_key
                    )?;

                    count += 1;
                }
            }
            Err(e) => {
                debug!("Skipping invalid JSON at line {}: {}", line_num + 1, e);
            }
        }
    }

    info!("Indexed {} documents from {:?}", count, path);
    Ok(count)
}

/// Extract project name from file path
fn extract_project_from_path(path: &Path) -> Option<String> {
    // Path pattern: ~/.claude/projects/{project-hash}/*.jsonl
    let path_str = path.to_string_lossy();
    if path_str.contains(".claude/projects/") {
        path.parent()
            .and_then(|p| p.file_name())
            .map(|n| n.to_string_lossy().to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_create_index() {
        let dir = tempdir().unwrap();
        let index = SolarIndex::open_or_create(dir.path()).unwrap();
        let stats = index.stats().unwrap();
        assert_eq!(stats.total_docs, 0);
    }
}
