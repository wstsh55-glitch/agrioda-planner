import os
import html
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from dotenv import load_dotenv


# =========================================================
# 기본 설정
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
STATIC_DIR = BASE_DIR / "data_static"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env", override=True)

st.set_page_config(
    page_title="AgriODA Planner",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

KOICA_SERVICE_KEY = os.getenv("KOICA_SERVICE_KEY", "").strip()
API_FORCE_REFRESH = os.getenv("API_FORCE_REFRESH", "false").lower().strip() == "true"

KOICA_DEV_TRENDS_ENDPOINT = os.getenv(
    "KOICA_DEV_TRENDS_ENDPOINT",
    "https://apis.data.go.kr/B260003/DevCprTrendService2/getDevCprTrendList2",
).strip()

ODCLOUD_PATHS = {
    "country_support": os.getenv("ODCLOUD_COUNTRY_SUPPORT_PATH", "").strip(),
    "region_sector_support": os.getenv("ODCLOUD_REGION_SECTOR_SUPPORT_PATH", "").strip(),
    "income_level_oda": os.getenv("ODCLOUD_INCOME_LEVEL_ODA_PATH", "").strip(),
}


# =========================================================
# 유틸
# =========================================================
def h(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return html.escape(str(value))


def render_html(markup: str):
    markup = markup.strip()
    try:
        st.html(markup)
    except Exception:
        st.markdown(markup, unsafe_allow_html=True)


def first_nonempty(*values) -> str:
    for v in values:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except Exception:
            pass

        text = str(v).strip()
        if text and text.lower() != "nan":
            return text

    return ""


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    columns = list(df.columns)
    lower_map = {str(c).lower().strip(): c for c in columns}

    for c in candidates:
        if c in columns:
            return c

        key = c.lower().strip()
        if key in lower_map:
            return lower_map[key]

    return None


def contains_uganda(series: pd.Series) -> pd.Series:
    text = series.astype(str)
    return (
        text.str.contains("우간다", na=False)
        | text.str.contains("Uganda", case=False, na=False)
    )


def uganda_mask_from_columns(df: pd.DataFrame, columns: list[str | None]) -> pd.Series:
    mask = pd.Series(False, index=df.index)

    for col in columns:
        if col and col in df.columns:
            mask = mask | contains_uganda(df[col])

    return mask


def row_all_text(row: pd.Series) -> str:
    values = []
    for v in row.values:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except Exception:
            pass
        values.append(str(v))
    return " ".join(values)


def deterministic_choice(text: str, choices: list[str]) -> str:
    if not choices:
        return "Central"
    digest = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
    idx = int(digest[:8], 16) % len(choices)
    return choices[idx]


def sort_latest_first(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    date_col = find_col(out, ["날짜", "written_dt", "작성일", "date"])
    year_col = find_col(out, ["연도", "year", "년도", "시작연도", "종료연도"])

    if date_col:
        out["_sort_date"] = pd.to_datetime(out[date_col], errors="coerce")
        out = out.sort_values("_sort_date", ascending=False)
        out = out.drop(columns=["_sort_date"])
        return out

    if year_col:
        out["_sort_year"] = pd.to_numeric(out[year_col], errors="coerce")
        out = out.sort_values("_sort_year", ascending=False)
        out = out.drop(columns=["_sort_year"])
        return out

    return out


def filter_rows_about_uganda(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    priority_cols = [
        "country_nm",
        "국가",
        "국가명",
        "대상국가",
        "사업대상국",
        "country_eng_nm",
        "수원국",
    ]

    for col in priority_cols:
        if col in df.columns:
            filtered = df[contains_uganda(df[col])].copy()
            if not filtered.empty:
                return filtered

    mask = pd.Series(False, index=df.index)
    for col in df.columns:
        mask = mask | contains_uganda(df[col])

    filtered = df[mask].copy()
    if not filtered.empty:
        return filtered

    return pd.DataFrame()


# =========================================================
# CSS
# =========================================================
render_html(
    """
<style>
html, body, [data-testid="stAppViewContainer"] {
    margin: 0;
    padding: 0;
    overflow: hidden;
    background: #EAF2F8;
}

.block-container {
    padding: 0 !important;
    margin: 0 !important;
    max-width: 100% !important;
}

header[data-testid="stHeader"] {
    display: none;
}

footer {
    display: none;
}

section.main > div {
    padding: 0 !important;
}

div[data-testid="stIFrame"] {
    position: fixed !important;
    top: 58px !important;
    left: 0 !important;
    width: 100vw !important;
    height: calc(100vh - 58px) !important;
    z-index: 1 !important;
}

div[data-testid="stIFrame"] iframe {
    width: 100vw !important;
    height: calc(100vh - 58px) !important;
    border: none !important;
}

.top-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 58px;
    background: #0F80D9;
    color: white;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 28px;
    box-sizing: border-box;
    border-bottom: 1px solid #0C6DB8;
}

.brand-wrap {
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-mark {
    width: 34px;
    height: 34px;
    border-radius: 9px;
    background: white;
    color: #0F80D9;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    font-size: 18px;
}

.brand-title {
    font-size: 20px;
    font-weight: 900;
    letter-spacing: -0.4px;
}

.brand-sub {
    font-size: 13px;
    opacity: 0.9;
    margin-left: 8px;
}

.top-menu {
    display: flex;
    gap: 24px;
    font-size: 14px;
    font-weight: 800;
}

.panel-toggle-input {
    display: none;
}

.left-toggle-label,
.right-toggle-label {
    position: fixed;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 78px;
    background: rgba(255,255,255,0.98);
    border: 1px solid #D8E1EA;
    color: #475569;
    z-index: 10001;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    cursor: pointer;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.14);
    user-select: none;
    transition: all 0.24s ease;
}

.left-toggle-label {
    left: 352px;
    border-radius: 0 14px 14px 0;
}

.right-toggle-label {
    right: 427px;
    border-radius: 14px 0 0 14px;
}

.left-toggle-label:hover,
.right-toggle-label:hover {
    background: #F8FAFC;
    color: #0F80D9;
}

.toggle-arrow {
    font-size: 24px;
    font-weight: 900;
    line-height: 1;
    transition: transform 0.24s ease;
}

.toggle-text {
    font-size: 10px;
    font-weight: 800;
    color: #64748B;
    line-height: 1;
}

.left-panel-fixed {
    position: fixed;
    top: 78px;
    left: 22px;
    width: 330px;
    max-height: calc(100vh - 105px);
    overflow-y: auto;
    background: rgba(255,255,255,0.96);
    border: 1px solid #D8E1EA;
    border-radius: 18px;
    box-shadow: 0 8px 28px rgba(15, 23, 42, 0.16);
    z-index: 9999;
    padding: 18px;
    box-sizing: border-box;
    font-family: Arial, sans-serif;
    transition: transform 0.24s ease, opacity 0.24s ease;
}

.right-panel-fixed {
    position: fixed;
    top: 78px;
    right: 22px;
    width: 405px;
    max-height: calc(100vh - 105px);
    overflow-y: auto;
    background: rgba(255,255,255,0.96);
    border: 1px solid #D8E1EA;
    border-radius: 18px;
    box-shadow: 0 8px 28px rgba(15, 23, 42, 0.16);
    z-index: 9999;
    padding: 18px;
    box-sizing: border-box;
    font-family: Arial, sans-serif;
    transition: transform 0.24s ease, opacity 0.24s ease;
}

#left-panel-toggle:checked ~ .left-panel-fixed {
    transform: translateX(-380px);
    opacity: 0;
    pointer-events: none;
}

#left-panel-toggle:checked ~ .left-toggle-label {
    left: 8px;
    border-radius: 0 14px 14px 0;
}

#left-panel-toggle:checked ~ .left-toggle-label .toggle-arrow {
    transform: rotate(180deg);
}

#left-panel-toggle:not(:checked) ~ .left-toggle-label .toggle-text::before {
    content: "접기";
}

#left-panel-toggle:checked ~ .left-toggle-label .toggle-text::before {
    content: "열기";
}

#right-panel-toggle:checked ~ .right-panel-fixed {
    transform: translateX(455px);
    opacity: 0;
    pointer-events: none;
}

#right-panel-toggle:checked ~ .right-toggle-label {
    right: 8px;
    border-radius: 14px 0 0 14px;
}

#right-panel-toggle:checked ~ .right-toggle-label .toggle-arrow {
    transform: rotate(180deg);
}

#right-panel-toggle:not(:checked) ~ .right-toggle-label .toggle-text::before {
    content: "접기";
}

#right-panel-toggle:checked ~ .right-toggle-label .toggle-text::before {
    content: "열기";
}

.panel-title {
    font-size: 22px;
    font-weight: 900;
    color: #0875C9;
    margin-bottom: 16px;
}

.field-label {
    font-size: 12px;
    color: #64748B;
    font-weight: 800;
    margin-bottom: 6px;
}

.rank-title {
    font-size: 15px;
    font-weight: 900;
    color: #0F172A;
    border-top: 1px solid #E5EAF2;
    padding-top: 14px;
    margin-bottom: 8px;
}

.rank-row {
    display: flex;
    justify-content: space-between;
    border-bottom: 1px solid #EEF2F6;
    padding: 8px 0;
    font-size: 13px;
}

.rank-row span {
    color: #334155;
    font-weight: 700;
}

.rank-row b {
    color: #0F172A;
}

.note-box {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    color: #9A3412;
    border-radius: 10px;
    padding: 10px;
    font-size: 12px;
    line-height: 1.5;
    margin-top: 14px;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 16px;
}

.kpi-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 12px;
    min-height: 72px;
}

.kpi-label {
    font-size: 11px;
    color: #64748B;
    font-weight: 800;
}

.kpi-value {
    font-size: 24px;
    font-weight: 900;
    color: #0F172A;
    margin-top: 4px;
}

.source-chip {
    display: inline-block;
    background: #EFF6FF;
    color: #1D4ED8;
    border: 1px solid #BFDBFE;
    border-radius: 999px;
    padding: 5px 9px;
    font-size: 11px;
    font-weight: 800;
    margin-bottom: 10px;
}

.mini-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-top: 10px;
}

.mini-table th {
    text-align: left;
    color: #64748B;
    font-weight: 900;
    border-bottom: 1px solid #E5EAF2;
    padding: 7px 4px;
}

.mini-table td {
    border-bottom: 1px solid #EEF2F6;
    padding: 8px 4px;
    color: #0F172A;
    font-weight: 700;
    vertical-align: top;
}

.data-list {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.data-card {
    border: 1px solid #E5EAF2;
    border-radius: 12px;
    padding: 10px;
    background: #FFFFFF;
}

.data-title {
    font-size: 13px;
    font-weight: 900;
    color: #0F172A !important;
    margin-bottom: 4px;
}

.data-meta {
    font-size: 11px;
    color: #475569 !important;
    line-height: 1.45;
}

.right-panel-fixed h3 {
    color: #0F172A !important;
}

.right-tab-input {
    display: none;
}

.right-tab-labels {
    display: flex;
    gap: 12px;
    border-bottom: 1px solid #E5EAF2;
    margin-bottom: 14px;
    overflow-x: auto;
}

.right-tab-labels label {
    padding: 8px 0;
    font-size: 13px;
    font-weight: 900;
    color: #64748B;
    white-space: nowrap;
    cursor: pointer;
}

.right-tab-content {
    display: none;
}

#tab-business:checked ~ .right-tab-labels label[for="tab-business"],
#tab-trend:checked ~ .right-tab-labels label[for="tab-trend"],
#tab-support:checked ~ .right-tab-labels label[for="tab-support"],
#tab-api:checked ~ .right-tab-labels label[for="tab-api"],
#tab-report:checked ~ .right-tab-labels label[for="tab-report"] {
    color: #EF4444;
    border-bottom: 3px solid #EF4444;
}

#tab-business:checked ~ .tab-business-content,
#tab-trend:checked ~ .tab-trend-content,
#tab-support:checked ~ .tab-support-content,
#tab-api:checked ~ .tab-api-content,
#tab-report:checked ~ .tab-report-content {
    display: block;
}

.left-metric-input {
    display: none;
}

.left-metric-labels {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin: 12px 0 16px 0;
}

.left-metric-labels label {
    border: 1px solid #E5EAF2;
    background: #F8FAFC;
    border-radius: 10px;
    padding: 10px 4px;
    text-align: center;
    font-size: 11px;
    font-weight: 800;
    color: #475569;
    cursor: pointer;
}

#metric-count:checked ~ .left-metric-labels label[for="metric-count"],
#metric-amount:checked ~ .left-metric-labels label[for="metric-amount"],
#metric-agri:checked ~ .left-metric-labels label[for="metric-agri"],
#metric-result:checked ~ .left-metric-labels label[for="metric-result"] {
    background: #0F80D9;
    color: white;
    border-color: #0F80D9;
}

.left-metric-content {
    display: none;
}

#metric-count:checked ~ .metric-count-content,
#metric-amount:checked ~ .metric-amount-content,
#metric-agri:checked ~ .metric-agri-content,
#metric-result:checked ~ .metric-result-content {
    display: block;
}
</style>
"""
)


# =========================================================
# CSV 로딩
# =========================================================
def find_static_csv(kind: str) -> Path | None:
    patterns = {
        "country_projects": [
            "koica_country_projects.csv",
            "koica_country_projects.csv.csv",
            "koica_country*.csv",
            "*국별협력사업*.csv",
            "*국별협력*.csv",
        ],
        "ppp_projects": [
            "koica_ppp_projects.csv",
            "koica_ppp_projects.csv.csv",
            "koica_ppp*.csv",
            "*민관협력사업*.csv",
            "*민관협력*.csv",
        ],
        "dev_trends": [
            "koica_dev_trends.csv",
            "koica_dev_trends.csv.csv",
            "koica_dev*.csv",
            "*개발협력동향*.csv",
            "*국별 개발협력동향*.csv",
        ],
        "volunteer_dispatch": [
            "koica_volunteer_dispatch.csv",
            "koica_volunteer_dispatch.csv.csv",
            "koica_volunteer*.csv",
            "*해외봉사단 파견현황*.csv",
            "*파견현황*.csv",
        ],
    }

    for pattern in patterns.get(kind, []):
        direct = STATIC_DIR / pattern
        if "*" not in pattern and direct.exists():
            return direct

        matched = sorted(STATIC_DIR.glob(pattern))
        if matched:
            return matched[0]

    return None


def read_csv_flexible(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()

    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]

    for enc in encodings:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = [str(c).strip() for c in df.columns]
            df.attrs["source_path"] = str(path)
            return df
        except Exception:
            continue

    return pd.DataFrame()


def load_static_csvs() -> dict:
    return {
        "dev_trends": read_csv_flexible(find_static_csv("dev_trends")),
        "ppp_projects": read_csv_flexible(find_static_csv("ppp_projects")),
        "country_projects": read_csv_flexible(find_static_csv("country_projects")),
        "volunteer_dispatch": read_csv_flexible(find_static_csv("volunteer_dispatch")),
    }


# =========================================================
# 위치 정규화 및 좌표
# =========================================================
LOCATION_RULES = [
    ("makerere", "Kampala"),
    ("마케레레", "Kampala"),
    ("kampala", "Kampala"),
    ("캄팔라", "Kampala"),

    ("jinja", "Jinja"),
    ("진자", "Jinja"),

    ("gulu", "Gulu"),
    ("굴루", "Gulu"),
    ("글루", "Gulu"),

    ("lira", "Lira"),
    ("리라", "Lira"),

    ("mbarara", "Mbarara"),
    ("음바라라", "Mbarara"),

    ("moroto", "Moroto"),
    ("모로토", "Moroto"),

    ("karamoja", "Karamoja"),
    ("karamoja_", "Karamoja"),
    ("카라모자", "Karamoja"),

    ("abim", "Abim"),
    ("아빔", "Abim"),

    ("ntoroko", "Ntoroko"),
    ("은토로코", "Ntoroko"),

    ("bukedea", "Bukedea"),
    ("부케데아", "Bukedea"),

    ("masaka", "Masaka"),
    ("마사카", "Masaka"),

    ("mukono", "Mukono"),
    ("무코노", "Mukono"),

    ("wakiso", "Wakiso"),
    ("와키소", "Wakiso"),

    ("iganga", "Iganga"),
    ("이강가", "Iganga"),

    ("busoga", "Busoga"),
    ("부소가", "Busoga"),

    ("luwero", "Luwero"),
    ("루웨로", "Luwero"),

    ("rukungiri", "Rukungiri"),
    ("룩응기리", "Rukungiri"),

    ("kamwenge", "Kamwenge"),
    ("카무웬게", "Kamwenge"),

    ("moyo", "Moyo"),
    ("moio", "Moyo"),
    ("모요", "Moyo"),

    ("nakapiripirit", "Nakapiripirit"),
    ("나카피리피릿", "Nakapiripirit"),

    ("kiryandongo", "Kiryandongo"),
    ("키리안동고", "Kiryandongo"),

    ("kyankwanzi", "Kyankwanzi"),
    ("키얀콴지", "Kyankwanzi"),

    ("central", "Central"),
    ("중부", "Central"),

    ("northern", "Northern"),
    ("북부", "Northern"),

    ("eastern", "Eastern"),
    ("동부", "Eastern"),

    ("western", "Western"),
    ("서부", "Western"),

    ("west nile", "West Nile"),
    ("서나일", "West Nile"),
]

LOCATION_COORDS = {
    "Kampala": (0.3476, 32.5825),
    "Jinja": (0.4479, 33.2026),
    "Gulu": (2.7746, 32.2990),
    "Lira": (2.2350, 32.9097),
    "Mbarara": (-0.6072, 30.6545),
    "Moroto": (2.5345, 34.6666),
    "Karamoja": (2.5345, 34.6666),
    "Abim": (2.7017, 33.6761),
    "Ntoroko": (1.0411, 30.4818),
    "Bukedea": (1.3475, 34.0446),
    "Masaka": (-0.3338, 31.7341),
    "Mukono": (0.3533, 32.7553),
    "Wakiso": (0.3981, 32.4780),
    "Iganga": (0.6092, 33.4686),
    "Busoga": (0.7000, 33.3000),
    "Luwero": (0.8492, 32.4731),
    "Rukungiri": (-0.8411, 29.9419),
    "Kamwenge": (0.1866, 30.4539),
    "Moyo": (3.6609, 31.7247),
    "Nakapiripirit": (1.9167, 34.7833),
    "Kiryandongo": (1.8763, 32.0622),
    "Kyankwanzi": (1.1987, 31.8063),
    "Central": (0.3476, 32.5825),
    "Northern": (2.7746, 32.2990),
    "Eastern": (1.0644, 34.1794),
    "Western": (-0.6072, 30.6545),
    "West Nile": (3.0201, 30.9111),
}

FALLBACK_LOCATIONS = [
    "Kampala",
    "Gulu",
    "Jinja",
    "Mbarara",
    "Karamoja",
    "West Nile",
    "Eastern",
    "Western",
    "Northern",
    "Central",
]


def normalize_location_name(location_text: str, project_name: str = "", summary: str = "", row_text_value: str = "") -> str:
    raw = first_nonempty(location_text, "")
    text = f"{raw} {project_name} {summary} {row_text_value}".lower()

    for key, value in LOCATION_RULES:
        if key.lower() in text:
            return value

    invalid = {"", "nan", "none", "uganda", "우간다", "전국", "전역", "미정", "해당없음"}

    if raw.strip().lower() in invalid:
        return deterministic_choice(text or project_name or summary or "uganda", FALLBACK_LOCATIONS)

    cleaned = raw.strip()

    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        if parts:
            for p in parts:
                p_lower = p.lower()
                if p_lower not in invalid:
                    return normalize_location_name(p, project_name, summary, row_text_value)

    return cleaned


def guess_coords(location_name: str, project_name: str = "", summary: str = "", row_text_value: str = "") -> tuple[float, float]:
    normalized = normalize_location_name(location_name, project_name, summary, row_text_value)
    return LOCATION_COORDS.get(normalized, LOCATION_COORDS[deterministic_choice(normalized, FALLBACK_LOCATIONS)])


# =========================================================
# 정적 CSV 정규화
# =========================================================
def normalize_country_projects(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    country_col = find_col(df, ["사업대상국", "대상국가", "국가", "수원국"])
    name_col = find_col(df, ["사업명(국문)", "사업명_국문", "사업명", "국문사업명"])
    loc_col = find_col(df, ["사업대상지", "대상지역", "지역"])
    sector_col = find_col(df, ["지원분야", "사업분야", "분야"])
    budget_col = find_col(df, ["사업예산(만불)", "사업예산", "예산"])
    start_col = find_col(df, ["시작연도", "전체사업시작", "사업시작연도"])
    end_col = find_col(df, ["종료연도", "전체사업종료", "사업종료연도"])
    summary_col = find_col(df, ["사업목적", "사업요약", "사업내용", "요약"])
    stage_col = find_col(df, ["사업추진단계", "사업단계", "상태"])

    mask = uganda_mask_from_columns(df, [country_col, name_col, loc_col, summary_col])
    filtered = df[mask].copy()

    rows = []

    for _, r in filtered.iterrows():
        row_text_value = row_all_text(r)

        name = first_nonempty(r.get(name_col, "") if name_col else "")
        raw_location = first_nonempty(r.get(loc_col, "") if loc_col else "")
        sector = first_nonempty(r.get(sector_col, "") if sector_col else "미분류")
        start = first_nonempty(r.get(start_col, "") if start_col else "")
        end = first_nonempty(r.get(end_col, "") if end_col else "")
        summary = first_nonempty(r.get(summary_col, "") if summary_col else "")
        stage = first_nonempty(r.get(stage_col, "") if stage_col else "자료기반")

        display_location = normalize_location_name(raw_location, name, summary, row_text_value)
        lat, lon = guess_coords(display_location, name, summary, row_text_value)

        budget_usd = 0
        if budget_col:
            try:
                budget_usd = float(str(r.get(budget_col, 0)).replace(",", "")) * 10000
            except Exception:
                budget_usd = 0

        rows.append(
            {
                "project_name": name or "KOICA 국별협력사업",
                "district": display_location,
                "sector": sector or "미분류",
                "project_type": "국별협력사업",
                "period": f"{start}-{end}" if start or end else "",
                "status": stage,
                "budget_usd": budget_usd,
                "lat": lat,
                "lon": lon,
                "summary": summary,
                "source": "KOICA 국별협력사업 사업개요서 CSV",
            }
        )

    return pd.DataFrame(rows)


def normalize_ppp_projects(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    country_col = find_col(df, ["대상국가", "사업대상국", "국가", "수원국"])
    name_col = find_col(df, ["사업명_국문", "사업명(국문)", "사업명", "국문사업명"])
    loc_col = find_col(df, ["대상지역", "사업대상지", "지역"])
    sector_col = find_col(df, ["사업분야", "지원분야", "분야"])
    type_col = find_col(df, ["사업형태", "사업유형"])
    start_col = find_col(df, ["전체사업시작", "시작연도", "사업시작연도"])
    end_col = find_col(df, ["전체사업종료", "종료연도", "사업종료연도"])
    summary_col = find_col(df, ["사업요약", "사업목적", "사업내용", "요약"])
    budget_col = find_col(df, ["총약정액", "사업예산", "예산"])

    mask = uganda_mask_from_columns(df, [country_col, name_col, loc_col, summary_col])
    filtered = df[mask].copy()

    rows = []

    for _, r in filtered.iterrows():
        row_text_value = row_all_text(r)

        name = first_nonempty(r.get(name_col, "") if name_col else "")
        raw_location = first_nonempty(r.get(loc_col, "") if loc_col else "")
        sector = first_nonempty(r.get(sector_col, "") if sector_col else "미분류")
        project_type = first_nonempty(r.get(type_col, "") if type_col else "민관협력사업")
        start = first_nonempty(r.get(start_col, "") if start_col else "")
        end = first_nonempty(r.get(end_col, "") if end_col else "")
        summary = first_nonempty(r.get(summary_col, "") if summary_col else "")

        display_location = normalize_location_name(raw_location, name, summary, row_text_value)
        lat, lon = guess_coords(display_location, name, summary, row_text_value)

        budget_usd = 0
        if budget_col:
            try:
                budget_usd = float(str(r.get(budget_col, 0)).replace(",", ""))
            except Exception:
                budget_usd = 0

        rows.append(
            {
                "project_name": name or "KOICA 민관협력사업",
                "district": display_location,
                "sector": sector or "미분류",
                "project_type": project_type or "민관협력사업",
                "period": f"{start}-{end}" if start or end else "",
                "status": "자료기반",
                "budget_usd": budget_usd,
                "lat": lat,
                "lon": lon,
                "summary": summary,
                "source": "KOICA 민관협력사업 사업개요 CSV",
            }
        )

    return pd.DataFrame(rows)


def get_demo_projects() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project_name": "Uganda Agriculture ODA Planning Demo",
                "district": "Jinja",
                "sector": "농촌개발",
                "project_type": "Demo",
                "period": "2021-2025",
                "status": "시연",
                "budget_usd": 0,
                "lat": 0.4479,
                "lon": 33.2026,
                "summary": "CSV 파일이 없거나 우간다 사업이 필터링되지 않을 때 표시되는 시연용 데이터",
                "source": "Demo",
            }
        ]
    )


def get_sdg_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["식량안보", "SDG 2", "농가의 식량안보 인식 개선률"],
            ["농촌개발", "SDG 1", "참여 농가의 평균 소득 변화율"],
            ["축산", "SDG 2", "축산 질병 예방 교육 이수율"],
            ["기후스마트농업", "SDG 13", "기후적응 농법 도입 농가 수"],
            ["농식품 유통", "SDG 8", "농산물 시장 접근성 개선 농가 수"],
        ],
        columns=["sector", "sdg", "indicator"],
    )


# =========================================================
# API 캐시 및 호출
# =========================================================
def cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.csv"


def debug_path(name: str) -> Path:
    return CACHE_DIR / f"debug_{name}.txt"


def read_cache(name: str) -> pd.DataFrame:
    path = cache_path(name)

    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def write_cache(name: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return

    out = df.copy()
    out["_cached_at"] = datetime.utcnow().isoformat()
    out.to_csv(cache_path(name), index=False, encoding="utf-8-sig")


def write_debug(name: str, text: str) -> None:
    debug_path(name).write_text(text, encoding="utf-8")


def flatten_items(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    if "data" in data and isinstance(data["data"], list):
        return data["data"]

    response = data.get("response", {})
    body = response.get("body", {}) if isinstance(response, dict) else {}

    candidates = [
        body.get("items"),
        body.get("item"),
        data.get("items"),
        data.get("item"),
        data.get("result"),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        if isinstance(candidate, dict) and "item" in candidate:
            candidate = candidate["item"]

        if isinstance(candidate, dict):
            return [candidate]

        if isinstance(candidate, list):
            return candidate

    return []


def fetch_data_go_kr(endpoint: str, cache_name: str, extra_params: dict | None = None) -> pd.DataFrame:
    if not API_FORCE_REFRESH:
        cached = read_cache(cache_name)
        if not cached.empty:
            return cached

    if not endpoint:
        write_debug(cache_name, "Endpoint is empty.")
        return read_cache(cache_name)

    if not KOICA_SERVICE_KEY:
        write_debug(cache_name, "KOICA_SERVICE_KEY is empty.")
        return read_cache(cache_name)

    params = {
        "serviceKey": KOICA_SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 300,
        "returnType": "JSON",
    }

    if extra_params:
        params.update(extra_params)

    try:
        res = requests.get(endpoint, params=params, timeout=25)
        write_debug(
            cache_name,
            f"URL: {res.url}\n\nSTATUS: {res.status_code}\n\nTEXT:\n{res.text[:3000]}",
        )
        res.raise_for_status()

        data = res.json()
        df = pd.DataFrame(flatten_items(data))

        if not df.empty:
            write_cache(cache_name, df)

        return df

    except Exception as e:
        write_debug(cache_name, f"ERROR: {repr(e)}")
        return read_cache(cache_name)


def fetch_odcloud(path: str, cache_name: str, max_pages: int = 300) -> pd.DataFrame:
    if not API_FORCE_REFRESH:
        cached = read_cache(cache_name)
        if not cached.empty:
            return cached

    if not path:
        write_debug(cache_name, "ODCLOUD path is empty.")
        return read_cache(cache_name)

    if not KOICA_SERVICE_KEY:
        write_debug(cache_name, "KOICA_SERVICE_KEY is empty.")
        return read_cache(cache_name)

    url = path if path.startswith("http") else f"https://api.odcloud.kr{path}"
    all_rows = []
    debug_chunks = []

    try:
        for page in range(1, max_pages + 1):
            params = {
                "page": page,
                "perPage": 1000,
                "serviceKey": KOICA_SERVICE_KEY,
            }

            res = requests.get(url, params=params, timeout=30)
            debug_chunks.append(
                f"[PAGE {page}] URL: {res.url}\nSTATUS: {res.status_code}\nTEXT:\n{res.text[:800]}\n"
            )
            res.raise_for_status()

            data = res.json()
            rows = data.get("data", []) if isinstance(data, dict) else flatten_items(data)

            if not rows:
                break

            all_rows.extend(rows)

            total_count = data.get("totalCount", 0) if isinstance(data, dict) else 0
            if total_count and len(all_rows) >= int(total_count):
                break

        write_debug(cache_name, "\n\n".join(debug_chunks))

        df = pd.DataFrame(all_rows)

        if not df.empty:
            write_cache(cache_name, df)

        return df

    except Exception as e:
        write_debug(cache_name, f"ERROR: {repr(e)}\n\n" + "\n\n".join(debug_chunks))
        return read_cache(cache_name)


def load_all_api_data() -> dict:
    dev_trend_params = {
        "returnType": "JSON",
        "country_nm": "우간다",
        "country_iso_alp2": "UG",
    }

    return {
        "dev_trends": fetch_data_go_kr(
            KOICA_DEV_TRENDS_ENDPOINT,
            "api_dev_trends",
            dev_trend_params,
        ),
        "country_support": fetch_odcloud(
            ODCLOUD_PATHS["country_support"],
            "od_country_support",
        ),
        "region_sector_support": fetch_odcloud(
            ODCLOUD_PATHS["region_sector_support"],
            "od_region_sector_support",
        ),
        "income_level_oda": fetch_odcloud(
            ODCLOUD_PATHS["income_level_oda"],
            "od_income_level_oda",
        ),
    }


# =========================================================
# 지도
# =========================================================
def make_uganda_map(project_df: pd.DataFrame) -> folium.Map:
    m = folium.Map(
        location=[1.3733, 32.2903],
        zoom_start=7,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    m.get_root().html.add_child(
        folium.Element(
            """
            <style>
            .leaflet-popup-content {
                margin: 8px 10px !important;
                max-height: 155px !important;
                overflow-y: auto !important;
            }
            .leaflet-popup-content-wrapper {
                border-radius: 10px !important;
            }
            .leaflet-popup {
                max-width: 250px !important;
            }
            .marker-cluster-small,
            .marker-cluster-medium,
            .marker-cluster-large {
                background-color: rgba(15, 128, 217, 0.22) !important;
            }
            .marker-cluster-small div,
            .marker-cluster-medium div,
            .marker-cluster-large div {
                background-color: rgba(15, 128, 217, 0.88) !important;
                color: white !important;
                font-weight: 900 !important;
            }
            </style>
            """
        )
    )

    marker_cluster = MarkerCluster(
        name="KOICA Projects",
        options={
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": False,
            "zoomToBoundsOnClick": True,
            "disableClusteringAtZoom": 10,
            "maxClusterRadius": 45,
        },
    ).add_to(m)

    coord_count = {}

    for idx, (_, row) in enumerate(project_df.head(150).iterrows()):
        try:
            base_lat = float(row["lat"])
            base_lon = float(row["lon"])
        except Exception:
            continue

        coord_key = (round(base_lat, 4), round(base_lon, 4))
        duplicate_index = coord_count.get(coord_key, 0)
        coord_count[coord_key] = duplicate_index + 1

        if duplicate_index > 0:
            offsets = [
                (0.018, 0),
                (0.015, 0.010),
                (0.010, 0.015),
                (0, 0.018),
                (-0.010, 0.015),
                (-0.015, 0.010),
                (-0.018, 0),
                (-0.015, -0.010),
                (-0.010, -0.015),
                (0, -0.018),
                (0.010, -0.015),
                (0.015, -0.010),
            ]
            lat_offset, lon_offset = offsets[duplicate_index % len(offsets)]
            ring = duplicate_index // len(offsets)
            lat = base_lat + lat_offset * (1 + ring * 0.5)
            lon = base_lon + lon_offset * (1 + ring * 0.5)
        else:
            lat = base_lat
            lon = base_lon

        try:
            budget_value = float(row.get("budget_usd", 0))
            budget_text = f"USD {int(budget_value):,}" if budget_value > 0 else "-"
        except Exception:
            budget_text = "-"

        popup_html = f"""
        <div style="font-family:Arial; width:230px; max-height:150px; overflow-y:auto;">
            <div style="font-size:13px; font-weight:700; margin-bottom:5px;">
                {h(row.get('project_name', ''))}
            </div>
            <div style="font-size:11.5px; line-height:1.45;">
                <b>지역</b>: {h(row.get('district', ''))}<br>
                <b>분야</b>: {h(row.get('sector', ''))}<br>
                <b>유형</b>: {h(row.get('project_type', ''))}<br>
                <b>기간</b>: {h(row.get('period', ''))}<br>
                <b>상태</b>: {h(row.get('status', ''))}<br>
                <b>예산</b>: {h(budget_text)}<br>
                <b>출처</b>: {h(row.get('source', ''))}
            </div>
            <hr>
            <div style="font-size:11px; line-height:1.35; color:#444;">
                {h(str(row.get('summary', ''))[:260])}
            </div>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=255, min_width=220),
            tooltip=f"{row.get('project_name', '')} | {row.get('district', '')} | {row.get('sector', '')}",
            icon=folium.Icon(color="green", icon="info-sign"),
        ).add_to(marker_cluster)

    folium.LayerControl(position="bottomleft").add_to(m)

    return m


# =========================================================
# 데이터 로드
# =========================================================
static_data = load_static_csvs()
api_data = load_all_api_data()

country_projects = normalize_country_projects(static_data["country_projects"])
ppp_projects = normalize_ppp_projects(static_data["ppp_projects"])

project_frames = []

if not country_projects.empty:
    project_frames.append(country_projects)

if not ppp_projects.empty:
    project_frames.append(ppp_projects)

if project_frames:
    projects_df = pd.concat(project_frames, ignore_index=True)
else:
    projects_df = get_demo_projects()

sdg_df = get_sdg_df()
filtered_projects = projects_df.copy()

district_count = filtered_projects["district"].nunique() if "district" in filtered_projects else 0
sector_count = filtered_projects["sector"].nunique() if "sector" in filtered_projects else 0

rank_df = (
    filtered_projects.groupby("district")
    .size()
    .reset_index(name="count")
    .sort_values("count", ascending=False)
    .head(5)
    if "district" in filtered_projects.columns and not filtered_projects.empty
    else pd.DataFrame(columns=["district", "count"])
)


# =========================================================
# 패널 콘텐츠 생성
# =========================================================
rank_rows_html = ""

for _, row in rank_df.iterrows():
    rank_rows_html += (
        f"<div class='rank-row'>"
        f"<span>{h(row['district'])}</span>"
        f"<b>{int(row['count'])}건</b>"
        f"</div>"
    )

amount_rank_html = ""

if "budget_usd" in filtered_projects.columns and not filtered_projects.empty:
    amount_rank_df = (
        filtered_projects.groupby("district")["budget_usd"]
        .sum()
        .reset_index(name="amount")
        .sort_values("amount", ascending=False)
        .head(5)
    )

    for _, row in amount_rank_df.iterrows():
        amount_rank_html += (
            f"<div class='rank-row'>"
            f"<span>{h(row['district'])}</span>"
            f"<b>USD {int(float(row['amount'])):,}</b>"
            f"</div>"
        )

if not amount_rank_html:
    amount_rank_html = (
        "<div class='data-card'>"
        "<div class='data-title'>지원액 데이터 없음</div>"
        "<div class='data-meta'>CSV 예산 컬럼 또는 API 지원실적 연결 후 표시됩니다.</div>"
        "</div>"
    )

agri_project_html = ""

if not filtered_projects.empty:
    agri_mask = (
        filtered_projects["sector"].astype(str).str.contains("농|축산|식량|수산|Agriculture|Rural", case=False, na=False)
        | filtered_projects["project_name"].astype(str).str.contains("농|축산|식량|수산|Agriculture|Rural", case=False, na=False)
        | filtered_projects["summary"].astype(str).str.contains("농|축산|식량|수산|Agriculture|Rural", case=False, na=False)
    )
    agri_df = filtered_projects[agri_mask].head(6)
else:
    agri_df = pd.DataFrame()

if not agri_df.empty:
    for _, row in agri_df.iterrows():
        agri_project_html += (
            f"<div class='data-card'>"
            f"<div class='data-title'>{h(str(row.get('project_name', ''))[:48])}</div>"
            f"<div class='data-meta'>{h(row.get('district', ''))} · {h(row.get('sector', ''))}</div>"
            f"</div>"
        )
else:
    agri_project_html = (
        "<div class='data-card'>"
        "<div class='data-title'>농업 관련 사업 없음</div>"
        "<div class='data-meta'>현재 CSV에서 농업·축산·식량 관련 키워드가 확인되지 않았습니다.</div>"
        "</div>"
    )

sdg_html = ""

for _, row in sdg_df.iterrows():
    sdg_html += (
        f"<div class='data-card'>"
        f"<div class='data-title'>{h(row['sector'])} · {h(row['sdg'])}</div>"
        f"<div class='data-meta'>{h(row['indicator'])}</div>"
        f"</div>"
    )

project_rows_html = ""

for _, row in filtered_projects.head(14).iterrows():
    project_rows_html += (
        f"<tr>"
        f"<td>{h(str(row.get('project_name', ''))[:42])}</td>"
        f"<td>{h(str(row.get('district', ''))[:18])}</td>"
        f"<td>{h(str(row.get('sector', ''))[:18])}</td>"
        f"</tr>"
    )


def api_status(name: str, df: pd.DataFrame) -> str:
    status = "연결" if df is not None and not df.empty else "미연결"
    color = "#15803D" if status == "연결" else "#B91C1C"
    return f"<tr><td>{h(name)}</td><td style='color:{color}; font-weight:900;'>{status}</td></tr>"


api_status_rows = ""
api_status_rows += api_status("국가별 개발협력동향", api_data["dev_trends"])
api_status_rows += api_status("KOICA 국가별 지원실적", api_data["country_support"])
api_status_rows += api_status("KOICA 지역별분야별 지원실적", api_data["region_sector_support"])
api_status_rows += api_status("소득수준별 ODA 실적통계", api_data["income_level_oda"])

dev_trends_static = filter_rows_about_uganda(static_data["dev_trends"])
dev_trends_api = filter_rows_about_uganda(api_data.get("dev_trends", pd.DataFrame()))

if dev_trends_static is not None and not dev_trends_static.empty:
    dev_trend_source = sort_latest_first(dev_trends_static)
elif dev_trends_api is not None and not dev_trends_api.empty:
    dev_trend_source = sort_latest_first(dev_trends_api)
else:
    dev_trend_source = pd.DataFrame()

dev_trend_cards = ""

if not dev_trend_source.empty:
    title_col = find_col(dev_trend_source, ["trend_title_nm", "제목", "title"])
    date_col = find_col(dev_trend_source, ["written_dt", "작성일", "날짜", "date"])
    field_col = find_col(dev_trend_source, ["field_cd_nm", "분야", "구분"])
    ref_col = find_col(dev_trend_source, ["ref_nm", "출처"])
    body_col = find_col(dev_trend_source, ["bdtxt_1_cn", "본문1", "summary"])

    for _, row in dev_trend_source.head(5).iterrows():
        title = str(row.get(title_col, "개발협력동향"))[:54] if title_col else "개발협력동향"
        date = str(row.get(date_col, ""))[:20] if date_col else ""
        field = str(row.get(field_col, ""))[:20] if field_col else ""
        ref = str(row.get(ref_col, ""))[:24] if ref_col else ""
        body = str(row.get(body_col, ""))[:130] if body_col else ""

        dev_trend_cards += (
            f"<div class='data-card'>"
            f"<div class='data-title'>{h(title)}</div>"
            f"<div class='data-meta'>{h(field)} · {h(date)} · {h(ref)}</div>"
            f"<div class='data-meta' style='margin-top:6px;'>{h(body)}</div>"
            f"</div>"
        )
else:
    dev_trend_cards = (
        "<div class='data-card'>"
        "<div class='data-title'>우간다 개발협력동향 없음</div>"
        "<div class='data-meta'>API 또는 CSV에서 우간다 자료가 확인되지 않았습니다.</div>"
        "</div>"
    )


def make_support_cards(df: pd.DataFrame, title: str, filter_uganda: bool = False) -> str:
    if df is None or df.empty:
        return (
            f"<div class='data-card'>"
            f"<div class='data-title'>{h(title)} 미연결</div>"
            f"<div class='data-meta'>API 연결 후 표시됩니다.</div>"
            f"</div>"
        )

    source = df.copy()

    if filter_uganda:
        filtered = filter_rows_about_uganda(source)
        if not filtered.empty:
            source = filtered

    source = sort_latest_first(source)

    cards = ""

    year_col = find_col(source, ["연도", "year", "년도"])
    country_col = find_col(source, ["국가명", "국가", "country_nm", "수원국"])
    region_col = find_col(source, ["지역", "대륙", "권역"])
    sector_col = find_col(source, ["분야", "사업분야", "지원분야", "사업분류"])
    krw_col = find_col(source, ["지원액_원화", "지원액(원화)", "원화", "지원액_원"])
    usd_col = find_col(source, ["지원액_달러", "지원액(달러)", "달러", "지원액_미화"])

    for _, row in source.head(6).iterrows():
        year = first_nonempty(row.get(year_col, "") if year_col else "")
        country = first_nonempty(row.get(country_col, "") if country_col else "")
        region = first_nonempty(row.get(region_col, "") if region_col else "")
        sector = first_nonempty(row.get(sector_col, "") if sector_col else "")
        krw = first_nonempty(row.get(krw_col, "") if krw_col else "")
        usd = first_nonempty(row.get(usd_col, "") if usd_col else "")

        main = first_nonempty(country, region, sector, title)
        meta = " · ".join([x for x in [year, sector, region] if x])

        amount_parts = []
        if krw:
            amount_parts.append(f"KRW {krw}")
        if usd:
            amount_parts.append(f"USD {usd}")

        amount = " / ".join(amount_parts)

        cards += (
            f"<div class='data-card'>"
            f"<div class='data-title'>{h(main)}</div>"
            f"<div class='data-meta'>{h(meta)}</div>"
            f"<div class='data-meta' style='margin-top:6px;'>{h(amount)}</div>"
            f"</div>"
        )

    return cards


country_support_cards = make_support_cards(
    api_data["country_support"],
    "국가별 지원실적",
    filter_uganda=True,
)

region_sector_support_cards = make_support_cards(
    api_data["region_sector_support"],
    "지역별분야별 지원실적",
    filter_uganda=False,
)

income_level_cards = make_support_cards(
    api_data["income_level_oda"],
    "소득수준별 ODA 실적통계",
    filter_uganda=False,
)

csv_debug_html = f"""
<div class='data-card'>
    <div class='data-title'>CSV 로딩 상태</div>
    <div class='data-meta'>국별협력 원본: {h(f"{static_data['country_projects'].shape[0]}행 × {static_data['country_projects'].shape[1]}열")}</div>
    <div class='data-meta'>민관협력 원본: {h(f"{static_data['ppp_projects'].shape[0]}행 × {static_data['ppp_projects'].shape[1]}열")}</div>
    <div class='data-meta'>개발협력동향 원본: {h(f"{static_data['dev_trends'].shape[0]}행 × {static_data['dev_trends'].shape[1]}열")}</div>
    <div class='data-meta'>국별협력 우간다 필터: {len(country_projects)}건</div>
    <div class='data-meta'>민관협력 우간다 필터: {len(ppp_projects)}건</div>
    <div class='data-meta'>최종 사업 수: {len(filtered_projects)}건</div>
</div>
"""


# =========================================================
# 헤더
# =========================================================
render_html(
    """
<div class="top-header">
    <div class="brand-wrap">
        <div class="brand-mark">A</div>
        <div>
            <span class="brand-title">AgriODA Planner Uganda</span>
            <span class="brand-sub">KOICA 공공데이터 기반 농업 ODA 기획 플랫폼</span>
        </div>
    </div>
    <div class="top-menu">
        <span>지도분석</span>
        <span>사업정보</span>
        <span>성과지표</span>
        <span>AI보고서</span>
    </div>
</div>
"""
)


# =========================================================
# 지도 출력
# =========================================================
uganda_map = make_uganda_map(filtered_projects)

st_folium(
    uganda_map,
    height=900,
    use_container_width=True,
    returned_objects=[],
)


# =========================================================
# 오버레이 패널
# =========================================================
overlay_html = f"""
<input type="checkbox" id="left-panel-toggle" class="panel-toggle-input">
<input type="checkbox" id="right-panel-toggle" class="panel-toggle-input">

<label for="left-panel-toggle" class="left-toggle-label">
    <span class="toggle-arrow">‹</span>
    <span class="toggle-text"></span>
</label>

<label for="right-panel-toggle" class="right-toggle-label">
    <span class="toggle-arrow">›</span>
    <span class="toggle-text"></span>
</label>

<div class="left-panel-fixed">
    <div class="panel-title">우간다 ODA 분석</div>

    <div class="field-label">분석 기준</div>

    <input type="radio" name="left-metric" id="metric-count" class="left-metric-input" checked>
    <input type="radio" name="left-metric" id="metric-amount" class="left-metric-input">
    <input type="radio" name="left-metric" id="metric-agri" class="left-metric-input">
    <input type="radio" name="left-metric" id="metric-result" class="left-metric-input">

    <div class="left-metric-labels">
        <label for="metric-count">사업수</label>
        <label for="metric-amount">지원액</label>
        <label for="metric-agri">농업지표</label>
        <label for="metric-result">성과지표</label>
    </div>

    <div class="left-metric-content metric-count-content">
        <div class="rank-title">우선 검토 지역 TOP 5</div>
        {rank_rows_html}
    </div>

    <div class="left-metric-content metric-amount-content">
        <div class="rank-title">지원액 기준 지역 TOP 5</div>
        {amount_rank_html}
    </div>

    <div class="left-metric-content metric-agri-content">
        <div class="rank-title">농업 관련 사업</div>
        <div class="data-list">
            {agri_project_html}
        </div>
    </div>

    <div class="left-metric-content metric-result-content">
        <div class="rank-title">성과지표 후보</div>
        <div class="data-list">
            {sdg_html}
        </div>
    </div>

    <div class="note-box">
        사업대상지 텍스트를 기준으로 지도 좌표를 매칭했다.
        광역·전국 단위 사업은 사업명과 내용 기반으로 대표 권역에 배치했다.
    </div>
</div>

<div class="right-panel-fixed">
    <div class="panel-title">데이터 패널</div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">사업 수</div>
            <div class="kpi-value">{len(filtered_projects)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">대상 지역</div>
            <div class="kpi-value">{district_count}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">분야 수</div>
            <div class="kpi-value">{sector_count}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">성과지표</div>
            <div class="kpi-value">{len(sdg_df)}</div>
        </div>
    </div>

    <input type="radio" name="right-tabs" id="tab-business" class="right-tab-input" checked>
    <input type="radio" name="right-tabs" id="tab-trend" class="right-tab-input">
    <input type="radio" name="right-tabs" id="tab-support" class="right-tab-input">
    <input type="radio" name="right-tabs" id="tab-api" class="right-tab-input">
    <input type="radio" name="right-tabs" id="tab-report" class="right-tab-input">

    <div class="right-tab-labels">
        <label for="tab-business">사업</label>
        <label for="tab-trend">동향</label>
        <label for="tab-support">지원실적</label>
        <label for="tab-api">API</label>
        <label for="tab-report">보고서</label>
    </div>

    <div class="right-tab-content tab-business-content">
        <div class="source-chip">KOICA CSV + 위치 매칭</div>

        <h3 style="font-size:18px; font-weight:900; margin: 4px 0 10px 0;">
            KOICA 사업정보
        </h3>

        <table class="mini-table">
            <thead>
                <tr>
                    <th>사업명</th>
                    <th>지역</th>
                    <th>분야</th>
                </tr>
            </thead>
            <tbody>
                {project_rows_html}
            </tbody>
        </table>
    </div>

    <div class="right-tab-content tab-trend-content">
        <div class="source-chip">국가별 개발협력동향</div>

        <h3 style="font-size:18px; font-weight:900; margin: 4px 0 10px 0;">
            개발협력동향
        </h3>

        <div class="data-list">
            {dev_trend_cards}
        </div>
    </div>

    <div class="right-tab-content tab-support-content">
        <div class="source-chip">KOICA 지원실적 API</div>

        <h3 style="font-size:18px; font-weight:900; margin: 4px 0 10px 0;">
            국가별 지원실적
        </h3>
        <div class="data-list">
            {country_support_cards}
        </div>

        <h3 style="font-size:18px; font-weight:900; margin: 18px 0 10px 0;">
            지역별·분야별 지원실적
        </h3>
        <div class="data-list">
            {region_sector_support_cards}
        </div>

        <h3 style="font-size:18px; font-weight:900; margin: 18px 0 10px 0;">
            소득수준별 ODA 실적통계
        </h3>
        <div class="data-list">
            {income_level_cards}
        </div>
    </div>

    <div class="right-tab-content tab-api-content">
        <div class="source-chip">MVP 핵심 KOICA API</div>

        <h3 style="font-size:18px; font-weight:900; margin: 4px 0 10px 0;">
            API 연결 상태
        </h3>

        <table class="mini-table">
            <thead>
                <tr>
                    <th>데이터</th>
                    <th>상태</th>
                </tr>
            </thead>
            <tbody>
                {api_status_rows}
            </tbody>
        </table>

        <div class="data-list">
            {csv_debug_html}
        </div>
    </div>

    <div class="right-tab-content tab-report-content">
        <div class="source-chip">AI 보고서 생성 예정</div>

        <h3 style="font-size:18px; font-weight:900; margin: 4px 0 10px 0;">
            우간다 농업 ODA 기획 보고서
        </h3>

        <div class="data-card">
            <div class="data-title">자동 보고서 초안</div>
            <div class="data-meta">
                사업정보, 개발협력동향, 국가별 지원실적, 지역별·분야별 지원실적,
                소득수준별 ODA 통계를 근거로 사업 필요성·대상지·성과지표·리스크를 정리하는 영역이다.
            </div>
        </div>
    </div>
</div>
"""

render_html(overlay_html)