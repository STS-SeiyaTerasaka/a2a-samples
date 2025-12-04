from typing import Any, Dict, List, Optional
import logging
from google.adk.agents import Agent
from google.adk.models import LlmResponse, LlmRequest
from google.genai.types import Content, Part

# パッケージ内のモジュールからインポート
from .agent import ImageGenerationAgent

class CrewAIAdkWrapper(Agent):
    """
    CrewAIのエージェントをADK (Agent Development Kit) で動作させるためのラッパー。
    """
    def __init__(self, name: str, description: str = ""):
        super().__init__(name=name)
        self._description = description
        self.crew_agent = ImageGenerationAgent()

    @property
    def description(self) -> str:
        return self._description

    def process(self, request: LlmRequest, context: Dict[str, Any] = None) -> LlmResponse:
        user_prompt = ""
        if request.messages and len(request.messages) > 0:
            last_msg = request.messages[-1]
            if last_msg.content and last_msg.content.parts:
                user_prompt = last_msg.content.parts[0].text
        
        if not user_prompt:
            return LlmResponse(content=Content(role="model", parts=[Part(text="入力が見つかりませんでした。")]))

        session_id = "default_session"
        if context and 'session_id' in context:
            session_id = context['session_id']

        try:
            result = self.crew_agent.invoke(user_prompt, session_id)
            response_text = str(result)
            
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
