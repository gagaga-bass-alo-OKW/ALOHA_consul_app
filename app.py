import streamlit as st
import pandas as pd
import datetime
import json
import gspread
from google.oauth2.service_account import Credentials
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from io import BytesIO
import streamlit.components.v1 as components

# --- 1. 基本設定 ---
st.set_page_config(page_title="ALOHA Mentoring Base Pro", layout="wide")
COLUMNS = ["日付", "種別", "担当メンター", "生徒氏名", "学年", "文理", "試験名", "課題", "データJSON", "講師用メモ"]

# --- 2. ブラウザ離脱防止アラート ---
components.html(
    """
    <script>
    window.onbeforeunload = function() { return "入力内容が保存されない可能性があります。離れますか？"; };
    </script>
    """, height=0,
)

# --- 3. Google Sheets 接続 ---
def get_gspread_client():
    try:
        if "gspread_credentials" not in st.secrets: return None
        creds_dict = dict(st.secrets["gspread_credentials"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: {e}"); return None

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
        except: pass
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

def create_pdf(df, student_name):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, f"Mentoring Summary: {student_name}")
    p.setFont("Helvetica", 10)
    y = 770
    for i, row in df.iterrows():
        p.drawString(100, y, f"Date: {row['日付']} | Mentor: {row['担当メンター']}")
        y -= 15
        issue_text = str(row['課題']).replace('\n', ' ')
        p.drawString(120, y, f"Issue: {issue_text[:60]}...")
        y -= 25
        if y < 50: p.showPage(); y = 800
    p.save(); buffer.seek(0)
    return buffer

# --- 6. セッション状態初期化 ---
if 'actions' not in st.session_state: st.session_state.actions = []
if 'prev_actions' not in st.session_state: st.session_state.prev_actions = []
if 'dynamic_scores' not in st.session_state: st.session_state.dynamic_scores = []

# --- 7. メインUI ---
st.title("🎓 ALOHA Mentoring Base Pro")

# 指導種別のデフォルトを「家庭教師」に変更
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="家庭教師")

tab_new, tab_alert, tab_search, tab_stats, tab_preview = st.tabs([
    "📝 面談記録入力", "⚠️ 未提出アラート", "🔍 過去ログ・PDF", "📈 統計", "📄 レポート出力"
])

df_all = load_data()

with tab_new:
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        student_name = c1.text_input("生徒氏名")
        if c1.button("🔄 前回データを検索・読み込み"):
            last_row = get_last_session(student_name)
            if last_row is not None:
                last_data = json.loads(last_row['データJSON'])
                st.session_state.prev_actions = last_data.get('actions', [])
                st.success(f"{last_row['日付']}のデータを取得。各タブに入力してください。")
            else: st.warning("過去データなし")
        mentor_name = c2.text_input("担当メンター")
        stream = c2.radio("文理", ["理系", "文系"], horizontal=True)
        date_val = c3.date_input("実施日", datetime.date.today())
        grade = c3.selectbox("学年", ["中1", "中2", "中3", "高1", "高2", "高3", "既卒"], index=5)

    sub1, sub2, sub3 = st.tabs(["✅ 1. 前回振り返り", "📊 2. 試験結果・課題認識", "🚀 3. ネクストアクション"])

    with sub1:
        if st.session_state.prev_actions:
            for i, p in enumerate(st.session_state.prev_actions):
                with st.container(border=True):
                    st.markdown(f"**【{p.get('subject','科目不明')}】**")
                    txt = f"方針: {p.get('policy','')}\n対象: {p.get('item','')}\n量: {p.get('amount','')}\n方法: {p.get('method','')}\n基準: {p.get('goal','')}"
                    st.caption(txt.replace('\n', ' | '))
                    col_a, col_b = st.columns([1, 2])
                    st.session_state.prev_actions[i]['status_num'] = col_a.number_input("達成度(%)", 0, 100, 100, 5, key=f"p_n_{i}")
                    st.session_state.prev_actions[i]['review_comment'] = col_b.text_area("進捗詳細・テスト結果", key=f"p_r_{i}", height=70)
        else: st.info("生徒名入力後に前回データを読み込んでください。")

    with sub2:
        exam_name = st.text_input("試験名", placeholder="例: 中間テスト")
        for i, item in enumerate(st.session_state.dynamic_scores):
            r = st.columns([2, 1, 1, 1, 0.5])
            sub_val = r[0].text_input("科目", value=item.get('subject',''), key=f"s_n_{i}")
            sc_val = r[1].number_input("点", value=item.get('score',0), key=f"s_s_{i}")
            tg_val = r[2].number_input("目標", value=item.get('target',0), key=f"s_t_{i}")
            r[3].markdown(f"<div style='margin-top:25px;'>{sc_val-tg_val:+}</div>", unsafe_allow_html=True)
            if r[4].button("🗑️", key=f"s_d_{i}"):
                st.session_state.dynamic_scores.pop(i); st.rerun()
            st.session_state.dynamic_scores[i] = {"subject": sub_val, "score": sc_val, "target": tg_val}
        if st.button("＋ 科目追加"): st.session_state.dynamic_scores.append({}); st.rerun()
        st.divider()
        current_issue = st.text_area("課題認識・指導内容（レポート用）", height=150)
        mentor_private_memo = st.text_area("内部用メモ", height=70)

    with sub3:
        if st.session_state.prev_actions and st.button("📋 前回のアクションをコピー", use_container_width=True):
            st.session_state.actions = [dict(pa, priority=pa.get('priority','中')) for pa in st.session_state.prev_actions]
            st.rerun()
        for i in range(len(st.session_state.actions)):
            with st.expander(f"Action {i+1} : {st.session_state.actions[i].get('subject','')}", expanded=True):
                c_a, c_b, c_c = st.columns([2, 1, 2])
                st.session_state.actions[i]['subject'] = c_a.text_input("教科", st.session_state.actions[i].get('subject',''), key=f"as_{i}")
                st.session_state.actions[i]['priority'] = c_b.selectbox("優先", ["高","中","低"], index=["高","中","低"].index(st.session_state.actions[i].get('priority','中')), key=f"ap_{i}")
                st.session_state.actions[i]['deadline'] = c_c.text_input("期限", st.session_state.actions[i].get('deadline','次回まで'), key=f"ad_{i}")
                st.session_state.actions[i]['policy'] = st.text_area("方針", st.session_state.actions[i].get('policy',''), key=f"apol_{i}", height=70)
                l, r = st.columns(2)
                st.session_state.actions[i]['item'] = l.text_input("①対象", st.session_state.actions[i].get('item',''), key=f"ai_{i}")
                st.session_state.actions[i]['amount'] = r.text_input("②量", st.session_state.actions[i].get('amount',''), key=f"aa_{i}")
                l2, r2 = st.columns(2)
                st.session_state.actions[i]['method'] = l2.text_area("③方法", st.session_state.actions[i].get('method',''), key=f"am_{i}")
                st.session_state.actions[i]['goal'] = r2.text_area("④基準", st.session_state.actions[i].get('goal',''), key=f"ag_{i}")
                if st.button("削除", key=f"adel_{i}"): st.session_state.actions.pop(i); st.rerun()
        if st.button("＋ 追加"): st.session_state.actions.append({'priority':'中'}); st.rerun()
        st.divider()
        if st.button("💾 データベースに保存", type="primary", use_container_width=True):
            if not student_name: st.error("生徒名を入力してください")
            else:
                full_json = {"scores": st.session_state.dynamic_scores, "actions": st.session_state.actions, "prev_review": st.session_state.prev_actions}
                new_row = pd.DataFrame([{
                    "日付": date_val.strftime('%Y-%m-%d'), "種別": m_type, "担当メンター": mentor_name, "生徒氏名": student_name, 
                    "学年": grade, "文理": stream, "試験名": exam_name, "課題": current_issue, 
                    "データJSON": json.dumps(full_json, ensure_ascii=False), "講師用メモ": mentor_private_memo
                }])
                if save_data(new_row): st.success("保存成功！レポート出力タブを確認してください。")

