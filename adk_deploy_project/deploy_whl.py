import os
import asyncio
import subprocess
import time
import sys
import argparse
import logging
from glob import glob
from dotenv import load_dotenv

import vertexai
from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import storage
from google.api_core import exceptions as google_exceptions

# ADK Imports
from google.genai.types import HttpOptions
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, VertexAiSessionService

# A2A Imports
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

# Agent Engine Imports
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import A2aAgent
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# ユーザー設定: デプロイ対象のパッケージとエージェントのエントリポイント
# ==========================================
# .whl ファイル内のPythonパッケージ名と、そのパッケージ内のエージェントクラスを指定します。
AGENT_ENTRY_POINT = 'my_a2a_agents_pkg.a2a_agents.adapter:CrewAIAdkWrapper'
AGENT_DISPLAY_NAME = 'ImageGenerationCrewAIAgent_WHLS'
AGENT_DESCRIPTION = 'CrewAIを使った画像生成エージェント (WHLSデプロイ)'

# ==========================================
# 汎用デプロイロジック
# ==========================================

# .env ファイルから環境変数を読み込む
load_dotenv()

# --- Helper Classes ---

class MyVertexAiSessionService(VertexAiSessionService):
    async def create_session(self, app_name, user_id, state={}, session_id=None):
        return await super().create_session(app_name=app_name, user_id=user_id, state=state)

    async def get_session(self, app_name, user_id, session_id):
        try:
            return await super().get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        except:
            return None

def get_create_runner_class(agent_factory, resource_name):
    async def create_runner():
        return Runner(
            app_name=resource_name or AGENT_DISPLAY_NAME, 
            agent=agent_factory(), # ここでエージェントクラスをインスタンス化
            artifact_service=InMemoryArtifactService(),
            session_service=MyVertexAiSessionService(),
            memory_service=InMemoryMemoryService(),
        )
    return create_runner

def get_agent_executor_class(agent_factory, resource_name):
    def agent_executor_builder():
        return A2aAgentExecutor(runner=get_create_runner_class(agent_factory, resource_name))
    return agent_executor_builder

# エージェントクラスを動的にロードするファクトリ
def load_agent_class(entry_point_str: str):
    module_name, class_name = entry_point_str.rsplit(':', 1)
    # パッケージがすでにインストールされていることを前提にインポート
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)

def setup_staging_bucket(project_id: str, location: str, bucket_name: str) -> str:
    """
    ステージングバケットが存在するか確認し、なければ作成します。
    """
    # gs:// prefix を削除
    if bucket_name.startswith("gs://"):
        bucket_name = bucket_name[5:]

    storage_client = storage.Client(project=project_id)
    try:
        bucket = storage_client.lookup_bucket(bucket_name)
        if bucket:
            logger.info(f"Staging bucket gs://{bucket_name} already exists.")
        else:
            logger.info(f"Staging bucket gs://{bucket_name} not found. Creating...")
            new_bucket = storage_client.create_bucket(bucket_name, project=project_id, location=location)
            logger.info(f"Successfully created staging bucket gs://{new_bucket.name} in {location}.")
            # Uniform bucket-level access を有効化 (推奨)
            new_bucket.iam_configuration.uniform_bucket_level_access_enabled = True
            new_bucket.patch()
    except google_exceptions.Forbidden as e:
        logger.error(f"Permission denied for bucket gs://{bucket_name}. Ensure 'Storage Admin' role. Error: {e}")
        raise
    except google_exceptions.Conflict as e:
        logger.warning(f"Bucket gs://{bucket_name} likely already exists but owned by another project. Error: {e}")
    except Exception as e:
        logger.error(f"Failed to access/create bucket gs://{bucket_name}. Error: {e}")
        raise

    return f"gs://{bucket_name}"

# --- Deployment Functions ---

