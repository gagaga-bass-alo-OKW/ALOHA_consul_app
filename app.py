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
def get_worksheet():
    try:
        if "gspread_credentials" not in st.secrets: return None
        creds_dict = dict(st.secrets["gspread_credentials"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        return client.open_by_url(sheet_url).worksheet("logs")
    except Exception as e:
        st.error(f"認証エラー: {e}"); return None

def load_data():
    ws = get_worksheet()
    if ws:
        try:
            data = ws.get_all_records()
            if data:
                df = pd.DataFrame(data)
                df['日付'] = pd.to_datetime(df['日付']).dt.date
                return df
        except: pass
    return pd.DataFrame(columns=COLUMNS)

# --- 4. セッション状態初期化 ---
if 'actions' not in st.session_state: st.session_state.actions = []
if 'prev_actions' not in st.session_state: st.session_state.prev_actions = []
if 'dynamic_scores' not in st.session_state: st.session_state.dynamic_scores = []
if 'edit_mode' not in st.session_state: st.session_state.edit_mode = False
if 'edit_index' not in st.session_state: st.session_state.edit_index = None

def reset_session():
    st.session_state.actions = []
    st.session_state.prev_actions = []
    st.session_state.dynamic_scores = []
    st.session_state.edit_mode = False
    st.session_state.edit_index = None

# --- 5. メインUI ---
st.title("🎓 ALOHA Mentoring Base Pro")

# デフォルト設定を家庭教師に
m_type = st.segmented_control("指導種別", ["定期面談", "家庭教師"], default="家庭教師")

tab_new, tab_alert, tab_search, tab_stats, tab_preview = st.tabs([
    "📝 面談記録入力", "⚠️ 未提出アラート", "🔍 過去ログ・PDF", "📈 指導詳細統計", "📄 レポート出力"
])

df_all = load_data()

# --- タブ1: 面談記録入力 ---
with tab_new:
    if st.session_state.edit_mode:
        st.warning("⚠️ 現在【編集モード】です。保存すると既存のデータが更新されます。")
        if st.button("編集をキャンセルして新規作成に戻る"):
            reset_session(); st.rerun()

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        # keyを指定して値を保持できるようにする
        s_name = c1.text_input("生徒氏名", key="input_s_name")
        if c1.button("🔄 前回データを検索・読み込み"):
            res = df_all[df_all['生徒氏名'] == s_name]
            if not res.empty:
                last_row = res.iloc[-1]
                st.session_state.prev_actions = json.loads(last_row['データJSON']).get('actions', [])
                st.success(f"{last_row['日付']}のデータを取得。")
            else: st.warning("過去データなし")
        
        m_name = c2.text_input("担当メンター", key="input_m_name")
        stream = c2.radio("文理", ["理系", "文系"], horizontal=True, key="input_stream")
        date_val = c3.date_input("実施日", datetime.date.today(), key="input_date")
        grade = c3.selectbox("学年", ["中1", "中2", "中3", "高1", "高2", "高3", "既卒"], index=5, key="input_grade")

    sub1, sub2, sub3 = st.tabs(["✅ 1. 前回振り返り", "📊 2. 試験結果・課題認識", "🚀 3. ネクストアクション"])

    with sub1:
        if st.session_state.prev_actions:
            for i, p in enumerate(st.session_state.prev_actions):
                with st.container(border=True):
                    st.markdown(f"**【{p.get('subject','科目不明')}】**")
                    details = f"方針: {p.get('policy','')} | 対象: {p.get('item','')} | 量: {p.get('amount','')} | 方法: {p.get('method','')} | 基準: {p.get('goal','')}"
                    st.caption(details)
                    col_a, col_b = st.columns([1, 2])
                    st.session_state.prev_actions[i]['status_num'] = col_a.number_input("達成度(%)", 0, 100, p.get('status_num', 100), 5, key=f"p_n_{i}")
                    st.session_state.prev_actions[i]['review_comment'] = col_b.text_area("進捗詳細・テスト結果", p.get('review_comment',''), key=f"p_r_{i}", height=70)
        else: st.info("生徒名入力後に前回データを読み込んでください。")

    with sub2:
        exam_name = st.text_input("試験名", placeholder="例: 中間テスト", key="input_exam")
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
        current_issue = st.text_area("課題認識・指導内容（レポート用）", key="input_issue", height=150)
        mentor_memo = st.text_area("内部用メモ", key="input_memo", height=70)

    with sub3:
        if st.session_state.prev_actions and st.button("📋 前回のアクションをコピー", use_container_width=True):
            st.session_state.actions = [dict(pa) for pa in st.session_state.prev_actions]
            st.rerun()
        for i in range(len(st.session_state.actions)):
            with st.expander(f"Action {i+1} : {st.session_state.actions[i].get('subject','')}", expanded=True):
                a = st.session_state.actions[i]
                c_a, c_b, c_c = st.columns([2, 1, 2])
                st.session_state.actions[i]['subject'] = c_a.text_input("教科", a.get('subject',''), key=f"as_{i}")
                st.session_state.actions[i]['priority'] = c_b.selectbox("優先", ["高","中","低"], index=["高","中","低"].index(a.get('priority','中')), key=f"ap_{i}")
                st.session_state.actions[i]['deadline'] = c_c.text_input("期限", a.get('deadline','次回まで'), key=f"ad_{i}")
                st.session_state.actions[i]['policy'] = st.text_area("方針", a.get('policy',''), key=f"apol_{i}", height=70)
                l, r = st.columns(2)
                st.session_state.actions[i]['item'] = l.text_input("①対象", a.get('item',''), key=f"ai_{i}")
                st.session_state.actions[i]['amount'] = r.text_input("②量", a.get('amount',''), key=f"aa_{i}")
                l2, r2 = st.columns(2)
                st.session_state.actions[i]['method'] = l2.text_area("③方法", a.get('method',''), key=f"am_{i}", height=80)
                st.session_state.actions[i]['goal'] = r2.text_area("④基準", a.get('goal',''), key=f"ag_{i}", height=80)
                if st.button("このアクションを削除", key=f"adel_{i}"): st.session_state.actions.pop(i); st.rerun()
        if st.button("＋ アクション追加"): st.session_state.actions.append({'priority':'中', 'deadline':'次回まで'}); st.rerun()
        st.divider()
        
        save_label = "🆙 データを上書き保存" if st.session_state.edit_mode else "💾 データベースに保存"
        if st.button(save_label, type="primary", use_container_width=True):
            if not s_name: st.error("生徒名を入力してください")
            else:
                ws = get_worksheet()
                full_json = {"scores": st.session_state.dynamic_scores, "actions": st.session_state.actions, "prev_review": st.session_state.prev_actions}
                new_row = [date_val.strftime('%Y-%m-%d'), m_type, m_name, s_name, grade, stream, exam_name, current_issue, json.dumps(full_json, ensure_ascii=False), mentor_memo]
                if st.session_state.edit_mode:
                    ws.delete_rows(st.session_state.edit_index + 2)
                    ws.insert_rows([new_row], st.session_state.edit_index + 2)
                    st.success("更新しました！")
                else:
                    ws.append_row(new_row)
                    st.success("保存しました！")
                reset_session(); st.rerun()

# --- タブ3: 過去ログ・PDF (削除・編集ボタン) ---
with tab_search:
    st.subheader("🔍 過去ログ検索と管理")
    if not df_all.empty:
        target_s = st.selectbox("生徒を選択", ["すべて"] + list(df_all['生徒氏名'].unique()))
        filtered = df_all[df_all['生徒氏名'] == target_s] if target_s != "すべて" else df_all
        
        for idx, row in filtered.iterrows():
            with st.expander(f"{row['日付']} | {row['生徒氏名']} | {row['担当メンター']}"):
                col_txt, col_edit, col_del = st.columns([3, 1, 1])
                col_txt.write(f"**課題:** {row['課題']}")
                if col_edit.button("📝 編集", key=f"edit_btn_{idx}"):
                    data_obj = json.loads(row['データJSON'])
                    st.session_state.edit_mode = True
                    st.session_state.edit_index = idx
                    # 各フィールドにロード (Session State)
                    st.session_state.actions = data_obj.get('actions', [])
                    st.session_state.prev_actions = data_obj.get('prev_review', [])
                    st.session_state.dynamic_scores = data_obj.get('scores', [])
                    # テキスト入力などは st.session_state に直接入れる (key経由)
                    st.session_state.input_s_name = row['生徒氏名']
                    st.session_state.input_m_name = row['担当メンター']
                    st.session_state.input_issue = row['課題']
                    st.session_state.input_memo = row['講師用メモ']
                    st.session_state.input_exam = row['試験名']
                    st.info("データをロードしました。面談記録入力タブに移動してください。")
                    st.rerun()
                if col_del.button("🗑️ 削除", key=f"del_btn_{idx}"):
                    ws = get_worksheet(); ws.delete_rows(idx + 2)
                    st.success("削除しました"); st.rerun()
        
        if target_s != "すべて" and not filtered.empty:
            pdf = create_pdf(filtered, target_s)
            st.download_button("📄 PDFダウンロード", pdf, f"Report_{target_s}.pdf")

# --- タブ4: 指導詳細統計 (情報量UP) ---
with tab_stats:
    st.subheader("📈 指導詳細レポート一覧")
    if not df_all.empty:
        stats_list = []
        for _, r in df_all.iterrows():
            d = json.loads(r['データJSON'])
            acts = d.get('actions', [])
            score_avg = sum([p.get('status_num', 100) for p in d.get('prev_review', [])]) / max(len(d.get('prev_review', [])), 1)
            stats_list.append({
                "日付": r["日付"], "生徒": r["生徒氏名"], "メンター": r["担当メンター"],
                "平均達成度": f"{score_avg:.1f}%", "課題": r["課題"], 
                "宿題数": len(acts), "主な教科": ", ".join([a.get('subject','') for a in acts if a.get('subject')])
            })
        st.dataframe(pd.DataFrame(stats_list), use_container_width=True)
        st.divider()
        st.bar_chart(df_all.groupby('担当メンター').size())

# --- タブ5: レポート出力 ---
with tab_preview:
    st.subheader("📄 LINE用レポート")
    # 入力フォームの内容をそのまま反映
    report = f"【{m_type}報告書】\n実施日: {date_val}\n担当: {m_name}\n生徒: {s_name}様\n\n"
    if st.session_state.prev_actions:
        report += "■前回宿題の達成状況\n"
        for p in st.session_state.prev_actions:
            report += f"・{p.get('subject', '科目なし')}: 達成度 {p.get('status_num', 0)}%\n  [結果] {p.get('review_comment', '特記なし')}\n"
    report += f"\n■課題認識・指導内容\n{current_issue}\n\n■ネクストアクション\n"
    for i, a in enumerate(st.session_state.actions):
        report += f"{i+1}. 【{a.get('subject', '科目なし')}】 ({a.get('deadline', '期限なし')})\n"
        report += f"   - 方針: {a.get('policy','')}\n   - 対象: {a.get('item','')}\n   - 方法: {a.get('method','')}\n   - 基準: {a.get('goal','')}\n\n"
    st.code(report, language="text")
