-- ============================================================
-- Supabase テーブル定義
-- Supabase の SQL Editor に貼り付けて実行してください
-- ============================================================

-- 機器別電力データ（5分毎）
CREATE TABLE IF NOT EXISTS device_power (
    id          BIGSERIAL PRIMARY KEY,
    device_id   TEXT        NOT NULL,
    device_name TEXT,
    recorded_at TIMESTAMPTZ NOT NULL,
    power_w     NUMERIC,        -- 消費電力 (W)
    voltage_v   NUMERIC,        -- 電圧 (V)
    current_a   NUMERIC,        -- 電流 (A)
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 検索用インデックス
CREATE INDEX IF NOT EXISTS idx_device_power_device_id   ON device_power (device_id);
CREATE INDEX IF NOT EXISTS idx_device_power_recorded_at ON device_power (recorded_at DESC);

-- 古いデータを自動削除するポリシー（任意: 1年以上前のデータを保持しない）
-- 必要に応じてコメントを外して実行してください
-- SELECT cron.schedule('delete-old-device-power', '0 3 * * *',
--   $$DELETE FROM device_power WHERE recorded_at < NOW() - INTERVAL '1 year'$$);
