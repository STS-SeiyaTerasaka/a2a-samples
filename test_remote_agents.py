import asyncio
import os
from dotenv import load_dotenv
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.genai.types import Part, Content
from utils.a2a_helpers import create_a2a_factory

# 環境変数の読み込み
load_dotenv()

# ==========================================
# 設定: ここにテストしたいエージェントのCard URLを設定してください
# ==========================================
# 例: https://us-central1-aiplatform.../a2a/v1/card

# 1. Secretary Agent (Worker) のURL
SECRETARY_URL = "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/1060275483775/locations/us-central1/reasoningEngines/1855443464058044416/a2a/v1/card"

# 2. Planner Agent (Orchestrator) のURL
PLANNER_URL = "https://us-central1-aiplatform.googleapis.com/v1beta1/projects/1060275483775/locations/us-central1/reasoningEngines/7809202171441840128/a2a/v1/card"
# ==========================================

async def test_agent(agent_name, agent_url, message_text):
    print(f"\n--- Testing {agent_name} ---")
    print(f"URL: {agent_url}")
    print(f"Message: {message_text}")
    
    if not agent_url or "projects/..." in agent_url: # プレースホルダーチェック
        print("Error: URLが正しく設定されていません。")
        return

    try:
        factory = create_a2a_factory()
        # 通信タイムアウトを延長したFactoryを使うため、ここでは明示的にタイムアウト設定済みのFactoryが返ってくるはず
        
        agent = RemoteA2aAgent(
            name=agent_name,
            description="Test Agent",
            agent_card=agent_url,
            a2a_client_factory=factory
        )

        print("Sending message...")
        response_events = agent.send_message(
            Content(role='user', parts=[Part(text=message_text)])
        )
        
        print("Response:")
        async for event in response_events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    print(part.text, end="")
        print("\n[Done]")

    except Exception as e:
        print(f"\nError occurred: {e}")
        import traceback
        traceback.print_exc()

async def main():
    # Test 1: Secretary Agent (Worker) - Direct check
    # シンプルな機能確認
    # await test_agent("Secretary Agent", SECRETARY_URL, "カレンダー登録リンクを作成して。タイトル: テスト会議, 日時: 2025-12-25T10:00:00")

    # Test 2: Planner Agent - Hello check
    # 挨拶だけでエラーが出ないか確認
    await test_agent("Planner Agent (Hello)", PLANNER_URL, "こんにちは")

    # Test 3: Planner Agent - Calendar check
    # 検索を使わずにカレンダー登録を依頼
    await test_agent("Planner Agent (Calendar)", PLANNER_URL, "検索は不要です。明日の10時に会議という予定でカレンダー登録リンクを作ってください")

if __name__ == "__main__":
    asyncio.run(main())
