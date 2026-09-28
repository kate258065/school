from datetime import datetime, timedelta, timezone
import re
import requests
import streamlit as st

# 페이지 설정
st.set_page_config(page_title="송탄고등학교 달력별 급식", page_icon="📅", layout="wide")

# 송탄고등학교 고정 정보
ATPT_OFCDC_SC_CODE = "J10"  # 경기도교육청
SD_SCHUL_CODE = "7530480"  # 송탄고등학교
SCHOOL_NAME = "송탄고등학교"


def get_korea_today():
    """한국 표준시(KST, UTC+9) 기준 오늘 날짜 반환"""
    kst_tz = timezone(timedelta(hours=9))
    return datetime.now(kst_tz).date()


def get_meal_info(date_str: str):
    """나이스 급식식단정보 API 호출 (중식 MMEAL_SC_CODE=2)"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE": ATPT_OFCDC_SC_CODE,
        "SD_SCHUL_CODE": SD_SCHUL_CODE,
        "MMEAL_SC_CODE": "2",
        "MLSV_FROM_YMD": date_str,
        "MLSV_TO_YMD": date_str,
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "mealServiceDietInfo" in data:
            rows = data["mealServiceDietInfo"][1]["row"]
            if rows:
                return rows[0]
        return None
    except Exception:
        return None


def parse_menu_items(ddish_nm: str, show_allergy: bool):
    """<br/>로 구분된 메뉴 항목들을 분리하고 알레르기 번호 표기 여부를 처리"""
    if not ddish_nm:
        return []

    # <br/> 및 HTML 태그 분리
    raw_items = ddish_nm.replace("<br/>", "\n").replace("<br>", "\n").split("\n")
    cleaned_items = []

    for item in raw_items:
        # 태그 제거 및 공백 정리
        item = re.sub(r"<[^>]+>", "", item).strip()
        if not item:
            continue

        if not show_allergy:
            # 괄호 안의 알레르기 숫자 및 연관 기호 제거 (예: "(1.2.3.4)" or "(1.2.5..)")
            item = re.sub(r"\([\d\.]+\)", "", item).strip()

        cleaned_items.append(item)

    return cleaned_items


# 헤더
st.title(f"🏫 {SCHOOL_NAME} 달력별 급식")
st.caption("날짜를 선택하여 중식 메뉴와 알레르기 및 칼로리 정보를 확인하세요.")

# 상단 컨트롤: 날짜 선택과 알레르기 정보 스위치를 나란히 배치
col_date, col_toggle = st.columns([2, 1])

with col_date:
    today_kst = get_korea_today()
    selected_date = st.date_input("📅 날짜 선택", value=today_kst)

with col_toggle:
    st.write("")  # 수평 맞춤용 여백
    st.write("")
    show_allergy = st.toggle("알레르기 정보 보기", value=True)

st.markdown("---")

if selected_date:
    ymd_str = selected_date.strftime("%Y%m%d")
    meal = get_meal_info(ymd_str)

    formatted_date_str = selected_date.strftime("%Y년 %m월 %d일")

    if meal:
        ddish_nm = meal.get("DDISH_NM", "")
        cal_info = meal.get("CAL_INFO", "정보 없음")
        menu_items = parse_menu_items(ddish_nm, show_allergy)

        st.subheader(f"🍱 {formatted_date_str} 중식 메뉴")

        # 주요 요약 메트릭 카드 (메뉴 가짓수 & 칼로리)
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.metric(label="🍽️ 메뉴 수", value=f"{len(menu_items)}개")
        with m_col2:
            st.metric(label="🔥 총 칼로리", value=cal_info)

        st.markdown("##### 📋 오늘의 메뉴 구성")

        # 메뉴 항목을 카드 형태로 나란히 배치 (한 줄에 최대 4개씩)
        if menu_items:
            num_cols = min(4, len(menu_items))
            cols = st.columns(num_cols)

            for idx, item in enumerate(menu_items):
                col_idx = idx % num_cols
                with cols[col_idx]:
                    with st.container(border=True):
                        st.markdown(f"**{item}**")
        else:
            st.info("등록된 메뉴 항목이 없습니다.")

    else:
        st.info("ℹ️ 급식이 없는 날입니다.")
