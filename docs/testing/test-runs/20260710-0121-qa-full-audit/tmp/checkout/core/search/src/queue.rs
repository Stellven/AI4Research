//! Index queue for async document indexing
//!
//! Provides a persistent queue in SQLite for reliable async indexing.

use anyhow::{Context, Result};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::path::Path;
use tracing::{debug, info, warn};

use crate::schema::DocType;

/// Queue item status
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QueueStatus {
    Pending,
    Processing,
    Indexed,
    Failed,
}

impl QueueStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            QueueStatus::Pending => "pending",
            QueueStatus::Processing => "processing",
            QueueStatus::Indexed => "indexed",
            QueueStatus::Failed => "failed",
        }
    }
}

/// Queue item representing a document to be indexed
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueueItem {
    pub id: i64,
    pub doc_type: String,
    pub source_id: String,
    pub content: String,
    pub title: Option<String>,
    pub source_path: Option<String>,
    pub timestamp: u64,
    pub role: Option<String>,
    pub project: Option<String>,
    pub metadata: Option<String>,
    pub status: String,
    pub retry_count: i32,
    pub created_at: String,
    // Schema Optimization v0.3 新增字段
    pub artifact_id: Option<i64>,
    pub content_path: Option<String>,
    pub score: Option<f64>,
    pub kind: Option<String>,
    pub tags: Option<String>,
    pub task_id: Option<String>,
    pub citation_key: Option<String>,
}

/// Index queue manager
pub struct IndexQueue {
    conn: Connection,
}

impl IndexQueue {
    /// Open or create the queue database
    pub fn open(db_path: impl AsRef<Path>) -> Result<Self> {
        let conn = Connection::open(db_path.as_ref())
            .with_context(|| format!("Failed to open queue DB: {:?}", db_path.as_ref()))?;

        // Create schema
        conn.execute_batch(include_str!("../sql/queue_schema.sql"))
            .context("Failed to create queue schema")?;

        Ok(Self { conn })
    }

    /// Open using the default Solar database
    pub fn open_default() -> Result<Self> {
        let db_path = dirs::home_dir()
            .map(|h| h.join(".solar").join("solar.db"))
            .unwrap_or_else(|| std::path::PathBuf::from("/tmp/solar.db"));

        Self::open(&db_path)
    }

    /// Add an item to the queue
    pub fn enqueue(
        &self,
        doc_type: DocType,
        source_id: &str,
        content: &str,
        title: Option<&str>,
        source_path: Option<&str>,
        timestamp: u64,
        role: Option<&str>,
        project: Option<&str>,
        metadata: Option<&str>,
    ) -> Result<i64> {
        self.conn.execute(
            "INSERT INTO tantivy_queue (
                doc_type, source_id, content, title, source_path,
                timestamp, role, project, metadata, status
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, 'pending')",
            params![
                doc_type.as_str(),
                source_id,
                content,
                title,
                source_path,
                timestamp as i64,
                role,
                project,
                metadata,
            ],
        )?;

        let id = self.conn.last_insert_rowid();
        debug!("Enqueued item: id={}, source_id={}", id, source_id);

