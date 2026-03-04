import streamlit as st
import pandas as pd
import datetime
import json

# --- 設定 ---
st.set_page_config(page_title="ALOHA Mentoring Base Pro", layout="wide")

# --- マスタデータ ---
SUBJECTS = {
    '理系': ['英語', '数学(理系)', '現代文', '古文', '漢文', '物理', '化学', '生物', '情報'],
    '文系': ['英語', '数学(文系)', '現代文', '古文', '漢文', '世界史', '日本史', '地理', '情報']
}

# --- データベース接続設定 ---
try:
    from streamlit_gsheets import GSheetsConnection
    conn = st.connection("gsheets", type=GSheetsConnection)
    DB_MODE = True
except:
    DB_MODE = False

COLUMNS = ["日付", "種別", "担当メンター", "生徒氏名", "学年", "文理", "志望科類", "試験名", "課題", "データJSON"]

# --- ロジック関数 ---
def load_data():
    if DB_MODE:
        try:
            return conn.read(worksheet="logs", ttl=0)
        except:
            return pd.DataFrame(columns=COLUMNS)
    else:
        if "demo_data" not in st.session_state:
            st.session_state.demo_data = pd.DataFrame(columns=COLUMNS)
        return st.session_state.demo_data

def save_data(new_row_df):
    current_df = load_data()
    updated_df = pd.concat([new_row_df, current_df], ignore_index=True)
    if DB_MODE:
        try:
            conn.update(worksheet="logs", data=updated_df)
            return True
        except Exception as e:
            st.error(f"保存エラー: {e}")
            return False
    else:
        st.session_state.demo_data = updated_df
        return True

def get_last_session(student_name):
    """特定の生徒の最新1件を取得"""
    df = load_data()
    if not df.empty and student_name:
        res = df[df['生徒氏名'] == student_name]
        if not res.empty:
            return res.iloc[0]
    return None

# --- セッション初期化 ---
if 'actions' not in st.session_state:
    st.session_state.actions = [{'subject': '英語', 'priority': '高', 'policy': '', 'specificTask': '', 'deadline': '次回まで'}]
if 'prev_actions' not in st.session_state:
    st.session_state.prev_actions = []

# --- UI構築 ---
st.title("🎓 ALOHA Mentoring Base Pro")

# 指導種別の選択（これによって保存先やレポート内容を区別可能にする）
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
                else:
                    st.warning("過去のデータが見つかりません")
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
        exam_name = e_col2.text_input("試験名 (例: 1学期中間 / 第1回東大本番レベル)", key="in_exam_name")
        
        # 動的な科目入力
        current_subjects = SUBJECTS[stream]
        score_data = {}
        
        st.caption("左に「今回の点数」、右に「次回の目標点数」を入力")
        cols = st.columns(len(current_subjects) // 2 + 1)
        for i, sub in enumerate(current_subjects):
            with cols[i % (len(current_subjects) // 2 + 1)]:
                st.write(f"**{sub}**")
                sc1, sc2 = st.columns(2)
                s_val = sc1.text_input("点数", key=f"score_{sub}", label_visibility="collapsed", placeholder="点数")
                t_val = sc2.text_input("目標", key=f"target_{sub}", label_visibility="collapsed", placeholder="目標")
                score_data[sub] = {"score": s_val, "target": t_val}

    # --- 課題・ネクストアクション ---
    current_issue = st.text_area("課題認識・指導内容", key="in_issue")

    st.subheader("🚀 ネクストアクション")
    for i, action in enumerate(st.session_state.actions):
        with st.expander(f"Action {i+1}: {action['subject']}", expanded=True):
            ac1, ac2, ac3 = st.columns([2, 1, 2])
            st.session_state.actions[i]['subject'] = ac1.selectbox("教科", current_subjects, key=f"s_{i}")
            st.session_state.actions[i]['priority'] = ac2.selectbox("優先", ["高", "中", "低"], key=f"p_{i}")
            st.session_state.actions[i]['deadline'] = ac3.text_input("期限", key=f"d_{i}", value="次回まで")
            st.session_state.actions[i]['policy'] = st.text_input("方針設定", key=f"pol_{i}")
            st.session_state.actions[i]['specificTask'] = st.text_input("具体的タスク", key=f"t_{i}")
            if st.button("削除", key=f"del_{i}"):
                st.session_state.actions.pop(i)
                st.rerun()
    
    if st.button("＋ アクション追加"):
        st.session_state.actions.append({'subject': '英語', 'priority': '中', 'policy': '', 'specificTask': '', 'deadline': '1週間後'})
        st.rerun()

    # --- 保存 ---
    if st.button("💾 この内容を保存する", type="primary"):
        if not student_name:
            st.error("生徒氏名を入力してください")
        else:
            full_data = {
                "mentor": mentor_name,
                "scores": score_data,
                "exam_category": exam_category,
                "prev_actions": st.session_state.prev_actions, # 振り返り込み
                "actions": st.session_state.actions,
                "type": m_type
            }
            new_row = pd.DataFrame([{
                "日付": date_val.strftime('%Y-%m-%d'),
                "種別": m_type,
                "担当メンター": mentor_name,
                "生徒氏名": student_name,
                "学年": grade,
                "文理": stream,
                "志望科類": "", # 必要に応じて追加
                "試験名": exam_name,
                "課題": current_issue,
                "データJSON": json.dumps(full_data, ensure_ascii=False)
            }])
            if save_data(new_row):
                st.success("保存完了！")
                # リセット処理（任意）

with tab_search:
    st.subheader("過去ログ検索")
    df = load_data()
    if not df.empty:
        search = st.text_input("生徒名検索")
        display_df = df[df['生徒氏名'].str.contains(search)] if search else df
        st.dataframe(display_df.drop(columns=["データJSON"]), use_container_width=True)

with tab_preview:
    st.subheader("📄 指導レポート出力")
    # 入力中のデータからレポートを構成
    report_text = f"【{m_type}報告書】\n"
    report_text += f"実施日: {date_val} / 担当: {mentor_name}\n"
    report_text += f"生徒: {student_name}様 ({grade})\n"
    report_text += f"課題: {current_issue}\n\n"
    
    if st.session_state.prev_actions:
        report_text += "■前回タスク振り返り\n"
        for pa in st.session_state.prev_actions:
            report_text += f"・{pa['subject']}: {pa['status']} ({pa['specificTask']})\n"
        report_text += "\n"

    report_text += f"■{exam_category}結果・目標\n"
    for sub, vals in score_data.items():
        if vals['score'] or vals['target']:
            report_text += f"・{sub}: {vals['score']}点 (次目標: {vals['target']}点)\n"
    
    report_text += "\n■今後のアクション\n"
    for i, act in enumerate(st.session_state.actions):
        report_text += f"{i+1}. 【{act['subject']}】{act['specificTask']} (期限: {act['deadline']})\n"
    
    st.code(report_text)
