import streamlit as st
import pandas as pd
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# --- 設定 ---
st.set_page_config(page_title="ALOHA Mentoring Base Pro", layout="wide")

def get_gspread_client():
    try:
        # SecretsからJSON文字列を取得してパース
        json_str = st.secrets["gspread_credentials"]["json_content"]
        creds_dict = json.loads(json_str) # ここでJSONとして読み込む
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

# --- Google Sheets 接続関数 (gspread使用) ---
def get_gspread_client():
    try:
        # 1. Secretsから辞書として直接取得（json.loadsを使わない）
        if "gspread_credentials" not in st.secrets:
            st.error("Secretsに [gspread_credentials] の見出しが見つかりません。")
            return None
            
        # 2. Secretsの内容を辞書形式に変換
        creds_dict = dict(st.secrets["gspread_credentials"])
        
        # 3. 認証情報の作成
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
        
    except Exception as e:
        st.error(f"認証エラーの詳細: {e}")
        # どの項目が足りないかデバッグ表示
        st.write("現在Secretsから読み込めている項目:", list(st.secrets["gspread_credentials"].keys()))
        return None

# --- データ読み書きロジック ---
def load_data():
    client = get_gspread_client()
    if client:
        try:
            # スプレッドシートのURLをSecretsから取得
            sheet = client.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
            worksheet = sheet.worksheet("logs")
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            st.warning(f"データ読み込み失敗 (新規作成します): {e}")
            return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)

def save_data(new_row_df):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
            worksheet = sheet.worksheet("logs")
            # DataFrameをリスト形式に変換して追加（ヘッダーなし）
            values = new_row_df.values.tolist()
            worksheet.append_rows(values)
            return True
        except Exception as e:
            st.error(f"保存エラー: {e}")
            return False
    return False

# --- 基本設定 ---
COLUMNS = ["日付", "種別", "担当メンター", "生徒氏名", "学年", "文理", "試験名", "課題", "データJSON"]

# --- セッション初期化 ---
if 'actions' not in st.session_state:
    st.session_state.actions = [{'subject': '英語', 'priority': '高', 'policy': '', 'specificTask': '', 'deadline': '次回まで'}]
if 'prev_actions' not in st.session_state:
    st.session_state.prev_actions = []
if 'dynamic_scores' not in st.session_state:
    st.session_state.dynamic_scores = [{'subject': '英語'}, {'subject': '数学'}]

def get_last_session(student_name):
    df = load_data()
    if not df.empty and student_name:
        res = df[df['生徒氏名'] == student_name]
        if not res.empty:
            return res.iloc[-1] # 一番最後（最新）の行を返す
    return None

# --- UI構築 (以下は以前のロジックと同じ) ---
st.title("🎓 ALOHA Mentoring Base Pro")
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="定期面談", key="in_type")

tab_new, tab_search, tab_preview = st.tabs(["📝 面談記録入力", "🔍 過去ログ検索", "📄 レポート出力"])

