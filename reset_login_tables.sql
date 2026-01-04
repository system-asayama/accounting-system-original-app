-- ログインシステムのテーブルをリセット（データのみ削除、テーブル構造は保持）

-- 外部キー制約のあるテーブルから順に削除
DELETE FROM "T_テナント管理者_テナント";
DELETE FROM "T_管理者_店舗";
DELETE FROM "T_従業員_店舗";
DELETE FROM "T_テナントアプリ設定";
DELETE FROM "T_店舗アプリ設定";
DELETE FROM "T_店舗";
DELETE FROM "T_従業員";
DELETE FROM "T_管理者";
DELETE FROM "T_テナント";

-- シーケンスをリセット
ALTER SEQUENCE "T_テナント管理者_テナント_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_管理者_店舗_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_従業員_店舗_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_テナントアプリ設定_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_店舗アプリ設定_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_店舗_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_従業員_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_管理者_id_seq" RESTART WITH 1;
ALTER SEQUENCE "T_テナント_id_seq" RESTART WITH 1;
