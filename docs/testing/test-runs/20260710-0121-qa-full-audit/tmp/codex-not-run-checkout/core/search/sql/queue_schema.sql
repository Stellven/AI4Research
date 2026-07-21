-- Tantivy Index Queue Schema
-- Persistent queue for async document indexing

CREATE TABLE IF NOT EXISTS tantivy_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Document identification
    doc_type TEXT NOT NULL,           -- conversation, memory, code, document, registry, stats
    source_id TEXT NOT NULL,          -- Unique ID from source system

    -- Content
    content TEXT NOT NULL,            -- Main text to index (snippet for artifacts)
    title TEXT,                       -- Optional title
    source_path TEXT,                 -- Source file path

    -- Metadata
    timestamp INTEGER DEFAULT 0,      -- Unix timestamp
    role TEXT,                        -- user, assistant, system (for conversations)
    project TEXT,                     -- Project identifier
    metadata TEXT,                    -- JSON metadata

    -- Queue management
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, indexed, failed
    retry_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    indexed_at DATETIME,

    -- Schema Optimization v0.3 新增字段
    artifact_id INTEGER,              -- Numeric artifact ID for efficient joins
    content_path TEXT,                -- FS path to full content
    score REAL,                       -- Credibility score (0.0 - 1.0)
    kind TEXT,                        -- Artifact kind: outline, draft, review, final
    tags TEXT,                        -- Comma-separated tags
    task_id TEXT,                     -- Explicit task_id for Cortex artifacts
    citation_key TEXT,                -- Citation key for references

    -- Unique constraint to prevent duplicates
    UNIQUE(doc_type, source_id)
);

-- Indexes for efficient queue operations
CREATE INDEX IF NOT EXISTS idx_tantivy_queue_status ON tantivy_queue(status);
CREATE INDEX IF NOT EXISTS idx_tantivy_queue_created ON tantivy_queue(created_at);
CREATE INDEX IF NOT EXISTS idx_tantivy_queue_doc_type ON tantivy_queue(doc_type);

-- View for pending items count
CREATE VIEW IF NOT EXISTS v_tantivy_queue_stats AS
SELECT
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest,
    MAX(created_at) as newest
FROM tantivy_queue
GROUP BY status;

-- Trigger to prevent reprocessing already indexed items
CREATE TRIGGER IF NOT EXISTS tr_tantivy_queue_no_reprocess
BEFORE INSERT ON tantivy_queue
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM tantivy_queue
    WHERE doc_type = NEW.doc_type AND source_id = NEW.source_id
    AND status = 'indexed'
)
BEGIN
    SELECT RAISE(IGNORE);
END;
