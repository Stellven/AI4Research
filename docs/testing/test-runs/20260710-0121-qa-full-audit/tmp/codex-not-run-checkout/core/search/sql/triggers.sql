-- Solar Search SQLite Triggers
-- Automatically queue new records for indexing

-- =============================================
-- Memory Tables Triggers (evo_memory_* tables)
-- =============================================

-- Semantic Memory
CREATE TRIGGER IF NOT EXISTS tr_index_semantic_memory
AFTER INSERT ON evo_memory_semantic
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'memory',
        'evo_memory_semantic:' || NEW.memory_id,
        NEW.key || ': ' || COALESCE(json_extract(NEW.value, '$'), CAST(NEW.value AS TEXT)),
        NEW.namespace || '/' || NEW.key,
        'evo_memory_semantic',
        strftime('%s', NEW.created_at),
        NULL,
        CASE WHEN NEW.namespace LIKE 'project/%' THEN SUBSTR(NEW.namespace, 9) ELSE NULL END,
        json_object('namespace', NEW.namespace, 'confidence', NEW.confidence, 'source_type', NEW.source_type),
        'pending'
    );
END;

-- Episodic Memory
CREATE TRIGGER IF NOT EXISTS tr_index_episodic_memory
AFTER INSERT ON evo_memory_episodic
WHEN NEW.event_summary IS NOT NULL
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'memory',
        'evo_memory_episodic:' || NEW.memory_id,
        NEW.event_summary || COALESCE(' ' || json_extract(NEW.event_details, '$.description'), ''),
        NEW.event_type,
        'evo_memory_episodic',
        strftime('%s', NEW.occurred_at),
        NULL,
        CASE WHEN NEW.namespace LIKE 'project/%' THEN SUBSTR(NEW.namespace, 9) ELSE NULL END,
        json_object('event_type', NEW.event_type, 'importance', NEW.importance, 'outcome', NEW.outcome),
        'pending'
    );
END;

-- Procedural Memory
CREATE TRIGGER IF NOT EXISTS tr_index_procedural_memory
AFTER INSERT ON evo_memory_procedural
WHEN NEW.description IS NOT NULL
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'memory',
        'evo_memory_procedural:' || NEW.memory_id,
        NEW.procedure_name || ': ' || COALESCE(NEW.description, '') || ' ' || COALESCE(json_extract(NEW.trigger_keywords, '$'), ''),
        NEW.procedure_name,
        'evo_memory_procedural',
        strftime('%s', NEW.created_at),
        NULL,
        CASE WHEN NEW.namespace LIKE 'project/%' THEN SUBSTR(NEW.namespace, 9) ELSE NULL END,
        json_object(
            'procedure_type', NEW.procedure_type,
            'success_rate', CASE WHEN NEW.execution_count > 0 THEN CAST(NEW.success_count AS REAL) / NEW.execution_count ELSE 0 END
        ),
        'pending'
    );
END;

-- =============================================
-- Registry Tables Triggers
-- =============================================

-- Skills Registry (joins with sys_resources for description)
CREATE TRIGGER IF NOT EXISTS tr_index_skill
AFTER INSERT ON sys_skills
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'registry',
        'sys_skills:' || NEW.skill_id,
        COALESCE(
            (SELECT description FROM sys_resources WHERE resource_id = NEW.skill_id),
            NEW.command || ' skill'
        ) || ' ' || COALESCE(NEW.command, ''),
        COALESCE(
            (SELECT name FROM sys_resources WHERE resource_id = NEW.skill_id),
            NEW.command
        ),
        COALESCE(NEW.path, 'sys_skills'),
        strftime('%s', 'now'),
        'skill',
        NULL,
        json_object('command', NEW.command, 'category', NEW.category, 'user_invocable', NEW.user_invocable),
        'pending'
    );
END;

-- Scripts Registry
CREATE TRIGGER IF NOT EXISTS tr_index_script
AFTER INSERT ON sys_scripts
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'registry',
        'sys_scripts:' || NEW.script_id,
        COALESCE(NEW.description, '') || ' ' || COALESCE(NEW.intent_keywords, ''),
        NEW.name,
        COALESCE(NEW.file_path, 'sys_scripts'),
        strftime('%s', NEW.created_at),
        'script',
        NULL,
        json_object('runtime', NEW.runtime, 'status', NEW.status, 'source', NEW.source),
        'pending'
    );
END;

