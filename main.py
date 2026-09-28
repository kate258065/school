import collections
from datetime import datetime, timedelta, timezone
import re
import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
import streamlit as st

# 페이지 설정
st.set_page_config(
    page_title="한달동안 많이 나온 급식 순위", page_icon="📊", layout="wide"
)

# 송탄고등학교 고정 정보
ATPT_OFCDC_SC_CODE = "J10"  # 경기도교육청
SD_SCHUL_CODE = "7530480"  # 송탄고등학교
SCHOOL_NAME = "송탄고등학교"

# 한글 폰트 설정 (기본 폰트 사용 시 한글 깨짐 방지)
plt.rcParams["font.family"] = "NanumGothic"
plt.rcParams["axes.unicode_minus"] = False


def clean_menu_item(menu_str: str) -> str:
    """메뉴 항목에서 알레르기 정보(괄호 숫자와 점) 및 HTML 태그를 제거하고 정제"""
    # HTML 태그 제거
    cleaned = re.sub(r"<[^>]+>", "", menu_str).strip()
    # 괄호 안 알레르기 번호 제거 (예: "(1.2.3.4)", "(5..)")
    cleaned = re.sub(r"\([\d\.]+\)", "", cleaned).strip()
    return cleaned


@st.cache_data(ttl=3600)
def fetch_meals_for_month(year: int, month: int):
    """지정한 연/월의 송탄고 중식 데이터 전체를 API 수집 (KEY 사용 및 페이징 처리)"""
    # Secrets에서 NEIS_API_KEY 꺼내기
    api_key = st.secrets.get("NEIS_API_KEY", "")

    # 해당 월의 시작일과 마지막일 구하기
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    from_ymd = start_date.strftime("%Y%m%d")
    to_ymd = end_date.strftime("%Y%m%d")

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    p_size = 1000  # API 최대 수량
    p_index = 1
    all_rows = []

    while True:
        params = {
            "Type": "json",
            "KEY": api_key,
            "ATPT_OFCDC_SC_CODE": ATPT_OFCDC_SC_CODE,
            "SD_SCHUL_CODE": SD_SCHUL_CODE,
            "MMEAL_SC_CODE": "2",  # 중식
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

                # 전체 건수를 모두 수집했으면 종료
                if len(all_rows) >= total_count or len(rows) == 0:
                    break
                p_index += 1
            else:
                break
        except Exception:
            break

    return all_rows


def process_menu_data(rows):
    """
    수집한 급식 데이터에서 날짜별 메뉴를 정제하고,
    '같은 날 같은 메뉴'는 하루(1회)로 카운트하여 통계 집계
    """
    date_menu_map = collections.defaultdict(set)

    for row in rows:
        ymd = row.get("MLSV_YMD")
        raw_ddish = row.get("DDISH_NM", "")
        if not ymd or not raw_ddish:
            continue

        # <br/> 또는 <br> 기준으로 메뉴 낱개 분리
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

# 1. 월 선택 셀렉트박스 생성 (2025년 9월 ~ 2026년 9월)
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
    # 데이터 프레임 생성
    df = pd.DataFrame(menu_counts.most_common(), columns=["메뉴", "제공일수"])
    df["제공비율(%)"] = (df["제공일수"] / total_days * 100).round(1)

    top_1_menu = df.iloc[0]["메뉴"]
    top_1_days = df.iloc[0]["제공일수"]
    top_1_ratio = df.iloc[0]["제공비율(%)"]

    # 상위 지표 카드 (Metric)
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

    col_chart, col_table = st.columns([1.3, 1])

    with col_chart:
        st.subheader(f"🏆 가장 자주 나온 메뉴 TOP {top_n}")

        # 가로 막대 그래프 그리기 (Seaborn / Matplotlib)
        fig, ax = plt.subplots(figsize=(7, max(4, top_n * 0.45)))

        # 값이 클수록 진한 색 팔레트 적용
        palette = sns.color_palette("Blues_r", n_colors=len(df_top))[::-1]

        sns.barplot(
            data=df_top,
            x="제공일수",
            y="메뉴",
            palette=palette,
            ax=ax,
            orient="h",
        )

        ax.set_xlabel("제공 일수(일)")
        ax.set_ylabel("메뉴명")
        ax.set_title(
            f"{selected_month_str} 급식 메뉴 순위 (TOP {top_n})", fontsize=12
        )

        # 막대 끝에 값 및 비율 표시
        for p in ax.patches:
            width = p.get_width()
            if width > 0:
                percentage = (width / total_days) * 100
                ax.annotate(
                    f" {int(width)}일 ({percentage:.1f}%)",
                    (width, p.get_y() + p.get_height() / 2.0),
                    ha="left",
                    va="center",
                    fontsize=9,
                )

        # X축 여백 확장
        ax.set_xlim(0, max(df_top["제공일수"]) * 1.25)
        st.pyplot(fig)

    with col_table:
        st.subheader("📋 메뉴별 상세 제공 기록")
        df_display = df_top.copy()
        df_display.index = range(1, len(df_display) + 1)
        df_display.index.name = "순위"

        # 비율 포맷팅
        df_display["제공비율"] = df_display["제공비율(%)"].astype(str) + "%"
        df_display["제공일수"] = df_display["제공일수"].astype(str) + "일"

        st.dataframe(
            df_display[["메뉴", "제공일수", "제공비율"]],
            use_container_width=True,
        )
