-- Run only in the isolated feedback database with existing non-owner login roles.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"feedback_api_role", :"feedback_analysis_role";
GRANT SELECT ON feedback_actors,feedback_targets TO :"feedback_api_role", :"feedback_analysis_role";
GRANT UPDATE(last_checked_at) ON feedback_actors TO :"feedback_api_role", :"feedback_analysis_role";
GRANT SELECT,INSERT,UPDATE ON feedback_targets,feedback_preferences,feedback_prompts,feedback_records,feedback_themes TO :"feedback_api_role";
GRANT INSERT ON feedback_audit TO :"feedback_api_role", :"feedback_analysis_role";
GRANT USAGE ON SEQUENCE feedback_audit_id_seq TO :"feedback_api_role", :"feedback_analysis_role";
GRANT SELECT ON feedback_analysis_sources TO :"feedback_analysis_role";
GRANT INSERT(id,target,fingerprint,kind,severity,contributor_count,source_ids,payload) ON feedback_themes TO :"feedback_analysis_role";
GRANT SELECT(id,fingerprint) ON feedback_themes TO :"feedback_analysis_role";
-- The analysis role cannot read unconsented raw records, edit consent, resolve
-- concerns, change identities, change business ratings or access Life Profiles.
