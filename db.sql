CREATE TABLE IF NOT EXISTS users (
	id INTEGER PRIMARY KEY,
	request_time INTEGER NOT NULL
);

INSERT OR IGNORE INTO users
VALUES (1, 4294967296);