        Ok(id)
    }

    /// Get pending items for processing
    pub fn get_pending(&self, limit: usize) -> Result<Vec<QueueItem>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, doc_type, source_id, content, title, source_path,
                    timestamp, role, project, metadata, status, retry_count, created_at,
                    artifact_id, content_path, score, kind, tags, task_id, citation_key
             FROM tantivy_queue
             WHERE status = 'pending'
             ORDER BY created_at ASC
             LIMIT ?1",
        )?;

        let items = stmt
            .query_map([limit], |row| {
                Ok(QueueItem {
                    id: row.get(0)?,
                    doc_type: row.get(1)?,
                    source_id: row.get(2)?,
                    content: row.get(3)?,
                    title: row.get(4)?,
                    source_path: row.get(5)?,
                    timestamp: row.get::<_, i64>(6)? as u64,
                    role: row.get(7)?,
                    project: row.get(8)?,
                    metadata: row.get(9)?,
                    status: row.get(10)?,
                    retry_count: row.get(11)?,
                    created_at: row.get(12)?,
                    // Schema Optimization v0.3 新增字段
                    artifact_id: row.get(13)?,
                    content_path: row.get(14)?,
                    score: row.get(15)?,
                    kind: row.get(16)?,
                    tags: row.get(17)?,
                    task_id: row.get(18)?,
                    citation_key: row.get(19)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;

        Ok(items)
    }

    /// Mark items as processing
    pub fn mark_processing(&self, ids: &[i64]) -> Result<()> {
        if ids.is_empty() {
            return Ok(());
        }

        let placeholders: Vec<String> = ids.iter().map(|_| "?".to_string()).collect();
        let sql = format!(
            "UPDATE tantivy_queue SET status = 'processing' WHERE id IN ({})",
            placeholders.join(",")
        );

        let mut stmt = self.conn.prepare(&sql)?;
        let params: Vec<&dyn rusqlite::ToSql> = ids.iter().map(|id| id as &dyn rusqlite::ToSql).collect();
        stmt.execute(params.as_slice())?;

        Ok(())
    }

    /// Mark items as indexed
    pub fn mark_indexed(&self, ids: &[i64]) -> Result<()> {
        if ids.is_empty() {
            return Ok(());
        }

        let placeholders: Vec<String> = ids.iter().map(|_| "?".to_string()).collect();
        let sql = format!(
            "UPDATE tantivy_queue SET status = 'indexed', indexed_at = CURRENT_TIMESTAMP WHERE id IN ({})",
            placeholders.join(",")
        );

        let mut stmt = self.conn.prepare(&sql)?;
        let params: Vec<&dyn rusqlite::ToSql> = ids.iter().map(|id| id as &dyn rusqlite::ToSql).collect();
        stmt.execute(params.as_slice())?;

        info!("Marked {} items as indexed", ids.len());

        Ok(())
    }

    /// Mark items as failed
    pub fn mark_failed(&self, ids: &[i64]) -> Result<()> {
        if ids.is_empty() {
            return Ok(());
        }

        let placeholders: Vec<String> = ids.iter().map(|_| "?".to_string()).collect();
        let sql = format!(
            "UPDATE tantivy_queue SET status = 'failed', retry_count = retry_count + 1 WHERE id IN ({})",
            placeholders.join(",")
        );

        let mut stmt = self.conn.prepare(&sql)?;
        let params: Vec<&dyn rusqlite::ToSql> = ids.iter().map(|id| id as &dyn rusqlite::ToSql).collect();
        stmt.execute(params.as_slice())?;

        warn!("Marked {} items as failed", ids.len());

        Ok(())
    }

    /// Retry failed items (reset to pending)
    pub fn retry_failed(&self, max_retries: i32) -> Result<usize> {
        let count = self.conn.execute(
            "UPDATE tantivy_queue SET status = 'pending'
             WHERE status = 'failed' AND retry_count < ?1",
            [max_retries],
        )?;

        if count > 0 {
            info!("Reset {} failed items for retry", count);
        }

        Ok(count)
    }

    /// Clean up indexed items older than specified days
    pub fn cleanup(&self, days: i32) -> Result<usize> {
        let count = self.conn.execute(
            "DELETE FROM tantivy_queue
             WHERE status = 'indexed'
             AND created_at < datetime('now', ?1)",
            [format!("-{} days", days)],
        )?;

        if count > 0 {
            info!("Cleaned up {} old indexed items", count);
        }

        Ok(count)
    }

    /// Get queue statistics
    pub fn stats(&self) -> Result<QueueStats> {
        let mut stmt = self.conn.prepare(
            "SELECT status, COUNT(*) FROM tantivy_queue GROUP BY status",
        )?;

        let mut stats = QueueStats::default();

        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })?;

        for row in rows {
            let (status, count) = row?;
            match status.as_str() {
                "pending" => stats.pending = count as usize,
                "processing" => stats.processing = count as usize,
                "indexed" => stats.indexed = count as usize,
                "failed" => stats.failed = count as usize,
                _ => {}
            }
        }

        Ok(stats)
    }
}

#[derive(Debug, Default, Serialize)]
pub struct QueueStats {
    pub pending: usize,
    pub processing: usize,
    pub indexed: usize,
    pub failed: usize,
}

impl QueueStats {
    pub fn total(&self) -> usize {
        self.pending + self.processing + self.indexed + self.failed
    }
}
