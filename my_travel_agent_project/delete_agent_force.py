from google.cloud import aiplatform_v1beta1
import os
import time
import google.auth

# プロジェクトIDとロケーションは環境変数から取得、または直接指定
try:
    credentials, project_id = google.auth.default()
    print(f"Project ID: {project_id}")
except Exception as e:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "sts-osaka-si-learn-terasaka")
    print(f"Project ID from env: {project_id}")

location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
resource_id_to_delete = "759133614142128128" # エラーメッセージから取得したID

resource_name = f"projects/{project_id}/locations/{location}/reasoningEngines/{resource_id_to_delete}"

client = aiplatform_v1beta1.ReasoningEngineServiceClient(
    client_options={'api_endpoint': f'{location}-aiplatform.googleapis.com'}
)

print(f"Deleting ReasoningEngine: {resource_name} with force=True...")
try:
    # force=True を指定して強制削除
    operation = client.delete_reasoning_engine(name=resource_name, force=True)
    print("Deletion operation initiated. Waiting for completion...")
    
    # LROの完了を待つ
    operation.result() 
    print(f"ReasoningEngine {resource_name} deleted successfully.")
except Exception as e:
    print(f"Failed to delete ReasoningEngine {resource_name}: {e}")
