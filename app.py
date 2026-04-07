import streamlit as st
import pandas as pd
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

# --- 1. 基本設定 ---
st.set_page_config(page_title="ALOHA Mentoring Base Pro", layout="wide")
COLUMNS = ["日付", "種別", "担当メンター", "生徒氏名", "学年", "文理", "試験名", "課題", "データJSON"]

# --- 2. Google Sheets 接続関数 ---
def get_gspread_client():
    try:
        if "gspread_credentials" not in st.secrets:
            st.error("Secretsに [gspread_credentials] が見つかりません。")
            return None
        # 最も安定する直接辞書変換方式
        creds_dict = dict(st.secrets["gspread_credentials"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

# --- 3. データ読み書きロジック ---
def load_data():
    client = get_gspread_client()
    if client:
        try:
            sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.worksheet("logs")
            data = worksheet.get_all_records()
            if data:
                df = pd.DataFrame(data)
                df['日付'] = pd.to_datetime(df['日付']).dt.date
                return df
            return pd.DataFrame(columns=COLUMNS)
        except Exception:
            return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)

def save_data(new_row_df):
    client = get_gspread_client()
    if client:
        try:
            sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.worksheet("logs")
            worksheet.append_rows(new_row_df.values.tolist())
            return True
        except Exception as e:
            st.error(f"保存エラー: {e}")
            return False
    return False

def get_last_session(student_name):
    df = load_data()
    if not df.empty and student_name:
        res = df[df['生徒氏名'].astype(str) == student_name]
        if not res.empty:
            return res.iloc[-1]
    return None

# --- 4. PDF生成関数 ---
def create_pdf(df, student_name):
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    # ※標準フォントのため日本語は「-」等に化ける可能性があります。
    # 運用上、日本語が必要な場合は.ttfファイルを読み込む処理が必要です。
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, f"Mentoring Summary: {student_name}")
    p.setFont("Helvetica", 10)
    y = 770
    for i, row in df.iterrows():
        p.drawString(100, y, f"Date: {row['日付']} | Mentor: {row['担当メンター']}")
        y -= 15
        p.drawString(120, y, f"Issue: {str(row['課題'])[:60]}...")
        y -= 25
        if y < 50:
            p.showPage()
            y = 800
    p.save()
    buffer.seek(0)
    return buffer

# --- 5. セッション状態の初期化 ---
if 'actions' not in st.session_state:
    st.session_state.actions = [{'subject': '英語', 'priority': '高', 'deadline': '次回まで'}]
if 'prev_actions' not in st.session_state:
    st.session_state.prev_actions = []
if 'dynamic_scores' not in st.session_state:
    st.session_state.dynamic_scores = [{'subject': '英語'}, {'subject': '数学'}]

# --- 6. メインUI ---
st.title("🎓 ALOHA Mentoring Base Pro")
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="定期面談")

tab_new, tab_search, tab_stats, tab_preview = st.tabs(["📝 面談記録入力", "🔍 過去ログ・PDF", "📈 メンター統計", "📄 レポート出力"])

