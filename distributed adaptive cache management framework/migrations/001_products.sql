CREATE TABLE IF NOT EXISTS products (
 id BIGINT PRIMARY KEY CHECK (id > 0),
 name TEXT NOT NULL,
 payload TEXT NOT NULL DEFAULT '',
 version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO products(id,name,payload)
SELECT i, 'Product ' || i, repeat('x',1024) FROM generate_series(1,1000) i
ON CONFLICT DO NOTHING;
