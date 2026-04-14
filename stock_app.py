import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os.path
import json
from datetime import datetime, date , timedelta # timedelta  dateを追加（期限切れ用）


# --- 設定（ここを書き換えてください） ---
SPREADSHEET_ID = '1XWnNOEKv5VRhJXxxr923nqPrHlLsF-3lEDl0wYaZpC8'  # URLの d/ と /edit の間の文字列
RANGE_NAME = 'inventory!A:L'  # シート名が inventory の場合

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

    # リストの区切り線
    st.divider()

    for index, row in target_df.iterrows():
        cur = int(row['現在の在庫数'])
        limit = int(row['設定在庫数（最低数）'])
        is_low = cur < limit

        # --- 期限の判定（ここを追加！） ---
        is_expired = False
        expiry_str = str(row['消費期限']) if row['消費期限'] else ""
        
        # 「空っぽ」「0」「None」「nan」などは無視する
        invalid_values = ["", "0","0.0", "None", "nan", "未設定"]

        if expiry_str not in invalid_values:
            try:
                # 文字列を日付データに変換
                expiry_date = datetime.strptime(expiry_str, '%Y/%m/%d').date()
                # 今日より前なら「期限切れ」とみなす
                if expiry_date < date.today():
                    is_expired = True
            except ValueError:
                pass # 日付の形式が違う場合は無視する
            
        # --- 買い物リストに出す条件の変更 ---
        # 「在庫不足」または「期限切れ」なら警告を出す
        should_alert = is_low or is_expired
        
        # アイコンの優先順位：期限切れ(🚨) > 在庫不足(⚠️)
        if is_expired:
            alert_icon = "🚨"
        elif is_low:
            alert_icon = "⚠️"
        else:
            alert_icon = ""

        # 全体のメイン色（商品名や在庫数に使う）
        text_color = "#FF4B4B" if should_alert else "#31333F"
        
        # 期限行だけの色（期限切れなら赤、それ以外は控えめなグレー）
        expiry_color = "#FF4B4B" if is_expired else "#666666"

        # 4. 表示部分
        item_code = row['商品コード'] if row['商品コード'] else "---"
       

# 画面を左右に分ける箱を準備します
        col_info, col_btn = st.columns([3, 2])
        
        with col_info:
            # 商品名と「現在数/最低数」を表示（Markdownで色付け）
            st.caption(f"ID: {item_code}") # ここに商品コードを表示
            st.markdown(f"**{row['商品名']}** <br> <span style='color:{text_color}; font-size:1.2em;'>{cur}</span>/{limit} <small>{row['単位']}</small>", unsafe_allow_html=True)
            # 期限表示（切れていたら「期限切れ！」と表示）
            
            if expiry_str in invalid_values:
                expiry_display = "📅 期限: 未設定"
            elif is_expired:
                expiry_display = f"🚨 **期限切れ！ ({expiry_str})**"
            else:
                expiry_display = f"📅 期限: {expiry_str}"
            
            # 期限表示（ここは expiry_color を使うので、空白なら赤くならない）
            st.markdown(f"<span style='color:{expiry_color};'>{expiry_display}</span>", unsafe_allow_html=True)
        with col_btn:




            # ボタンを横に3つ並べる（プラス、マイナス、お気に入り）
            b1, b2, b3 = st.columns(3)
            with b1:

                # 期限リセット用追加
                cycle = row['サイクル'] if 'サイクル' in row and row['サイクル'] else 0
                try:
                    # 数字として扱えるように変換
                    cycle_days = int(float(cycle))
                except:
                    cycle_days = 0


                if st.button("＋", key=f"plus_{prefix}_{index}"):
                    update_stock(service, index + 2, cur + 1, cycle_days)
            with b2:
                if st.button("ー", key=f"minus_{prefix}_{index}"):
                    update_stock(service, index + 2, max(0, cur - 1))
            with b3:
                # お気に入り状態（TRUE/FALSE）を判定してアイコンを変える
                is_fav = str(row['お気に入り']).upper() == 'TRUE'
                if st.button("★" if is_fav else "☆", key=f"fav_{prefix}_{index}"):
                    update_fav(service, index + 2, not is_fav)
        
