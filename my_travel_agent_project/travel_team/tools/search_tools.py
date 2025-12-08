# travel_team/tools/search_tools.py
from google.adk.tools import google_search

# ADKのGoogleSearchGroundingツールをそのまま使用
# これを使う場合、追加のAPIキーやCSE ID設定は不要です。
# Vertex AIの機能としてGoogle検索が行われます。
search_tool = google_search