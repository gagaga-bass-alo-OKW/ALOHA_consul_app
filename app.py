import streamlit as st
import pandas as pd
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from reportlab.pdfgen import canvas
from io import BytesIO
import streamlit.components.v1 as components

# --- 1. 基本設定 ---
st.set_page_config(page_title="ALOHA Mentoring Base Pro", layout="wide")
COLUMNS = ["日付", "種別", "担当メンター", "生徒氏名", "学年", "文理", "試験名", "課題", "データJSON", "講師用メモ"]

# --- 2. ブラウザ離脱防止アラート (JavaScript) ---
# タブを閉じたりリロードしようとした時に警告を出します。
components.html(
    """
    <script>
    window.onbeforeunload = function() {
        return "入力内容が保存されない可能性があります。このサイトを離れますか？";
    };
    </script>
    """,
    height=0,
)

# --- 3. Google Sheets 接続関数 ---
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
        st.error(f"認証エラー: {e}"); return None

# --- 4. データ管理ロジック ---
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
        except: return pd.DataFrame(columns=COLUMNS)
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

def get_last_session(student_name):
    df = load_data()
    if not df.empty and student_name:
        res = df[df['生徒氏名'].astype(str) == student_name]
        if not res.empty: return res.iloc[-1]
    return None

# --- 5. PDF生成 ---
def create_pdf(df, student_name):
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, f"Mentoring Summary: {student_name}")
    p.setFont("Helvetica", 10)
    y = 770
    for i, row in df.iterrows():
        p.drawString(100, y, f"Date: {row['日付']} | Mentor: {row['担当メンター']}")
        y -= 15
        p.drawString(120, y, f"Issue: {str(row['課題'])[:60]}...")
        y -= 25
        if y < 50: p.showPage(); y = 800
    p.save()
    buffer.seek(0)
    return buffer

# --- 6. セッション状態初期化 ---
if 'actions' not in st.session_state:
    st.session_state.actions = [{'subject': '英語', 'priority': '高', 'policy': '', 'specificTask': '', 'deadline': '次回まで'}]
if 'prev_actions' not in st.session_state:
    st.session_state.prev_actions = []
if 'dynamic_scores' not in st.session_state:
    st.session_state.dynamic_scores = [{'subject': '英語'}, {'subject': '数学'}]

# --- 7. メインUI ---
st.title("🎓 ALOHA Mentoring Base Pro")
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="定期面談")

tab_new, tab_search, tab_stats, tab_preview = st.tabs(["📝 面談記録入力", "🔍 過去ログ・PDF", "📈 統計", "📄 レポート出力"])

