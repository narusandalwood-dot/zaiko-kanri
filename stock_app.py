import streamlit as st
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import os.path
import json
from datetime import datetime, date , timedelta # timedelta  dateを追加（期限切れ用）

# --- 画像を保存する---
from googleapiclient.http import MediaIoBaseUpload
import io

# --- Googleドライブの設定 ---
SPREADSHEET_ID = '1XWnNOEKv5VRhJXxxr923nqPrHlLsF-3lEDl0wYaZpC8'  # URLの d/ と /edit の間の文字列
IMAGE_FOLDER_ID = "18bYiEiFDRTzRo4ZMo4ITUDMEzpBFJyX9"# 写真保管のフォルダ
RANGE_NAME = 'inventory!A:L'  # シート名が inventory の場合

# スコープ（権限）の設定（スプレッドシート＆ドライブ）
SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file' # ドライブの操作権限
    ]


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

# 2. サービス（窓口）を作成する　スプレッドシート＆ドライブの２つ
    service_sheets = build('sheets', 'v4', credentials=creds)
    service_drive = build('drive', 'v3', credentials=creds)

    # 3. 2つまとめて返す
    return service_sheets, service_drive



# --- Googleドライブへ画像を保存する関数 ---
def upload_image_to_drive(service_drive, image_file, file_name):
    """
    image_file: Streamlitのカメラ入力から得られたデータ
    file_name: 保存するファイル名
    """
    file_metadata = {
        'name': file_name,
        'parents': [IMAGE_FOLDER_ID]
    }
    
    # 画像データをドライブが読める形式に変換
    media = MediaIoBaseUpload(
        io.BytesIO(image_file.getvalue()), 
        mimetype='image/jpeg'
    )
    
    # アップロード実行
    file = service_drive.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    # 誰でも閲覧できるリンク（直リンクではないが、まずはこれ）を取得
    return file.get('webViewLink')


# ==========================================
# 編集関数
# ==========================================
@st.dialog("品物情報の登録・修正")
def item_form_dialog(service_sheets, service_drive, index=None, row=None):
    # --- 1. モードの判定 ---
    is_edit = index is not None

