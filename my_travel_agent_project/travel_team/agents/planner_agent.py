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
# クラウド実行時のフォールバックとして、デプロイ済みのSecretary AgentのリソースIDを指定
DEFAULT_SECRETARY_RESOURCE_NAME = "projects/1060275483775/locations/us-central1/reasoningEngines/2765951242042605568"
secretary_resource_name = os.environ.get("SECRETARY_RESOURCE_NAME", DEFAULT_SECRETARY_RESOURCE_NAME)
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
  また、カレンダー作成に必要な情報（イベントのタイトル、開始日時、終了日時、場所、詳細）は旅行プランを基に
　作成してください 

制約:
- 提案は常に日本語で行いなさい。
- 不明な点があれば、ユーザーに質問しなさい。
- 最終的にカレンダー登録リンクが生成されたら、それをユーザーに提示し、お礼の言葉を述べて会話を終えなさい。

プラン例：
旅行テーマ:歴史的建造物巡り、河原町周辺散策、京料理を満喫
日程:2025年12月13日(土)~12月14日(日)
人数:4名様
予算:20万円(交通費を除く)
1日目:2025年12月13日(土)河原町散策と東山·祇園の歴史探訪
·午前:河原町周辺を散策(本能寺、近代建築群、錦天満宮)
·ランチ:錦市場または河原町周辺で京料理
●午後:東山·祇園エリア(清水寺、二年坂·三年坂、高台寺、建仁寺)
·夕食:祇園エリアで京料理
·夜:京都タワーまたは京都駅ビルイルミネーション
2日目:2025年12月14日(日)嵐山の絶景と金閣の輝き、禅の精神を体験
·午前:嵐山(渡月橋、竹林の道、天龍寺)
·ランチ:嵐山周辺で湯豆腐または軽食
●午後:金閣寺、龍安寺
●夕食:京都駅周辺で食事とお土産
費用目安(4名様分、交通費除く)
·宿泊費:60,000円
· 食費:56,000円
● 観光·拝観料:10,000円
お十産代·一
●お土産代:74,000円(調整可能)
合計:200,000円
その他アドバイス:服装、交通手段、イベント情報
このプランでよろしいでしょうか?変更点や追加したい点があれば、お気軽にお申し付けください。
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
