-- migrate_vendor_portal.sql
-- Adds vendor portal token columns to rfq_vendors table
-- Run once against your s2p_matrix MySQL database
-- Usage: mysql -u root -p s2p_matrix < scripts/migrate_vendor_portal.sql

USE s2p_matrix;

-- Add invite_token (unique per vendor-RFQ pair, used as URL token)
ALTER TABLE rfq_vendors
  ADD COLUMN IF NOT EXISTS invite_token  VARCHAR(100)  NULL UNIQUE,
  ADD COLUMN IF NOT EXISTS token_expires DATETIME      NULL,
  ADD COLUMN IF NOT EXISTS token_used    TINYINT(1)    NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS email_status  ENUM('Not Sent','Simulated','Sent','Failed')
                                         NOT NULL DEFAULT 'Not Sent';

-- Index for fast token lookups (portal page queries by token)
ALTER TABLE rfq_vendors
  ADD INDEX IF NOT EXISTS idx_rfq_vendors_token (invite_token);

-- Verify
SELECT 'Migration complete ✅' AS status;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 's2p_matrix'
  AND TABLE_NAME   = 'rfq_vendors'
ORDER BY ORDINAL_POSITION;
