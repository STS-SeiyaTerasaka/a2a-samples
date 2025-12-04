from typing import Any, Dict, List, Optional
import logging

from google.adk.agents import Agent
from google.adk.models import LlmResponse, LlmRequest
from google.genai.types import Content, Part

# CrewAI Logic
from crewai_agent_logic import ImageGenerationAgent

class CrewAIAdkWrapper(Agent):
    """
    CrewAIのエージェントをADK (Agent Development Kit) で動作させるためのラッパー。
    ADKからの入力を受け取り、CrewAIのinvokeを呼び出し、結果をADK形式で返します。
    """
    def __init__(self, name: str, description: str = ""):
        super().__init__(name=name)
        self._description = description
        # CrewAIのエージェントインスタンスを初期化
        self.crew_agent = ImageGenerationAgent()

    @property
    def description(self) -> str:
        return self._description

    def process(self, request: LlmRequest, context: Dict[str, Any] = None) -> LlmResponse:
        """
        ADK Runnerから呼び出されるメインメソッド。
        """
        # 1. ユーザー入力の抽出
        # request.input は LlmRequest オブジェクトの可能性がありますが、
        # 基本的には直近のユーザーメッセージを取得します。
        user_prompt = ""
        if request.messages and len(request.messages) > 0:
             # 最後のメッセージのテキスト部分を取得
            last_msg = request.messages[-1]
            if last_msg.content and last_msg.content.parts:
                user_prompt = last_msg.content.parts[0].text
        
        if not user_prompt:
            return LlmResponse(content=Content(role="model", parts=[Part(text="入力が見つかりませんでした。")]))

        # セッションIDの取得 (ADKのcontextから)
        session_id = "default_session"
        if context and 'session_id' in context:
            session_id = context['session_id']

        # 2. CrewAIの実行
        try:
            # CrewAIのinvokeメソッドを呼び出し
            # Note: invokeは同期的に実行されます
            result = self.crew_agent.invoke(user_prompt, session_id)
            
            # 結果が画像のIDなどで返ってくる場合があるため、テキスト形式に変換
            response_text = str(result)

            # 画像データが生成された場合の処理 (オプション)
            # 元のコードでは image_key = os.path.splitext(result.raw)[0] などで取得していますが、
            # ここではシンプルにテキスト応答として返します。
            # 必要であればここで InMemoryCache から画像を取り出し、Part(inline_data=...) で返すことも可能です。
            
            return LlmResponse(
                content=Content(
                    role="model", 
                    parts=[Part(text=f"CrewAI Execution Result:\n{response_text}")]
                )
            )

        except Exception as e:
            logging.error(f"CrewAI Execution Error: {e}")
            return LlmResponse(
                content=Content(
                    role="model", 
                    parts=[Part(text=f"CrewAIの実行中にエラーが発生しました: {e}")]
                )
            )
