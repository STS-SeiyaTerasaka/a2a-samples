import os
from google.adk.agents.llm_agent import LlmAgent
from google.genai.types import Part, Content
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

# ツールとヘルパーをインポート
# search_tools.py から google_search ツール（Grounding）をインポート
from travel_team.tools.search_tools import search_tool 
from travel_team.agents.search_agent import search_agent # Search Agent
from utils.a2a_helpers import create_a2a_factory, get_agent_resource

PLANNER_MODEL_NAME = 'gemini-2.5-flash'

# --- ツール設定 ---

# 1. Search Agent Tool
search_agent_tool = AgentTool(search_agent)

# 2. Secretary Agent Tool (Remote Agent)
# 環境変数からリソース名を取得し、クラウド/ローカルのURLを切り替える
secretary_resource_name = os.environ.get("SECRETARY_RESOURCE_NAME")
location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

if secretary_resource_name:
    # クラウドデプロイ時: リソース名からURLを構築
    # パスは /v1/card (Agent Engine仕様)
    secretary_url = f'https://{location}-aiplatform.googleapis.com/v1beta1/{secretary_resource_name}/a2a/v1/card'
    print(f"Configuring Secretary Agent with Cloud URL: {secretary_url}")
else:
    # ローカル実行時: デフォルトポート8001
    secretary_port = int(os.environ.get("SECRETARY_PORT", 8001))
    # パスは /.well-known/agent-card.json (to_a2a仕様)
    secretary_url = f'http://localhost:{secretary_port}/.well-known/agent-card.json'
    print(f"Configuring Secretary Agent with Local URL: {secretary_url}")

factory = create_a2a_factory()
secretary_remote_agent = RemoteA2aAgent(
    name="secretary_agent",
    description="旅行プランナーからの指示でGoogleカレンダー登録リンクを作成する秘書エージェント。タイトル、日時、場所、詳細を受け取ります。",
    agent_card=secretary_url,
    a2a_client_factory=factory,
)
secretary_agent_tool = AgentTool(secretary_remote_agent)

planner_instruction = '''
あなたはユーザーの旅行計画をサポートする優秀な旅行プランナーです。
ユーザーの要望（場所、日程、興味など）を聞き出し、最新情報に基づいて魅力的で現実的な旅行プランを提案してください。

Discovery:
- 最新のイベントや観光地情報を調べる必要がある場合は、`search_agent` ツールを積極的に使用しなさい。
- ユーザーにプランを提案し、合意が得られたらカレンダー登録リンクの作成を提案しなさい。

Execution:
- ユーザーがカレンダー登録を希望した場合、`secretary_agent` ツールを呼び出してカレンダー登録リンクを作成させなさい。
  この際、ツールにはイベントのタイトル、開始日時、終了日時、場所、詳細を正確に渡しなさい。

制約:
- 提案は常に日本語で行いなさい。
- 不明な点があれば、ユーザーに質問しなさい。
- 最終的にカレンダー登録リンクが生成されたら、それをユーザーに提示し、お礼の言葉を述べて会話を終えなさい。
'''

planner_agent = LlmAgent(
    name='planner_agent',
    model=PLANNER_MODEL_NAME, # 文字列指定
    description='Google検索と秘書エージェントと連携して旅行プランを作成・カレンダー登録を支援するエージェント',
    instruction=planner_instruction,
    tools=[
        search_agent_tool,   # Search Agent (AgentTool)
        secretary_agent_tool # Secretary Agent (AgentTool/Remote)
    ], 
)