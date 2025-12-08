import os
# from google.adk.tools import Tool # Tool import removed
from google.adk.agents.llm_agent import LlmAgent
# GoogleLLM import removed
from google.genai.types import Part, Content

# ツールとヘルパーをインポート
# search_tools.py から google_search ツール（Grounding）をインポート
from travel_team.tools.search_tools import search_tool 
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from utils.a2a_helpers import create_a2a_factory, get_agent_resource

PLANNER_MODEL_NAME = 'gemini-2.5-flash'

def create_call_secretary_tool(location: str):
    secretary_display_name = 'secretary_agent'
    secretary_resource_name = get_agent_resource(secretary_display_name)

    if not secretary_resource_name:
        print(f"Warning: Secretary Agent '{secretary_display_name}' not found.")
        secretary_a2a_url = f'https://{location}-aiplatform.googleapis.com/v1beta1/projects/UNKNOWN/locations/{location}/reasoningEngines/UNKNOWN/a2a'
    else:
        secretary_a2a_url = f'https://{location}-aiplatform.googleapis.com/v1beta1/{secretary_resource_name}/a2a'
    
    async def call_secretary_agent_function(
        title: str,
        start_datetime: str,
        end_datetime: str,
        location: str = "",
        details: str = ""
    ) -> str:
        """
        旅行プランの情報を秘書エージェントに渡し、Googleカレンダー登録リンクを作成させます。
        Args:
            title: イベントのタイトル。
            start_datetime: イベントの開始日時 (ISOフォーマット例: '2025-12-25T09:00:00')。
            end_datetime: イベントの終了日時 (ISOフォーマット例: '2025-12-25T10:00:00')。
            location: イベントの場所 (任意)。
            details: イベントの詳細説明 (任意)。
        Returns:
            秘書エージェントが生成したGoogleカレンダー登録用のURL。
        """
        print(f"Calling Secretary Agent at {secretary_a2a_url}...")
        
        factory = create_a2a_factory()
        secretary_remote_agent = RemoteA2aAgent(
            name=secretary_display_name,
            description="秘書エージェント",
            agent_card=f'{secretary_a2a_url}/v1/card',
            a2a_client_factory=factory,
        )

        message_to_secretary = (
            f"カレンダー登録リンクを作成してください。\n"
            f"タイトル: {title}\n"
            f"開始日時: {start_datetime}\n"
            f"終了日時: {end_datetime}\n"
            f"場所: {location}\n"
            f"詳細: {details}"
        )
        
        try:
            response_events = secretary_remote_agent.send_message(
                Content(role='user', parts=[Part(text=message_to_secretary)])
            )
            
            final_response_text = ""
            async for event in response_events:
                if event.content and event.content.parts:
                    final_response_text += '\n'.join([p.text for p in event.content.parts if p.text])
            
            return final_response_text
        except Exception as e:
            return f"Error calling secretary agent: {e}"

    return call_secretary_agent_function

planner_instruction = '''
あなたはユーザーの旅行計画をサポートする優秀な旅行プランナーです。
ユーザーの要望（場所、日程、興味など）を聞き出し、最新情報に基づいて魅力的で現実的な旅行プランを提案してください。

Discovery:
- 最新のイベントや観光地情報を調べる必要がある場合は、`google_search` ツール（Grounding）を積極的に使用しなさい。
- ユーザーにプランを提案し、合意が得られたらカレンダー登録リンクの作成を提案しなさい。

Execution:
- ユーザーがカレンダー登録を希望した場合、`call_secretary_agent` ツールを呼び出してカレンダー登録リンクを作成させなさい。
  この際、ツールにはイベントのタイトル、開始日時、終了日時、場所、詳細を正確に渡しなさい。

制約:
- 提案は常に日本語で行いなさい。
- 不明な点があれば、ユーザーに質問しなさい。
- 最終的にカレンダー登録リンクが生成されたら、それをユーザーに提示し、お礼の言葉を述べて会話を終えなさい。
'''

planner_agent = LlmAgent(
    name='planner_agent',
    model=PLANNER_MODEL_NAME, # 文字列指定に戻す
    description='Google検索と秘書エージェントと連携して旅行プランを作成・カレンダー登録を支援するエージェント',
    instruction=planner_instruction,
    tools=[
        search_tool, # Google Search Grounding Tool
        # call_secretary_agent はデプロイスクリプトで追加される
    ], 
)