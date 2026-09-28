from datetime import datetime, timedelta, timezone
import re
import requests
import streamlit as st

# 페이지 설정
st.set_page_config(page_title="학교 급식 찾아보기", page_icon="🏫")

st.title("🏫 학교 급식 찾아보기")


def get_korea_today():
    """한국 표준시(KST, UTC+9) 기준 오늘 날짜 반환"""
    kst_tz = timezone(timedelta(hours=9))
    return datetime.now(kst_tz).date()


def search_school_api(school_name: str):
    """나이스 학교기본정보 API 호출"""
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {"Type": "json", "SCHUL_NM": school_name}

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "schoolInfo" in data:
            return data["schoolInfo"][1]["row"]
        elif "RESULT" in data and data["RESULT"].get("CODE") == "INFO-200":
            return []
        return []
    except Exception:
        return []


def search_school(query: str):
    """학교 이름 검색 (줄임말 자동 보정 처리 포함)"""
    # 1차 검색
    results = search_school_api(query)
    if results:
        return results

    # 2차 검색 (줄임말 보정 처리)
    expanded_query = query
    # '여고' -> '여자고등학교'
    if "여고" in expanded_query:
        expanded_query = expanded_query.replace("여고", "여자고등학교")
    # '고' -> '고등학교' (이미 '여자고등학교'로 치환된 경우는 중복 적용 방지)
    elif "고" in expanded_query and "고등학교" not in expanded_query:
        expanded_query = expanded_query.replace("고", "고등학교")

    if expanded_query != query:
        return search_school_api(expanded_query)

    return []


def get_meal_info(office_code: str, school_code: str, date_str: str):
    """나이스 급식식단정보 API 호출 (중식 MMEAL_SC_CODE=2)"""
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


# 1. 학교 검색 섹션
st.subheader("1. 학교 검색")
input_name = st.text_input(
    "학교 이름을 입력하세요 (예: 수도여고, 서울고, 환일고)",
    placeholder="학교명 입력",
)

school_list = []
if input_name.strip():
    school_list = search_school(input_name.strip())

selected_school = None

if input_name.strip():
    if not school_list:
        st.info("검색된 학교가 없습니다. 학교 이름을 다시 확인해 주세요.")
    else:
        # 학교 목록 드롭다운 옵션 생성 (학교명 (지역))
        options = {
            f"{sch['SCHUL_NM']} ({sch.get('LCTN_SC_NM', '지역 정보 없음')})": sch
            for sch in school_list
        }
        selected_option = st.selectbox("학교를 선택하세요:", list(options.keys()))
        selected_school = options[selected_option]

# 2. 날짜 선택 및 급식 조회 섹션
st.markdown("---")
st.subheader("2. 급식 날짜 선택")

today_kst = get_korea_today()
selected_date = st.date_input("조회할 날짜를 선택하세요", value=today_kst)

if selected_school and selected_date:
    ymd_str = selected_date.strftime("%Y%m%d")
    meal = get_meal_info(
        office_code=selected_school["ATPT_OFCDC_SC_CODE"],
        school_code=selected_school["SD_SCHUL_CODE"],
        date_str=ymd_str,
    )

    st.markdown("---")
    st.subheader(
        f"🍱 {selected_school['SCHUL_NM']} ({selected_date.strftime('%Y년 %m월 %d일')}) 중식 메뉴"
    )

    if meal:
        # HTML 태그 <br/> 제거 및 줄바꿈 처리
        raw_ddish = meal.get("DDISH_NM", "")
        formatted_ddish = raw_ddish.replace("<br/>", "\n").replace("<br>", "\n")
        
        # 정규식을 이용해 HTML/XML 잔여 태그 제거
        formatted_ddish = re.sub(r"<[^>]+>", "", formatted_ddish)

        cal_info = meal.get("CAL_INFO", "정보 없음")

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown("**[오늘의 식단]**")
            st.text(formatted_ddish)

        with col2:
            st.markdown("**[열량 정보]**")
            st.info(f"🔥 {cal_info}")
    else:
        st.warning("해당 날짜에는 급식 정보(중식)가 없습니다.")
elif not selected_school and input_name.strip():
    st.caption("위의 검색 결과에서 학교를 먼저 선택해 주세요.")
