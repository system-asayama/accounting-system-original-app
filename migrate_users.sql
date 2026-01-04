-- usersテーブルにカラムを追加
ALTER TABLE users ADD COLUMN IF NOT EXISTS login_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'admin';
ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_owner BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS can_manage_admins BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS openai_api_key TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at VARCHAR(19);
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at VARCHAR(19);

-- login_idにユニーク制約を追加
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'users_login_id_key'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_login_id_key UNIQUE (login_id);
    END IF;
END $$;

-- user_organizationsテーブルを作成
CREATE TABLE IF NOT EXISTS user_organizations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    organization_id INTEGER REFERENCES organizations(id) NOT NULL,
    created_at VARCHAR(19),
    UNIQUE(user_id, organization_id)
);
