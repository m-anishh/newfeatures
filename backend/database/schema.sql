-- ============================================================
-- VisionX - PostgreSQL schema (AWS RDS / any PostgreSQL 13+)
-- Idempotent: safe to run on every startup.
-- Single source of truth for the database schema.
-- ============================================================

-- ------------------------------------------------------------
-- Auth
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    last_sign_in_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));

CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email TEXT,
    full_name TEXT,
    username TEXT,
    avatar_url TEXT,
    bio TEXT,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Image analysis pipeline
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL,
    module_type VARCHAR(32) NOT NULL DEFAULT 'image',
    input_type VARCHAR(32),
    input_content TEXT,
    source_url VARCHAR(2048),
    title VARCHAR(255),
    status VARCHAR(32) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    current_agent VARCHAR(128),
    current_stage VARCHAR(64),
    estimated_duration INTEGER DEFAULT 120,
    overall_confidence DOUBLE PRECISION,
    overall_verdict VARCHAR(64),
    risk_level VARCHAR(32) DEFAULT 'medium',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    agent_results JSONB DEFAULT '{}',
    extra_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON analysis_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_module_type ON analysis_jobs(module_type);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON analysis_jobs(created_at);

CREATE TABLE IF NOT EXISTS agent_results (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    analysis_id VARCHAR(36) NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    agent_name VARCHAR(128) NOT NULL,
    agent_order INTEGER DEFAULT 0,
    agent_group INTEGER DEFAULT 1,
    handler VARCHAR(128),
    status VARCHAR(32) DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms DOUBLE PRECISION DEFAULT 0.0,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    reasoning TEXT,
    summary TEXT,
    raw_output JSONB DEFAULT '{}',
    evidence JSONB DEFAULT '{}',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    is_critical BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_result_analysis ON agent_results(analysis_id);

CREATE TABLE IF NOT EXISTS agent_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    analysis_id VARCHAR(36) NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    agent_name VARCHAR(128),
    level VARCHAR(16) DEFAULT 'info',
    message TEXT NOT NULL,
    correlation_id VARCHAR(36),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_log_analysis ON agent_logs(analysis_id);

CREATE TABLE IF NOT EXISTS evidence_items (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    analysis_id VARCHAR(36) NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    agent_name VARCHAR(128) NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,
    key VARCHAR(255) NOT NULL,
    value TEXT,
    reference_url VARCHAR(2048),
    confidence DOUBLE PRECISION DEFAULT 0.0,
    is_exculpatory BOOLEAN DEFAULT FALSE,
    is_inculpatory BOOLEAN DEFAULT FALSE,
    extra_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evidence_analysis ON evidence_items(analysis_id);

CREATE TABLE IF NOT EXISTS uploads (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(2048) NOT NULL,
    public_url VARCHAR(2048),
    mime_type VARCHAR(128),
    file_size BIGINT,
    sha256 VARCHAR(64),
    status VARCHAR(32) DEFAULT 'completed',
    extra_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);

CREATE TABLE IF NOT EXISTS analysis (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL,
    upload_id VARCHAR(36) REFERENCES uploads(id) ON DELETE SET NULL,
    trust_score DOUBLE PRECISION,
    authenticity_status VARCHAR(64) DEFAULT 'unknown',
    risk_level VARCHAR(32),
    summary TEXT,
    ai_model VARCHAR(128),
    reasoning JSONB DEFAULT '{}',
    evidence_summary JSONB DEFAULT '[]',
    recommendations JSONB DEFAULT '[]',
    agent_results JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analysis_user_id ON analysis(user_id);

CREATE TABLE IF NOT EXISTS reports (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    report_id VARCHAR(64),
    user_id VARCHAR(36) NOT NULL,
    analysis_id VARCHAR(36) NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    upload_id VARCHAR(36) REFERENCES uploads(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    trust_score INTEGER,
    authenticity_status VARCHAR(64) DEFAULT 'unknown',
    risk_level VARCHAR(32) DEFAULT 'medium',
    verdict VARCHAR(64),
    report_data JSONB DEFAULT '{}',
    pdf_url VARCHAR(2048),
    pdf_path VARCHAR(1024),
    download_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_analysis_id ON reports(analysis_id);
CREATE INDEX IF NOT EXISTS idx_reports_report_id ON reports(report_id);

CREATE TABLE IF NOT EXISTS incidents (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL,
    analysis_id VARCHAR(36),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    reason TEXT,
    severity VARCHAR(32) DEFAULT 'medium',
    risk_level VARCHAR(32),
    trust_score DOUBLE PRECISION,
    status VARCHAR(32) DEFAULT 'open',
    tags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_incidents_user_id ON incidents(user_id);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at);

-- ------------------------------------------------------------
-- News verification
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    input_type TEXT,
    input_content TEXT,
    source_url TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    current_agent TEXT,
    trust_score DOUBLE PRECISION DEFAULT 0,
    authenticity_score DOUBLE PRECISION DEFAULT 0,
    authenticity_level TEXT DEFAULT 'unknown',
    risk_level TEXT,
    verdict TEXT,
    confidence DOUBLE PRECISION,
    source_credibility DOUBLE PRECISION DEFAULT 0,
    bias_score DOUBLE PRECISION DEFAULT 0,
    claim_count INTEGER DEFAULT 0,
    evidence_count INTEGER DEFAULT 0,
    executive_summary TEXT,
    error_message TEXT,
    processing_time_ms BIGINT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_news_analyses_user_id ON news_analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_news_analyses_status ON news_analyses(status);
CREATE INDEX IF NOT EXISTS idx_news_analyses_created_at ON news_analyses(created_at DESC);

CREATE TABLE IF NOT EXISTS news_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES news_analyses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    report_data JSONB,
    report_json JSONB,
    report_type TEXT DEFAULT 'json',
    executive_summary TEXT,
    recommendations JSONB DEFAULT '[]',
    claims JSONB DEFAULT '[]',
    evidence JSONB DEFAULT '[]',
    sources JSONB DEFAULT '[]',
    bias_analysis JSONB DEFAULT '{}',
    context_analysis JSONB DEFAULT '{}',
    ai_explanation TEXT,
    confidence DOUBLE PRECISION,
    risk_level TEXT,
    verdict TEXT,
    processing_time_ms BIGINT DEFAULT 0,
    pdf_path TEXT,
    pdf_url TEXT,
    download_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_news_reports_analysis_id ON news_reports(analysis_id);
CREATE INDEX IF NOT EXISTS idx_news_reports_user_id ON news_reports(user_id);

CREATE TABLE IF NOT EXISTS news_agent_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES news_analyses(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    agent_order INTEGER,
    status TEXT,
    confidence DOUBLE PRECISION DEFAULT 0,
    findings JSONB DEFAULT '[]',
    evidence JSONB DEFAULT '[]',
    input JSONB,
    output JSONB,
    raw_output JSONB,
    processed_output JSONB DEFAULT '{}',
    error TEXT,
    error_message TEXT,
    processing_time_ms BIGINT DEFAULT 0,
    execution_time_ms DOUBLE PRECISION,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_news_agent_results_analysis_id ON news_agent_results(analysis_id);

CREATE TABLE IF NOT EXISTS news_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES news_analyses(id) ON DELETE CASCADE,
    agent_name TEXT,
    evidence_type TEXT DEFAULT 'text',
    type TEXT DEFAULT 'text',
    key TEXT,
    value TEXT,
    reference_url TEXT,
    confidence DOUBLE PRECISION,
    claim TEXT,
    source TEXT,
    url TEXT,
    excerpt TEXT,
    credibility DOUBLE PRECISION DEFAULT 0,
    supports_claim BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_news_evidence_analysis_id ON news_evidence(analysis_id);

-- ------------------------------------------------------------
-- Video analysis
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS video_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    input_type TEXT NOT NULL,
    input_content TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    trust_score NUMERIC,
    authenticity_score NUMERIC,
    authenticity_level TEXT,
    risk_level TEXT,
    verdict TEXT,
    confidence NUMERIC,
    metadata JSONB,
    executive_summary TEXT,
    error_message TEXT,
    processing_time_ms BIGINT,
    claim_count INTEGER,
    evidence_count INTEGER,
    frame_count INTEGER,
    audio_duration_seconds NUMERIC,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_analyses_user_id ON video_analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_video_analyses_status ON video_analyses(status);
CREATE INDEX IF NOT EXISTS idx_video_analyses_created_at ON video_analyses(created_at);

CREATE TABLE IF NOT EXISTS video_frames (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    timestamp_seconds NUMERIC NOT NULL,
    frame_path TEXT,
    thumbnail_path TEXT,
    scene_change BOOLEAN DEFAULT FALSE,
    motion_score NUMERIC,
    ocr_text TEXT,
    objects_detected JSONB,
    faces_detected JSONB,
    deepfake_score NUMERIC,
    manipulation_indicators JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_frames_analysis_id ON video_frames(analysis_id);

CREATE TABLE IF NOT EXISTS video_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    reference_url TEXT,
    confidence NUMERIC,
    claim TEXT,
    source TEXT,
    url TEXT,
    excerpt TEXT,
    credibility NUMERIC,
    supports_claim BOOLEAN DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_evidence_analysis_id ON video_evidence(analysis_id);

CREATE TABLE IF NOT EXISTS video_audio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    audio_path TEXT,
    transcript TEXT,
    language_detected TEXT,
    confidence NUMERIC,
    speaker_segments JSONB,
    silence_periods JSONB,
    audio_manipulation_indicators JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_audio_analysis_id ON video_audio(analysis_id);

CREATE TABLE IF NOT EXISTS video_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    report_data JSONB,
    report_type TEXT DEFAULT 'json',
    executive_summary TEXT,
    executive_summary_short TEXT,
    recommendations JSONB,
    claims JSONB,
    evidence JSONB,
    sources JSONB,
    frame_analysis JSONB,
    ocr_findings JSONB,
    audio_findings JSONB,
    deepfake_findings JSONB,
    bias_analysis JSONB,
    context_analysis JSONB,
    ai_explanation TEXT,
    processing_time_ms BIGINT,
    pdf_path TEXT,
    pdf_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_reports_analysis_id ON video_reports(analysis_id);
CREATE INDEX IF NOT EXISTS idx_video_reports_user_id ON video_reports(user_id);

CREATE TABLE IF NOT EXISTS video_agent_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES video_analyses(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    agent_order INTEGER,
    status TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms NUMERIC,
    confidence NUMERIC,
    reasoning TEXT,
    summary TEXT,
    raw_output JSONB,
    evidence JSONB,
    error_message TEXT,
    retry_count INTEGER,
    findings JSONB,
    processing_time_ms BIGINT,
    processed_output JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_video_agent_results_analysis_id ON video_agent_results(analysis_id);
