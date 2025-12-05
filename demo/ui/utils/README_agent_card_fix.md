# Agent Card 取得ロジックの修正解説 (`demo/ui/utils/agent_card.py`)

このドキュメントでは、デモUIが Google Cloud Agent Engine (Vertex AI) 上のエージェントに接続できるようにするために行った、`agent_card.py` の修正内容とその背景を解説します。

## 1. 背景と課題

オリジナルのコードは、ローカル環境（`localhost` など）で動作する認証不要なエージェントへの接続を前提としていました。そのため、以下の課題がありました。

1.  **認証トークンの欠如**: Google Cloud 上の Agent Engine は IAM 認証（OAuth2 トークン）を必須としますが、オリジナルのコードは認証ヘッダーを送っていなかったため、`401 Unauthorized` や `403 Forbidden` エラーが発生しました。
2.  **URLパスの不一致**: オリジナルのコードは、エージェント情報の取得先として `/.well-known/agent-card.json` という固定パスを使用していましたが、Agent Engine は `/v1/card` というパスを使用するため、`404 Not Found` エラーが発生しました。

## 2. 修正内容

これらの課題を解決しつつ、従来のローカルエージェントへの接続も維持するために、以下のロジックを実装しました。

### A. Google Cloud 認証の追加

`google.auth` ライブラリを使用して、実行環境（ローカルPCやCloud Shellなど）の認証情報からアクセストークンを動的に取得し、HTTPリクエストのヘッダーに追加するようにしました。

```python
def get_auth_headers():
    # ... (省略) ...
    credentials, _ = google.auth.default()
    return {"Authorization": f"Bearer {credentials.token}"}
```

### B. 複数のパスに対するフォールバック（自動再試行）ロジック

異なる種類のエージェント（ローカル vs クラウド）に対応するため、複数のパスを順番に試行するロジックを導入しました。

1.  **試行1**: デフォルトパス `/.well-known/agent-card.json` にアクセス。
    *   成功 → そのまま Agent Card を返却（ローカルエージェントの場合）。
    *   失敗 (404) → 次へ。
2.  **試行2**: Agent Engine 用パス `/v1/card` にアクセス。
    *   成功 → Agent Card を返却（Agent Engine の場合）。
    *   失敗 → エラーとして終了。

これにより、ユーザーは接続先がどちらのタイプかを意識する必要がなくなりました。

## 3. コードの変更点（Before / After）

### Before (修正前)

```python
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

def get_agent_card(remote_agent_address: str) -> AgentCard:
    # 単純に固定パスを結合して、認証なしでGETリクエスト
    agent_card = requests.get(
        f'{remote_agent_address}{AGENT_CARD_WELL_KNOWN_PATH}'
    )
    return AgentCard(**agent_card.json())
```

### After (修正後)

```python
import google.auth
# ... 他のインポート

def get_agent_card(remote_agent_address: str) -> AgentCard:
    base_url = remote_agent_address.rstrip('/')
    headers = get_auth_headers() # 認証ヘッダー取得

    # 試行するパスのリスト
    paths_to_try = [
        AGENT_CARD_WELL_KNOWN_PATH, # /.well-known/agent-card.json
        "/v1/card"                  # Agent Engine用
    ]

    for path in paths_to_try:
        url = f"{base_url}{path}"
        try:
            # 認証ヘッダー付きでリクエスト
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return AgentCard(**response.json())
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                continue # 404なら次のパスを試す
            raise e # それ以外（401など）は即エラー
            
    raise requests.exceptions.RequestException(...)
```

## 4. 期待される動作

*   **ローカルエージェントへの接続**: 1回目の試行（`/.well-known/...`）で成功し、従来通り動作します。
*   **Agent Engineへの接続**: 1回目は 404 エラーになりますが、内部でキャッチして2回目の試行（`/v1/card`）を行い、成功します。認証トークンも付与されているため、権限エラーも発生しません。
