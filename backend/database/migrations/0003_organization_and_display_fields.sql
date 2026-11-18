-- Organization, location and human-readable employee fields (Track A, 2026-11-18).
-- Taken from the database branch's design (48b2a1a): the rules only need ids, but a manager
-- reviewing an exception needs to see who and where. Display data only: no rule, validator or
-- authorization decision may read these columns.

CREATE TABLE organizations (
    org_id     text PRIMARY KEY CHECK (org_id <> ''),
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE locations (
    location_id text PRIMARY KEY CHECK (location_id <> ''),
    org_id      text REFERENCES organizations ON DELETE RESTRICT,
    name        text NOT NULL,
    city        text,
    country     text,
    -- The employee's own timezone stays authoritative for work dates; this one is for display
    -- and for seeding new employees at a site.
    timezone    text
);

-- employees.location_id already holds these ids. No foreign key yet: existing rows were created
-- before this table, and locations is optional reference data. Add the key in a later migration
-- once every deployment has backfilled its sites.
ALTER TABLE employees
    ADD COLUMN full_name text,
    ADD COLUMN job_title text,
    ADD COLUMN pay_type  text CHECK (pay_type IN ('hourly', 'salary'));