# row が None（新規登録）なら、空の辞書 {} に置き換える
    if row is None:
        row = {}

    title = "【修正】" if is_edit else "【新規登録】"
    st.write(f"### {title}")

    # --- 2. 初期値の設定（修正なら既存データ、新規なら空っぽ・初期値） ---
    # row.get() や row['列名'] を使って、今の値をフォームにセットします
    d_code  = row.get('商品コード（管理番号）', "") 
    d_name  = row.get('商品名', "")
    d_cat   = row.get('カテゴリ', "日用品")
    d_place = row.get('場所', "")
    d_cur   = int(row.get('現在の在庫数', 0))
    d_limit = int(row.get('設定在庫数（最低数）', 1))
    d_unit  = row.get('単位', "個")
    d_cycle = int(float(row['サイクル'])) if is_edit and row['サイクル'] else 30
    d_img   = row.get('画像URL', "") if is_edit else ""

    # --- 3. カメラ機能 ---
    st.write("📷 商品写真")
    img_file = st.camera_input("撮影する", key=f"cam_{index if is_edit else 'new'}")
    
    if img_file:
        # 🌟 撮影時はデータだけを一旦保持（まだアップロードしない）
        st.session_state["temp_img_data"] = img_file
        st.success("写真を撮影しました（保存ボタンを押すと確定します）")

    # --- 4. 入力フォーム（以前の項目をすべて復活） ---
    edit_code  = st.text_input("商品コード（管理番号）", value=d_code)
    edit_name  = st.text_input("商品名（必須）", value=d_name)
    edit_cat   = st.selectbox("カテゴリ", ["日用品", "食料品", "掃除用品", "その他"], 
                            index=["日用品", "食料品", "掃除用品", "その他"].index(d_cat) if d_cat in ["日用品", "食料品", "掃除用品", "その他"] else 0)
    edit_place = st.text_input("保管場所（A, Bなど）", value=d_place)
    
    col1, col2 = st.columns(2)
    with col1:
        edit_cur   = st.number_input("現在の在庫数", min_value=0, value=d_cur)
        edit_limit = st.number_input("最低在庫数", min_value=0, value=d_limit)
    with col2:
        edit_unit  = st.text_input("単位（個、パックなど）", value=d_unit)
        edit_cycle = st.number_input("交換サイクル（日）", min_value=0, value=d_cycle)

    # --- 5. 保存・削除ボタン ---
    st.divider()
    col_save, col_cancel = st.columns(2)

    with col_save:
        btn_label = "変更を保存" if is_edit else "新規登録する"
        if st.button(btn_label, type="primary", use_container_width=True):
            if not edit_name:
                st.error("商品名を入力してください")
                return

            with st.spinner("情報を保存中..."):
            # 保存ボタンが押された「今」の商品名を使ってファイル名を作る
                new_img_data = st.session_state.get("temp_img_data")
            
            if new_img_data:
                # 商品名 ＋ 日時 でファイル名を作成（空白になりにくい）
                time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                f_name = f"{edit_name}_{time_str}.jpg"
                
                # ここで初めてドライブにアップロード
                final_img_url = upload_image_to_drive(service_drive, new_img_data, f_name)
            else:
                # 写真を新しく撮っていない場合は、元のURLを維持
                final_img_url = d_img
            
            # --- スプレッドシートの列順に合わせてリストを作成（重要！） ---
            # A:商品名, B:現在の在庫数, C:設定在庫数(最低数), D:単位, E:カテゴリ, 
            # F:場所, G:お気に入り, H:商品コード, I:RUSH(※不要なら空), J:継続(※空), 
            # K:期待値(※空), L:サイクル, M:画像URL
            # ※お気に入りは修正なら維持、新規ならFalse
            row_data = [
                edit_name,  # A
                str(edit_cur),   # B
                str(edit_limit), # C
                edit_unit,  # D
                edit_cat,   # E
                edit_place, # F
                row['お気に入り'] if is_edit else "FALSE", # G
                edit_code,  # H
                "", "", "", # I, J, K (パチンコ計算用列の空き)
                str(edit_cycle), # L
                final_img_url    # M
            ]

            if is_edit:
                # 既存の行を上書き
                service_sheets.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID, range=f'inventory!A{index+2}',
                    valueInputOption='USER_ENTERED', body={'values': [row_data]}
                ).execute()
            else:
                # 最終行に追加
                service_sheets.spreadsheets().values().append(
                    spreadsheetId=SPREADSHEET_ID, range='inventory!A:M',
                    valueInputOption='USER_ENTERED', body={'values': [row_data]}
                ).execute()

            if "temp_img_url" in st.session_state:
                del st.session_state["temp_img_url"]
            st.success("保存完了しました！")
            st.rerun()

    if is_edit:
        with col_cancel:
            if st.button("🗑️ この品物を削除", type="secondary", use_container_width=True):
                delete_row(service_sheets, index + 2)
                st.rerun()




# ==========================================
# 2. 【表示の職人】リストを画面に描く関数
# ==========================================
# target_df: 表示したいデータ, title: 見出しの名前, prefix: ボタンの重複防止用, service: 通信用
def display_list(target_df, title, prefix, service_sheets, service_drive):
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
        text_color = "#FF4B4B" if should_alert else "#31333F"
        expiry_color = "#FF4B4B" if is_expired else "#666666"
        
        if is_expired:
            alert_icon = ""
        elif is_low:
            alert_icon = ""
        else:
            alert_icon = ""

        # 表示用テキストの整理
        item_code = row['商品コード'] if row['商品コード'] else "---"
        if expiry_str in invalid_values:
            expiry_display = "未設定"
        elif is_expired:
            expiry_display = f"🚨期限切({expiry_str})"
        else:
            expiry_display = expiry_str

        # --- レイアウト作成 ---
        col_info, col_btn = st.columns([4, 2])
        
        with col_info:
            # --- 画像URLがあるかチェック ---
            img_link = row.get('画像URL')
            # 画像があればカメラアイコンのリンクを作成、なければ空文字
            cam_icon = f" [ [📷]({img_link}) ]" if img_link else ""

            # 1行目：品名 ＋ カメラアイコン（もしあれば）
            # cam_icon を最後に追加しています
            st.markdown(f"{alert_icon}<strong style='font-size:1.1em;'>{row['商品名']}</strong>{cam_icon}", unsafe_allow_html=True)
            # 2行目：在庫/基準/期限/IDを1行に凝縮
            # 隙間を詰めるために margin-top をマイナスに設定
            info_html = f"""
            <div style='margin-top:-5px; font-size:0.92em; line-height:1.5;'>
                <span style='color:#666;'>在庫:</span><span style='color:{text_color}; font-weight:bold;'>{cur}</span>/{limit}{row['単位']} | 
                <span style='color:#666;'>期限:</span><span style='color:{expiry_color};'>{expiry_display}</span> | 
                <span style='color:#888;'>ID:{item_code}</span>
            </div>
            """
            st.markdown(info_html, unsafe_allow_html=True)



