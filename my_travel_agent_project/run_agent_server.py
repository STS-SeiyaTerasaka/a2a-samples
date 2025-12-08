import os
import uvicorn
from dotenv import load_dotenv
import vertexai
from google.genai.types import Part, Content
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool
from utils.a2a_helpers import create_a2a_factory

# .envファイルから環境変数を読み込む
load_dotenv()

# Vertex AIの使用を明示的に強制する
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'

# デバッグ用：環境変数の確認
print(f"DEBUG: GOOGLE_CLOUD_PROJECT={os.getenv('GOOGLE_CLOUD_PROJECT')}")
print(f"DEBUG: GOOGLE_CLOUD_LOCATION={os.getenv('GOOGLE_CLOUD_LOCATION')}")
print(f"DEBUG: GOOGLE_GENAI_USE_VERTEXAI={os.getenv('GOOGLE_GENAI_USE_VERTEXAI')}")

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from travel_team.agents.planner_agent import planner_agent
from travel_team.agents.search_agent import search_agent # Search Agentをインポート

# Vertex AIの初期化（環境変数があれば）
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
if project_id:
    print(f"Initializing Vertex AI with project: {project_id}, location: {location}")
    vertexai.init(project=project_id, location=location)
else:
    print("WARNING: GOOGLE_CLOUD_PROJECT is NOT set. Authentication may fail.")

# --- ツール設定 (Agent-as-a-Tool パターン) ---

# 1. Search Agent (Local Agent)
print("Preparing Search Agent as a tool...")
search_agent_tool = AgentTool(search_agent)

# 2. Secretary Agent (Remote Agent)
# A2Aファクトリの作成
factory = create_a2a_factory()

# ローカルのSecretary Agentのポート（デフォルト8001）
secretary_port = int(os.getenv("SECRETARY_PORT", 8001))
# ローカル(to_a2a)では /.well-known/agent-card.json がデフォルトのエンドポイントになります
secretary_url = f'http://localhost:{secretary_port}/.well-known/agent-card.json'

print(f"Defining RemoteA2aAgent for Secretary at {secretary_url}...")

secretary_remote_agent = RemoteA2aAgent(
    name="secretary_agent",
    description="旅行プランナーからの指示でGoogleカレンダー登録リンクを作成する秘書エージェント。タイトル、日時、場所、詳細を受け取ります。",
    agent_card=secretary_url,
    a2a_client_factory=factory,
)
secretary_agent_tool = AgentTool(secretary_remote_agent)

# Planner Agentのツールを再設定（上書きして競合を排除）
print("Configuring tools for planner_agent: [search_agent, secretary_agent]")
# 元々入っていた search_tool を削除し、AgentToolのみにする
planner_agent.tools = [search_agent_tool, secretary_agent_tool]

# ----------------------------------------------------

# ポート番号の設定（デフォルトは8000）
PORT = int(os.getenv("PORT", 8000))

# ADKのエージェントをA2Aアプリ（FastAPIアプリ）に変換
a2a_app = to_a2a(planner_agent, port=PORT)

if __name__ == "__main__":
    print(f"Starting Planner Agent Server on port {PORT}...")
    print(f"Agent Card URL: http://localhost:{PORT}/v1/card")
    
    # uvicornを使ってサーバーを起動
    uvicorn.run(a2a_app, host="0.0.0.0", port=PORT)
