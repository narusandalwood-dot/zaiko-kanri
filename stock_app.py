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

# ==========================================
# 2. 【表示の職人】リストを画面に描く関数
# ==========================================
# target_df: 表示したいデータ, title: 見出しの名前, prefix: ボタンの重複防止用, service: 通信用
def display_list(target_df, title, prefix, service):
    st.subheader(title)
    if target_df.empty:
        st.write("対象となる商品はありません。")
        return

    # 見出し（スマホで見やすくするため薄い文字で表示）
    c1, c2 = st.columns([3, 2])
    with c1: st.caption("商品名 / 在庫状況")
    with c2: st.caption("操作ボタン")

    # 1件ずつループして表示
    for index, row in target_df.iterrows():
        cur = int(row['現在の在庫数'])
        limit = int(row['設定在庫数（最低数）'])
        is_low = cur < limit  # 在庫が最低数を下回っているかチェック
        
        # 在庫不足なら文字を赤くする設定
        color = "#FF4B4B" if is_low else "#31333F"
        
        # 画面の左側（情報）と右側（ボタン）を分ける
        col_info, col_btn = st.columns([3, 2])
        
        with col_info:
            # 商品名と「現在数/最低数」を表示（Markdownで色付け）
            st.markdown(f"**{row['商品名']}** <br> <span style='color:{color}; font-size:1.2em;'>{cur}</span>/{limit} <small>{row['単位']}</small>", unsafe_allow_html=True)
        
        with col_btn:
            # ボタンを横に3つ並べる（プラス、マイナス、お気に入り）
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("＋", key=f"plus_{prefix}_{index}"):
                    update_stock(service, index + 2, cur + 1)
            with b2:
                if st.button("ー", key=f"minus_{prefix}_{index}"):
                    update_stock(service, index + 2, max(0, cur - 1))
            with b3:
                # お気に入り状態（TRUE/FALSE）を判定してアイコンを変える
                is_fav = str(row['お気に入り']).upper() == 'TRUE'
                if st.button("★" if is_fav else "☆", key=f"fav_{prefix}_{index}"):
                    update_fav(service, index + 2, not is_fav)
        
        st.divider()  # 区切り線

# ==========================================
# 3. 【司令塔】メインの処理
# ==========================================
def main():
    st.set_page_config(page_title="在庫管理", layout="wide")
    service = get_sheets_service()
    
    # --- スプレッドシートからデータを取ってくる ---
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    if not values:
        st.error("データが見つかりません。")
        return

    # データを扱いやすい表形式(DataFrame)に変換
    df = pd.DataFrame(values[1:], columns=values[0])
    df['現在の在庫数'] = pd.to_numeric(df['現在の在庫数'], errors='coerce').fillna(0)
    df['設定在庫数（最低数）'] = pd.to_numeric(df['設定在庫数（最低数）'], errors='coerce').fillna(0)

    st.title("🛒 在庫管理アプリ")

    # --- 画面上部にタブ（切り替えボタン）を作成 ---
    t_buy, t_fav, t_all, t_place = st.tabs(["🛍️ 買い物", "⭐ お気に入り", "📦 すべて", "📍 場所別"])

    # 1. 買い物タブ：在庫が足りないものだけ抽出して表示
    with t_buy:
        buy_df = df[df['現在の在庫数'].astype(int) < df['設定在庫数（最低数）'].astype(int)]
        display_list(buy_df, "買い出しが必要なもの", "buy", service)

    # 2. お気に入りタブ：H列がTRUEのものだけ抽出して表示
    with t_fav:
        fav_df = df[df['お気に入り'].astype(str).str.upper() == 'TRUE']
        display_list(fav_df, "お気に入りアイテム", "fav", service)

    # 3. すべてタブ：全件表示（カテゴリで絞り込み可能）
    with t_all:
        cats = ["すべて"] + sorted(df['カテゴリ'].unique().tolist())
        cat_choice = st.selectbox("カテゴリを選択", cats)
        all_df = df if cat_choice == "すべて" else df[df['カテゴリ'] == cat_choice]
        display_list(all_df, f"全在庫 ({cat_choice})", "all", service)

    # 4. 場所別タブ：場所（A, B, C...）で選んで表示
    with t_place:
        places = sorted(df['場所'].unique().tolist())
        place_choice = st.radio("場所を選択", places, horizontal=True)
        place_df = df[df['場所'] == place_choice]
        display_list(place_df, f"場所 {place_choice} の在庫", "place", service)

# ==========================================
# 4. 【書き換えのプロ】スプレッドシートを更新する関数
# ==========================================
def update_stock(service, row_idx, new_val):
    user_name = "ゆるり"  # 更新した人の名前
    now = datetime.now().strftime("%Y/%m/%d %H:%M")  # 現在時刻
    
    # B列（在庫数）を書き換える
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!B{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[new_val]]}
    ).execute()
    # I列（更新者）とJ列（日時）を書き換える
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!I{row_idx}:J{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[user_name, now]]}
    ).execute()
    st.rerun()  # 画面をリフレッシュ

def update_fav(service, row_idx, new_status):
    # H列（お気に入り）の状態を書き換える
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!H{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[str(new_status).upper()]]}
    ).execute()
    st.rerun()

# --- プログラムのスタート地点 ---
if __name__ == "__main__":
    main()