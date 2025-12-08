import os
# Tool import removed
from google.adk.agents.llm_agent import LlmAgent
# GoogleLLM import removed

# ツールをインポート
from travel_team.tools.calendar_tools import create_google_calendar_link

SECRETARY_MODEL_NAME = 'gemini-2.5-flash'

secretary_instruction = '''
あなたは優秀な秘書エージェントです。
旅行プランナーエージェントから渡されたイベント情報（タイトル、開始日時、終了日時、場所、詳細）を元に、
Googleカレンダーに登録するためのURLを生成することがあなたの唯一の役割です。

指示された情報を正確に受け取り、`create_google_calendar_link` ツールを使ってURLを生成し、そのURLのみを返答しなさい。
余計な会話や情報は一切不要です。ユーザーに直接話しかけるような返答もしてはいけません。
'''

# ツール定義のラッパー（Toolクラス）は削除し、関数を直接使用

secretary_agent = LlmAgent(
    name='secretary_agent',
    model=SECRETARY_MODEL_NAME, # 文字列指定に戻す
    description='Googleカレンダーの登録リンクを生成する秘書エージェント',
    instruction=secretary_instruction,
    tools=[create_google_calendar_link], # ★関数を直接登録
)
