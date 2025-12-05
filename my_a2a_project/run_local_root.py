import asyncio
import os
import vertexai
from agents.root_agent_def import create_root_agent
from utils.local_app import LocalApp
import google.auth

async def main():
    print("Initializing...")
    
    # 1. Setup Project (needed for vertexai.init inside helpers/root def if called)
    try:
        credentials, project_id = google.auth.default()
    except:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        
    if project_id:
        # We initialize here to ensure get_agent_resource works
        vertexai.init(project=project_id, location='us-central1')
        
        # 明示的に環境変数を設定して、ADK/GenAIライブラリにVertex AIの使用を強制します
        os.environ['GOOGLE_CLOUD_PROJECT'] = project_id
        os.environ['GOOGLE_CLOUD_LOCATION'] = 'us-central1'
        os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'True'
    else:
        print("Warning: Could not determine Project ID. Remote agent lookup might fail.")

    # 2. Create the Root Agent
    # This will look up the deployed agents in the cloud
    print("Building Root Agent and connecting to remote agents...")
    try:
        root_agent = create_root_agent(location='us-central1')
    except Exception as e:
        print(f"Error creating root agent: {e}")
        return

    # 3. Start the App
    app = LocalApp(root_agent)
    
    print("\n" + "="*50)
    print("Chat started! (Type 'quit' or 'exit' to stop)")
    print("="*50 + "\n")
    
    # Initial greeting trigger (optional, or just wait for user)
    # await app.stream("こんにちは") 

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ['quit', 'exit']:
                break
            if not user_input.strip():
                continue
                
            print("Agent is thinking...")
            await app.stream(user_input)
            print("-" * 30)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
