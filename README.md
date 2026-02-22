# home-energy-analysis

家庭の電力使用データを自動収集・可視化するツール。
SwitchBot API からデバイス別の消費電力を5分毎に取得し、Supabase に蓄積。
Streamlit ダッシュボードでグラフ表示する。**全て無料**で動作する。

```
[GitHub Actions] --5分毎--> [SwitchBot API] --> [Supabase] <-- [Streamlit Cloud]
```

---

## フォルダ構成

```
home-energy-analysis/
├── .github/workflows/
│   └── collect_switchbot.yml   # 自動収集ジョブ（5分毎）
├── sb-data-accumulator/
│   ├── collector.py            # SwitchBot → Supabase
│   ├── sb_monitor.py           # 旧スクリプト（ローカル実行用・参考）
│   ├── requirements.txt
│   └── .env.example
├── power-dashboard/
│   ├── app.py                  # Streamlit ダッシュボード
│   ├── requirements.txt
│   └── .env.example
├── power-detail-reader/        # EneVista連携（今後実装予定）
├── db/
│   └── schema.sql              # Supabase テーブル定義
└── .gitignore
```

---

## セットアップ手順

### 1. Supabase でデータベースを作成する

1. [https://supabase.com](https://supabase.com) にアクセスして無料アカウントを作成
2. 新しいプロジェクトを作成（Project name は任意）
3. 左メニュー **SQL Editor** を開き、`db/schema.sql` の内容をコピー&ペーストして **Run** を実行
4. 左メニュー **Settings → API** を開き、以下の2つをメモする
   - `Project URL`（例: `https://xxxx.supabase.co`）
   - `anon public` キー

---

### 2. GitHub リポジトリを作成して Secrets を設定する

1. GitHub で新しいリポジトリを作成（**Public** 推奨: Actions の無料枠が無制限になる）
2. このフォルダの内容をプッシュする

   ```bash
   git init
   git add .
   git commit -m "initial commit"
   git remote add origin https://github.com/<あなたのユーザー名>/<リポジトリ名>.git
   git push -u origin main
   ```

3. GitHub リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で以下を登録する

   | Secret 名 | 値の取得元 |
   |---|---|
   | `SB_API_TOKEN` | SwitchBot アプリ → プロフィール → 設定 → 開発者向けオプション |
   | `SB_API_SECRET` | 同上（v1.1 で追加された Secret） |
   | `DEVICE_IDS` | SwitchBot アプリ → デバイス → 設定 → デバイス情報 でID確認。カンマ区切りで全台分 |
   | `DEVICE_NAMES` | `ペンペン,デスクライト,冷蔵庫,トイレ,ベッド,玄関充電,デスクチャージャー,テレビ他,洗濯機,ドライヤー`（DEVICE_IDSと同じ順番） |
   | `SUPABASE_URL` | Supabase の Project URL |
   | `SUPABASE_ANON_KEY` | Supabase の anon public キー |

4. **Actions タブ → collect_switchbot.yml → Run workflow** で手動実行してエラーが出ないか確認する

---

### 3. Streamlit Cloud でダッシュボードを公開する

1. [https://streamlit.io/cloud](https://streamlit.io/cloud) にアクセスして GitHub アカウントでログイン
2. **New app** を押して以下を設定する
   - Repository: このリポジトリを選択
   - Branch: `main`
   - Main file path: `power-dashboard/app.py`
3. **Advanced settings → Secrets** に以下を入力する（TOML 形式）

   ```toml
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_ANON_KEY = "your_anon_key_here"
   ```

4. **Deploy** を押す

---

## ローカルでの動作確認

### collector.py を手元で試す

```bash
cd sb-data-accumulator

# 環境変数ファイルを作成
cp .env.example .env
# .env を編集して実際の値を入力

# 依存パッケージをインストール
pip install -r requirements.txt

# 1回実行してみる
python collector.py
```

成功すると以下のように表示される：
```
2024-01-01 12:00:00 - ペンペン: 5.2
2024-01-01 12:00:00 - デスクライト: 12.1
...
✅ データ保存完了: 10 件 (2024-01-01T03:00:00+00:00)
```

Supabase の **Table Editor → device_power** を開いてデータが入っていれば成功。

### ダッシュボードをローカルで起動する

```bash
cd power-dashboard

cp .env.example .env
# .env を編集して SUPABASE_URL と SUPABASE_ANON_KEY を入力

pip install -r requirements.txt
streamlit run app.py
```

ブラウザが自動で開き `http://localhost:8501` にダッシュボードが表示される。

---

## 動作確認チェックリスト

- [ ] `collector.py` をローカルで実行してコンソールにエラーが出ない
- [ ] Supabase の `device_power` テーブルにデータが入っている
- [ ] GitHub Actions の **Actions タブ** で `collect_switchbot.yml` が緑になっている
- [ ] 5分後にもう一度 Supabase を確認して行が増えている
- [ ] Streamlit ダッシュボードにグラフが表示されている

---

## 料金について

| サービス | 利用状況 | 費用 |
|---|---|---|
| GitHub Actions | Public リポジトリは無制限 | **¥0** |
| Supabase | 500MB まで無料 | **¥0** |
| Streamlit Cloud | Public リポジトリのアプリは無料 | **¥0** |

5分毎・10台のデータを1年間蓄積すると約 **50MB**（Supabase 500MB 枠の10%）の見込み。

---

## 今後の予定

- [ ] `power-detail-reader/` — EneVista からの電力会社データ取得（スクレイピング）
