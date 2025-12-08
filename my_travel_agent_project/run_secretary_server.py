import os
import uvicorn
from dotenv import load_dotenv
import vertexai

# .envファイルから環境変数を読み込む
load_dotenv()

# Vertex AIの使用を明示的に強制する（これが重要！）
os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from travel_team.agents.secretary_agent import secretary_agent

# Vertex AIの初期化
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
if project_id:
    print(f"Initializing Vertex AI with project: {project_id}, location: {location}")
    vertexai.init(project=project_id, location=location)

# ポート番号の設定（デフォルトは8001。Planner Agentの8000と競合しないように）
PORT = int(os.getenv("PORT", 8001))

# ADKのエージェントをA2Aアプリ（FastAPIアプリ）に変換
a2a_app = to_a2a(secretary_agent, port=PORT)

if __name__ == "__main__":
    print(f"Starting Secretary Agent Server on port {PORT}...")
    print(f"Agent Card URL: http://localhost:{PORT}/v1/card")
    
    # uvicornを使ってサーバーを起動
    uvicorn.run(a2a_app, host="0.0.0.0", port=PORT)