with tab_new:
    # --- 未提出アラート ---
    df_all = load_data()
    if not df_all.empty:
        latest_dates = df_all.groupby('生徒氏名')['日付'].max().reset_index()
        alert_threshold = 7
        missing = latest_dates[latest_dates['日付'] < (datetime.date.today() - datetime.timedelta(days=alert_threshold))]
        if not missing.empty:
            with st.expander(f"⚠️ 指導報告の未提出アラート ({len(missing)}名)", expanded=True):
                for _, r in missing.iterrows():
                    st.warning(f"**{r['生徒氏名']}**: 最終指導日 {r['日付']}（{alert_threshold}日以上経過）")

    st.link_button("🚀 Googleフォームを開く", "https://docs.google.com/forms/d/e/1FAIpQLSdLYRJaDRWkYImkm3pcwDY_lywllRQCcoDWm64XMKsdu2el0w/viewform", type="primary", use_container_width=True)
    st.divider()

    # 基本情報
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        student_name = c1.text_input("生徒氏名")
        if c1.button("🔄 前回データを読み込む"):
            last_row = get_last_session(student_name)
            if last_row is not None:
                last_data = json.loads(last_row['データJSON'])
                st.session_state.prev_actions = last_data.get('actions', [])
                st.success(f"{last_row['日付']} のデータを読み込みました")
            else: st.warning("過去のデータが見つかりません")
        mentor_name = c2.text_input("担当メンター")
        stream = c2.radio("文理", ["理系", "文系"], horizontal=True)
        date_val = c3.date_input("実施日", datetime.date.today())
        grade = c3.selectbox("学年", ["中1", "中2", "中3", "高1", "高2", "高3", "既卒"], index=5)

    # 前回タスク確認
    if st.session_state.prev_actions:
        with st.expander("✅ 前回タスクの達成度確認", expanded=True):
            for i, p_act in enumerate(st.session_state.prev_actions):
                col_a, col_b = st.columns([3, 1])
                col_a.write(f"**{p_act.get('subject','')}**: {p_act.get('specificTask','')}")
                p_act['status'] = col_b.select_slider("達成度", options=["×", "△", "◯", "◎"], value="◯", key=f"p_status_{i}")

    # 試験結果
    with st.container(border=True):
        st.subheader("📊 試験結果・目標設定")
        exam_name = st.text_area("試験名 (例: 1学期中間)", height=68)
        score_results = []
        for i, item in enumerate(st.session_state.dynamic_scores):
            r = st.columns([2, 1, 1, 1, 0.5])
            sub = r[0].text_input("科目", value=item.get('subject',''), key=f"sub_{i}")
            sc = r[1].number_input("点", value=0, key=f"sc_{i}")
            tg = r[2].number_input("目", value=0, key=f"tg_{i}")
            r[3].markdown(f"<div style='text-align:center;margin-top:25px;'>{sc-tg:+}</div>", unsafe_allow_html=True)
            if r[4].button("🗑️", key=f"sd_{i}"):
                st.session_state.dynamic_scores.pop(i); st.rerun()
            score_results.append({"subject": sub, "score": sc, "target": tg})
        if st.button("＋ 科目追加"): st.session_state.dynamic_scores.append({}); st.rerun()

    current_issue = st.text_area("課題認識・指導内容 (生徒への共有用)", height=150)
    
    with st.expander("🔐 講師用メモ (生徒には共有されません)", expanded=False):
        mentor_private_memo = st.text_area("内部引き継ぎ事項など", key="private_memo", height=150)

    # ネクストアクション
    st.subheader("🚀 ネクストアクション")
    for i, action in enumerate(st.session_state.actions):
        with st.expander(f"Action {i+1}", expanded=True):
            ac1, ac2, ac3 = st.columns([2, 1, 2])
            st.session_state.actions[i]['subject'] = ac1.text_input("教科", value=action['subject'], key=f"as_{i}")
            st.session_state.actions[i]['priority'] = ac2.selectbox("優先", ["高", "中", "低"], key=f"ap_{i}")
            st.session_state.actions[i]['deadline'] = ac3.text_area("期限", value=action['deadline'], key=f"ad_{i}", height=68)
            st.session_state.actions[i]['policy'] = st.text_area("方針設定", value=action.get('policy',''), key=f"apol_{i}", height=100)
            st.session_state.actions[i]['specificTask'] = st.text_area("具体的タスク", value=action.get('specificTask',''), key=f"atask_{i}", height=100)
            if st.button("アクション削除", key=f"adel_{i}"):
                st.session_state.actions.pop(i); st.rerun()
    if st.button("＋ アクション追加"):
        st.session_state.actions.append({'subject': '', 'priority': '中', 'policy': '', 'specificTask': '', 'deadline': '次回まで'}); st.rerun()

    if st.button("💾 データベースに保存する", type="primary"):
        if not student_name: st.error("生徒氏名を入力してください")
        else:
            full_json = {"scores": score_results, "actions": st.session_state.actions}
            new_row = pd.DataFrame([{
                "日付": date_val.strftime('%Y-%m-%d'), "種別": m_type, "担当メンター": mentor_name, 
                "生徒氏名": student_name, "学年": grade, "文理": stream, "試験名": exam_name, 
                "課題": current_issue, "データJSON": json.dumps(full_json, ensure_ascii=False),
                "講師用メモ": mentor_private_memo
            }])
            if save_data(new_row): st.success("保存完了！")

# --- タブ2: 検索 & PDF ---
with tab_search:
    st.subheader("🔍 過去ログ検索と歩みの出力")
    if not df_all.empty:
        target_s = st.selectbox("生徒を選択", ["すべて"] + list(df_all['生徒氏名'].unique()))
        col_d1, col_d2 = st.columns(2)
        start_d = col_d1.date_input("開始日", datetime.date.today() - datetime.timedelta(days=90))
        end_d = col_d2.date_input("終了日", datetime.date.today())
        filtered = df_all.copy()
        if target_s != "すべて": filtered = filtered[filtered['生徒氏名'] == target_s]
        filtered = filtered[(filtered['日付'] >= start_d) & (filtered['日付'] <= end_d)]
        st.dataframe(filtered.drop(columns=["データJSON"]), use_container_width=True)
        if target_s != "すべて" and not filtered.empty:
            if st.button(f"📄 {target_s}様のレポートをPDF出力"):
                pdf = create_pdf(filtered, target_s); st.download_button("📥 ダウンロード", pdf, f"{target_s}.pdf")

# --- タブ3: 統計 ---
with tab_stats:
    st.subheader("📈 指導統計")
    if not df_all.empty:
        unit_map = {"日ごと": "D", "週ごと": "W-MON", "月ごと": "ME", "年ごと": "YE"}
        selected_unit = st.selectbox("集計単位", list(unit_map.keys()), index=1)
        df_stats = df_all.copy()
        df_stats['日付'] = pd.to_datetime(df_stats['日付'])
        pivot_df = df_stats.groupby([pd.Grouper(key='日付', freq=unit_map[selected_unit]), '担当メンター']).size().unstack(fill_value=0)
        st.bar_chart(pivot_df)
        st.table(pivot_df)

# --- タブ4: レポートプレビュー ---
with tab_preview:
    st.subheader("📄 指導レポート出力")
    report = f"【{m_type}報告書】\n実施日: {date_val}\n担当: {mentor_name}\n生徒: {student_name}様\n\n■課題認識\n{current_issue}\n\n■今後のアクション\n"
    for a in st.session_state.actions:
        report += f"・{a['subject']}: {a['specificTask']} ({a['deadline']})\n"
    st.code(report)