# ボタン
        with col_btn:
            # ボタンを5つ並べる（＋, ー, 詳細, 📸, ★）
            b1, b2, b3, b4, b5 = st.columns(5)
            
            cycle = row['サイクル'] if 'サイクル' in row and row['サイクル'] else 0
            try:
                cycle_days = int(float(cycle))
            except:
                cycle_days = 0




            with b1:
                # 期限リセット用追加
                cycle = row['サイクル'] if 'サイクル' in row and row['サイクル'] else 0
                try:
                    # 数字として扱えるように変換
                    cycle_days = int(float(cycle))
                except:
                    cycle_days = 0


                if st.button("＋", key=f"plus_{prefix}_{index}"):
                    update_stock(service_sheets, index + 2, cur + 1, cycle_days)
            with b2:
                if st.button("ー", key=f"minus_{prefix}_{index}"):
                    new_val = max(0, cur - 1)
                    # 在庫が0になったら、期限を空っぽにする
                    if new_val == 0:
                        update_stock(service_sheets, index + 2, 0, cycle_days=None) # 期限を消去する指示
                    else:
                        update_stock(service_sheets, index + 2, new_val)
            with b3:
                # 詳細ボタン（クリックで編集用ポップアップを出す）
                if st.button("📝", key=f"edit_{prefix}_{index}", help="詳細・修正"):
                    item_form_dialog(service_sheets, service_drive, index, row) # 引数あり
                    
            with b4:
                # バーコードボタン（今はまだ枠だけ）
                st.button("📸", key=f"barcode_{prefix}_{index}", help="バーコード（準備中）")
            with b5:
                is_fav = str(row['お気に入り']).upper() == 'TRUE'
                if st.button("★" if is_fav else "☆", key=f"fav_{prefix}_{index}"):
                    update_fav(service_sheets, index + 2, not is_fav)

    
# 線を細くして余白をさらに節約
        st.markdown("<hr style='margin:8px 0; border:0; border-top:1px solid #eee;'>", unsafe_allow_html=True)

# ==========================================
# ソートボタン関数
# ==========================================
# ソートボタンを表示して、並び替えた後のデータを返す関数
def apply_sorting_ui(df, prefix):

    col_s1, col_s2, col_spacer = st.columns([0.4, 0.25, 0.35])
    with col_s1:
        sort_key = st.segmented_control(
            label="並び替えを選択",
            options=["更新日時", "現在の在庫数", "消費期限"],
            default="更新日時",
            key=f"sort_key_{prefix}"
        )
    with col_s2:
        sort_order = st.segmented_control(
            label=f"sort_order_{prefix}",
            options=["昇順 (↑)", "降順 (↓)"],
            default="降順 (↓)",
            key=f"sort_order_{prefix}",
            label_visibility="hidden" # 項目名と高さを合わせるために hidden にする
        )

    # 並び替え実行
    ascending = (sort_order == "昇順 (↑)")
    if sort_key == "消費期限":
        df_sorted = df.copy()
        df_sorted['sort_tmp'] = pd.to_datetime(df_sorted['消費期限'], errors='coerce')
        return df_sorted.sort_values(by='sort_tmp', ascending=ascending).drop(columns=['sort_tmp'])
    else:
        return df.sort_values(by=sort_key, ascending=ascending)









# ==========================================
# 3. 【司令塔】メインの処理
# ==========================================
def main():
    st.set_page_config(page_title="在庫管理", layout="wide")
