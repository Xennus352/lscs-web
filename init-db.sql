-- MySQL initialization script for LBVD project
-- This runs automatically when the MySQL container starts

CREATE DATABASE IF NOT EXISTS lbvd CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lbvd;

-- Create users table (as per app/main.py init_db function)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin', 'staff') NOT NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Insert a default admin user (password: 12345678)
-- Password hash would be generated in production; using plain text for dev
INSERT IGNORE INTO users (username, password, role) VALUES ('admin', '12345678', 'admin');

-- Note: The personcv table ALTER operations are handled by the application
-- via the ensure_personcv_status() function in main.py lifespan