async def deploy_whl_agent(args):
    project_id = args.project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = args.location or os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    bucket_name = args.bucket or os.getenv("STAGING_BUCKET")
    
    if not project_id:
        raise ValueError("Project ID is required. Set GOOGLE_CLOUD_PROJECT or use --project_id.")
    if not bucket_name:
        # デフォルトのバケット名を設定
        bucket_name = f"{project_id}-a2a-staging"
        logger.info(f"No bucket specified. Using default: {bucket_name}")

    print(f"Project: {project_id}, Location: {location}, Bucket: {bucket_name}")

    # 1. バケットの準備
    staging_bucket_uri = setup_staging_bucket(project_id, location, bucket_name)

    # 2. Vertex AI 初期化
    vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket_uri)

    client = vertexai.Client(
        project=project_id,
        location=location,
        http_options=HttpOptions(api_version='v1beta1', base_url=f'https://{location}-aiplatform.googleapis.com/')
    )

    if args.delete:
        if not args.resource_id:
            print("Error: --resource_id is required for delete operation.")
            return
        print(f"Deleting agent with resource ID: {args.resource_id}...")
        try:
            agent_engines.delete(name=args.resource_id)
            print("Successfully deleted agent.")
        except Exception as e:
            print(f"Error deleting agent: {e}")
        return

    # Create/Update Operation
    
    # 3. .whl ファイルを見つける
    dist_files = glob('dist/*.whl')
    if not dist_files:
        print("Error: No .whl file found in the 'dist' directory. Please run 'python -m build' first.")
        sys.exit(1)
    whl_path = dist_files[0]
    print(f"Found .whl file: {whl_path}")

    # 4. IAM権限の設定 (自動)
    print("\n--- Configuring IAM Permissions ---")
    # ... (既存のIAM設定ロジックを簡略化して呼び出し) ...
    # ここでは実装を省略し、必要に応じて以前のロジックを使用してください。
    # 基本的には setup_staging_bucket で権限エラーが出なければ、基本的な権限はあるはずです。

    # 5. .whlファイルをAgent Engineのrequirementsとしてデプロイ
    print("\n--- Deploying Agent to Agent Engine ---")
    
    AgentClass = load_agent_class(AGENT_ENTRY_POINT)
    
    # ADK Agent として初期化 (Card生成用)
    temp_adk_agent_instance = AgentClass(name=AGENT_DISPLAY_NAME, description=AGENT_DESCRIPTION)
    agent_card_content = await AgentCardBuilder(agent=temp_adk_agent_instance).build()
    a2a_agent_card = create_agent_card(
        agent_name=agent_card_content.name,
        description=agent_card_content.description,
        skills=agent_card_content.skills
    )

    existing_agent_resource_name = None
    if not args.create: # --create が明示されていない場合は既存を探す
        for ag in agent_engines.list():
            if ag.display_name == AGENT_DISPLAY_NAME:
                existing_agent_resource_name = ag.resource_name
                break

    # 環境変数の準備
    env_vars = {
        "GOOGLE_GENAI_USE_VERTEXAI": os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "True"),
        # 必要に応じて他の環境変数も追加
    }

    config = {
        'display_name': AGENT_DISPLAY_NAME,
        'description': AGENT_DESCRIPTION,
        'requirements': [
            whl_path,
            'google-adk==1.14.1',
            'google-genai==1.36.0',
            'google-cloud-aiplatform==1.113.0',
            'a2a-sdk==0.3.5',
            'crewai==0.35.0',
            'Pillow==10.3.0',
            'python-dotenv==1.0.1',
            'google-generativeai==0.8.0',
        ],
        'http_options': {'base_url': f'https://{location}-aiplatform.googleapis.com', 'api_version': 'v1beta1'},
        'staging_bucket': staging_bucket_uri,
        'entry_point': AGENT_ENTRY_POINT,
        'env_vars': env_vars # 環境変数を注入
    }

    a2a_agent_instance = A2aAgent(
        agent_card=a2a_agent_card,
        agent_executor_builder=get_agent_executor_class(AgentClass, existing_agent_resource_name)
    )

    if existing_agent_resource_name and not args.create:
        print(f"  Updating existing Agent Engine instance: {AGENT_DISPLAY_NAME} ({existing_agent_resource_name})...")
        remote_agent = client.agent_engines.update(
            name=existing_agent_resource_name,
            agent=a2a_agent_instance,
            config=config,
        )
    else:
        print(f"  Creating new Agent Engine instance: {AGENT_DISPLAY_NAME}...")
        remote_agent = client.agent_engines.create(
            agent=a2a_agent_instance,
            config=config,
        )
    
    print("\n==========================================")
    print("       DEPLOYMENT COMPLETE SUCCESS")
    print("==========================================")
    print(f"Root Agent Resource Name: {remote_agent.resource_name}")
    print("You can now call this agent from your application.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Agent to Vertex AI Agent Engine using .whl file.")
    parser.add_argument("--project_id", help="GCP Project ID")
    parser.add_argument("--location", help="GCP Location (e.g., us-central1)")
    parser.add_argument("--bucket", help="Staging Bucket Name")
    parser.add_argument("--create", action="store_true", help="Force create a new agent instance")
    parser.add_argument("--delete", action="store_true", help="Delete an existing agent")
    parser.add_argument("--resource_id", help="Resource ID of the agent to delete")

    args = parser.parse_args()
    
    asyncio.run(deploy_whl_agent(args))
