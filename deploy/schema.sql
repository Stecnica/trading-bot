-- Fresh MariaDB schema. An existing database is upgraded in place by ensure_schema
-- and does not need this file. Do not copy AUTO_INCREMENT values from a live install.

CREATE TABLE IF NOT EXISTS market_history (
    id INT NOT NULL AUTO_INCREMENT,
    asset_name VARCHAR(255) NOT NULL,
    timestamp DATETIME NOT NULL,
    price DECIMAL(18,8) NOT NULL,
    open_price DECIMAL(18,8) NULL,
    high_price DECIMAL(18,8) NULL,
    low_price DECIMAL(18,8) NULL,
    volume DECIMAL(20,4) NULL,
    vwap DECIMAL(18,8) NULL,
    trade_count INT NULL,
    bar_ms BIGINT NULL,
    otc TINYINT(1) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_asset_ts (asset_name, timestamp),
    KEY idx_history_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS preferences (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    value VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uniq_pref_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS transactions (
    id INT NOT NULL AUTO_INCREMENT,
    type VARCHAR(10) NOT NULL,
    asset_name VARCHAR(255) NOT NULL,
    amount DECIMAL(18,8) NOT NULL,
    price DECIMAL(18,8) NOT NULL,
    timestamp DATETIME NOT NULL,
    fees DECIMAL(18,8) NOT NULL,
    taxes DECIMAL(18,8) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_tx_timestamp (timestamp),
    KEY idx_tx_type (type),
    KEY idx_tx_asset (asset_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS classification (
    code VARCHAR(220) NOT NULL,
    parent_code VARCHAR(220) NULL,
    name VARCHAR(160) NOT NULL,
    PRIMARY KEY (code),
    KEY idx_class_parent (parent_code),
    CONSTRAINT fk_class_parent FOREIGN KEY (parent_code) REFERENCES classification (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS asset_class (
    asset_name VARCHAR(16) NOT NULL,
    classification_code VARCHAR(220) NOT NULL,
    PRIMARY KEY (asset_name),
    KEY idx_asset_class (classification_code),
    CONSTRAINT fk_asset_class FOREIGN KEY (classification_code) REFERENCES classification (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
