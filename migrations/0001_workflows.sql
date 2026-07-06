-- Workflow index table: one row per agent workflow. Full step-by-step state
-- lives in LangGraph's checkpoint tables; this table is the queryable index
-- (status dashboard, dedupe, metrics).
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id    TEXT PRIMARY KEY,
    issue          JSONB NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    classification TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows (status);
