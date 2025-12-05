from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

# Import helpers from utils
from utils.a2a_helpers import (
    get_agent_resource,
    get_print_agent,
    create_a2a_factory
)

def create_root_agent(location="us-central1"):
    """
    Root Agentと、その配下のチーム(Sequential Agents)を作成して返します。
    デプロイ済みのリモートエージェントの情報を使用します。
    """
    
    # 1. Setup A2A Client Factory (Authentication)
    factory = create_a2a_factory()
    
    # 2. Define Remote Agents (Proxies)
    # Helper to create RemoteA2aAgent cleanly
    def create_remote_proxy(agent_name, display_name, description):
        resource_name = get_agent_resource(display_name)
        if not resource_name:
            print(f"Warning: Resource for {display_name} not found. Please deploy first.")
            return None 

        a2a_url = f'https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}/a2a'
        return RemoteA2aAgent(
            name=agent_name,
            description=description,
            agent_card=f'{a2a_url}/v1/card',
            a2a_client_factory=factory,
        )

    # Create the 4 proxies
    research_agent1_remoteA2a = create_remote_proxy(
        'research_agent1', 
        'research_agent1_a2a',
        '記事の執筆に必要な情報を収集してレポートにまとめるエージェント（テーマ選定）'
    )
    
    research_agent2_remoteA2a = create_remote_proxy(
        'research_agent2', 
        'research_agent2_a2a',
        '記事の執筆に必要な情報を収集してレポートにまとめるエージェント（レポート作成）'
    )
    
    writer_agent_remoteA2a = create_remote_proxy(
        'writer_agent', 
        'writer_agent_a2a',
        '特定のテーマに関する読み物記事を書くエージェント'
    )
    
    review_agent_remoteA2a = create_remote_proxy(
        'review_agent', 
        'review_agent_a2a',
        '読み物記事をレビューするエージェント'
    )

    # 3. Create Teams (Sequential Agents)
    
    # Research Team
    research_sub_agents = [
        get_print_agent('\n---\n## リサーチエージェントが調査レポートを作成します。\n---\n'),
        get_print_agent('\n## 調査対象のトピックを選定します。\n'),
        research_agent1_remoteA2a,
        get_print_agent('\n## 選定したトピックに基づいて、調査レポートを作成します。\n'),
        research_agent2_remoteA2a,
        get_print_agent('\n#### 調査レポートが準備できました。記事の作成に取り掛かってもよいでしょうか？\n'),
    ]
    # Filter out None if any agent failed to load (safety check)
    research_sub_agents = [a for a in research_sub_agents if a is not None]

    research_agent = SequentialAgent(
        name='research_agent',
        sub_agents=research_sub_agents,
        description='記事の執筆に必要な情報を収集してレポートにまとめるエージェント',
    )

    # Writing & Review Team
    writer_sub_agents = [
        get_print_agent('\n---\n## ライターエージェントが記事を執筆します。\n---\n'),
        writer_agent_remoteA2a,
        get_print_agent('\n---\n## レビューエージェントが記事をレビューします。\n---\n'),
        review_agent_remoteA2a,
       get_print_agent('\n#### レビューに基づいて記事の修正を依頼しますか？\n'),
    ]
    writer_sub_agents = [a for a in writer_sub_agents if a is not None]

    write_and_review_agent = SequentialAgent(
        name='write_and_review_agent',
        sub_agents=writer_sub_agents,
        description='記事を作成、レビューする。',
    )

    # 4. Create Root Agent
    instruction_root = '''
何ができるか聞かれた場合は、以下の処理をすることをわかりやすくフレンドリーな文章にまとめて返答してください。

- ユーザーが指定したテーマの記事を作成する業務フローを実行する。
- はじめに、テーマに関する調査レポートを作成する。
- その後、ライターエージェントとレビューエージェントが協力して、編集方針に則した記事を作成する。

ユーザーが記事のテーマを指定した場合は、次のフローを実行します。

1. そのテーマの記事の作成に取り掛かる旨を伝えて、research_agent に転送して、調査レポートを依頼します。
2. ユーザー記事の作成を支持したら、write_and_review_agent に転送して、記事の作成とレビューを依頼します。
3. ユーザーが記事の修正を希望する場合は、write_and_review_agent に転送します。

**条件**
research_agent のニックネームは、リサーチエージェント
write_and_review_agent のネックネームは、ライターエージェントとレビューエージェント
'''

    root_agent = LlmAgent(
        name='article_generation_flow',
        model='gemini-2.5-flash',
        instruction=instruction_root,
        sub_agents=[
            research_agent,
            write_and_review_agent,
        ],
        description='記事を作成する業務フローを実行するエージェント'
    )
    
    return root_agent