-- Agents Registry (joins with sys_resources for description)
CREATE TRIGGER IF NOT EXISTS tr_index_agent
AFTER INSERT ON sys_agents
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'registry',
        'sys_agents:' || NEW.agent_id,
        COALESCE(
            (SELECT description FROM sys_resources WHERE resource_id = NEW.agent_id),
            ''
        ) || ' ' || COALESCE(NEW.role, '') || ' ' || COALESCE(NEW.tools, ''),
        COALESCE(
            (SELECT name FROM sys_resources WHERE resource_id = NEW.agent_id),
            NEW.agent_id
        ),
        'sys_agents',
        strftime('%s', 'now'),
        'agent',
        NULL,
        json_object('emoji', NEW.emoji, 'phases', NEW.phases, 'default_model', NEW.default_model),
        'pending'
    );
END;

-- Resources Registry (generic)
CREATE TRIGGER IF NOT EXISTS tr_index_resource
AFTER INSERT ON sys_resources
WHEN NEW.resource_type NOT IN ('agent', 'skill')  -- agents and skills have their own triggers
BEGIN
    INSERT OR IGNORE INTO tantivy_queue (
        doc_type, source_id, content, title, source_path, timestamp, role, project, metadata, status
    ) VALUES (
        'registry',
        'sys_resources:' || NEW.resource_id,
        COALESCE(NEW.description, '') || ' ' || COALESCE(NEW.keywords, ''),
        NEW.name,
        'sys_resources',
        strftime('%s', NEW.created_at),
        NEW.resource_type,
        NULL,
        json_object('type', NEW.resource_type, 'status', NEW.status, 'layer', NEW.layer),
        'pending'
    );
END;

-- =============================================
-- Update Triggers (re-index on update)
-- =============================================

CREATE TRIGGER IF NOT EXISTS tr_reindex_semantic_memory
AFTER UPDATE ON evo_memory_semantic
WHEN NEW.value != OLD.value OR NEW.key != OLD.key
BEGIN
    UPDATE tantivy_queue
    SET content = NEW.key || ': ' || COALESCE(json_extract(NEW.value, '$'), CAST(NEW.value AS TEXT)),
        title = NEW.namespace || '/' || NEW.key,
        status = 'pending',
        indexed_at = NULL
    WHERE source_id = 'evo_memory_semantic:' || NEW.memory_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_reindex_episodic_memory
AFTER UPDATE ON evo_memory_episodic
WHEN NEW.event_summary != OLD.event_summary
BEGIN
    UPDATE tantivy_queue
    SET content = NEW.event_summary || COALESCE(' ' || json_extract(NEW.event_details, '$.description'), ''),
        status = 'pending',
        indexed_at = NULL
    WHERE source_id = 'evo_memory_episodic:' || NEW.memory_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_reindex_script
AFTER UPDATE ON sys_scripts
WHEN NEW.description != OLD.description OR NEW.name != OLD.name
BEGIN
    UPDATE tantivy_queue
    SET content = COALESCE(NEW.description, '') || ' ' || COALESCE(NEW.intent_keywords, ''),
        title = NEW.name,
        status = 'pending',
        indexed_at = NULL
    WHERE source_id = 'sys_scripts:' || NEW.script_id;
END;

-- =============================================
-- Delete Triggers (remove from queue)
-- =============================================

CREATE TRIGGER IF NOT EXISTS tr_delete_semantic_memory
AFTER DELETE ON evo_memory_semantic
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'evo_memory_semantic:' || OLD.memory_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_delete_episodic_memory
AFTER DELETE ON evo_memory_episodic
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'evo_memory_episodic:' || OLD.memory_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_delete_procedural_memory
AFTER DELETE ON evo_memory_procedural
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'evo_memory_procedural:' || OLD.memory_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_delete_skill
AFTER DELETE ON sys_skills
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'sys_skills:' || OLD.skill_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_delete_script
AFTER DELETE ON sys_scripts
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'sys_scripts:' || OLD.script_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_delete_agent
AFTER DELETE ON sys_agents
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'sys_agents:' || OLD.agent_id;
END;

CREATE TRIGGER IF NOT EXISTS tr_delete_resource
AFTER DELETE ON sys_resources
BEGIN
    DELETE FROM tantivy_queue WHERE source_id = 'sys_resources:' || OLD.resource_id;
END;

-- =============================================
-- Utility Views
-- =============================================

-- View for queue monitoring
CREATE VIEW IF NOT EXISTS v_tantivy_queue_monitor AS
SELECT
    doc_type,
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest_item,
    MAX(created_at) as newest_item,
    AVG(retry_count) as avg_retries
FROM tantivy_queue
GROUP BY doc_type, status
ORDER BY doc_type, status;

-- View for pending items with content preview
CREATE VIEW IF NOT EXISTS v_tantivy_pending AS
SELECT
    id,
    doc_type,
    source_id,
    SUBSTR(content, 1, 100) || CASE WHEN LENGTH(content) > 100 THEN '...' ELSE '' END as content_preview,
    title,
    created_at,
    retry_count
FROM tantivy_queue
WHERE status = 'pending'
ORDER BY created_at ASC
LIMIT 100;
