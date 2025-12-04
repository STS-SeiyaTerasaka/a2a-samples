import httpx
import os
import asyncio
import subprocess
import time
import sys
from typing import Dict, Any
from google.auth import default
from google.auth.transport.requests import Request
import vertexai
from dotenv import load_dotenv

load_dotenv() # .env ファイルから環境変数を読み込む

# ADK Imports
from google.genai.types import HttpOptions
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

# A2A Imports
from a2a.client import ClientConfig, ClientFactory
from a2a.types import TransportProtocol
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

# Agent Engine Imports
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import A2aAgent
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card

# ユーザー設定ファイルの読み込み
try:
    from agent_config import define_leaf_agents, define_root_agent, COMMON_REQUIREMENTS
except ImportError:
    print("Error: 'agent_config.py' not found. Please create it defining your agents.")
    sys.exit(1)

# ==========================================
# 汎用デプロイロジック (編集不要)
# ==========================================

# --- 環境設定 ---
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

if not PROJECT_ID:
    try:
        PROJECT_ID = subprocess.check_output(["gcloud", "config", "list", "--format", "value(core.project)"]).decode("utf-8").strip()
    except:
        pass

if not PROJECT_ID:
    raise ValueError("PROJECT_ID environment variable is not set.")

STAGING_BUCKET = os.getenv("STAGING_BUCKET", f"gs://{PROJECT_ID}")

print(f"Project: {PROJECT_ID}, Location: {LOCATION}, Bucket: {STAGING_BUCKET}")

vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)


# --- Helper Classes ---

class MyVertexAiSessionService(VertexAiSessionService):
    async def create_session(self, app_name, user_id, state={}, session_id=None):
        return await super().create_session(app_name=app_name, user_id=user_id, state=state)

    async def get_session(self, app_name, user_id, session_id):
        try:
            return await super().get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        except:
            return None

def get_create_runner_class(agent, resource_name):
    async def create_runner():
        return Runner(
            app_name=resource_name or agent.name,
            agent=agent,
            artifact_service=InMemoryArtifactService(),
            session_service=MyVertexAiSessionService(),
            memory_service=InMemoryMemoryService(),
        )
    return create_runner

def get_agent_executor_class(agent, resource_name):
    def agent_executor_builder():
        return A2aAgentExecutor(runner=get_create_runner_class(agent, resource_name))
    return agent_executor_builder

async def get_agent_card(agent):
    builder = AgentCardBuilder(agent=agent)
    card = await builder.build()
    return create_agent_card(agent_name=card.name, description=card.description, skills=card.skills)

class GoogleAuthRefresh(httpx.Auth):
    def __init__(self, scopes):
        self.credentials, _ = default(scopes=scopes)
        self.transport_request = Request()
        self.credentials.refresh(self.transport_request)

    def auth_flow(self, request):
        if not self.credentials.valid:
            self.credentials.refresh(self.transport_request)
        request.headers['Authorization'] = f'Bearer {self.credentials.token}'
        yield request

