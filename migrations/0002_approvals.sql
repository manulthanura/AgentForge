-- Approval requests: one pending human decision per workflow (Phase 3).
CREATE TABLE IF NOT EXISTS approvals (
    workflow_id  TEXT PRIMARY KEY,
    action       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    feedback     TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at   TIMESTAMPTZ,
    reminded_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals (status);
