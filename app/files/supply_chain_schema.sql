-- =============================================
-- DerivInsight Supply Chain Digital Twin Schema
-- Phase 3 of AGENTS.md roadmap
-- =============================================

-- Warehouses: physical locations holding stock
CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id   VARCHAR(36)  PRIMARY KEY,
    name           TEXT         NOT NULL,
    city           TEXT         NOT NULL,
    country        TEXT         NOT NULL DEFAULT 'IN',
    latitude       REAL,
    longitude      REAL,
    capacity_units INTEGER      NOT NULL DEFAULT 10000,
    is_active      INTEGER      NOT NULL DEFAULT 1,
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- Inventory items: SKU stock levels per warehouse
CREATE TABLE IF NOT EXISTS inventory_items (
    item_id         INTEGER     PRIMARY KEY AUTOINCREMENT,
    sku             TEXT        NOT NULL,
    warehouse_id    VARCHAR(36) NOT NULL,
    quantity_on_hand INTEGER    NOT NULL DEFAULT 0,
    quantity_reserved INTEGER   NOT NULL DEFAULT 0,  -- allocated to pending orders
    quantity_in_transit INTEGER NOT NULL DEFAULT 0,  -- in-bound shipments
    reorder_point   INTEGER     NOT NULL DEFAULT 10, -- trigger restock below this
    unit_cost_usd   REAL        NOT NULL DEFAULT 0.0,
    last_restocked_at TIMESTAMP,
    updated_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_sku ON inventory_items(sku);
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse ON inventory_items(warehouse_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_sku_warehouse ON inventory_items(sku, warehouse_id);

-- Fulfillment orders: web order routing decisions
CREATE TABLE IF NOT EXISTS fulfillment_orders (
    order_id        VARCHAR(36)  PRIMARY KEY,
    sku             TEXT         NOT NULL,
    quantity        INTEGER      NOT NULL DEFAULT 1,
    customer_city   TEXT,
    customer_country TEXT        NOT NULL DEFAULT 'IN',
    source_warehouse VARCHAR(36),        -- assigned fulfillment warehouse
    fulfillment_type TEXT        NOT NULL DEFAULT 'standard',  -- standard | click_collect | express
    status          TEXT        NOT NULL DEFAULT 'pending',    -- pending | picked | shipped | delivered | cancelled
    carbon_kg       REAL,               -- estimated CO2 for this shipment
    created_at      TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    shipped_at      TIMESTAMP,
    delivered_at    TIMESTAMP,
    FOREIGN KEY (source_warehouse) REFERENCES warehouses(warehouse_id)
);

CREATE INDEX IF NOT EXISTS idx_fulfillment_sku ON fulfillment_orders(sku);
CREATE INDEX IF NOT EXISTS idx_fulfillment_status ON fulfillment_orders(status);

-- =============================================
-- Seed: default warehouses
-- =============================================

INSERT OR IGNORE INTO warehouses (warehouse_id, name, city, country, latitude, longitude, capacity_units)
VALUES
  ('WH-MUM-01', 'Mumbai Central FC',    'Mumbai',    'IN',  19.0760,  72.8777, 50000),
  ('WH-DEL-01', 'Delhi North FC',       'Delhi',     'IN',  28.7041,  77.1025, 45000),
  ('WH-BLR-01', 'Bengaluru Tech Park',  'Bengaluru', 'IN',  12.9716,  77.5946, 30000),
  ('WH-HYD-01', 'Hyderabad Logistics',  'Hyderabad', 'IN',  17.3850,  78.4867, 20000),
  ('WH-CHE-01', 'Chennai South Hub',    'Chennai',   'IN',  13.0827,  80.2707, 25000);
