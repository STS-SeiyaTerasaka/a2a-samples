from typing import Dict, Any, Tuple
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.models import LlmResponse, LlmRequest
from google.genai.types import Part, Content
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from crewai_adk_wrapper import CrewAIAdkWrapper

# ==========================================
# ユーザー設定: エージェント定義ファイル
# このファイルを編集して、デプロイしたいエージェントを定義してください。
# ==========================================

# 共通で使用するライブラリ要件
# 必要に応じて追加してください
COMMON_REQUIREMENTS = [
    'google-adk==1.14.1',
    'google-genai==1.36.0',
    'google-cloud-aiplatform==1.113.0',
    'a2a-sdk==0.3.5',
    'crewai==0.35.0', # CrewAIを追加
    'Pillow==10.3.0', # 画像処理ライブラリ
    'python-dotenv==1.0.1', # 環境変数管理
    'google-generativeai==0.8.0' # google.genaiクライアント
]

def define_leaf_agents() -> Dict[str, Any]:
    """
    A2Aの末端(Leaf)となるエージェント群を定義して辞書で返してください。
    
    Returns:
        Dict[str, Agent]: { "Agent Engineでの表示名": エージェントインスタンス }
    """
    
    # --- 定義例 ---
    
    instruction_research1 = '''
あなたの役割は、記事の執筆に必要な情報を収集して調査レポートにまとめる事です。
指定されたテーマの記事を執筆する際に参考となるトピックを５項目程度のリストにまとめます。
後段のエージェントがこのリストに基づいて、調査レポートを作成します。
* 出力形式: 日本語で出力。
'''
    r1 = LlmAgent(
        name='research_agent1',
        model='gemini-2.5-flash',
        description='記事の執筆に必要な情報を収集してレポートにまとめるエージェント（テーマ選定）',
        instruction=instruction_research1,
    )

    instruction_research2 = '''
あなたの役割は、記事の執筆に必要な情報を収集して調査レポートにまとめる事です。
前段のエージェントは、５項目程度の調査対象トピックを指定します。
* 出力形式: 日本語で出力。調査レポートは、トピックごとに客観的情報をまとめます。
'''
    r2 = LlmAgent(
        name='research_agent2',
        model='gemini-2.5-flash',
        description='記事の執筆に必要な情報を収集してレポートにまとめるエージェント（レポート作成）',
        instruction=instruction_research2,
    )

    instruction_writer = '''
あなたの役割は、特定のテーマに関する気軽な読み物記事を書くことです。
記事の「テーマ」と、その内容に関連する「調査レポート」が与えられるので、
調査レポートに記載の客観的事実に基づいて、信頼性のある読み物記事を書いてください。
'''
    w1 = LlmAgent(
        name='writer_agent',
        model='gemini-2.5-flash',
        description='特定のテーマに関する読み物記事を書くエージェント',
        instruction=instruction_writer,
    )

    instruction_review = '''
あなたの役割は、読み物記事をレビューして、記事の条件にあった内容にするための改善コメントを与える事です。
* 出力形式: 日本語で出力。はじめに記事の良い点、次に修正ポイントを箇条書き。
'''
    rev1 = LlmAgent(
        name='review_agent',
        model='gemini-2.5-flash',
        description='読み物記事をレビューするエージェント',
        instruction=instruction_review,
    )

    # 辞書のキーがAgent Engine上の表示名になります
    agents = {
        'research_agent1_a2a': r1,
        'research_agent2_a2a': r2,
        'writer_agent_a2a': w1,
        'review_agent_a2a': rev1,
    }

    # CrewAI Image Generation Agentを追加
    crewai_image_agent = CrewAIAdkWrapper(
        name='image_generation_crewai_agent',
        description='''CrewAIを使った画像生成エージェント。
                     プロンプトに応じて画像を生成または編集できます。''',
    )
    agents['image_generation_crewai_a2a'] = crewai_image_agent

    return agents

def define_root_agent(remote_agents: Dict[str, RemoteA2aAgent]) -> Tuple[Any, str]:
    """
    デプロイ済みのリモートエージェント(ラッパー)を受け取り、Rootエージェントを構築して返してください。
    
    Args:
        remote_agents: define_leaf_agentsで定義したキーに対応するRemoteA2aAgentが入った辞書。
                       例: remote_agents['research_agent1_a2a'] でアクセス可能。
    
    Returns:
        tuple: (Rootエージェントのインスタンス, Rootエージェントの表示名)
    """

    # ヘルパー: メッセージを表示するだけのエージェント
    def get_print_agent(text):
        def before_model_callback(ctx, req):
            return LlmResponse(content=Content(role='model', parts=[Part(text=text)]))
        return LlmAgent(name='print_agent', model='gemini-2.0-flash', description='', instruction='', before_model_callback=before_model_callback)

    # --- Root Agent 組み立て例 ---

    # ラッパーの取得
    r1 = remote_agents['research_agent1_a2a']
    r2 = remote_agents['research_agent2_a2a']
    w1 = remote_agents['writer_agent_a2a']
    rev1 = remote_agents['review_agent_a2a']

    # Sequential Agents (フロー定義)
    research_flow = SequentialAgent(
        name='research_agent',
        sub_agents=[
            get_print_agent('\n---\n## リサーチエージェントが調査レポートを作成します。\n---\n'),
            get_print_agent('\n## 調査対象のトピックを選定します。\n'),
            r1,
            get_print_agent('\n## 選定したトピックに基づいて、調査レポートを作成します。\n'),
            r2,
            get_print_agent('\n#### 調査レポートが準備できました。記事の作成に取り掛かってもよいでしょうか？\n'),
        ],
        description='記事の執筆に必要な情報を収集してレポートにまとめるエージェント',
    )

    writer_flow = SequentialAgent(
        name='write_and_review_agent',
        sub_agents=[
            get_print_agent('\n---\n## ライターエージェントが記事を執筆します。\n---\n'),
            w1,
            get_print_agent('\n---\n## レビューエージェントが記事をレビューします。\n---\n'),
            rev1,
            get_print_agent('\n#### レビューに基づいて記事の修正を依頼しますか？\n'),
        ],
        description='記事を作成、レビューする。',
    )

    # Root Agent 本体
    root_agent = LlmAgent(
        name='article_generation_flow',
        model='gemini-2.0-flash',
        instruction='''
何ができるか聞かれた場合は、以下の処理をすることをわかりやすくフレンドリーな文章にまとめて返答してください。
- ユーザーが指定したテーマの記事を作成する業務フローを実行する。
ユーザーが記事のテーマを指定した場合は、次のフローを実行します。
1. research_agent に転送して、調査レポートを依頼します。
2. write_and_review_agent に転送して、記事の作成とレビューを依頼します。
3. ユーザーが記事の修正を希望する場合は、write_and_review_agent に転送します。
''',
        sub_agents=[
            research_flow,
            writer_flow,
        ],
        description='記事を作成する業務フローを実行するエージェント'
    )

    return root_agent, 'article_generation_flow_agent'
