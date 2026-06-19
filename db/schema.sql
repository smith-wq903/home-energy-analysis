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

-- RLS（Row Level Security）
-- service_role キーは RLS をバイパスするため、INSERT 側はポリシー不要
-- anon キー（Streamlit アプリ）が読み取れるよう SELECT ポリシーを追加
ALTER TABLE device_power ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_anon_read" ON device_power
    FOR SELECT TO anon USING (true);

-- 古いデータを自動削除するポリシー（任意: 1年以上前のデータを保持しない）
-- 必要に応じてコメントを外して実行してください
-- SELECT cron.schedule('delete-old-device-power', '0 3 * * *',
--   $$DELETE FROM device_power WHERE recorded_at < NOW() - INTERVAL '1 year'$$);

-- ============================================================
-- Data API (PostgREST) アクセス権限
-- 2026/10/30 以降、public スキーマのテーブルは明示的な GRANT が必要
-- ダッシュボード（app.py）は anon キー経由でこれらのテーブルを読む
-- ============================================================
GRANT SELECT ON TABLE public.device_power       TO anon;
GRANT SELECT ON TABLE public.device_power_30min TO anon;
GRANT SELECT ON TABLE public.enevisata_30min     TO anon;
GRANT SELECT ON TABLE public.enevisata_daily     TO anon;
GRANT SELECT ON TABLE public.enevisata_monthly   TO anon;