with tab_alert:
    st.subheader("⚠️ 報告未提出チェック")
    if not df_all.empty:
        df_kt = df_all[df_all['種別'] == "家庭教師"]
        if not df_kt.empty:
            latest = df_kt.groupby('生徒氏名')['日付'].max().reset_index()
            missing = latest[latest['日付'] < (datetime.date.today() - datetime.timedelta(days=7))]
            if not missing.empty:
                missing['経過日数'] = (datetime.date.today() - missing['日付']).apply(lambda x: x.days)
                st.table(missing.sort_values('経過日数', ascending=False))
            else: st.success("滞りなし")

with tab_search:
    st.subheader("🔍 過去ログ検索")
    if not df_all.empty:
        target_s = st.selectbox("生徒を選択", ["すべて"] + list(df_all['生徒氏名'].unique()))
        filtered = df_all[df_all['生徒氏名'] == target_s] if target_s != "すべて" else df_all
        st.dataframe(filtered.drop(columns=["データJSON"]), use_container_width=True)
        if target_s != "すべて" and not filtered.empty:
            pdf = create_pdf(filtered, target_s)
            st.download_button("📄 PDFダウンロード", pdf, f"Report_{target_s}.pdf")

with tab_stats:
    st.subheader("📈 指導統計")
    if not df_all.empty:
        df_stats = df_all.copy(); df_stats['日付'] = pd.to_datetime(df_stats['日付'])
        pivot = df_stats.groupby([pd.Grouper(key='日付', freq='W-MON'), '担当メンター']).size().unstack(fill_value=0)
        st.bar_chart(pivot)

with tab_preview:
    st.subheader("📄 LINE用レポート")
    report = f"【{m_type}報告書】\n実施日: {date_val}\n担当: {mentor_name}\n生徒: {student_name}様\n\n"
    if st.session_state.prev_actions:
        report += "■前回宿題の達成状況\n"
        for p in st.session_state.prev_actions:
            report += f"・{p.get('subject', '科目なし')}: 達成度 {p.get('status_num', 0)}%\n  [結果] {p.get('review_comment', '特記なし')}\n"
        report += "\n"
    report += f"■課題認識・指導内容\n{current_issue}\n\n■ネクストアクション\n"
    for i, a in enumerate(st.session_state.actions):
        report += f"{i+1}. 【{a.get('subject', '科目なし')}】 ({a.get('deadline', '期限なし')})\n"
        if a.get('item'): report += f"   - 対象: {a['item']}\n"
        if a.get('amount'): report += f"   - ペース: {a['amount']}\n"
        if a.get('method'): report += f"   - 方法: {a['method']}\n"
        if a.get('goal'): report += f"   - 完了基準: {a['goal']}\n"
        report += "\n"
    st.code(report, language="text")
