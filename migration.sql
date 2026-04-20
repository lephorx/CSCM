-- Migration: extend servers table + add playit_tunnels and dns_records tables
-- Run once against your Neon database.

-- 1. Add craftyId column to existing servers table (if not already present)
ALTER TABLE servers
  ADD COLUMN IF NOT EXISTS "craftyId" TEXT;

-- 2. PlayIT tunnels — one row per tunnel created for a server
CREATE TABLE IF NOT EXISTS playit_tunnels (
    id             SERIAL PRIMARY KEY,
    server_id      INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    tunnel_name    VARCHAR(255) NOT NULL,
    tunnel_address VARCHAR(255) NOT NULL,   -- e.g. abc.deu.mcjoin.link
    local_port     INTEGER NOT NULL,
    external_port  INTEGER,                 -- discovered via SRV lookup
    created_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 3. DNS records — one row per Cloudflare record (CNAME + SRV) per server
CREATE TABLE IF NOT EXISTS dns_records (
    id                  SERIAL PRIMARY KEY,
    server_id           INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    record_type         VARCHAR(10) NOT NULL,  -- 'CNAME' or 'SRV'
    name                VARCHAR(255) NOT NULL,  -- full DNS name
    target              VARCHAR(255) NOT NULL,  -- content / target
    port                INTEGER,               -- only for SRV
    cloudflare_record_id VARCHAR(255) NOT NULL, -- CF record ID for direct deletion
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
