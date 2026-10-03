-- Quorlo demo schema: a deliberately messy retail database.
--
-- Every problem here is on purpose: cryptic names, undocumented status codes, a table
-- without a primary key, near-duplicate tables, a staging dump with positional column
-- names. dim_product is the one well-documented table, so a scan shows a range of scores.
--
-- All personal data below is fake: example.com addresses, 555-01xx phone numbers.

CREATE SCHEMA retail_raw;
COMMENT ON SCHEMA retail_raw IS 'Raw retail data loaded nightly from the legacy order system.';

SET search_path TO retail_raw;

-- Customer master: cryptic column names and an undocumented integer status.
CREATE TABLE cust_mstr (
    cust_id   integer PRIMARY KEY,
    nm        varchar(100) NOT NULL,
    eml       varchar(255),
    phn       varchar(20),
    addr1     varchar(200),
    pc        varchar(10),
    cntry_cd  char(2),
    st        smallint NOT NULL DEFAULT 1,
    crt_dt    date NOT NULL DEFAULT current_date
);
COMMENT ON COLUMN cust_mstr.cust_id IS 'Customer identifier from the legacy order system.';

INSERT INTO cust_mstr (cust_id, nm, eml, phn, addr1, pc, cntry_cd, st, crt_dt) VALUES
    (1, 'Ada Example',    'ada@example.com',    '555-0101', '123 Example St', '10001', 'US', 1, '2023-01-15'),
    (2, 'Ben Sample',     'ben@example.com',    '555-0102', '124 Example St', '10002', 'US', 2, '2023-02-20'),
    (3, 'Cleo Placeholder','cleo@example.com',  '555-0103', '125 Example St', '10003', 'CA', 1, '2023-03-05'),
    (4, 'Dev Testperson', 'dev@example.com',    '555-0104', '126 Example St', '10004', 'GB', 3, '2023-04-11'),
    (5, 'Eve Fictional',  'eve@example.com',    '555-0105', '127 Example St', '10005', 'US', 9, '2023-05-30');

-- Order header: another undocumented status code.
CREATE TABLE ord_hdr (
    ord_id    integer PRIMARY KEY,
    cust_id   integer NOT NULL REFERENCES cust_mstr (cust_id),
    ord_dt    timestamp NOT NULL,
    st        smallint NOT NULL,
    tot_amt   numeric(12, 2) NOT NULL
);
COMMENT ON TABLE ord_hdr IS 'Order headers.';

INSERT INTO ord_hdr VALUES
    (1001, 1, '2024-01-03 10:15', 4, 120.50),
    (1002, 2, '2024-01-04 11:00', 4,  35.00),
    (1003, 1, '2024-01-07 09:30', 2,  89.99),
    (1004, 4, '2024-01-09 16:45', 7,  12.00);

-- Order lines: no primary key, on purpose.
CREATE TABLE ord_ln (
    ord_id    integer NOT NULL REFERENCES ord_hdr (ord_id),
    ln_no     smallint NOT NULL,
    prod_id   integer NOT NULL,
    qty       integer NOT NULL,
    unit_prc  numeric(10, 2) NOT NULL
);

INSERT INTO ord_ln VALUES
    (1001, 1, 10, 2, 50.25),
    (1001, 2, 11, 1, 20.00),
    (1002, 1, 12, 1, 35.00),
    (1003, 1, 10, 1, 89.99),
    (1004, 1, 13, 3,  4.00);

-- Two tables for the same concept. Which one is right? Nothing says.
CREATE TABLE revenue_daily (
    day       date PRIMARY KEY,
    revenue   numeric(14, 2) NOT NULL
);

CREATE TABLE daily_revenue_v2 (
    rev_dt    date PRIMARY KEY,
    gross_amt numeric(14, 2) NOT NULL,
    net_amt   numeric(14, 2) NOT NULL
);

INSERT INTO revenue_daily VALUES ('2024-01-03', 120.50), ('2024-01-04', 35.00);
INSERT INTO daily_revenue_v2 VALUES ('2024-01-03', 120.50, 110.00), ('2024-01-04', 35.00, 32.00);

-- A staging dump nobody cleaned up.
CREATE TABLE stg_imp_01 (
    c1 text,
    c2 text,
    f1 numeric,
    f2 numeric
);

INSERT INTO stg_imp_01 VALUES ('A', 'x', 1, 2), ('B', 'y', 3, 4);

-- A view over the mess.
CREATE VIEW v_ord_summary AS
SELECT h.ord_id, h.cust_id, h.ord_dt, count(l.*) AS ln_cnt, h.tot_amt
FROM ord_hdr h
LEFT JOIN ord_ln l ON l.ord_id = h.ord_id
GROUP BY h.ord_id, h.cust_id, h.ord_dt, h.tot_amt;

-- The contrast: a table an agent can actually use.
CREATE TABLE dim_product (
    product_id    integer PRIMARY KEY,
    product_name  varchar(200) NOT NULL,
    category      varchar(100) NOT NULL,
    list_price    numeric(10, 2) NOT NULL,
    is_active     boolean NOT NULL DEFAULT true
);
COMMENT ON TABLE dim_product IS 'Product dimension. One row per sellable product; the source of truth for product names and list prices.';
COMMENT ON COLUMN dim_product.product_id IS 'Product identifier, referenced by ord_ln.prod_id.';
COMMENT ON COLUMN dim_product.product_name IS 'Display name shown to customers.';
COMMENT ON COLUMN dim_product.category IS 'Merchandising category, e.g. "Kitchen" or "Garden".';
COMMENT ON COLUMN dim_product.list_price IS 'Current list price in USD, before discounts and tax.';
COMMENT ON COLUMN dim_product.is_active IS 'True while the product can be ordered; false once discontinued.';

INSERT INTO dim_product VALUES
    (10, 'Chef Knife',     'Kitchen', 50.25, true),
    (11, 'Cutting Board',  'Kitchen', 20.00, true),
    (12, 'Garden Hose',    'Garden',  35.00, true),
    (13, 'Seed Packet',    'Garden',   4.00, false);

-- Fresh planner statistics, so row-count estimates are populated.
ANALYZE;
