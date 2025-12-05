import requests
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from a2a.types import AgentCard
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

def get_auth_headers():
    """Google Cloudのアクセストークンを取得してヘッダーを返す"""
    try:
        credentials, _ = google.auth.default()
        credentials.refresh(GoogleAuthRequest())
        return {"Authorization": f"Bearer {credentials.token}"}
    except Exception as e:
        print(f"Warning: Failed to get Google Cloud credentials: {e}")
        return {}

def get_agent_card(remote_agent_address: str) -> AgentCard:
    """Get the agent card with authentication, trying multiple paths."""
    if not remote_agent_address.startswith(('http://', 'https://')):
        remote_agent_address = 'http://' + remote_agent_address
    
    base_url = remote_agent_address.rstrip('/')
    headers = get_auth_headers()

    # 試行するパスのリスト
    # 1. デフォルトパス (/.well-known/agent-card.json)
    # 2. Agent Engine パス (/v1/card)
    paths_to_try = [
        AGENT_CARD_WELL_KNOWN_PATH,
        "/v1/card"
    ]

    # ユーザーが既に特定のパスを含んでいる場合は、そのパスを最優先で試す
    if base_url.endswith('/v1/card') or base_url.endswith('agent-card.json'):
        paths_to_try.insert(0, "") # そのままのリクエストを最初に試す

    last_error = None

    for path in paths_to_try:
        # パスを結合（base_urlが既にパスを含んでいる場合に対応）
        if path == "":
            url = base_url
        elif base_url.endswith(path):
            url = base_url
        else:
            # base_url が /a2a で終わっている場合とそうでない場合を考慮
            # シンプルに結合する
            url = f"{base_url}{path}"

        try:
            print(f"DEBUG: Trying to fetch Agent Card from: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # 成功したらAgentCardを返して終了
            print(f"DEBUG: Successfully fetched Agent Card from: {url}")
            return AgentCard(**response.json())
            
        except requests.exceptions.HTTPError as e:
            # 404なら次のパスを試す
            if e.response.status_code == 404:
                print(f"DEBUG: 404 Not Found at {url}, trying next path...")
                last_error = e
                continue
            else:
                # 404以外のエラー（401, 500など）は即座にraiseする
                raise e
        except Exception as e:
            last_error = e
            continue

    # 全てのパスで失敗した場合
    print("DEBUG: All attempts to fetch Agent Card failed.")
    if last_error:
        raise last_error
    else:
        raise requests.exceptions.RequestException(f"Failed to fetch agent card from {base_url}")
