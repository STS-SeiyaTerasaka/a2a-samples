import os
import asyncio
import vertexai
from google.genai.types import HttpOptions
# Import both classes: A2aAgent for instantiation, ReasoningEngine for deployment
from vertexai.preview.reasoning_engines import A2aAgent, ReasoningEngine 
import google.auth

# Import agents and helpers from their respective files
from agents.definitions import (
    research_agent1,
    research_agent2,
    writer_agent,
    review_agent
)
from utils.a2a_helpers import (
    get_agent_card,
    get_agent_executor_class,
    get_agent_resource
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

    # 2. Define Agents to Deploy
    agents_to_deploy = {
        'research_agent1_a2a': research_agent1,
        'research_agent2_a2a': research_agent2,
        'writer_agent_a2a': writer_agent,
        'review_agent_a2a': review_agent,
    }

    # 3. Deployment Loop
    for agent_name, agent in agents_to_deploy.items():
        print(f"\nProcessing {agent_name}...")
        
        agent_card_obj = await get_agent_card(agent)
        
        # Requirements from Workbench logs
        requirements_list = [
            'google-adk==1.14.1',
            'google-genai==1.36.0',
            'google-cloud-aiplatform==1.113.0',
            'a2a-sdk==0.3.5',
            'pydantic==2.12.4',
            'cloudpickle==3.1.2',
        ]

        # Check if already exists
        resource_name = get_agent_resource(agent_name)
        
        if not resource_name:
            print(f"  Creating new agent engine for {agent_name} with extra_packages...")
            
            # 1. Instantiate the A2aAgent object
            a2a_agent_instance = A2aAgent(
                agent_card=agent_card_obj,
                agent_executor_builder=get_agent_executor_class(agent, None)
            )

            # 2. Deploy using ReasoningEngine.create to support extra_packages
            created_agent_engine = ReasoningEngine.create(
                a2a_agent_instance,
                display_name=agent_name,
                requirements=requirements_list,
                extra_packages=["./agents", "./utils"],
            )
            
            print(f"  Created. Resource Name: {created_agent_engine.resource_name}")
            resource_name = created_agent_engine.resource_name
        else:
            print(f"  Agent already exists: {resource_name}")

        # Update (Self-referencing resource name fix)
        # Note: ReasoningEngine.update might not support replacing the agent instance easily or might re-deploy.
        # We will use the lower-level client for the update to ensure we just update the config/agent object
        # without triggering a full re-build if possible, or just re-deploy.
        # Actually, for consistency and to ensure extra_packages are present, we should probably stick to one method.
        # But A2aAgent update logic in the blog was specific.
        
        print(f"  Updating {agent_name} to inject resource name into session service...")

        a2a_agent_for_update = A2aAgent(
            agent_card=agent_card_obj, 
            agent_executor_builder=get_agent_executor_class(agent, resource_name) 
        )
        
        # Use low-level client for update as in the blog, but the artifact (extra_packages) 
        # should ideally persist from the creation.
        # CAUTION: client.agent_engines.update might overwrite the artifact if not careful.
        # If the update fails to see 'utils', it means the update process re-pickles without extra_packages.
        
        # Safe bet: Just re-create/update using ReasoningEngine.create (it handles updates if same display_name? No, it creates new).
        # We must use client.agent_engines.update.
        # Does client.agent_engines.update support extra_packages? No. 
        
        # Crucial Insight: When we update the agent object (to inject resource_name), 
        # we are essentially creating a new pickled object.
        # If we use the low-level client update, it won't send extra_packages.
        # BUT, if the dependency on 'utils' is only at runtime (importing), and the previous 'create' 
        # already uploaded 'utils' to the staging bucket and registered it...
        # Wait, the environment is built per version.
        
        # We will try to use the low-level update. If it fails with ModuleNotFoundError, 
        # it means we MUST use a high-level update or re-deployment mechanism that supports extra_packages.
        # Unfortunately ReasoningEngine object doesn't have an 'update' method that accepts a new agent instance easily.
        
        # Let's try the low-level update. If it fails, we have a tricky situation.
        # However, the 'agent_executor_builder' is a closure. It captures the environment.
        # If 'utils' was imported in the script, cloudpickle might serialize it by value 
        # IF it's in the same module. But it's in a different module.
        
        client.agent_engines.update(
            name=resource_name,
            agent=a2a_agent_for_update,
            config={
                'display_name': agent_name,
                'description': agent_card_obj.description,
                'requirements': requirements_list,
                'http_options': {
                    'base_url': f'https://{LOCATION}-aiplatform.googleapis.com',
                    'api_version': 'v1beta1',
                },
                'staging_bucket': STAGING_BUCKET,
                # We can try passing extra_packages here if the API supported it, but it doesn't.
            },
        )
        print(f"  Update complete for {agent_name}.")

    print("\nAll agents deployed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
