-- SynthUX schema v1 — PostgreSQL 15+ with pgvector.
-- Embeddings are Qwen3-Embedding-0.6B outputs (1024 dimensions).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------- studies

CREATE TABLE studies (
    study_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    mode            text NOT NULL DEFAULT 'TASK_TEST',
        -- TASK_TEST | DISCOVERABILITY | COMPREHENSION | COMPARATIVE | ...
    product_context text,
    audience_spec   jsonb NOT NULL,          -- researcher's audience definition
    input_kind      text NOT NULL,           -- url | figma | screenshots
    input_ref       text,                    -- URL / file key / Figma file id
    panel_frozen    boolean NOT NULL DEFAULT false,
        -- frozen panels replay identical participants for regression mode
    parent_study_id uuid REFERENCES studies(study_id),
        -- regression runs / design-B arms point at their baseline study
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    task_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id          uuid NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
    researcher_prompt text NOT NULL,
    spec              jsonb NOT NULL,        -- models.TaskSpec (goal variants,
                                             -- predicate, optimal path, caps)
    optimal_actions   int NOT NULL
);

-- ----------------------------------------------------------- participants

CREATE TABLE participants (
    participant_id  text PRIMARY KEY,        -- e.g. IND_04381 (stable across
                                             -- regression re-runs of a panel)
    study_id        uuid NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
    source_dataset  text NOT NULL,
    source_license  text,
    persona         jsonb NOT NULL,          -- full persona.schema.json document
    cohorts         text[] NOT NULL DEFAULT '{}',
    seed            bigint NOT NULL,         -- frozen sampling for replayability
    temperature     real NOT NULL
);

CREATE INDEX participants_study_idx  ON participants (study_id);
CREATE INDEX participants_cohort_idx ON participants USING gin (cohorts);

-- ------------------------------------------------------------ world model

CREATE TABLE screens (
    screen_id   text NOT NULL,
    study_id    uuid NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
    summary     text,
    perception  jsonb NOT NULL,              -- models.ScreenPerception
    screenshot  text,                        -- object-store key
    PRIMARY KEY (study_id, screen_id)
);

-- --------------------------------------------------------------- sessions

CREATE TABLE sessions (
    session_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        uuid NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
    task_id         uuid NOT NULL REFERENCES tasks(task_id),
    participant_id  text NOT NULL REFERENCES participants(participant_id),
    outcome         text,                    -- SUCCESS | PARTIAL | FAILURE | ABANDONED
    end_screen_id   text,
    claimed_done    boolean NOT NULL DEFAULT false,
    plausible       boolean NOT NULL DEFAULT true,  -- judge veto: down-weighted
    metrics         jsonb,                   -- models.SessionMetrics
    started_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sessions_study_idx ON sessions (study_id);

-- One row per participant step: the interaction telemetry.
CREATE TABLE steps (
    session_id      uuid NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    step_index      int  NOT NULL,
    screen_id       text NOT NULL,
    action_type     text NOT NULL,           -- click|scroll|type|back|open_help|give_up|declare_done
    target_label    text,
    typed_value     text,
    thinking_aloud  text,                    -- withheld from judge pass 1
    confidence      real,
    feeling         text,
    dwell_seconds   real,
    memory_snapshot jsonb,                   -- working-memory contents this step
    attention_map   jsonb,                   -- Predicted Attention (model output,
                                             -- never presented as eye tracking)
    PRIMARY KEY (session_id, step_index)
);

-- ------------------------------------------------------------- evaluation

CREATE TABLE observations (
    observation_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    study_id        uuid NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
    screen_id       text NOT NULL,
    element_label   text,
    category        text NOT NULL,           -- models.FailureCategory
    statement       text NOT NULL,           -- specific, testable claim
    evidence        text NOT NULL,           -- telemetry citation
    quote           text,                    -- verbatim think-aloud
    source          text NOT NULL DEFAULT 'evaluator',  -- evaluator | judge
    judge_attribution text,                  -- interface | persona_limit | mixed
    embedding       vector(1024)             -- Qwen3-Embedding-0.6B
);

CREATE INDEX observations_study_idx ON observations (study_id);
-- HNSW cosine index for clustering / nearest-neighbour dedup.
CREATE INDEX observations_embedding_idx
    ON observations USING hnsw (embedding vector_cosine_ops);

CREATE TABLE issues (
    issue_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    study_id        uuid NOT NULL REFERENCES studies(study_id) ON DELETE CASCADE,
    title           text NOT NULL,
    category        text NOT NULL,
    severity        text NOT NULL,           -- LOW | MEDIUM | HIGH | CRITICAL
    severity_score  real NOT NULL,
    affected_participants int NOT NULL,
    cohort_shares   jsonb NOT NULL DEFAULT '{}',
    statement       text NOT NULL,
    recommendation  text NOT NULL,
    calibrated      boolean NOT NULL DEFAULT false,
    centroid        vector(1024)
);

CREATE TABLE issue_evidence (
    issue_id        uuid NOT NULL REFERENCES issues(issue_id) ON DELETE CASCADE,
    observation_id  uuid NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    PRIMARY KEY (issue_id, observation_id)
);

-- -------------------------------------------------------------- reporting

CREATE TABLE study_reports (
    study_id    uuid PRIMARY KEY REFERENCES studies(study_id) ON DELETE CASCADE,
    report      jsonb NOT NULL,              -- models.StudyReport
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ calibration

-- Correction factors learned from paired synthetic + human studies:
--   factor = human_observed(metric) / synthetic_predicted(metric)
CREATE TABLE calibration_factors (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cohort          text NOT NULL,           -- '*' = all cohorts
    metric          text NOT NULL,           -- e.g. success_rate, abandon_rate
    domain          text NOT NULL DEFAULT '*',
    factor          real NOT NULL,
    n_paired_studies int NOT NULL,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cohort, metric, domain)
);
