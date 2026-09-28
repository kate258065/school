import collections
from datetime import datetime, timedelta, timezone
import re
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# 페이지 설정
st.set_page_config(page_title="학교 급식 찾아보기", page_icon="🏫", layout="wide")


def get_korea_today():
    """한국 표준시(KST, UTC+9) 기준 오늘 날짜 반환"""
    kst_tz = timezone(timedelta(hours=9))
    return datetime.now(kst_tz).date()


def clean_menu_item(menu_str: str) -> str:
    """메뉴 항목에서 알레르기 정보(괄호 숫자와 점) 및 HTML 태그 제거"""
    cleaned = re.sub(r"<[^>]+>", "", menu_str).strip()
    cleaned = re.sub(r"\([\d\.]+\)", "", cleaned).strip()
    return cleaned


def parse_menu_items(ddish_nm: str, show_allergy: bool):
    """급식 메뉴 문자열 분리 및 알레르기 옵션 처리"""
    if not ddish_nm:
        return []
    raw_items = ddish_nm.replace("<br/>", "\n").replace("<br>", "\n").split("\n")
    cleaned_items = []
    for item in raw_items:
        item = re.sub(r"<[^>]+>", "", item).strip()
        if not item:
            continue
        if not show_allergy:
            item = re.sub(r"\([\d\.]+\)", "", item).strip()
        cleaned_items.append(item)
    return cleaned_items


# API 검색 함수
def search_school_api(school_name: str):
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {"Type": "json", "SCHUL_NM": school_name}
    try:
        res = requests.get(url, params=params, timeout=5)
        res.raise_for_status()
        data = res.json()
        if "schoolInfo" in data:
            return data["schoolInfo"][1]["row"]
        return []
    except Exception:
        return []


def search_school(query: str):
    results = search_school_api(query)
    if results:
        return results
    expanded_query = query
    if "여고" in expanded_query:
        expanded_query = expanded_query.replace("여고", "여자고등학교")
    elif "고" in expanded_query and "고등학교" not in expanded_query:
        expanded_query = expanded_query.replace("고", "고등학교")
    if expanded_query != query:
        return search_school_api(expanded_query)
    return []


