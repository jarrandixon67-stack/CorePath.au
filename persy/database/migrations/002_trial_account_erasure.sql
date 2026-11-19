-- Keep ordinary runtime access to audit and nonce rows append-only.
BEGIN;
CREATE FUNCTION persy_erase_account(target_owner CHAR(64))
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM persy_operations WHERE owner_key = target_owner;
    DELETE FROM persy_conversations WHERE owner_key = target_owner;
    DELETE FROM persy_nonces WHERE owner_key = target_owner;
    DELETE FROM persy_audit WHERE owner_key = target_owner;
    DELETE FROM persy_members WHERE owner_key = target_owner;
    -- A pseudonymous revocation marker prevents a deleted invitation being reused.
    INSERT INTO persy_members (owner_key, is_active) VALUES (target_owner, false);
END;
$$;
DO $$
BEGIN
    EXECUTE format(
        'ALTER FUNCTION %I.persy_erase_account(character) SET search_path TO pg_catalog, %I, pg_temp',
        current_schema(), current_schema()
    );
END;
$$;
REVOKE ALL ON FUNCTION persy_erase_account(character) FROM PUBLIC;
COMMIT;
