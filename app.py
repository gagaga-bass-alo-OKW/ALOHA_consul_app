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
import copy

# --- 1. 基本設定 ---
st.set_page_config(page_title="ALOHA Mentoring Base Pro", layout="wide")
COLUMNS = ["日付", "種別", "担当メンター", "生徒氏名", "学年", "文理", "試験名", "課題", "データJSON", "講師用メモ"]

# --- 2. ブラウザ離脱防止アラート ---
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
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 800, f"Mentoring Summary: {student_name}")
    p.setFont("Helvetica", 10)
    y = 770
    for i, row in df.iterrows():
        p.drawString(100, y, f"Date: {row['日付']} | Mentor: {row['担当メンター']} | Type: {row['種別']}")
        y -= 15
        issue_text = str(row['課題']).replace('\n', ' ')
        p.drawString(120, y, f"Issue: {issue_text[:60]}...")
        y -= 25
        if y < 50: 
            p.showPage()
            y = 800
            p.setFont("Helvetica", 10)
    p.save()
    buffer.seek(0)
    return buffer

# --- 6. セッション状態初期化 ---
if 'actions' not in st.session_state:
    st.session_state.actions = []
if 'prev_actions' not in st.session_state:
    st.session_state.prev_actions = []
if 'dynamic_scores' not in st.session_state:
    st.session_state.dynamic_scores = []

# --- 7. メインUI ---
st.title("🎓 ALOHA Mentoring Base Pro")
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="定期面談")

tab_new, tab_alert, tab_search, tab_stats, tab_preview = st.tabs([
    "📝 面談記録入力", "⚠️ 未提出アラート", "🔍 過去ログ・PDF", "📈 統計", "📄 レポート出力"
])

df_all = load_data()

# --- タブ1: 面談記録入力 ---
with tab_new:
    st.link_button("🚀 Googleフォームを開く", "https://docs.google.com/forms/d/e/1FAIpQLSdLYRJaDRWkYImkm3pcwDY_lywllRQCcoDWm64XMKsdu2el0w/viewform", type="primary", use_container_width=True)
    st.divider()

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        student_name = c1.text_input("生徒氏名")
        
        if c1.button("🔄 前回データを読み込む"):
            last_row = get_last_session(student_name)
            if last_row is not None:
                last_data = json.loads(last_row['データJSON'])
                st.session_state.prev_actions = last_data.get('actions', [])
                st.success(f"{last_row['日付']} のデータを取得しました。下に振り返り欄が表示されます。")
            else: st.warning("過去のデータが見つかりません")
            
        mentor_name = c2.text_input("担当メンター")
        stream = c2.radio("文理", ["理系", "文系"], horizontal=True)
        date_val = c3.date_input("実施日", datetime.date.today())
        grade = c3.selectbox("学年", ["中1", "中2", "中3", "高1", "高2", "高3", "既卒"], index=5)

    # --- ①前回タスクの振り返り（四指標表示の修正） ---
    if st.session_state.prev_actions:
        with st.expander("✅ 前回タスクの振り返り（達成度・進捗詳細）", expanded=True):
            for i, p_act in enumerate(st.session_state.prev_actions):
                st.markdown(f"**【{p_act.get('subject','科目なし')}】**")
                
                # 四指標を詳細に表示
                details = []
                if p_act.get('policy'): details.append(f"**方針**: {p_act['policy']}")
                if p_act.get('item'):   details.append(f"**①対象**: {p_act['item']}")
                if p_act.get('amount'): details.append(f"**②量**: {p_act['amount']}")
                if p_act.get('method'): details.append(f"**③方法**: {p_act['method']}")
                if p_act.get('goal'):   details.append(f"**④基準**: {p_act['goal']}")
                
                if details:
                    st.markdown("<br>".join(details), unsafe_allow_html=True)
                
                col_rev1, col_rev2 = st.columns([1, 2])
                # 振り返り内容をセッションに保持
                st.session_state.prev_actions[i]['status_num'] = col_rev1.number_input(f"達成度(%) - {p_act.get('subject')}", min_value=0, max_value=100, value=100, step=5, key=f"p_num_{i}")
                st.session_state.prev_actions[i]['review_comment'] = col_rev2.text_area(f"進捗・テスト結果詳細", key=f"p_rev_{i}", height=100, placeholder="具体量やテストの点数を記入")
                st.divider()

    with st.container(border=True):
        st.subheader("📊 試験結果・目標設定")
        exam_name = st.text_area("試験名", height=68)
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
        if st.button("＋ 試験科目追加"): st.session_state.dynamic_scores.append({}); st.rerun()

    current_issue = st.text_area("課題認識・指導内容", height=150)
    with st.expander("🔐 講師用メモ", expanded=False):
        mentor_private_memo = st.text_area("内部引き継ぎ", key="private_memo", height=150)

    st.subheader("🚀 ネクストアクション")
    
    # --- ②コピペロジックの修正（1番目も確実にコピー） ---
    if st.session_state.prev_actions:
        if st.button("📋 前回のアクションを今回の入力欄にコピーする", use_container_width=True):
            copied_list = []
            for pa in st.session_state.prev_actions:
                # 辞書の中身を確実に新しいオブジェクトとしてコピー
                entry = {
                    'subject': pa.get('subject', ''),
                    'priority': pa.get('priority', '中'),
                    'deadline': pa.get('deadline', '次回まで'),
                    'policy': pa.get('policy', ''),
                    'item': pa.get('item', '') or pa.get('specificTask', ''),
                    'amount': pa.get('amount', ''),
                    'method': pa.get('method', ''),
                    'goal': pa.get('goal', '')
                }
                copied_list.append(entry)
            st.session_state.actions = copied_list
            st.rerun()

    # アクション入力
    for i in range(len(st.session_state.actions)):
        action = st.session_state.actions[i]
        with st.expander(f"Action {i+1} : {action.get('subject', '新規アクション')}", expanded=True):
            ac1, ac2, ac3 = st.columns([2, 1, 2])
            st.session_state.actions[i]['subject'] = ac1.text_input("教科", value=action.get('subject',''), key=f"as_{i}")
            
            p_list = ["高", "中", "低"]
            cur_p = action.get('priority', '中')
            p_idx = p_list.index(cur_p) if cur_p in p_list else 1
            st.session_state.actions[i]['priority'] = ac2.selectbox("優先", p_list, index=p_idx, key=f"ap_{i}")
            
            st.session_state.actions[i]['deadline'] = ac3.text_input("期限", value=action.get('deadline','次回まで'), key=f"ad_{i}")
            st.session_state.actions[i]['policy'] = st.text_area("方針", value=action.get('policy',''), key=f"apol_{i}", height=70)
            
            c_a, c_b = st.columns(2)
            st.session_state.actions[i]['item'] = c_a.text_input("① 対象", value=action.get('item',''), key=f"aitem_{i}")
            st.session_state.actions[i]['amount'] = c_b.text_input("② 量・頻度", value=action.get('amount',''), key=f"aamt_{i}")
            
            c_c, c_d = st.columns(2)
            st.session_state.actions[i]['method'] = c_c.text_area("③ 方法", value=action.get('method',''), key=f"ameth_{i}", height=100)
            st.session_state.actions[i]['goal'] = c_d.text_area("④ 基準", value=action.get('goal',''), key=f"agoal_{i}", height=100)
            
            if st.button("アクション削除", key=f"adel_{i}"):
                st.session_state.actions.pop(i); st.rerun()
    
    if st.button("＋ アクション追加"):
        st.session_state.actions.append({'subject': '', 'priority': '中', 'deadline': '次回まで', 'policy': '', 'item': '', 'amount': '', 'method': '', 'goal': ''})
        st.rerun()

    if st.button("💾 データベースに保存する", type="primary"):
        if not student_name: st.error("生徒氏名を入力してください")
        else:
            full_json = {"scores": score_results, "actions": st.session_state.actions, "prev_review": st.session_state.prev_actions}
            new_row = pd.DataFrame([{
                "日付": date_val.strftime('%Y-%m-%d'), "種別": m_type, "担当メンター": mentor_name, 
                "生徒氏名": student_name, "学年": grade, "文理": stream, "試験名": exam_name, 
                "課題": current_issue, "データJSON": json.dumps(full_json, ensure_ascii=False),
                "講師用メモ": mentor_private_memo
            }])
            if save_data(new_row): st.success("保存完了しました！")