def get_meal_info(office_code: str, school_code: str, date_str: str):
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MMEAL_SC_CODE": "2",
        "MLSV_FROM_YMD": date_str,
        "MLSV_TO_YMD": date_str,
    }
    try:
        res = requests.get(url, params=params, timeout=5)
        res.raise_for_status()
        data = res.json()
        if "mealServiceDietInfo" in data:
            rows = data["mealServiceDietInfo"][1]["row"]
            if rows:
                return rows[0]
        return None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def fetch_songtan_meals_for_month(year: int, month: int):
    api_key = st.secrets.get("NEIS_API_KEY", "")
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    from_ymd = start_date.strftime("%Y%m%d")
    to_ymd = end_date.strftime("%Y%m%d")

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    p_size = 1000
    p_index = 1
    all_rows = []

    while True:
        params = {
            "Type": "json",
            "KEY": api_key,
            "ATPT_OFCDC_SC_CODE": "J10",
            "SD_SCHUL_CODE": "7530480",
            "MMEAL_SC_CODE": "2",
            "MLSV_FROM_YMD": from_ymd,
            "MLSV_TO_YMD": to_ymd,
            "pIndex": p_index,
            "pSize": p_size,
        }
        try:
            res = requests.get(url, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()

            if "mealServiceDietInfo" in data:
                head = data["mealServiceDietInfo"][0]["head"]
                total_count = int(head[0]["list_total_count"])
                rows = data["mealServiceDietInfo"][1]["row"]
                all_rows.extend(rows)
                if len(all_rows) >= total_count or len(rows) == 0:
                    break
                p_index += 1
            else:
                break
        except Exception:
            break
    return all_rows


def process_menu_data(rows):
    date_menu_map = collections.defaultdict(set)
    for row in rows:
        ymd = row.get("MLSV_YMD")
        raw_ddish = row.get("DDISH_NM", "")
        if not ymd or not raw_ddish:
            continue
        items = raw_ddish.replace("<br/>", "\n").replace("<br>", "\n").split("\n")
        for item in items:
            cleaned = clean_menu_item(item)
            if cleaned:
                date_menu_map[ymd].add(cleaned)

    total_meal_days = len(date_menu_map)
    menu_counts = collections.Counter()
    for ymd, menus in date_menu_map.items():
        for m in menus:
            menu_counts[m] += 1
    return total_meal_days, menu_counts


# --- 메인 타이틀 ---
st.title("🏫 학교 급식 정보 한눈에 보기")
st.caption("전국 학교 검색부터 송탄고등학교 달력 및 한 달 빈도 순위까지 한 화면에서 확인하세요.")
st.markdown("---")


# ==============================================================================
# SECTION 1: 학교 급식 찾아보기 (전국 학교 검색)
# ==============================================================================
st.header("1️⃣ 학교 급식 찾아보기")
st.caption("학교 이름을 입력하여 해당 날짜의 중식 메뉴와 칼로리를 확인하세요.")

col_sch_input, col_sch_date = st.columns([2, 1])

with col_sch_input:
    input_name = st.text_input(
        "학교 이름 입력 (예: 수도여고, 서울고, 환일고)",
        placeholder="학교명 입력",
        key="sec1_input",
    )

with col_sch_date:
    today_kst = get_korea_today()
    sec1_date = st.date_input("조회할 날짜", value=today_kst, key="sec1_date")

selected_school = None
if input_name.strip():
    school_list = search_school(input_name.strip())
    if not school_list:
        st.info("검색된 학교가 없습니다. 학교 이름을 다시 확인해 주세요.")
    else:
        options = {
            f"{sch['SCHUL_NM']} ({sch.get('LCTN_SC_NM', '지역 정보 없음')})": sch
            for sch in school_list
        }
        selected_option = st.selectbox("학교 선택:", list(options.keys()), key="sec1_select")
        selected_school = options[selected_option]

if selected_school and sec1_date:
    ymd_str = sec1_date.strftime("%Y%m%d")
    meal = get_meal_info(
        office_code=selected_school["ATPT_OFCDC_SC_CODE"],
        school_code=selected_school["SD_SCHUL_CODE"],
        date_str=ymd_str,
    )
    st.markdown(f"##### 🍱 {selected_school['SCHUL_NM']} ({sec1_date.strftime('%Y-%m-%d')}) 중식 메뉴")
    if meal:
        formatted_ddish = meal.get("DDISH_NM", "").replace("<br/>", "\n").replace("<br>", "\n")
        formatted_ddish = re.sub(r"<[^>]+>", "", formatted_ddish)
        c1, c2 = st.columns([2, 1])
        with c1:
            st.text(formatted_ddish)
        with c2:
            st.info(f"🔥 {meal.get('CAL_INFO', '정보 없음')}")
    else:
        st.warning("해당 날짜에는 급식 정보(중식)가 없습니다.")

st.markdown("<br/><hr/><br/>", unsafe_allow_html=True)


# ==============================================================================
# SECTION 2: 우리 학교 달력별 급식 (송탄고등학교 고정)
# ==============================================================================
st.header("2️⃣ 우리 학교 달력별 급식 (송탄고등학교)")

col_s2_date, col_s2_toggle = st.columns([2, 1])

with col_s2_date:
    sec2_date = st.date_input("📅 날짜 선택", value=today_kst, key="sec2_date")

with col_s2_toggle:
    st.write("")
    st.write("")
    show_allergy = st.toggle("알레르기 정보 보기", value=True, key="sec2_toggle")

if sec2_date:
    ymd_str = sec2_date.strftime("%Y%m%d")
    songtan_meal = get_meal_info(
        office_code="J10", school_code="7530480", date_str=ymd_str
    )

    if songtan_meal:
        ddish_nm = songtan_meal.get("DDISH_NM", "")
        cal_info = songtan_meal.get("CAL_INFO", "정보 없음")
        menu_items = parse_menu_items(ddish_nm, show_allergy)

        st.subheader(f"🍱 송탄고등학교 ({sec2_date.strftime('%Y년 %m월 %d일')}) 중식 메뉴")

        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.metric(label="🍽️ 메뉴 수", value=f"{len(menu_items)}개")
        with m_col2:
            st.metric(label="🔥 총 칼로리", value=cal_info)

        if menu_items:
            num_cols = min(4, len(menu_items))
            cols = st.columns(num_cols)
            for idx, item in enumerate(menu_items):
                col_idx = idx % num_cols
                with cols[col_idx]:
                    with st.container(border=True):
                        st.markdown(f"**{item}**")
    else:
        st.info("ℹ️ 급식이 없는 날입니다.")

st.markdown("<br/><hr/><br/>", unsafe_allow_html=True)


# ==============================================================================
# SECTION 3: 한 달 동안 많이 나온 급식 순위 (송탄고등학교)
# ==============================================================================
st.header("3️⃣ 한 달 동안 많이 나온 급식 순위 (송탄고등학교)")
st.caption("2025년 9월 ~ 2026년 9월 기간 중 선택한 월의 메뉴 출현 빈도를 분석합니다.")

year_months = []
for y in [2025, 2026]:
    for m in range(1, 13):
        if (y == 2025 and m >= 9) or (y == 2026 and m <= 9):
            year_months.append((y, m))

month_options = [f"{y}년 {m:02d}월" for y, m in year_months]

col_select, col_slider = st.columns([1, 2])
with col_select:
    selected_month_str = st.selectbox("조회할 월을 선택하세요:", month_options, key="sec3_month")
    selected_year, selected_month = map(int, re.findall(r"\d+", selected_month_str))

with col_slider:
    top_n = st.slider("상위 몇 위까지 표시할까요?", min_value=5, max_value=20, value=10, key="sec3_slider")

rows = fetch_songtan_meals_for_month(selected_year, selected_month)
total_days, menu_counts = process_menu_data(rows)

if total_days == 0 or not menu_counts:
    st.info(f"ℹ️ {selected_month_str}에는 집계된 급식 데이터가 없습니다.")
else:
    df = pd.DataFrame(menu_counts.most_common(), columns=["메뉴", "제공일수"])
    df["제공비율(%)"] = (df["제공일수"] / total_days * 100).round(1)

    top_1_menu = df.iloc[0]["메뉴"]
    top_1_days = df.iloc[0]["제공일수"]
    top_1_ratio = df.iloc[0]["제공비율(%)"]

    # 상위 메트릭
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(label="📅 총 급식 제공일수", value=f"{total_days}일")
    with m2:
        st.metric(label="🥇 가장 자주 나온 메뉴 (1위)", value=top_1_menu)
    with m3:
        st.metric(label="📈 1위 메뉴 비율", value=f"{top_1_days}일 ({top_1_ratio}%)")

    st.markdown("---")

    df_top = df.head(top_n).copy()
    # 1위가 맨 위에 오도록 역순 정렬
    df_chart = df_top.iloc[::-1].copy()
    df_chart["표시텍스트"] = (
        df_chart["제공일수"].astype(str) + "일 (" + df_chart["제공비율(%)"].astype(str) + "%)"
    )

    st.subheader(f"🏆 가장 자주 나온 메뉴 TOP {top_n}")

    # Plotly 대형 가로 막대 차트
    fig = px.bar(
        df_chart,
        x="제공일수",
        y="메뉴",
        orientation="h",
        text="표시텍스트",
        color="제공일수",
        color_continuous_scale="Blues",
        labels={"제공일수": "제공 일수(일)", "메뉴": "메뉴명"},
    )

    chart_height = max(500, top_n * 45)
    fig.update_layout(
        height=chart_height,
        xaxis_title="제공 일수(일)",
        yaxis_title="메뉴명",
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(size=14),
    )
    fig.update_traces(textposition="outside", textfont_size=13)

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 메뉴별 상세 제공 기록")
    df_display = df_top.copy()
    df_display.index = range(1, len(df_display) + 1)
    df_display.index.name = "순위"
    df_display["제공비율"] = df_display["제공비율(%)"].astype(str) + "%"
    df_display["제공일수"] = df_display["제공일수"].astype(str) + "일"

    st.dataframe(
        df_display[["메뉴", "제공일수", "제공비율"]],
        use_container_width=True,
    )
