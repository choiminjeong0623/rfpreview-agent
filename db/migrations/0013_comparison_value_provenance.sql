ALTER TABLE product_master ADD COLUMN IF NOT EXISTS comparison_values_assumed CHAR(1) NOT NULL DEFAULT 'Y' CHECK (comparison_values_assumed IN ('Y','N'));
ALTER TABLE product_master ADD COLUMN IF NOT EXISTS comparison_values_source VARCHAR(400);