# 項目ごとに線を引く
        st.divider()

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
    t_buy, t_fav, t_all, t_place, t_add = st.tabs(["🛍️ 買い物", "⭐ お気に入り", "📦 すべて", "📍 場所別", "➕ 品物追加"])

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

     # 5. 品物追加タブ
    with t_add:
        st.subheader("新しい品物を登録する")
        with st.form("add_form", clear_on_submit=True):
            new_code = st.text_input("商品コード（管理番号）") # H列用
            new_name = st.text_input("商品名（必須）")
            new_cat = st.selectbox("カテゴリ", ["日用品", "食料品", "掃除用品", "その他"]) # 選択肢は自由に変えてください
            new_place = st.text_input("保管場所（A, Bなど）")
            new_cur = st.number_input("現在の在庫数", min_value=0, value=0)
            new_limit = st.number_input("最低在庫数", min_value=0, value=1)
            new_unit = st.text_input("単位（個、パックなど）", value="個")
            new_cycle = st.number_input("交換サイクル（何日で切れるか：数字のみ）", min_value=0, value=30)
            submit = st.form_submit_button("登録する")
            
            if submit:
                if new_name:

                    # 登録時の期限を「今日+サイクル」で計算
                    calc_expiry = (datetime.now() + timedelta(days=new_cycle)).strftime('%Y/%m/%d') if new_cycle > 0 else "未設定"


                    # スプレッドシートへ書き込む関数を呼び出す
                    add_new_item(service, [
                    new_name, new_cur, new_limit, new_unit, 
                    new_cat, new_place, calc_expiry, new_code, new_cycle
                ])
                    
                    st.success(f"「{new_name}」を登録しました！")
                    st.rerun()
                else:
                    st.error("商品名は必ず入力してください。")   

# ==========================================
# 4. 【書き換えのプロ】スプレッドシートを更新する関数
# ==========================================
def update_stock(service, row_idx, new_val, cycle_days=0):
    user_name = "ゆるり"
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y/%m/%d %H:%M")
    
    # 1. 在庫数(B列)の更新
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!B{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[new_val]]}
    ).execute()
    
    # 2. もしサイクル(L列)が設定されていれば、期限(G列)を今日から再計算
    if cycle_days > 0:
        new_expiry = (now_dt + timedelta(days=int(cycle_days))).strftime('%Y/%m/%d')
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=f'inventory!G{row_idx}',
            valueInputOption='USER_ENTERED', body={'values': [[new_expiry]]}
        ).execute()
    
    # 3. 更新者(J列)と更新日時(K列)の記録
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!J{row_idx}:K{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[user_name, now_str]]}
    ).execute()
    
    st.rerun()

# お気に入りボタンを制御する関数
def update_fav(service, row_idx, new_status):
    # お気に入り(I列)の状態を書き換える
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!I{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[str(new_status).upper()]]}
    ).execute()
    st.rerun()


# ==========================================
# 5. 【新規登録のプロ】スプレッドシートに1行追加する
# ==========================================
def add_new_item(service, item_list):
    # item_list の中身: [商品名, 現在数, 最低数, 単位, カテゴリ, 場所]
    # スプレッドシートの並び順に合わせてデータを整理
    # item_list の中身: [商品名, 現在数, 最低数, 単位, カテゴリ, 場所, 期限, 商品コード, サイクル]
    user_name = "ゆるり"
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    
# スプレッドシートの A列〜L列 の順番に並び替えます
    new_row = [
        item_list[0],  # A: 商品名
        item_list[1],  # B: 現在の在庫数
        item_list[2],  # C: 設定在庫数（最低数）
        item_list[3],  # D: 単位
        item_list[4],  # E: カテゴリ
        item_list[5],  # F: 場所
        item_list[6],  # G: 消費期限（計算済みの値）
        item_list[7],  # H: 商品コード
        "FALSE",       # I: お気に入り（初期値）
        user_name,     # J: 更新者
        now,           # K: 更新日時
        item_list[8]   # L: サイクル（←ここが重要！）
    ]
    
    # 最終行の下にデータを追加する命令 (append)
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="inventory!A:A", # どこに追加するか（A列基準で探す）
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [new_row]}
    ).execute()



# --- プログラムのスタート地点 ---
if __name__ == "__main__":
    main()