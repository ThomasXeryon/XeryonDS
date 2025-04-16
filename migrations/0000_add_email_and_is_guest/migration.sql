-- Add email column to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;

-- Add is_guest column to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS is_guest BOOLEAN NOT NULL DEFAULT FALSE;

-- Make password column nullable
ALTER TABLE users
ALTER COLUMN password DROP NOT NULL;