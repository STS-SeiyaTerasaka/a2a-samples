import uuid
from google.genai.types import Part, Content
from google.adk.runners import Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

class LocalApp:
    def __init__(self, agent, app_name='default_app', user_id='default_user'):
        self._agent = agent
        self._app_name = app_name
        self._user_id = user_id
        self._runner = Runner(
            app_name=self._app_name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        self._session = None
        
    async def stream(self, query):
        if not self._session:
            self._session = await self._runner.session_service.create_session(
                app_name=self._app_name,
                user_id=self._user_id,
                session_id=uuid.uuid4().hex,
            )
        content = Content(role='user', parts=[Part(text=query)])
        async_events = self._runner.run_async(
            user_id=self._user_id,
            session_id=self._session.id,
            new_message=content,
        )
        result = []
        async for event in async_events:
            if (event.content and event.content.parts):
                response = '\n'.join([p.text for p in event.content.parts if p.text])
                if response:
                    print(response)
                    result.append(response)
        return result
