CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capsules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    access_code VARCHAR(255) NOT NULL,
    temperature FLOAT DEFAULT 22.0,
    oxygen_level FLOAT DEFAULT 95.0,
    status VARCHAR(20) DEFAULT 'day',
    cluster_name VARCHAR(100),
    cluster_key VARCHAR(100),
    owner_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_requests (
    id SERIAL PRIMARY KEY,
    sender_capsule_name VARCHAR(100) NOT NULL,
    receiver_capsule_name VARCHAR(100) NOT NULL,
    cluster_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_capsules_name ON capsules(name);
CREATE INDEX IF NOT EXISTS idx_capsules_owner_id ON capsules(owner_id);
CREATE INDEX IF NOT EXISTS idx_capsules_cluster_key ON capsules(cluster_name);
CREATE INDEX IF NOT EXISTS idx_cluster_requests_sender_name ON cluster_requests(sender_capsule_name);
CREATE INDEX IF NOT EXISTS idx_cluster_requests_receiver_name ON cluster_requests(receiver_capsule_name);
CREATE INDEX IF NOT EXISTS idx_cluster_requests_status ON cluster_requests(status);
CREATE INDEX IF NOT EXISTS idx_cluster_requests_cluster_key ON cluster_requests(cluster_name);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_pending_requests 
ON cluster_requests(sender_capsule_name, receiver_capsule_name) 
WHERE status = 'pending';