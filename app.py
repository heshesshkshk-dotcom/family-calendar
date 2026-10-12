import calendar
import hmac
from datetime import date, time

import streamlit as st
from supabase import create_client

st.set_page_config(page_title="우리집 캘린더", page_icon="🏠", layout="wide")
st.title("🏠 우리집 캘린더")

MEMBERS = ["지영", "하성", "지호", "은수", "현민", "예주"]
COLORS = {"지영": "🔵", "하성": "🟣", "지호": "🟢", "은수": "🟠", "현민": "🟡", "예주": "🔴"}

# 가족 공용 비밀번호: 브라우저 세션마다 로그인
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.form("login_form"):
        password = st.text_input("가족 공용 비밀번호", type="password")
        login = st.form_submit_button("로그인")
    if login:
        if hmac.compare_digest(password, st.secrets["FAMILY_PASSWORD"]):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    st.stop()

if st.button("로그아웃"):
    st.session_state.logged_in = False
    st.session_state.pop("pending_delete", None)
    st.rerun()

# 기존 Supabase schedules 테이블을 그대로 사용합니다.
@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

try:
    supabase = get_supabase()
except Exception:
    st.error("데이터베이스 연결에 실패했습니다. secrets.toml 설정을 확인하세요.")
    st.stop()

# 선택 월을 변경하면 선택 날짜도 해당 월 1일로 이동
if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()
if "view_year" not in st.session_state:
    st.session_state.view_year = date.today().year
if "view_month" not in st.session_state:
    st.session_state.view_month = date.today().month

def sync_selected_month():
    current = st.session_state.selected_date
    y, m = st.session_state.view_year, st.session_state.view_month
    if (current.year, current.month) != (y, m):
        st.session_state.selected_date = date(y, m, 1)
    st.session_state.pop("pending_delete", None)

col_year, col_month = st.columns(2)
with col_year:
    year = st.number_input("연도", min_value=2020, max_value=2100,
                           step=1, key="view_year", on_change=sync_selected_month)
with col_month:
    month = st.selectbox("월", range(1, 13),
                         format_func=lambda value: f"{value}월",
                         key="view_month", on_change=sync_selected_month)

st.subheader(f"📅 {year}년 {month}월")
first_day = date(year, month, 1)
next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

try:
    monthly_schedules = (
        supabase.table("schedules")
        .select("id,date,time,member,content")
        .gte("date", first_day.isoformat())
        .lt("date", next_month.isoformat())
        .order("time")
        .execute()
        .data or []
    )
except Exception as exc:
    st.error("월별 일정을 불러오지 못했습니다.")
    st.caption(f"오류 코드 확인용: {exc}")
    st.stop()

schedule_map = {}
for item in monthly_schedules:
    day = int(item["date"][-2:])
    schedule_map.setdefault(day, []).append(item)

# 모바일에서도 날짜 버튼이 한 칸에 들어가도록 간단한 숫자만 표시
weekdays = ["월", "화", "수", "목", "금", "토", "일"]
header_cols = st.columns(7, gap="small")
for i, weekday in enumerate(weekdays):
    header_cols[i].markdown(f"**{weekday}**")

for week in calendar.monthcalendar(year, month):
    cols = st.columns(7, gap="small")
    for i, day in enumerate(week):
        if day == 0:
            continue
        count = len(schedule_map.get(day, []))
        label = f"{day} 📌" if count else str(day)
        if cols[i].button(label, key=f"day_{year}_{month}_{day}",
                          help=f"{day}일: 일정 {count}건", use_container_width=True):
            st.session_state.selected_date = date(year, month, day)
            st.session_state.pop("pending_delete", None)
            st.rerun()

selected_date = st.session_state.selected_date
st.divider()
st.subheader(f"📌 {selected_date:%Y-%m-%d} 일정")

# 이미 불러온 해당 월 자료를 재사용합니다.
schedules = schedule_map.get(selected_date.day, []) if (
    selected_date.year == year and selected_date.month == month
) else []

if not schedules:
    st.info("등록된 일정이 없습니다.")
else:
    for schedule in schedules:
        item_id = schedule["id"]
        member = schedule["member"]
        schedule_time = str(schedule["time"])[:5]
        content = schedule["content"]
        info_col, delete_col = st.columns([5, 1])
        with info_col:
            st.write(f"{schedule_time} {COLORS.get(member, '⚪')} {member} - {content}")
        with delete_col:
            if st.button("삭제", key=f"delete_{item_id}"):
                st.session_state.pending_delete = item_id
                st.rerun()

        if st.session_state.get("pending_delete") == item_id:
            st.warning(f"'{content}' 일정을 정말 삭제할까요?")
            confirm_col, cancel_col = st.columns(2)
            with confirm_col:
                if st.button("삭제 확인", key=f"confirm_{item_id}", type="primary"):
                    try:
                        supabase.table("schedules").delete().eq("id", item_id).execute()
                        st.session_state.pop("pending_delete", None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"삭제 실패: {exc}")
            with cancel_col:
                if st.button("취소", key=f"cancel_{item_id}"):
                    st.session_state.pop("pending_delete", None)
                    st.rerun()

st.divider()
st.subheader("➕ 새로운 일정 등록")
with st.form("schedule_form", clear_on_submit=False):
    schedule_date = st.date_input("날짜", value=selected_date)
    schedule_time = st.time_input("시간", value=time(9, 0))
    member = st.selectbox("가족 구성원", MEMBERS)
    content = st.text_input("일정 내용", placeholder="예: 병원 예약, 학교 행사")
    submitted = st.form_submit_button("💾 일정 저장", use_container_width=True)

if submitted:
    if not content.strip():
        st.warning("일정 내용을 입력해 주세요.")
    else:
        try:
            supabase.table("schedules").insert({
                "date": schedule_date.isoformat(),
                "time": schedule_time.strftime("%H:%M:%S"),
                "member": member,
                "content": content.strip(),
            }).execute()
            st.session_state.selected_date = schedule_date
            st.session_state.view_year = schedule_date.year
            st.session_state.view_month = schedule_date.month
            st.session_state.pop("pending_delete", None)
            st.rerun()
        except Exception as exc:
            st.error(f"일정 저장에 실패했습니다: {exc}")
