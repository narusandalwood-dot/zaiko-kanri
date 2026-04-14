import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os.path
import json

# --- 設定（ここを書き換えてください） ---
SPREADSHEET_ID = '1XWnNOEKv5VRhJXxxr923nqPrHlLsF-3lEDl0wYaZpC8'  # URLの d/ と /edit の間の文字列
RANGE_NAME = 'inventory!A:F'  # シート名が inventory の場合

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
def load_data():
    service = get_sheets_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    
    if not values:
        return pd.DataFrame()
    
    # 1行目をヘッダーとしてデータフレーム作成
    df = pd.DataFrame(values[1:], columns=values[0])
    # 数値を計算できるように変換
    df['現在の在庫数'] = pd.to_numeric(df['現在の在庫数'], errors='coerce').fillna(0)
    df['設定在庫数（最低数）'] = pd.to_numeric(df['設定在庫数（最低数）'], errors='coerce').fillna(0)
    return df

# --- 在庫を更新する関数 ---
def update_stock(row_index, new_stock):
    service = get_sheets_service()
    # スプレッドシートの行番号は「データフレームのインデックス + 2」 (ヘッダーがあるため)
    range_to_update = f'inventory!B{row_index + 2}' 
    body = {'values': [[int(new_stock)]]}
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=range_to_update,
        valueInputOption='RAW', body=body).execute()

# --- メイン画面 ---
st.title("🏠 ゆるり家・在庫管理システム")

df = load_data()

if df.empty:
    st.warning("スプレッドシートにデータがありません。")
else:
    # 1. 在庫アラート（設定在庫を下回っているもの）
    shortage_items = df[df['現在の在庫数'] < df['設定在庫数（最低数）']]
    if not shortage_items.empty:
        st.error("🚨 買い出しが必要なアイテムがあります！")
        st.dataframe(shortage_items[['商品名', '現在の在庫数', '設定在庫数（最低数）', '単位']])

    st.divider()

    # 2. 在庫一覧と操作
    st.header("📦 現在の在庫一覧")
    for index, row in df.iterrows():
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        
        with col1:
            st.write(f"**{row['商品名']}** ({row['現在の在庫数']}{row['単位']})")
        
        with col2:
            if st.button("＋", key=f"plus_{index}"):
                update_stock(index, row['現在の在庫数'] + 1)
                st.rerun()
        
        with col3:
            if st.button("ー", key=f"minus_{index}"):
                update_stock(index, max(0, row['現在の在庫数'] - 1))
                st.rerun()
        
        with col4:
            st.caption(f"目標: {row['設定在庫数（最低数）']}")