# ここを2つ受け取る形にする
    service_sheets, service_drive = get_sheets_service()

    
    # --- スプレッドシートからデータを取ってくる ---
    result = service_sheets.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, 
        range=RANGE_NAME
    ).execute()
    values = result.get('values', [])
    if not values:
        st.error("データが見つかりません。")
        return

    # データを扱いやすい表形式(DataFrame)に変換
    df = pd.DataFrame(values[1:], columns=values[0])
    df['現在の在庫数'] = pd.to_numeric(df['現在の在庫数'], errors='coerce').fillna(0)
    df['設定在庫数（最低数）'] = pd.to_numeric(df['設定在庫数（最低数）'], errors='coerce').fillna(0)
    # 期限切れ判定（簡易版）
    df['is_low'] = df['現在の在庫数'].astype(int) < df['設定在庫数（最低数）'].astype(int)
    today_str = date.today().strftime('%Y/%m/%d')
    # 期限が入力されていて、かつ今日より前の日付のものを探す
    df['is_expired'] = (df['消費期限'].str.contains(r'\d{4}/\d{2}/\d{2}', na=False)) & (df['消費期限'] < today_str)

    st.title("🛒 在庫管理アプリ")

    # --- 画面上部にタブ（切り替えボタン）を作成 ---
    t_buy, t_fav, t_all, t_place, t_add = st.tabs(["🛍️ 買い物", "⭐ お気に入り", "📦 すべて", "📍 場所別", "➕ 品物追加"])
 
    # 1. 買い物タブ：在庫が足りないものだけ抽出して表示
    with t_buy:
        #buy_df = df[df['現在の在庫数'].astype(int) < df['設定在庫数（最低数）'].astype(int)]
        # 買い物リスト変更：在庫不足 OR 期限切れ
        buy_df = df[df['is_low'] | df['is_expired']]
        buy_df = apply_sorting_ui(buy_df, "buy")#ソートボタン---
        display_list(buy_df, "買い出しが必要なもの", "buy", service_sheets, service_drive)

    # 2. お気に入りタブ：H列がTRUEのものだけ抽出して表示
    with t_fav:
        fav_df = df[df['お気に入り'].astype(str).str.upper() == 'TRUE']
        fav_df = apply_sorting_ui(fav_df, "fav")#ソートボタン---
        display_list(fav_df, "お気に入りアイテム", "fav", service_sheets, service_drive)

    # 3. すべてタブ：全件表示（カテゴリで絞り込み可能）
    with t_all:
        cats = ["すべて"] + sorted(df['カテゴリ'].unique().tolist())
        # --- セレクトボックスを「クリック形式」に変更 ---
        cat_choice = st.segmented_control(
            label="カテゴリを選択",
            options=cats,
            default="すべて",
            selection_mode="single"
        )

        all_df = df if cat_choice == "すべて" else df[df['カテゴリ'] == cat_choice]
        all_df = apply_sorting_ui(all_df, "all")#ソートボタン---
        display_list(all_df, f"全在庫 ({cat_choice})", "all", service_sheets, service_drive)

    # 4. 場所別タブ：場所（A, B, C...）で選んで表示
    with t_place:
        places = sorted(df['場所'].unique().tolist())
        place_choice = st.segmented_control(
            label="場所を選択",
            options=places,
            default=places[0] if places else None,
            selection_mode="single"
        )


        place_df = df[df['場所'] == place_choice]
        place_df = apply_sorting_ui(place_df, "place")#ソートボタン---
        display_list(place_df, f"場所 {place_choice} の在庫", "place", service_sheets, service_drive)

     # 5. 品物追加タブ
    with t_add:
        if st.button("➕ 新しい商品を追加"):
            item_form_dialog(service_sheets, service_drive) # 引数なし

# ==========================================
# 4. 【書き換えのプロ】スプレッドシートを更新する関数
# ==========================================
def update_stock(service_sheets, row_idx, new_val, cycle_days=0):
    user_name = "ゆるり"
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y/%m/%d %H:%M")
    
    # 1. 在庫数(B列)の更新
    service_sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!B{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[new_val]]}
    ).execute()

    # --- 期限(G列)の更新判定 ---
    if cycle_days is None:
        # None が渡されたら期限を消去
        service_sheets.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=f'inventory!G{row_idx}',
            valueInputOption='USER_ENTERED', body={'values': [[""]]}
        ).execute()

    
    # 2. もしサイクル(L列)が設定されていれば、期限(G列)を今日から再計算
    elif cycle_days > 0:
        new_expiry = (now_dt + timedelta(days=int(cycle_days))).strftime('%Y/%m/%d')
        service_sheets.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=f'inventory!G{row_idx}',
            valueInputOption='USER_ENTERED', body={'values': [[new_expiry]]}
        ).execute()
    
    # 3. 更新者(J列)と更新日時(K列)の記録
    service_sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!J{row_idx}:K{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[user_name, now_str]]}
    ).execute()
    
    st.rerun()

# お気に入りボタンを制御する関数
def update_fav(service_sheets, row_idx, new_status):
    # お気に入り(I列)の状態を書き換える
    service_sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=f'inventory!I{row_idx}',
        valueInputOption='USER_ENTERED', body={'values': [[str(new_status).upper()]]}
    ).execute()
    st.rerun()


# ==========================================
# 5. 【新規登録のプロ】スプレッドシートに1行追加する
# ==========================================
def add_new_item(service_sheets, item_list):
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
    service_sheets.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="inventory!A:A", # どこに追加するか（A列基準で探す）
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [new_row]}
    ).execute()



# --- プログラムのスタート地点 ---
if __name__ == "__main__":
    main()