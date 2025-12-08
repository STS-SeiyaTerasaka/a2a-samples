from google.adk.agents.llm_agent import LlmAgent
from travel_team.tools.search_tools import search_tool

# 検索専用エージェント
SEARCH_AGENT_MODEL = 'gemini-2.5-flash'

search_agent = LlmAgent(
    name='search_agent',
    model=SEARCH_AGENT_MODEL,
    description='Google検索を実行し、最新情報やイベント情報を調査して返すエージェント。',
    instruction='''
    あなたは検索担当のエージェントです。
    ユーザーからの質問や依頼に基づいて、Google検索ツールを適切に使用し、必要な情報を収集してください。
    検索結果を要約して、わかりやすく回答してください。
    ''',
    tools=[search_tool], # ここでGroundingツールを使用（これ単独ならOK）
)
