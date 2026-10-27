-- Multi-database provisioning for Metabase BI isolation
SELECT 'CREATE DATABASE metabase'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metabase')\gexec

-- The configured POSTGRES_USER creates and owns this database. No hard-coded role.