# --- タブ3: 過去ログ・PDF出力 ---
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
            pdf_data = create_pdf(filtered, target_s)
            st.download_button(label=f"📄 {target_s}様の指導履歴をPDFダウンロード", data=pdf_data, file_name=f"Report_{target_s}.pdf", mime="application/pdf")

# --- タブ5: レポート出力 ---
with tab_preview:
    st.subheader("📄 指導レポート出力")
    report = f"【{m_type}報告書】\n実施日: {date_val}\n担当: {mentor_name}\n生徒: {student_name}様\n\n"
    
    if st.session_state.prev_actions:
        report += "■前回宿題の達成状況\n"
        for p in st.session_state.prev_actions:
            report += f"・{p.get('subject', '科目なし')}: 達成度 {p.get('status_num', 0)}%\n"
            report += f"  [実施状況・結果] {p.get('review_comment', '特記事項なし')}\n"
        report += "\n"
    
    report += f"■課題認識・指導内容\n{current_issue}\n\n■ネクストアクション\n"
    for i, a in enumerate(st.session_state.actions):
        p_mark = " 🔥" if a.get('priority') == "高" else ""
        report += f"{i+1}. 【{a.get('subject', '科目なし')}】 ({a.get('deadline', '期限なし')}){p_mark}\n"
        if a.get('policy'): report += f"   - 方針: {a['policy']}\n"
        item_val = a.get('item') or a.get('specificTask')
        if item_val: report += f"   - 対象: {item_val}\n"
        if a.get('amount'): report += f"   - ペース: {a['amount']}\n"
        if a.get('method'): report += f"   - 方法: {a['method']}\n"
        if a.get('goal'): report += f"   - 完了基準: {a['goal']}\n"
        report += "\n"
    
    st.code(report, language="text")
    st.info("💡 上記をコピーしてLINE等に貼り付けてください。")