# --- タブ1: 面談記録入力 ---
with tab_new:
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            student_name = st.text_input("生徒氏名")
            if st.button("🔄 前回データを読み込む"):
                last_row = get_last_session(student_name)
                if last_row is not None:
                    try:
                        last_data = json.loads(last_row['データJSON'])
                        st.session_state.prev_actions = last_data.get('actions', [])
                        st.success(f"{last_row['日付']} のデータを読み込みました")
                    except: st.error("JSONデータの解析に失敗しました")
                else: st.warning("過去のデータが見つかりません")
        with c2:
            mentor_name = st.text_input("担当メンター")
            stream = st.radio("文理", ["理系", "文系"], horizontal=True)
        with c3:
            date_val = st.date_input("実施日", datetime.date.today())
            grade = st.selectbox("学年", ["中1", "中2", "中3", "高1", "高2", "高3", "既卒"], index=5)

    with st.container(border=True):
        st.subheader("📊 試験結果・目標設定")
        exam_name = st.text_input("試験名 (例: 1学期中間)")
        h = st.columns([2, 1, 1, 1, 0.5])
        titles = ["科目名", "今回の点数", "次回の目標", "差分", "削除"]
        for col, t in zip(h, titles): col.caption(t)
        
        score_results = []
        for i, item in enumerate(st.session_state.dynamic_scores):
            r = st.columns([2, 1, 1, 1, 0.5])
            sub = r[0].text_input("科目", value=item.get('subject',''), key=f"sub_{i}", label_visibility="collapsed")
            score = r[1].number_input("点", value=0, key=f"sc_{i}", label_visibility="collapsed")
            target = r[2].number_input("目", value=0, key=f"tg_{i}", label_visibility="collapsed")
            diff = score - target
            r[3].markdown(f"<div style='text-align:center;padding-top:10px;'>{diff:+}</div>", unsafe_allow_html=True)
            if r[4].button("🗑️", key=f"sd_{i}"):
                st.session_state.dynamic_scores.pop(i); st.rerun()
            score_results.append({"subject": sub, "score": score, "target": target})
        if st.button("＋ 科目を追加"):
            st.session_state.dynamic_scores.append({'subject': ''}); st.rerun()

    current_issue = st.text_area("課題認識・指導内容")

    if st.button("💾 この内容を保存する", type="primary"):
        if not student_name: st.error("生徒氏名を入力してください")
        else:
            full_json = {"scores": score_results, "actions": st.session_state.actions}
            new_row = pd.DataFrame([{
                "日付": date_val.strftime('%Y-%m-%d'), "種別": m_type, "担当メンター": mentor_name,
                "生徒氏名": student_name, "学年": grade, "文理": stream, "試験名": exam_name,
                "課題": current_issue, "データJSON": json.dumps(full_json, ensure_ascii=False)
            }])
            if save_data(new_row): st.success("保存完了！")

# --- タブ2: 過去ログ・PDF出力 ---
with tab_search:
    st.subheader("🔍 過去ログ検索と歩みの出力")
    df_logs = load_data()
    if not df_logs.empty:
        col_f1, col_f2 = st.columns(2)
        target_s = col_f1.selectbox("生徒を選択", ["すべて"] + list(df_logs['生徒氏名'].unique()))
        
        # 期間指定
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=90))
        end_date = col_d2.date_input("終了日", datetime.date.today())

        filtered_df = df_logs.copy()
        if target_s != "すべて":
            filtered_df = filtered_df[filtered_df['生徒氏名'] == target_s]
        filtered_df = filtered_df[(filtered_df['日付'] >= start_date) & (filtered_df['日付'] <= end_date)]

        st.dataframe(filtered_df.drop(columns=["データJSON"], errors='ignore'), use_container_width=True)

        if target_s != "すべて" and not filtered_df.empty:
            if st.button(f"📄 {target_s}様の期間内レポートをPDFで作成"):
                pdf_bytes = create_pdf(filtered_df, target_s)
                st.download_button("📥 PDFをダウンロード", pdf_bytes, file_name=f"{target_s}_report.pdf")
    else: st.info("データがありません")

# --- タブ3: メンター統計 ---
with tab_stats:
    st.subheader("📈 メンター別出席・指導回数")
    if not df_logs.empty:
        mentor_counts = df_logs['担当メンター'].value_counts().reset_index()
        mentor_counts.columns = ['メンター名', '指導回数']
        st.bar_chart(mentor_counts.set_index('メンター名'))
        st.table(mentor_counts)
    else: st.info("統計データがありません")

# --- タブ4: レポートプレビュー ---
with tab_preview:
    st.subheader("📄 指導レポート出力")
    report = f"【{m_type}報告書】\n実施日: {date_val} / 担当: {mentor_name}\n生徒: {student_name}様\n\n■課題認識\n{current_issue}"
    st.code(report)