with tab_new:
    # --- 基本情報 ---
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            student_name = st.text_input("生徒氏名", key="in_student")
            if st.button("🔄 前回データを読み込む"):
                last_row = get_last_session(student_name)
                if last_row is not None:
                    last_data = json.loads(last_row['データJSON'])
                    st.session_state.prev_actions = last_data.get('actions', [])
                    st.success(f"{last_row['日付']} のデータを読み込みました")
                else: st.warning("過去のデータが見つかりません")
        with c2:
            mentor_name = st.text_input("担当メンター", key="in_mentor")
            stream = st.radio("文理", ["理系", "文系"], horizontal=True, key="in_stream")
        with c3:
            date_val = st.date_input("実施日", datetime.date.today())
            grade = st.selectbox("学年", ["中1", "中2", "中3", "高1", "高2", "高3", "既卒"], index=5)

    # --- 前回タスクの振り返り ---
    if st.session_state.prev_actions:
        with st.expander("✅ 前回タスクの達成度確認", expanded=True):
            for i, p_act in enumerate(st.session_state.prev_actions):
                col_a, col_b = st.columns([3, 1])
                col_a.write(f"**{p_act['subject']}**: {p_act['specificTask']}")
                p_act['status'] = col_b.select_slider("達成度", options=["×", "△", "◯", "◎"], value="◯", key=f"prev_status_{i}")

    # --- 試験結果・目標入力 ---
    with st.container(border=True):
        st.subheader("📊 試験結果・目標設定")
        e_col1, e_col2 = st.columns([1, 2])
        exam_category = e_col1.selectbox("種別", ["定期試験", "東大二次模試", "共通テスト模試"])
        exam_name = e_col2.text_input("試験名 (例: 1学期中間)", key="in_exam_name")
        st.divider()

        h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([2, 1, 1, 1, 0.5])
        h_col1.caption("科目名")
        h_col2.caption("今回の点数")
        h_col3.caption("次回の目標")
        h_col4.caption("差分")
        h_col5.caption("削除")
        
        score_results = []
        for i, item in enumerate(st.session_state.dynamic_scores):
            r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([2, 1, 1, 1, 0.5])
            sub = r_col1.text_input("科目名", value=item.get('subject', ''), key=f"sub_name_{i}", label_visibility="collapsed")
            score = r_col2.number_input("点数", value=0, key=f"sub_score_{i}", label_visibility="collapsed")
            target = r_col3.number_input("目標", value=0, key=f"sub_target_{i}", label_visibility="collapsed")
            diff = score - target
            diff_text = f"{diff:+}" if target > 0 else "-"
            r_col4.markdown(f"<div style='text-align: center; font-weight: bold; margin-top: 10px;'>{diff_text}</div>", unsafe_allow_html=True)
            
            if r_col5.button("🗑️", key=f"sub_del_{i}"):
                st.session_state.dynamic_scores.pop(i)
                st.rerun()
            score_results.append({"subject": sub, "score": score, "target": target, "diff": diff})

        if st.button("＋ 科目を追加"):
            st.session_state.dynamic_scores.append({'subject': ''})
            st.rerun()
            
    current_issue = st.text_area("課題認識・指導内容", key="in_issue")

    st.subheader("🚀 ネクストアクション")
    for i, action in enumerate(st.session_state.actions):
        with st.expander(f"Action {i+1}", expanded=True):
            ac1, ac2, ac3 = st.columns([2, 1, 2])
            st.session_state.actions[i]['subject'] = ac1.text_input("教科", value=action['subject'], key=f"s_{i}")
            st.session_state.actions[i]['priority'] = ac2.selectbox("優先", ["高", "中", "低"], key=f"p_{i}")
            st.session_state.actions[i]['deadline'] = ac3.text_input("期限", key=f"d_{i}", value=action['deadline'])
            st.session_state.actions[i]['policy'] = st.text_input("方針設定", key=f"pol_{i}", value=action.get('policy',''))
            st.session_state.actions[i]['specificTask'] = st.text_input("具体的タスク", key=f"t_{i}", value=action.get('specificTask',''))
            if st.button("アクション削除", key=f"del_{i}"):
                st.session_state.actions.pop(i)
                st.rerun()
    
    if st.button("＋ アクション追加"):
        st.session_state.actions.append({'subject': '', 'priority': '中', 'policy': '', 'specificTask': '', 'deadline': '次回まで'})
        st.rerun()

    if st.button("💾 この内容を保存する", type="primary"):
        if not student_name: st.error("生徒氏名を入力してください")
        else:
            full_data = {
                "scores": score_results,
                "actions": st.session_state.actions,
                "type": m_type,
                "exam_category": exam_category
            }
            new_row = pd.DataFrame([{
                "日付": date_val.strftime('%Y-%m-%d'), "種別": m_type, "担当メンター": mentor_name,
                "生徒氏名": student_name, "学年": grade, "文理": stream, "試験名": exam_name,
                "課題": current_issue, "データJSON": json.dumps(full_data, ensure_ascii=False)
            }])
            if save_data(new_row): st.success("保存完了！")

with tab_search:
    st.subheader("過去ログ検索")
    df = load_data()
    if not df.empty:
        search = st.text_input("生徒名検索")
        display_df = df[df['生徒氏名'].str.contains(search)] if search else df
        st.dataframe(display_df.drop(columns=["データJSON"]), use_container_width=True)

with tab_preview:
    st.subheader("📄 指導レポート出力")
    report_text = f"【{m_type}報告書】\n実施日: {date_val} / 担当: {mentor_name}\n生徒: {student_name}様 ({grade})\n\n"
    # (以下、レポート生成ロジックは以前と同様のため中略)
    st.code(report_text)
