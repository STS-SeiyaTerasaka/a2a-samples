import urllib.parse
from datetime import datetime

def create_google_calendar_link(
    title: str,
    start_datetime: str, # ISOフォーマット 'YYYY-MM-DDTHH:MM:SS'
    end_datetime: str,   # ISOフォーマット 'YYYY-MM-DDTHH:MM:SS'
    location: str = "",
    details: str = ""
) -> str:
    """
    Googleカレンダーにイベントを追加するためのURLを生成します。

    Args:
        title: イベントのタイトル。
        start_datetime: イベントの開始日時 (ISOフォーマット例: '2025-12-25T09:00:00')。
        end_datetime: イベントの終了日時 (ISOフォーマット例: '2025-12-25T10:00:00')。
        location: イベントの場所 (任意)。
        details: イベントの詳細説明 (任意)。

    Returns:
        Googleカレンダーのイベント作成ページへ遷移するURL。
    """
    base_url = "https://www.google.com/calendar/render"
    
    # Google Calendar APIのイベント日時フォーマットは 'YYYYMMDDTHHMMSS' または 'YYYYMMDDTHHMMSSZ' (UTC)
    # ここでは簡易的にISOフォーマットからタイムゾーンなしの形式に変換
    try:
        start_dt = datetime.fromisoformat(start_datetime)
        end_dt = datetime.fromisoformat(end_datetime)
        formatted_start = start_dt.strftime('%Y%m%dT%H%M%S')
        formatted_end = end_dt.strftime('%Y%m%dT%H%M%S')
    except ValueError:
        # ISOフォーマットでない場合はエラーとして、簡易的な日付のみの形式で再試行
        # またはエラーをraiseする
        print(f"Warning: Invalid datetime format. Using simple date format. Start: {start_datetime}, End: {end_datetime}")
        formatted_start = start_datetime.split('T')[0].replace('-','') # YYYYMMDD
        formatted_end = end_datetime.split('T')[0].replace('-','')     # YYYYMMDD

    params = {
        'action': 'TEMPLATE',
        'text': title,
        'dates': f'{formatted_start}/{formatted_end}',
        'details': details,
        'location': location,
        'sf': 'true',
        'output': 'xml',
    }
    
    encoded_params = urllib.parse.urlencode(params)
    return f"{base_url}?{encoded_params}"

# テスト用
if __name__ == "__main__":
    print("--- Test 1: Full Datetime ---")
    link1 = create_google_calendar_link(
        title="デモ旅行プラン",
        start_datetime="2025-12-25T09:00:00",
        end_datetime="2025-12-25T17:00:00",
        location="箱根",
        details="美術館巡り"
    )
    print(link1)

    print("\n--- Test 2: Date Only (Implicit) ---")
    link2 = create_google_calendar_link(
        title="日帰り旅行",
        start_datetime="2025-12-30", # 日付のみ
        end_datetime="2025-12-30",   # 日付のみ
        location="鎌倉",
        details="散策とカフェ巡り"
    )
    print(link2)

    print("\n--- Test 3: Invalid Datetime Format ---")
    link3 = create_google_calendar_link(
        title="エラーテスト",
        start_datetime="不正な日付",
        end_datetime="2025-01-01T12:00:00",
        location="不明"
    )
    print(link3)
