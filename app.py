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
        creds_dict = dict(st.secrets["gspread_credentials"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

# --- 3. データロジック ---
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
        except:
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
            st.error(f"保存エラー: {e}"); return False
    return False

# --- 4. PDF生成関数 (簡易版) ---
def create_pdf(df, student_name):
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    # ※本番では日本語フォントの読み込みが必要ですが、ここでは標準フォントを使用
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, f"Mentoring Report: {student_name}")
    p.setFont("Helvetica", 10)
    y = 770
    for i, row in df.iterrows():
        p.drawString(100, y, f"[{row['日付']}] Mentor: {row['担当メンター']} / Issue: {row['課題'][:40]}...")
        y -= 20
        if y < 50: p.showPage(); y = 800
    p.save()
    buffer.seek(0)
    return buffer

# --- 5. セッション初期化 ---
for key, val in {'actions': [{'subject': '英語', 'priority': '高', 'deadline': '次回まで'}], 'prev_actions': [], 'dynamic_scores': [{'subject': '英語'}, {'subject': '数学'}]}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 6. UI構築 ---
st.title("🎓 ALOHA Mentoring Base Pro")
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="定期面談")

tab_new, tab_search, tab_stats = st.tabs(["📝 面談記録入力", "🔍 過去ログ検索", "📈 メンター統計"])

# --- タブ1: 入力 ---
with tab_new:
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        student_name = c1.text_input("生徒氏名")
        mentor_name = c2.text_input("担当メンター")
        date_val = c3.date_input("実施日", datetime.date.today())
        grade = c3.selectbox("学年", ["高1", "高2", "高3", "既卒"], index=2)
        stream = c2.radio("文理", ["理系", "文系"], horizontal=True)

    # 試験結果入力 (ズレ修正済み)
    with st.container(border=True):
        st.subheader("📊 試験結果")
        h_col = st.columns([2, 1, 1, 1, 0.5])
        titles = ["科目名", "点数", "目標", "差分", "削"]
        for col, t in zip(h_col, titles): col.caption(t)
        
        score_results = []
        for i, item in enumerate(st.session_state.dynamic_scores):
            r = st.columns([2, 1, 1, 1, 0.5])
            sub = r[0].text_input("科目", value=item.get('subject',''), key=f"s_{i}", label_visibility="collapsed")
            sc = r[1].number_input("点", value=0, key=f"sc_{i}", label_visibility="collapsed")
            tg = r[2].number_input("目", value=0, key=f"tg_{i}", label_visibility="collapsed")
            diff = sc - tg
            r[3].markdown(f"<div style='text-align:center;margin-top:10px;'>{diff:+}</div>", unsafe_allow_html=True)
            if r[4].button("🗑️", key=f"del_{i}"):
                st.session_state.dynamic_scores.pop(i); st.rerun()
            score_results.append({"subject": sub, "score": sc, "target": tg})
        if st.button("＋ 科目追加"): st.session_state.dynamic_scores.append({}); st.rerun()

    issue = st.text_area("課題認識")
    
    if st.button("💾 保存", type="primary"):
        new_row = pd.DataFrame([{"日付": date_val, "種別": m_type, "担当メンター": mentor_name, "生徒氏名": student_name, "学年": grade, "文理": stream, "試験名": "", "課題": issue, "データJSON": json.dumps({"scores": score_results, "actions": st.session_state.actions}, ensure_ascii=False)}])
        if save_data(new_row): st.success("保存完了！")

# --- タブ2: 検索 & PDF (①の実装) ---
with tab_search:
    st.subheader("🔍 生徒の歩みを振り返る")
    df = load_data()
    if not df.empty:
        target_student = st.selectbox("生徒を選択", df['生徒氏名'].unique())
        col_d1, col_d2 = st.columns(2)
        start_d = col_d1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=90))
        end_d = col_d2.date_input("終了日", datetime.date.today())
        
        filtered = df[(df['生徒氏名'] == target_student) & (df['日付'] >= start_d) & (df['日付'] <= end_d)]
        st.dataframe(filtered.drop(columns="データJSON"), use_container_width=True)
        
        if st.button("📄 期間内のレポートをPDF出力"):
            pdf_file = create_pdf(filtered, target_student)
            st.download_button("📥 PDFをダウンロード", pdf_file, file_name=f"report_{target_student}.pdf")

# --- タブ3: 統計 (②の実装) ---
with tab_stats:
    st.subheader("👥 メンター出席・指導回数")
    if not df.empty:
        stats = df['担当メンター'].value_counts().reset_index()
        stats.columns = ['メンター名', '指導回数']
        st.bar_chart(stats.set_index('メンター名'))
        st.table(stats)
