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
# --- 画像を表示する---
import requests  
from io import BytesIO
# --- バーコードスキャン---
from pyzbar.pyzbar import decode
from PIL import Image
import streamlit.components.v1 as components

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
        fields='id'
    ).execute()

    file_id = file.get('id')
    
    # webViewLink ではなく、直接画像を表示できる「サムネイル用URL」を返します
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w600"












# ==========================================
# 編集関数
# ==========================================
@st.dialog("品物情報の登録・修正")
def item_form_dialog(service_sheets, service_drive,df, index=None, row=None):
    # --- 1. モードの判定 ---
    is_edit = index is not None

# row が None（新規登録）なら、空の辞書 {} に置き換える
    if row is None:
        row = {}

    title = "【修正】" if is_edit else "【新規登録】"
    st.write(f"### {title}")


# --- 商品コード用バーコード関数を配置 ---
    # ラベル名は下の text_input と完全に一致させる必要があります
    code_label = "商品コード（管理番号）"
    render_barcode_scanner(
        label_target=code_label, 
        button_text="📷 バーコードをスキャン", 
        button_color="#4CAF50" # 登録・修正は緑色
    )



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
    # チェックを入れたときだけカメラを起動させる
    use_camera = st.checkbox("写真を撮影・更新する")

    img_file = None
    if use_camera:
        # label_visibility="collapsed" で余計なラベルを消し、
        # 外カメラを優先する設定を追加（※ブラウザ側の解釈に依存しますが、指示は出せます）
        img_file = st.camera_input(
            "撮影", 
            key=f"cam_{index if is_edit else 'new'}",
            label_visibility="collapsed"
        )
    
    if img_file:
        # 🌟 撮影時はデータだけを一旦保持（まだアップロードしない）
        st.session_state["temp_img_data"] = img_file
        st.success("写真を撮影しました（保存ボタンを押すと確定します）")

    # --- 4. 入力フォーム（以前の項目をすべて復活） ---
    edit_code  = st.text_input("商品コード（管理番号）", value=d_code)
    edit_name  = st.text_input("商品名（必須）", value=d_name)
  # --- カテゴリの選択 ＋ 新規入力 ---
    default_cats = ["日用品", "食料品", "掃除用品", "その他"]
    # 既存のカテゴリを抽出
    existing_cats = df['カテゴリ'].unique().tolist() if 'カテゴリ' in df.columns else []
    all_cats = sorted(list(set(default_cats + existing_cats)))
    cat_options = ["(新規入力)"] + [c for c in all_cats if c]

    selected_cat = st.selectbox(
        "カテゴリを選択", 
        options=cat_options,
        index=cat_options.index(d_cat) if d_cat in cat_options else 0
    )
    if selected_cat == "(新規入力)":
        edit_cat = st.text_input("新しいカテゴリ名を入力", value="")
    else:
        edit_cat = selected_cat

    # --- 保管場所の選択 ＋ 新規入力 ---
    # 既存の場所を抽出
    existing_places = sorted(df['場所'].unique().tolist()) if '場所' in df.columns else []
    place_options = ["(新規入力)"] + [p for p in existing_places if p]

    selected_place = st.selectbox(
        "保管場所を選択", 
        options=place_options,
        index=place_options.index(d_place) if d_place in place_options else 0
    )
    if selected_place == "(新規入力)":
        edit_place = st.text_input("新しい保管場所を入力（A, Bなど）", value="")
    else:
        edit_place = selected_place


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
                if use_camera and new_img_data:
                    time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    f_name = f"{edit_name}_{time_str}.jpg"
                    final_img_url = upload_image_to_drive(service_drive, new_img_data, f_name)
                else:
                    final_img_url = d_img # 撮ってなければ既存のURLを維持
            
            # --- スプレッドシートの列順に合わせてリストを作成（重要！） ---
            # A:商品名, B:現在の在庫数, C:設定在庫数(最低数), D:単位, E:カテゴリ, 
            # F:場所, G:お気に入り, H:商品コード, I:RUSH(※不要なら空), J:継続(※空), 
            # K:期待値(※空), L:サイクル, M:画像URL
            # ※お気に入りは修正なら維持、新規ならFalse

            # 🌟 現在の時刻とユーザー名（ゆるりさん）を用意
            now_str = datetime.now().strftime('%Y/%m/%d %H:%M')
            user_name = "ゆるり" # シートに合わせて固定、または変数で

            row_data = [
                edit_name,      # A: 商品名
                str(edit_cur),  # B: 現在の在庫数
                str(edit_limit),# C: 設定在庫数（最低数）
                edit_unit,      # D: 単位
                edit_cat,       # E: カテゴリ
                edit_place,     # F: 場所
                current_expiry,             # G: 消費期限（今回は入力なしなら空）
                edit_code,      # H: 商品コード
                "FALSE" if not is_edit else row.get('お気に入り', "FALSE"), # I: お気に入り
                user_name,      # J: 最後に更新した人
                now_str,        # K: 更新日時
                str(edit_cycle),# L: サイクル
                final_img_url   # M: 画像URL
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
# 【共通部品】バーコードスキャナー（JS）を生成する関数
# ==========================================
def render_barcode_scanner(label_target, button_text="バーコードスキャン", button_color="#FF4B4B"):
    """
    label_target: 値を流し込む対象の text_input の label名
    button_text: ボタンに表示する文字
    button_color: ボタンの色
    """
    import streamlit.components.v1 as components
    
    # JavaScript側で、対象の label を持つ input を探して値をセットするロジック
    scan_js = f"""
    <div style="text-align:center;">
        <button id="common-scan-btn" style="width:100%; height:50px; background-color:{button_color}; color:white; border:none; border-radius:8px; font-size:1.1em; font-weight:bold; cursor:pointer; margin-bottom:10px;">
            {button_text}
        </button>
        <div id="common-v-container" style="display:none; position:relative;">
            <video id="common-video" style="width:100%; border-radius:10px; border:2px solid {button_color};" playsinline></video>
        </div>
    </div>

    <script>
        const btn = document.getElementById('common-scan-btn');
        const video = document.getElementById('common-video');
        const container = document.getElementById('common-v-container');

        btn.onclick = async () => {{
            if (!('BarcodeDetector' in window)) {{
                alert("BarcodeDetector非対応のブラウザです（iOS17+のSafariやChromeを推奨）");
                return;
            }}
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: "environment" }} }});
                video.srcObject = stream;
                await video.play();
                container.style.display = 'block';
                btn.style.display = 'none';

                const detector = new BarcodeDetector({{ formats: ['ean_13', 'ean_8', 'code_128'] }});
                
                const scan = async () => {{
                    const barcodes = await detector.detect(video);
                    if (barcodes.length > 0) {{
                        const val = barcodes[0].rawValue;
                        
                        // 🌟 引数で指定された label を持つ入力を親画面から探す
                        const input = window.parent.document.querySelector('input[aria-label="{label_target}"]');
                        if (input) {{
                            input.value = val;
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            input.dispatchEvent(new KeyboardEvent('keydown', {{ 'key': 'Enter', bubbles: true }}));
                       
                            // バーコード入力数値が消える対策Pythonにも数値をおくる
                            window.parent.postMessage({{
                                isStreamlitMessage: true,
                                type: "streamlit:setComponentValue",
                                key: "barcode_data",
                                value: val
                            }}, "*");
                        }}
                        stream.getTracks().forEach(track => track.stop());
                        container.style.display = 'none';
                        btn.style.display = 'block';
                    }} else {{
                        requestAnimationFrame(scan);
                    }}
                }};
                scan();
            }} catch (e) {{
                alert("カメラの起動に失敗しました。許可設定を確認してください。");
            }}
        }};
    </script>
    """
    return components.html(scan_js, height=110)









# ==========================================
# 2. 【表示の職人】リストを画面に描く関数
# ==========================================
# target_df: 表示したいデータ, title: 見出しの名前, prefix: ボタンの重複防止用, service: 通信用
def display_list(target_df, title, prefix, service_sheets, service_drive, df):
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
            # 1. 画像URLの取得
            img_link = None
            try:
                # まず名前で探してみて、ダメなら12番目の列（M列）を直接見る
                img_link = row.get('画像URL')
                if img_link is None or str(img_link) in ["", "nan", "None"]:
                    img_link = row.iloc[12] # M列を直接指定
            except:
                pass
            
            # 🌟 ここで「見れないURL」を「見れるURL」に強制変換する
            if "drive.google.com" in str(img_link) and "thumbnail" not in str(img_link):
                try:
                    # URLの中からファイルIDを抜き出す
                    if "/d/" in str(img_link):
                        file_id = str(img_link).split("/d/")[1].split("/")[0]
                        # ゆるりさんが「見れる！」と言ったあの形式に作り変える
                        img_link = f"https://drive.google.com/thumbnail?id={file_id}&sz=w600"
                except:
                    pass # 失敗したら元のURLのまま（後の処理でエラー回避される）


            has_image = False
            # 2. 1行目：【画像】と【品名】を横に並べる
            col_img_icon, col_item_name = st.columns([0.4, 5.6])
            
            with col_img_icon:
                # 画像があれば st.image で表示（リンクではないので勝手に立ち上がらない）
                if img_link and "http" in str(img_link):
                    try:
                        st.image(img_link, use_container_width=True)
                        has_image = True
                    except Exception:
                        st.write("📷") # エラー時
                else:
                    st.write("📦") # 画像なし時

            with col_item_name:
                # 品名を少し大きめに表示（ここにはリンクを入れない）
                st.markdown(f"{alert_icon}<strong style='font-size:1.1em;'>{row['商品名']}</strong>", unsafe_allow_html=True)

            # 3. 2行目：在庫/基準/期限/ID（1行目の画像と重ならないように位置調整）
            # 画像がある場合は 65px ずらし、ない場合は 0px
            margin_left = "35px" if has_image else "0px"
            
            info_html = f"""
            <div style='margin-top:-5px; font-size:0.92em; line-height:1.5; margin-left:{margin_left};'>
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
                    item_form_dialog(service_sheets, service_drive, df, index, row) # 引数あり
                    
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
# 6. 【検索】キーワードやバーコードで商品を探す関数
# ==========================================
def show_search_section(df, service_sheets, service_drive):

    # 🌟 文字は見えないけど、ジャンプ先として機能する「透明な目印」
    st.markdown('<div id="🔍-商品を探す"></div>', unsafe_allow_html=True)
        
    # 検索窓とカメラボタンのレイアウト
    search_col1, search_col2 = st.columns([4, 1])
    
    # セッション状態で検索クエリを管理（バーコード読み取り結果を反映させるため）
# 1. セッションの準備
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""
    # 🌟 リセット管理用のカウンター
    if "search_reset_counter" not in st.session_state:
        st.session_state.search_reset_counter = 0    

# バーコード読み込み関数（ラベル名を一致させる）
    search_label = "キーワードまたは商品コード"
    #render_barcode_scanner(label_target=search_label, button_text="📷 バーコード読み取り開始", button_color="#FF4B4B")
    #バーコード消える対策
    render_barcode_scanner(label_target=search_label, button_text="📷 バーコード読み取り開始", button_color="#FF4B4B")
    res_search = st.session_state.get("barcode_data")

    if res_search:
        # 🌟 ここで金庫にバックアップ！
        st.session_state.search_query = str(res_search)
        # 🌟 2回連続で同じ処理が走らないよう、使い終わったポストを空にする
        st.session_state["barcode_data"] = None
        # 🌟 金庫が更新されたので、画面をリフレッシュして検索窓に反映させる
        st.rerun()


    # 毎回クリアボタンを押すたびに key が変わるようにします
    current_key = f"global_search_input_{st.session_state.search_reset_counter}"

    # 3. 検索窓（aria-labelをJS側から見つけやすくするためラベルを固定）
    input_val = st.text_input(
        "キーワードまたは商品コード", 
        value=st.session_state.search_query, 
        key=current_key
    )

    # スキャン結果が届いたらセッションを更新
    if input_val != st.session_state.search_query:
        st.session_state.search_query = input_val

    # 4. 手入力があった場合のみセッションを更新
    if input_val != st.session_state.search_query:
        st.session_state.search_query = input_val

    # 5. 検索実行と表示
    if st.session_state.search_query:
        q = st.session_state.search_query
        search_df = df[
            df['商品名'].str.contains(q, na=False, case=False) | 
            df['カテゴリ'].str.contains(q, na=False, case=False) |
            df['場所'].str.contains(q, na=False, case=False) |
            df['商品コード'].astype(str).str.contains(q, na=False)
        ]
        
        if not search_df.empty:
            st.success(f"「{q}」の検索結果: {len(search_df)} 件")
            display_list(search_df, "🎯 検索結果", "search", service_sheets, service_drive, df)
            
            if st.button("検索をクリア", key="clear_button"):
                st.session_state.search_query = ""
                if st.session_state.search_reset_counter == 0:
                    st.session_state.search_reset_counter = 1
                else:
                    st.session_state.search_reset_counter = 0
                st.rerun()
            st.divider() 
        else:
            st.warning(f"「{q}」は見つかりませんでした。")
            # 🌟 ヒットしなかった場合もクリアできるようにボタンを置く
            if st.button("入力をクリア", key="empty_clear_button"):
                st.session_state.search_query = ""
                st.rerun()




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
        range='inventory!A:M'
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




# 画面右下のトップへ戻るボタン
    st.markdown(
    """
    <style>
    .back-to-top {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background-color: #FF4B4B;
        color: white;
        padding: 10px 15px;
        border-radius: 50%;
        text-decoration: none;
        z-index: 999;
        font-weight: bold;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
    }
    </style>
    <a href="#🔍-商品を探す" class="back-to-top">▲</a>
    """,
    unsafe_allow_html=True
    )




        # --- 画面上部に検索窓を作成 ---
    show_search_section(df, service_sheets, service_drive)

    
    # --- 画面上部にタブ（切り替えボタン）を作成 ---
    t_buy, t_fav, t_all, t_place, t_add = st.tabs(["🛍️ 買い物", "⭐ お気に入り", "📦 すべて", "📍 場所別", "➕ 品物追加"])
 




    # 1. 買い物タブ：在庫が足りないものだけ抽出して表示
    with t_buy:
        #buy_df = df[df['現在の在庫数'].astype(int) < df['設定在庫数（最低数）'].astype(int)]
        # 買い物リスト変更：在庫不足 OR 期限切れ
        buy_df = df[df['is_low'] | df['is_expired']]
        buy_df = apply_sorting_ui(buy_df, "buy")#ソートボタン---
        display_list(buy_df, "買い出しが必要なもの", "buy", service_sheets, service_drive, df)

    # 2. お気に入りタブ：H列がTRUEのものだけ抽出して表示
    with t_fav:
        fav_df = df[df['お気に入り'].astype(str).str.upper() == 'TRUE']
        fav_df = apply_sorting_ui(fav_df, "fav")#ソートボタン---
        display_list(fav_df, "お気に入りアイテム", "fav", service_sheets, service_drive, df)

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
        display_list(all_df, f"全在庫 ({cat_choice})", "all", service_sheets, service_drive, df)

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
        display_list(place_df, f"場所 {place_choice} の在庫", "place", service_sheets, service_drive, df)

     # 5. 品物追加タブ
    with t_add:
        if st.button("➕ 新しい商品を追加"):
            item_form_dialog(service_sheets, service_drive, df) # 引数なし

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