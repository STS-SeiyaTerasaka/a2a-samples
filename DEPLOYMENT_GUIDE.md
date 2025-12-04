# Vertex AI Agent Engine デプロイ手順書

本ドキュメントは、CrewAIベースのエージェント（`crewai_image_gen`）をGoogle Cloud Vertex AI Agent Engineへデプロイするための手順書です。
これまでのトラブルシューティングで判明した問題（ディレクトリ名の競合、依存関係の欠落、インポートエラーなど）を解消した、成功実績のある手順をまとめています。

## 前提条件

*   Google Cloud SDK (`gcloud` CLI) がインストールされていること。
*   Python (3.10以上推奨) および `uv` コマンドがインストールされていること。
*   WSL (Windows Subsystem for Linux) 環境での作業を想定しています。

---

## 1. Google Cloud の認証とプロジェクト設定

まず、Google Cloudへの認証を行い、対象のプロジェクトを設定します。

```bash
# 1. Google Cloudへログイン
gcloud auth application-default login

# 2. プロジェクトIDを設定（ご自身のプロジェクトIDに置き換えてください）
gcloud config set project sts-osaka-si-learn-terasaka
```

## 2. Agent Starter Pack によるプロジェクト拡張（初回のみ）

既存のプロジェクトに対して、Agent Engineへのデプロイに必要なファイルを追加します。
※既に実施済みの場合はスキップ可能です。

```bash
# プロジェクトのルートディレクトリで実行
uvx agent-starter-pack enhance --adk -d agent_engine
```

## 3. ステージング用バケットの作成（初回のみ）

デプロイ用のファイルを一時保存するためのGoogle Cloud Storageバケットを作成します。

```bash
# バケットを作成（バケット名は一意である必要があります）
gcloud storage buckets create gs://sts-osaka-si-learn-terasaka-agent-staging --location=us-central1

# 作成確認
gcloud storage buckets describe gs://sts-osaka-si-learn-terasaka-agent-staging
```

---

## 4. プロジェクトの修正と準備（重要）

デプロイを成功させるために、以下の修正を適用します。

### 4.1 ディレクトリ名の変更
`crewai` というディレクトリ名はライブラリ名と競合し、インポートエラーの原因となるため変更します。

```bash
# samples/python/agents ディレクトリへ移動
cd samples/python/agents

# ディレクトリ名を変更
mv crewai crewai_image_gen
```

### 4.2 `agent.py` の修正
`samples/python/agents/crewai_image_gen/agent.py` を以下の2点について修正します。

1.  **インポートパスの修正**: ローカル/クラウド両対応にするため、絶対・相対インポートを併用します。
    ```python
    # 変更前
    from in_memory_cache import InMemoryCache

    # 変更後
    try:
        from in_memory_cache import InMemoryCache
    except ImportError:
        from .in_memory_cache import InMemoryCache
    ```

2.  **モデル初期化の修正**: ビルド環境で環境変数がない場合のエラーを防ぐため、フォールバックを追加します。
    ```python
    # __init__ メソッド内
    def __init__(self):
        if os.getenv('GOOGLE_GENAI_USE_VERTEXAI'):
            self.model = LLM(model='vertex_ai/gemini-2.5-flash-image')
        elif os.getenv('GOOGLE_API_KEY'):
            # ... (中略) ...
        else:
            # 【追加】デフォルト設定
            self.model = LLM(model='vertex_ai/gemini-2.5-flash-image')
    ```

### 4.3 依存関係の追加
`Pillow` ライブラリ（画像処理用）が不足しているため追加します。

1.  `samples/python/agents/crewai_image_gen/pyproject.toml` に `Pillow` を追加。
    ```toml
    dependencies = [
        # ... 他の依存関係 ...
        "Pillow",
    ]
    ```

2.  **`requirements.txt` の作成**（デプロイツールに依存関係を確実に認識させるため）
    `samples/python/agents/crewai_image_gen/requirements.txt` を作成し、以下を記述します。
    ```text
    crewai[tools]>=0.95.0
google-genai>=1.9.0
a2a-sdk>=0.3.0
google-adk>=1.15.0,<2.0.0
Pillow
    ```

### 4.4 不要なファイルの削除
デプロイ時間を短縮し、容量エラーを防ぐため、ローカルの仮想環境やバックアップファイルを削除します。

```bash
# samples/python/agents ディレクトリで実行
rm -rf crewai_image_gen/.venv
rm -rf crewai_image_gen/.backup_crewai_*
```

---

## 5. デプロイの実行

すべての準備が整ったら、デプロイを実行します。
**注意:** このコマンドは、エージェントのディレクトリ（`crewai_image_gen`）の**親ディレクトリ**（`samples/python/agents`）から実行し、引数で対象ディレクトリ名を指定します。

```bash
# 現在のディレクトリを確認（samples/python/agents であること）
pwd

# デプロイコマンド実行
uv run adk deploy agent_engine \
  --project=sts-osaka-si-learn-terasaka \
  --region=us-central1 \
  --staging_bucket=gs://sts-osaka-si-learn-terasaka-agent-staging \
  --display_name="CrewAI Image Generation Agent" \
  crewai_image_gen
```

### 成功時の出力
成功すると、以下のようなメッセージが表示されます。
```
AgentEngine created. Resource name: projects/.../locations/us-central1/reasoningEngines/...
Cleaning up the temp folder: ...
```

これでデプロイは完了です。Google CloudコンソールまたはSDKを通じてエージェントを利用できます。

```