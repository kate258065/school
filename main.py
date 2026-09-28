import collections
from datetime import datetime, timedelta
import re
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# 페이지 설정
st.set_page_config(
    page_title="한달동안 많이 나온 급식 순위", page_icon="📊", layout="wide"
)

# 상단 빠른 페이지 이동 메뉴 추가
st.markdown("### 📌 페이지 바로가기")
nav_col1, nav_col2, _ = st.columns([1, 1, 2])
with nav_col1:
    if st.button("🏫 1. 학교 급식 찾아보기", use_container_width=True):
        st.switch_page("main.py")
with nav_col2:
    if st.button("📅 2. 우리 학교 달력별 급식", use_container_width=True):
        st.switch_page("pages/1_달력별_급식.py")

st.markdown("---")

# 송탄고등학교 고정 정보
ATPT_OFCDC_SC_CODE = "J10"  # 경기도교육청
SD_SCHUL_CODE = "7530480"  # 송탄고등학교
SCHOOL_NAME = "송탄고등학교"


def clean_menu_item(menu_str: str) -> str:
    """메뉴 항목에서 알레르기 정보(괄호 숫자와 점) 및 HTML 태그를 제거하고 정제"""
    cleaned = re.sub(r"<[^>]+>", "", menu_str).strip()
    cleaned = re.sub(r"\([\d\.]+\)", "", cleaned).strip()
    return cleaned


@st.cache_data(ttl=3600)
def fetch_meals_for_month(year: int, month: int):
    """지정한 연/월의 송탄고 중식 데이터 전체를 API 수집 (KEY 사용 및 페이징 처리)"""
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
            "ATPT_OFCDC_SC_CODE": ATPT_OFCDC_SC_CODE,
            "SD_SCHUL_CODE": SD_SCHUL_CODE,
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
    """날짜별 메뉴 중복 제거 후 빈도 집계"""
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


# --- UI 구성 ---
st.title(f"📊 {SCHOOL_NAME} 한 달 동안 많이 나온 급식 순위")
st.caption("2025년 9월 ~ 2026년 9월 기간 중 선택한 월의 급식 메뉴 출현 빈도를 분석합니다.")

# 1. 월 선택 및 슬라이더
year_months = []
for y in [2025, 2026]:
    for m in range(1, 13):
        if (y == 2025 and m >= 9) or (y == 2026 and m <= 9):
            year_months.append((y, m))

month_options = [f"{y}년 {m:02d}월" for y, m in year_months]

col_select, col_slider = st.columns([1, 2])
with col_select:
    selected_month_str = st.selectbox("조회할 월을 선택하세요:", month_options)
    selected_year, selected_month = map(
        int, re.findall(r"\d+", selected_month_str)
    )

with col_slider:
    top_n = st.slider("상위 몇 위까지 표시할까요?", min_value=5, max_value=20, value=10)

# 데이터 수집 및 분석
rows = fetch_meals_for_month(selected_year, selected_month)
total_days, menu_counts = process_menu_data(rows)

st.markdown("---")

if total_days == 0 or not menu_counts:
    st.info(f"ℹ️ {selected_month_str}에는 집계된 급식 데이터가 없습니다.")
else:
    df = pd.DataFrame(menu_counts.most_common(), columns=["메뉴", "제공일수"])
    df["제공비율(%)"] = (df["제공일수"] / total_days * 100).round(1)

    top_1_menu = df.iloc[0]["메뉴"]
    top_1_days = df.iloc[0]["제공일수"]
    top_1_ratio = df.iloc[0]["제공비율(%)"]

    # 상위 지표 카드
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(label="📅 총 급식 제공일수", value=f"{total_days}일")
    with m2:
        st.metric(label="🥇 가장 자주 나온 메뉴 (1위)", value=top_1_menu)
    with m3:
        st.metric(label="📈 1위 메뉴 비율", value=f"{top_1_days}일 ({top_1_ratio}%)")

    st.markdown("---")

    # TOP N 데이터 추출
    df_top = df.head(top_n).copy()

    # 1위가 맨 위에 오도록 역순 정렬 (Plotly 가로 막대 표시 대응)
    df_chart = df_top.iloc[::-1].copy()

    # 표시용 텍스트 생성 (예: "3일 (60.0%)")
    df_chart["표시텍스트"] = (
        df_chart["제공일수"].astype(str)
        + "일 ("
        + df_chart["제공비율(%)"].astype(str)
        + "%)"
    )

    st.subheader(f"🏆 가장 자주 나온 메뉴 TOP {top_n}")

    # Plotly 대형 인터랙티브 가로 막대 차트
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

    # 차트 크기 및 디자인
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

    st.markdown("---")

    # 상세 표
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
