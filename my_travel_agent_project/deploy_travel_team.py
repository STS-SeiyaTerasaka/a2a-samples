import os
import asyncio
import vertexai
from google.genai.types import HttpOptions
from vertexai.preview.reasoning_engines import A2aAgent, ReasoningEngine 
import google.auth

# Import agents and helpers from their respective files
from travel_team.agents.secretary_agent import secretary_agent
from travel_team.agents.planner_agent import planner_agent
from travel_team.agents.search_agent import search_agent # Search Agentを追加
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from utils.a2a_helpers import (
    get_agent_card,
    get_agent_executor_class,
    get_agent_resource,
    create_a2a_factory # Factory作成用
)

async def main():
    # 1. Setup Project ID and Location
    try:
        credentials, project_id = google.auth.default()
    except Exception as e:
        print(f"Error getting default credentials: {e}")
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if not project_id:
        print("Error: Could not determine Google Cloud Project ID.")
        print("Please run 'gcloud auth application-default login' or set GOOGLE_CLOUD_PROJECT env var.")
        return

    LOCATION = 'us-central1'
    STAGING_BUCKET = f'gs://{project_id}'

    print(f"Deploying to Project: {project_id}, Location: {LOCATION}")

    # Initialize Vertex AI
    vertexai.init(project=project_id, location=LOCATION, staging_bucket=STAGING_BUCKET)
    
    # Client is still useful for listing/getting if needed, but not primary for creation now
    client = vertexai.Client(
        project=project_id,
        location=LOCATION,
        http_options=HttpOptions(
            api_version='v1beta1', base_url=f'https://{LOCATION}-aiplatform.googleapis.com/'
        ),
    )

    # Requirements from Workbench logs
    requirements_list = [
        'google-adk==1.14.1',
        'google-genai==1.36.0',
        'google-cloud-aiplatform==1.113.0',
        'a2a-sdk==0.3.5',
        'pydantic==2.12.4',
        'cloudpickle==3.1.2',
    ]

    # ==================================================================
    # STEP 1: Deploy Secretary Agent (Worker) first to get its resource_name
    # ==================================================================
    secretary_display_name = 'secretary_agent'
    print(f"\nProcessing {secretary_display_name}...")
    
    secretary_agent_card_obj = await get_agent_card(secretary_agent)
    
    secretary_resource_name = get_agent_resource(secretary_display_name)
    
    if not secretary_resource_name:
        print(f"  Creating new agent engine for {secretary_display_name} with extra_packages...")
        secretary_a2a_agent_instance = A2aAgent(
            agent_card=secretary_agent_card_obj,
            agent_executor_builder=get_agent_executor_class(secretary_agent, None)
        )

        created_secretary_engine = ReasoningEngine.create(
            secretary_a2a_agent_instance,
            display_name=secretary_display_name,
            requirements=requirements_list,
            extra_packages=["./travel_team", "./utils"],
        )
        
        print(f"  Created. Resource Name: {created_secretary_engine.resource_name}")
        secretary_resource_name = created_secretary_engine.resource_name
    else:
        print(f"  Agent already exists: {secretary_resource_name}")

    # Update (Self-referencing resource name fix)
    print(f"  Updating {secretary_display_name} to inject resource name into session service...")
    secretary_a2a_agent_for_update = A2aAgent(
        agent_card=secretary_agent_card_obj, 
        agent_executor_builder=get_agent_executor_class(secretary_agent, secretary_resource_name) 
    )
    client.agent_engines.update(
        name=secretary_resource_name,
        agent=secretary_a2a_agent_for_update,
        config={
            'display_name': secretary_display_name,
            'description': secretary_agent_card_obj.description,
            'requirements': requirements_list,
            'http_options': {
                'base_url': f'https://{LOCATION}-aiplatform.googleapis.com',
                'api_version': 'v1beta1',
            },
            'staging_bucket': STAGING_BUCKET,
        },
    )
    print(f"  Update complete for {secretary_display_name}.")

    # ==================================================================
    # STEP 2: Deploy Planner Agent (Orchestrator) with Agent-as-a-Tool
    # ==================================================================
    planner_display_name = 'planner_agent'
    print(f"\nProcessing {planner_display_name}...")

    # --- Tool Configuration (Agent-as-a-Tool) ---
    
    # 1. Search Agent Tool (Local Agent)
    print("  Preparing Search Agent as a tool...")
    search_agent_tool = AgentTool(search_agent)

    # 2. Secretary Agent Tool (Remote Agent)
    print("  Preparing Secretary Agent connection as a tool...")
    factory = create_a2a_factory()
    # クラウド上のA2A URLを構築 (Agent Engineの標準パス: /a2a/v1/card)
    # 注意: Agent EngineのURL構造は https://{location}-aiplatform.../{resource_name}/a2a
    # Agent Cardのパスはその配下の /v1/card
    secretary_a2a_card_url = f'https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{secretary_resource_name}/a2a/v1/card'
    
    secretary_remote_agent = RemoteA2aAgent(
        name="secretary_agent",
        description="旅行プランナーからの指示でGoogleカレンダー登録リンクを作成する秘書エージェント。",
        agent_card=secretary_a2a_card_url,
        a2a_client_factory=factory,
    )
    secretary_agent_tool = AgentTool(secretary_remote_agent)

    # Planner Agentのツールを再設定（上書きして競合を排除）
    print("  Configuring tools for planner_agent: [search_agent, secretary_agent]")
    planner_agent.tools = [search_agent_tool, secretary_agent_tool]
    
    # --------------------------------------------

    planner_agent_card_obj = await get_agent_card(planner_agent)
    
    planner_resource_name = get_agent_resource(planner_display_name)
    
    if not planner_resource_name:
        print(f"  Creating new agent engine for {planner_display_name} with extra_packages...")
        planner_a2a_agent_instance = A2aAgent(
            agent_card=planner_agent_card_obj,
            agent_executor_builder=get_agent_executor_class(planner_agent, None)
        )

        created_planner_engine = ReasoningEngine.create(
            planner_a2a_agent_instance,
            display_name=planner_display_name,
            requirements=requirements_list,
            extra_packages=["./travel_team", "./utils"],
        )
        
        print(f"  Created. Resource Name: {created_planner_engine.resource_name}")
        planner_resource_name = created_planner_engine.resource_name
    else:
        print(f"  Agent already exists: {planner_resource_name}")

    # Update (Self-referencing resource name fix)
    print(f"  Updating {planner_display_name} to inject resource name into session service...")
    planner_a2a_agent_for_update = A2aAgent(
        agent_card=planner_agent_card_obj, 
        agent_executor_builder=get_agent_executor_class(planner_agent, planner_resource_name) 
    )
    client.agent_engines.update(
        name=planner_resource_name,
        agent=planner_a2a_agent_for_update,
        config={
            'display_name': planner_display_name,
            'description': planner_agent_card_obj.description,
            'requirements': requirements_list,
            'http_options': {
                'base_url': f'https://{LOCATION}-aiplatform.googleapis.com',
                'api_version': 'v1beta1',
            },
            'staging_bucket': STAGING_BUCKET,
        },
    )
    print(f"  Update complete for {planner_display_name}.")

    print("\nAll travel agents deployed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
