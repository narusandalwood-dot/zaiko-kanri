import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os.path
import json
from datetime import datetime

# --- 設定（ここを書き換えてください） ---
SPREADSHEET_ID = '1XWnNOEKv5VRhJXxxr923nqPrHlLsF-3lEDl0wYaZpC8'  # URLの d/ と /edit の間の文字列
RANGE_NAME = 'inventory!A:J'  # シート名が inventory の場合

# スコープの設定（スプレッドシートの読み書き権限）
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# --- Google Sheets APIへの接続関数 ---
def get_sheets_service():
    creds = None

# --- ネット公開（Streamlit Cloud）用の設定 ---
    if "google_auth" in st.secrets:
        # Streamlit Cloudの「金庫」から鍵を取り出す
        creds_info = json.loads(st.secrets["google_auth"])
        creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
    
    # --- ローカルPC用の設定 ---
    elif os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 2. 合鍵がない、または期限切れの場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # フォルダにある申請書 (credentials.json) を使って認証を開始
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # 3. token.jsonを保存（ローカル実行時のみ）
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('sheets', 'v4', credentials=creds)

# --- データの読み込み ---
def main():
    st.set_page_config(page_title="在庫管理ダッシュボード", layout="wide")
    service = get_sheets_service()
    sheet = service.spreadsheets()

    # データの読み込み
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])

    if not values:
        st.error("データが見つかりません。")
        return

    # DataFrameの作成
    df = pd.DataFrame(values[1:], columns=values[0])
    # 数値変換
    df['現在の在庫数'] = pd.to_numeric(df['現在の在庫数'], errors='coerce').fillna(0)
    df['設定在庫数（最低数）'] = pd.to_numeric(df['設定在庫数（最低数）'], errors='coerce').fillna(0)

    st.title("🛒 在庫管理ダッシュボード")

    # タブの作成
    t_buy, t_fav, t_all, t_place = st.tabs(["🛍️ 買い物", "⭐ お気に入り", "📦 すべて", "📍 場所別"])

    # --- 各タブの表示ロジック ---
    def display_list(target_df, title):
        st.subheader(title)
        for index, row in target_df.iterrows():
            # 在庫不足チェック
            is_low = row['現在の在庫数'] <= row['設定在庫数（最低数）']
            bg_color = "#ffe6e6" if is_low else "white"
            
            with st.container():
                st.markdown(f"""
                <div style="background-color:{bg_color}; padding:10px; border-radius:10px; border:1px solid #ddd; margin-bottom:10px;">
                    <h3 style="margin:0;">{row['商品名']} <small>({row['カテゴリ']})</small></h3>
                    <p style="margin:5px 0;">場所: {row['場所']} | 在庫: <b>{int(row['現在の在庫数'])}</b> {row['単位']} (最低: {int(row['設定在庫数（最低数）'])})</p>
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
                with c1:
                    if st.button("➕", key=f"plus_{index}"):
                        update_stock(service, index + 2, int(row['現在の在庫数']) + 1)
                with c2:
                    if st.button("➖", key=f"minus_{index}"):
                        update_stock(service, index + 2, max(0, int(row['現在の在庫数']) - 1))
                with c3:
                    # お気に入りボタン
                    is_fav = str(row['お気に入り']).upper() == 'TRUE'
                    fav_icon = "★" if is_fav else "☆"
                    if st.button(fav_icon, key=f"fav_{index}"):
                        update_fav(service, index + 2, not is_fav)
                with c4:
                    st.caption(f"更新: {row['最後に更新した人']}")

    # 各タブの中身
    with t_buy:
        buy_df = df[df['現在の在庫数'] <= df['設定在庫数（最低数）']]
        display_list(buy_df, "買い出しが必要なもの")

    with t_fav:
        fav_df = df[df['お気に入り'].astype(str).str.upper() == 'TRUE']
        display_list(fav_df, "お気に入りアイテム")

    with t_all:
        cat_choice = st.selectbox("カテゴリ絞り込み", ["すべて"] + list(df['カテゴリ'].unique()))
        all_df = df if cat_choice == "すべて" else df[df['カテゴリ'] == cat_choice]
        display_list(all_df, f"全在庫 ({cat_choice})")

    with t_place:
        place_choice = st.radio("場所を選択", ["A", "B", "C", "D", "E"], horizontal=True)
        place_df = df[df['場所'] == place_choice]
        display_list(place_df, f"場所 {place_choice} の在庫")

# 在庫更新関数（I列, J列も更新するように修正）
def update_stock(service, row_idx, new_val):
    user_name = "ゆるり" # ここをセレクトボックスなどで変えられるようにするとさらに便利
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    
    # B列(在庫), I列(更新者), J列(日時)を更新
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'inventory!B{row_idx}',
        valueInputOption='USER_ENTERED',
        body={'values': [[new_val]]}
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'inventory!I{row_idx}:J{row_idx}',
        valueInputOption='USER_ENTERED',
        body={'values': [[user_name, now]]}
    ).execute()
    st.rerun()

# お気に入り更新関数
def update_fav(service, row_idx, new_status):
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f'inventory!H{row_idx}',
        valueInputOption='USER_ENTERED',
        body={'values': [[str(new_status).upper()]]}
    ).execute()
    st.rerun()

if __name__ == "__main__":
    main()