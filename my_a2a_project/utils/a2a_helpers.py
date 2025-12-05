import httpx
import json
import os
from google.auth import default
from google.auth.transport.requests import Request
import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import A2aAgent
from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models import LlmResponse, LlmRequest
from google.adk.runners import Runner
from google.adk.sessions import VertexAiSessionService
from google.genai.types import Part, Content

from a2a.client import ClientConfig, ClientFactory
from a2a.types import TransportProtocol
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

# --- Authentication ---

class GoogleAuthRefresh(httpx.Auth):
    def __init__(self, scopes):
        self.credentials, _ = default(scopes=scopes)
        self.transport_request = Request()
        self.credentials.refresh(self.transport_request)

    def auth_flow(self, request):
        if not self.credentials.valid:
            self.credentials.refresh(self.transport_request)
        request.headers['Authorization'] = f'Bearer {self.credentials.token}'
        yield request

def create_a2a_factory():
    """A2Aクライアントファクトリーを作成します"""
    return ClientFactory(
        ClientConfig(
            supported_transports=[TransportProtocol.http_json],
            use_client_preference=True,
            httpx_client=httpx.AsyncClient(
                timeout=60,
                headers={'Content-Type': 'application/json'},
                auth=GoogleAuthRefresh(scopes=['https://www.googleapis.com/auth/cloud-platform']) 
            ),
        ),
    )

# --- Session Service Wrapper ---

class MyVertexAiSessionService(VertexAiSessionService):
    async def create_session(self, app_name, user_id, state={}, session_id=None):
        session = await super().create_session(
            app_name=app_name,
            user_id=user_id,
            state=state,
        )
        return session

    async def get_session(self, app_name, user_id, session_id):
        try:
            session = await super().get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )
            return session
        except:
            return None

# --- Helper Functions for Deployment ---

def get_agent_resource(agent_name):
    """エージェントの表示名からResource Nameを取得します"""
    try:
        for agent in agent_engines.list():
            if agent.display_name == agent_name:
                return agent.resource_name
    except Exception as e:
        print(f"Error listing agent engines: {e}")
    return None

def get_create_runner_class(agent, resource_name):
    async def create_runner():
        return Runner(
            app_name=resource_name or agent.name,
            agent=agent,
            artifact_service=InMemoryArtifactService(),
            session_service=MyVertexAiSessionService(),
            memory_service=InMemoryMemoryService(),
        )
    return create_runner

def get_agent_executor_class(agent, resource_name):
    def agent_executor_builder():
        return A2aAgentExecutor(
            runner=get_create_runner_class(agent, resource_name),
        )       
    return agent_executor_builder

async def get_agent_card(agent):
    builder = AgentCardBuilder(agent=agent)
    adk_agent_card = await builder.build()
    return create_agent_card(
        agent_name=adk_agent_card.name,
        description=adk_agent_card.description,
        skills=adk_agent_card.skills
    )

# --- Helper Agent ---

def get_print_agent(text):
    """メッセージを表示するだけのAgentを作成します"""
    def before_model_callback(
        callback_context: CallbackContext, llm_request: LlmRequest
    ) -> LlmResponse:
        return LlmResponse(
            content=Content(
                role='model', parts=[Part(text=text)],
            )
        )
    return LlmAgent(
        name='print_agent',
        model='gemini-2.5-flash', 
        description='',
        instruction = '',
        before_model_callback=before_model_callback,
    )