CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    description TEXT NOT NULL
);

INSERT INTO products (product_id, stock, description)
VALUES
    (42, 10000, 'Demo product for concurrent purchase testing'),
    (101, 500, 'Small stock product'),
    (202, 0, 'Out of stock product')
ON CONFLICT (product_id) DO UPDATE
SET stock = EXCLUDED.stock,
    description = EXCLUDED.description;
