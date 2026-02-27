import os
import asyncio
import vertexai
from google.genai.types import HttpOptions
from vertexai.preview.reasoning_engines import A2aAgent, ReasoningEngine 
import google.auth

# Import agents
from travel_team.agents.secretary_agent import secretary_agent
from travel_team.agents.planner_agent import planner_agent

from utils.a2a_helpers import (
    get_agent_card,
    get_agent_executor_class,
    get_agent_resource,
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
    
    client = vertexai.Client(
        project=project_id,
        location=LOCATION,
        http_options=HttpOptions(
            api_version='v1beta1', base_url=f'https://{LOCATION}-aiplatform.googleapis.com/'
        ),
    )

    # Requirements
    requirements_list = [
        'google-adk>=1.14.1',
        'google-genai>=1.36.0',
        'google-cloud-aiplatform==1.123.0',
        'a2a-sdk==0.3.10',
        'pydantic==2.11.10',
        'cloudpickle==3.1.1',
    ]

    # ==================================================================
    # STEP 1: Deploy Secretary Agent (Worker)
    # ==================================================================
    secretary_display_name = 'secretary_agent'
    print(f"\nProcessing {secretary_display_name}...")
    
    secretary_agent_card_obj = await get_agent_card(secretary_agent)
    secretary_resource_name = get_agent_resource(secretary_display_name)
    print(f"  Skipping deployment for existing agent: {secretary_resource_name}")
    
    # if not secretary_resource_name:
    #     print(f"  Creating new agent engine for {secretary_display_name} with extra_packages...")
    #     secretary_a2a_agent_instance = A2aAgent(
    #         agent_card=secretary_agent_card_obj,
    #         agent_executor_builder=get_agent_executor_class(secretary_agent, None)
    #     )

    #     created_secretary_engine = ReasoningEngine.create(
    #         secretary_a2a_agent_instance,
    #         display_name=secretary_display_name,
    #         requirements=requirements_list,
    #         extra_packages=["./travel_team", "./utils"],
    #     )
        
    #     print(f"  Created. Resource Name: {created_secretary_engine.resource_name}")
    #     secretary_resource_name = created_secretary_engine.resource_name
    # else:
    #     print(f"  Agent already exists: {secretary_resource_name}")

    # # Update
    # print(f"  Updating {secretary_display_name}...")
    # secretary_a2a_agent_for_update = A2aAgent(
    #     agent_card=secretary_agent_card_obj, 
    #     agent_executor_builder=get_agent_executor_class(secretary_agent, secretary_resource_name) 
    # )
    # client.agent_engines.update(
    #     name=secretary_resource_name,
    #     agent=secretary_a2a_agent_for_update,
    #     config={
    #         'display_name': secretary_display_name,
    #         'description': secretary_agent_card_obj.description,
    #         'requirements': requirements_list,
    #         'http_options': {
    #             'base_url': f'https://{LOCATION}-aiplatform.googleapis.com',
    #             'api_version': 'v1beta1',
    #         },
    #         'staging_bucket': STAGING_BUCKET,
    #     },
    # )
    # print(f"  Update complete for {secretary_display_name}.")

    # ==================================================================
    # STEP 2: Deploy Planner Agent (Orchestrator)
    # ==================================================================
    planner_display_name = 'planner_agent'
    print(f"\nProcessing {planner_display_name}...")

    # Planner Agentに環境変数としてSecretaryのリソース名を渡す
    # (planner_agent.pyがこれを読み取って接続先を決定する)
    # 注意: Agent Engineのcreate/update時に環境変数を直接渡すAPIは標準ではない場合があるが、
    # ADK/Reasoning Engineでは通常コンテナの環境変数はビルド時に埋め込むか、実行時に渡す。
    # ここでは、planner_agent.pyが実行される環境（Cloud Run）に環境変数が設定されている必要がある。
    # 
    # もし environment_variables がサポートされていない場合、
    # planner_agent.py の import 時に os.environ['SECRETARY_RESOURCE_NAME'] = ... とする必要がある。
    # 
    # ここでは、デプロイ直前にローカル環境変数をセットしても、リモート実行環境には反映されない。
    # そのため、planner_agent.py 内のロジックが「デプロイ時の環境変数をキャプチャする」仕組みになっていない限り、
    # 環境変数を渡すのは難しい。
    #
    # 代替案: planner_agent.py の中の secretary_resource_name を書き換えるか、
    # あるいは、planner_agent.py を動的に生成する？
    # 
    # いや、my_a2a_project ではどうしていたか？ -> デプロイ時に接続済みだった。
    #
    # 解決策: `os.environ` をセットしてから `get_agent_card` や `A2aAgent` を作成するが、
    # 実際にクラウドで動くのは `planner_agent.py` というファイルそのもの。
    # したがって、クラウド上で `os.environ` がセットされている必要がある。
    # 
    # Vertex AI Reasoning Engine は Cloud Run 上で動くので、環境変数を設定できるはずだが、
    # SDK (ReasoningEngine.create) にその引数が見当たらない。
    #
    # 苦肉の策だが、planner_agent.py が読み込まれる前に環境変数を注入するラッパーを作るか、
    # 今回はデプロイスクリプト内で `planner_agent` オブジェクトの属性としてセットし、
    # それが pickle されることを期待するか...
    #
    # しかし、AgentTool内のRemoteA2aAgentは既に初期化されてしまっている（import時に）。
    # planner_agent.py のトップレベルで初期化しているため。
    #
    # 待てよ、planner_agent.py で `os.environ.get` している。
    # デプロイ時にローカルで `os.environ` をセットしてから `reload(planner_agent_module)` すれば、
    # メモリ上の `planner_agent` は Secretary のリソース名を持った状態で初期化される。
    # これを pickle してアップロードすれば、クラウド上でもその状態（SecretaryのURLを持った状態）で復元されるはず！
    # 
    # つまり、ローカルで環境変数をセット -> モジュールをリロード（または import） -> エージェントオブジェクト生成
    # -> pickle -> アップロード。これでいける！

    # Secretaryのリソース名を環境変数にセット
    os.environ['SECRETARY_RESOURCE_NAME'] = secretary_resource_name
    
    # planner_agent モジュールをリロードして、環境変数を反映させる
    import importlib
    import travel_team.agents.planner_agent
    importlib.reload(travel_team.agents.planner_agent)
    from travel_team.agents.planner_agent import planner_agent # リロードされたオブジェクトを取得

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

    # Update
    print(f"  Updating {planner_display_name}...")
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
    print("\n--- Planner Agent A2A Address ---")
    print(f"Planner Agent Resource Name: {planner_resource_name}")
    print(f"Planner Agent A2A Card URL: https://{LOCATION}-aiplatform.googleapis.com/v1beta1/{planner_resource_name}/a2a/v1/card")
    print("-----------------------------------")

if __name__ == "__main__":
    asyncio.run(main())