class MyClientFactory(ClientFactory):
    def create(self, card, consumers=None, interceptors=None):
        if not self._config.httpx_client:
            self._config.httpx_client=httpx.AsyncClient(
                timeout=60,
                headers={'Content-Type': 'application/json'},
                auth=GoogleAuthRefresh(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            )
            self._register_defaults(self._config.supported_transports)
        return super().create(card, consumers, interceptors)

class MyRemoteA2aAgent(RemoteA2aAgent):
    async def _ensure_httpx_client(self):
        if not self._httpx_client:
            self._httpx_client=httpx.AsyncClient(
                timeout=60,
                headers={'Content-Type': 'application/json'},
                auth=GoogleAuthRefresh(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            )
        return self._httpx_client

# --- Deployment Functions ---

async def deploy_leaf_agents(leaf_agents: Dict[str, Any], requirements: list) -> Dict[str, str]:
    """Leafエージェントを一括デプロイし、エージェント名とリソース名のマップを返します"""
    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
        http_options=HttpOptions(api_version='v1beta1', base_url=f'https://{LOCATION}-aiplatform.googleapis.com/')
    )
    
    resource_map = {}
    
    # 既存のエージェントを検索してリソースIDを特定するヘルパー
    def find_existing_resource(display_name):
        for ag in agent_engines.list():
            if ag.display_name == display_name:
                return ag.resource_name
        return None

    print(f"\n--- Deploying {len(leaf_agents)} Leaf Agents ---")
    
    for name, agent in leaf_agents.items():
        print(f"Processing: {name}...")
        
        # 1. 既存チェック
        existing_resource = find_existing_resource(name)
        
        # 2. 仮のエージェントカード作成
        card_content = await get_agent_card(agent)
        
        # 共通設定
        config = {
            'display_name': name,
            'description': card_content.agent_card.description,
            'requirements': requirements,
            'http_options': {'base_url': f'https://{LOCATION}-aiplatform.googleapis.com', 'api_version': 'v1beta1'},
            'staging_bucket': STAGING_BUCKET,
        }

        if not existing_resource:
            # 新規作成 (Resource ID確保のため)
            print(f"  Creating new Agent Engine instance for {name}...")
            # create時は resource_name なしで executor を組む
            a2a_agent_initial = A2aAgent(
                agent_card=card_content,
                agent_executor_builder=get_agent_executor_class(agent, None)
            )
            created_agent = client.agent_engines.create(
                agent=a2a_agent_initial,
                config=config,
            )
            existing_resource = created_agent.resource_name
            print(f"  Created. Resource Name: {existing_resource}")
            time.sleep(5) # 伝播待ち

        # 3. 本番デプロイ (Resource IDを埋め込んで更新)
        # これにより VertexAiSessionService が正しく動作する
        print(f"  Updating {name} with correct session configuration...")
        a2a_agent_final = A2aAgent(
            agent_card=card_content,
            agent_executor_builder=get_agent_executor_class(agent, existing_resource)
        )
        
        client.agent_engines.update(
            name=existing_resource,
            agent=a2a_agent_final,
            config=config,
        )
        
        resource_map[name] = existing_resource
        print(f"  Done: {name}")

    return resource_map

def setup_iam_permissions():
    """Agent Engineのサービスアカウントに権限を付与"""
    print("\n--- Configuring IAM Permissions ---")
    try:
        project_number = subprocess.check_output(
            ["gcloud", "projects", "describe", PROJECT_ID, "--format", "value(projectNumber)"]
        ).decode("utf-8").strip()
        
        service_account = f"service-{project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
        print(f"  Target Service Account: {service_account}")
        
        subprocess.run([
            "gcloud", "projects", "add-iam-policy-binding", PROJECT_ID,
            "--member", f"serviceAccount:{service_account}",
            "--role", "roles/aiplatform.user"
        ], check=True)
        print("  IAM permissions granted.")
    except Exception as e:
        print(f"  WARNING: Failed to set IAM permissions automatically. You may need to run this manually.\n  Error: {e}")

def create_remote_wrappers(resource_map: Dict[str, str], leaf_agents_def: Dict[str, Any]) -> Dict[str, MyRemoteA2aAgent]:
    """デプロイ済みエージェントのリソース名から、Rootエージェントで使用するRemoteラッパーを作成"""
    factory = MyClientFactory(
        ClientConfig(
            supported_transports=[TransportProtocol.http_json],
            use_client_preference=True,
        )
    )
    
    wrappers = {}
    for name, resource_name in resource_map.items():
        original_agent = leaf_agents_def[name]
        # ADKのエージェント定義から説明文などを引き継ぐ
        description = getattr(original_agent, 'description', '')
        # エージェント名は元の定義のname属性を使用 (display_nameではない)
        agent_internal_name = getattr(original_agent, 'name', name) 

        a2a_url = f'https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{resource_name}/a2a'
        
        wrappers[name] = MyRemoteA2aAgent(
            name=agent_internal_name,
            description=description,
            agent_card=f'{a2a_url}/v1/card',
            a2a_client_factory=factory,
        )
    return wrappers


# ==========================================
# メイン実行部
# ==========================================

async def main():
    print("=== A2A System Deployment Started ===")

    # 1. ユーザー定義のLeafエージェントを取得
    leaf_agents_def = define_leaf_agents()
    if not leaf_agents_def:
        print("No leaf agents defined in agent_config.py. Exiting.")
        return

    # 2. Leafエージェントのデプロイ
    resource_map = await deploy_leaf_agents(leaf_agents_def, COMMON_REQUIREMENTS)
    
    # 3. IAM権限の設定 (初回のみ必要だが毎回実行しても安全)
    setup_iam_permissions()

    # 4. リモートラッパーの作成
    print("\n--- Creating Remote Wrappers ---")
    remote_agents = create_remote_wrappers(resource_map, leaf_agents_def)
    
    # 5. Rootエージェントの定義とデプロイ
    print("\n--- Deploying Root Agent ---")
    root_agent, root_display_name = define_root_agent(remote_agents)
    
    remote_root = agent_engines.create(
        agent_engine=root_agent,
        display_name=root_display_name,
        requirements=COMMON_REQUIREMENTS,
    )
    
    print("\n==========================================")
    print("       DEPLOYMENT COMPLETE SUCCESS")
    print("==========================================")
    print(f"Root Agent Resource Name: {remote_root.resource_name}")
    print("You can now call this agent from your application.")

if __name__ == "__main__":
    asyncio.run(main())
