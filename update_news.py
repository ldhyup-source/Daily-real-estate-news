import os
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
import google.generativeai as genai

# 1. Gemini API 초기화
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

genai.configure(api_key=GEMINI_API_KEY)

# [수정] 내 계정에서 지원하는 최신 모델 자동 탐색 및 우선순위 지정
available_models = [
    m.name for m in genai.list_models()
    if 'generateContent' in m.supported_generation_methods
]
print("현재 내 계정에서 사용 가능한 모델 목록:", available_models)

# 구글 권장 최신 모델(3.6-flash) 최우선 배치
priority_list = [
    "models/gemini-3.6-flash",
    "models/gemini-3.5-flash",
    "models/gemini-flash-latest",
    "models/gemini-3.1-flash-lite",
    "models/gemini-2.5-flash-lite"
]

selected_model = None
for candidate in priority_list:
    if candidate in available_models:
        selected_model = candidate
        break

# 목록에 없을 경우 지원 모델 중 'flash' 단어가 포함된 첫 번째 모델 자동 지정
if not selected_model:
    flash_models = [m for m in available_models if "flash" in m]
    selected_model = flash_models[0] if flash_models else available_models[0]

print(f"최종 연결된 모델: {selected_model}")
model = genai.GenerativeModel(selected_model)
# 2. 최근 24시간 뉴스 RSS 수집 함수
def fetch_google_news(query, limit=5):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        root = ET.fromstring(res.content)
        articles = []
        for item in root.findall(".//item")[:limit]:
            title = item.find("title").text if item.find("title") is not None else ""
            pub_date = item.find("pubDate").text[:16] if item.find("pubDate") is not None else ""
            articles.append({"title": title, "pubDate": pub_date})
        return articles
    except Exception as e:
        print(f"뉴스 수집 실패 ({query}):", e)
        return []

re_news = fetch_google_news("대구 경북 부동산", limit=5)
airport_news = fetch_google_news("대구경북통합신공항", limit=3)

# 3. Gemini 구조화 분석 프롬프트
prompt = f"""
너는 대구·경북 전문 부동산 전략 분석가야.
아래 수집된 최근 24시간 뉴스 데이터를 바탕으로 핵심 내용을 분석해 JSON 형식으로만 응답해줘.
마크다운 코드블록(```json ... ```) 없이 순수 JSON 문자열만 출력해.

[수집된 부동산 기사]
{json.dumps(re_news, ensure_ascii=False)}

[수집된 신공항 기사]
{json.dumps(airport_news, ensure_ascii=False)}

[출력 JSON 스키마]:
{{
  "market_opinion": "대구경북 아파트 시황에 대한 객관적 사실 기반의 두괄식 한 줄 총평 (예: 보합세, 양극화, 거래 동향 등)",
  "airport_opinion": "TK신공항 현재 진행상황과 향후 예상에 대한 한 줄 총평",
  "airport_fact": "신공항 현재 공영개발 및 입법 진행상황 핵심 팩트 1~2줄",
  "airport_forecast": "국비 지원 및 개항 시점 등 향후 예상 1~2줄",
  "cards": [
    {{
      "badge": "구분 뱃지 (예: 주간 시세, 정비사업, 공급 통계, 경북 시황, 대출 규제)",
      "title": "카드 제목 (수치 포함, 캐주얼한 문장)",
      "bullet1": "핵심 수치 팩트 1",
      "bullet2": "핵심 수치 팩트 2",
      "desc": "왜 그런지에 대한 객관적 배경 설명 2줄 ('왜 그런가?' 문구 절대 쓰지 말 것)",
      "pub_date": "발행 기준 일시 (예: 2026.09.20 14:00)"
    }}
  ]
}}
주의: cards 배열은 반드시 5개 항목을 작성해줘.
"""

# 4. LLM 호출 및 파싱
response = model.generate_content(prompt)
response_text = response.text.strip()

# 코드블록 제거
if response_text.startswith("```"):
    response_text = re.sub(r"^```[a-zA-Z]*\n", "", response_text)
    response_text = re.sub(r"\n```$", "", response_text)

try:
    data = json.loads(response_text)
except Exception:
    # 파싱 에러 시 폴백 기본값
    data = {
        "market_opinion": "대구 아파트는 과잉 공급 충격을 흡수하며 보합권에 진입했으나, 도심 신축 대장주와 외곽 구축 간 초양극화가 이어집니다.",
        "airport_opinion": "민간 SPC 무산으로 공영개발로 선회했으나, 초과 사업비 국비 보전 특별법 통과 지연 시 개항 순연 및 재정 부담 확대가 예상됩니다.",
        "airport_fact": "대구시 공영개발 전환 확정, 국토부 민간공항 기본계획 고시 완료, 정기국회 내 행정통합 특별법 연계 추진 중.",
        "airport_forecast": "특별법 2차 개정안 미통과 시 지방채 누적 불가피, 실제 개항은 2032~2033년으로 순연 유력.",
        "cards": []
    }

# 5. 카드별 고해상도 이미지 매핑
card_images = [
    "[https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80](https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=800&q=80)",
    "[https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=800&q=80](https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&w=800&q=80)",
    "[https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=800&q=80](https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=800&q=80)",
    "[https://images.unsplash.com/photo-1474487548417-781cb71495f3?auto=format&fit=crop&w=800&q=80](https://images.unsplash.com/photo-1474487548417-781cb71495f3?auto=format&fit=crop&w=800&q=80)",
    "[https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=800&q=80](https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=800&q=80)"
]

cards_html = ""
for idx, card in enumerate(data.get("cards", [])[:5]):
    img_url = card_images[idx] if idx < len(card_images) else card_images[0]
    cards_html += f"""
    <div class="card">
      <div class="card-img-box">
        <img src="{img_url}" alt="{card.get('title', '')}">
        <span class="badge">TOP {idx+1} · {card.get('badge', '부동산 팩트')}</span>
      </div>
      <div class="card-content">
        <div class="card-title">{card.get('title', '')}</div>
        <div class="summary-box">
          <ul>
            <li>{card.get('bullet1', '')}</li>
            <li>{card.get('bullet2', '')}</li>
          </ul>
          <p>{card.get('desc', '')}</p>
        </div>
        <div class="card-footer">
          <span>대구경북 팩트체크</span>
          <span class="pub-date">발행: {card.get('pub_date', datetime.now().strftime('%Y.%m.%d %H:%M'))}</span>
        </div>
      </div>
    </div>
    """

# 6. 완성형 HTML 조립
full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>대구·경북 부동산 오늘 핵심 5選</title>
  <style>
    :root {{
      --primary: #0f172a;
      --point: #2563eb;
      --airport: #0284c7;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Pretendard", Roboto, sans-serif; }}
    body {{ background-color: var(--bg); padding: 24px 16px; color: var(--text); }}
    .wrapper {{ max-width: 1160px; margin: 0 auto; }}
    
    .header-area {{ margin-bottom: 14px; display: flex; justify-content: space-between; align-items: flex-end; }}
    .header-area h2 {{ font-size: 20px; font-weight: 800; color: var(--primary); }}
    .header-area span {{ font-size: 12px; color: var(--text-muted); }}

    .top-opinion-banner {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-left: 6px solid var(--point);
      border-radius: 14px;
      padding: 14px 18px;
      margin-bottom: 20px;
      box-shadow: 0 3px 10px rgba(0, 0, 0, 0.04);
    }}
    .top-opinion-banner h3 {{
      font-size: 14.5px;
      font-weight: 800;
      color: var(--point);
      margin-bottom: 4px;
    }}
    .top-opinion-banner p {{
      font-size: 12.5px;
      color: #334155;
      line-height: 1.55;
      word-break: keep-all;
    }}

    .card-slider {{
      display: flex;
      gap: 16px;
      overflow-x: auto;
      padding-bottom: 16px;
      scroll-snap-type: x mandatory;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: thin;
    }}
    .card-slider::-webkit-scrollbar {{ height: 6px; }}
    .card-slider::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}

    .card {{
      width: 360px;
      height: 360px;
      flex-shrink: 0;
      scroll-snap-align: start;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
      transition: transform 0.2s ease;
    }}
    .card:hover {{ transform: translateY(-3px); }}

    .card-img-box {{
      width: 100%;
      height: 165px;
      position: relative;
      overflow: hidden;
      background-color: #0f172a;
    }}
    .card-img-box img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      object-position: center;
      display: block;
    }}
    .badge {{
      position: absolute;
      top: 10px;
      left: 10px;
      background: rgba(15, 23, 42, 0.85);
      color: #ffffff;
      backdrop-filter: blur(4px);
      font-size: 11px;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 6px;
      z-index: 2;
    }}

    .card-content {{
      padding: 12px 14px 10px 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: 195px;
    }}
    .card-title {{
      font-size: 13.5px;
      font-weight: 800;
      line-height: 1.35;
      color: var(--primary);
      margin-bottom: 5px;
      word-break: keep-all;
    }}
    .summary-box {{
      background: #f8fafc;
      border: 1px solid #edf2f7;
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 11px;
      line-height: 1.45;
      color: #334155;
      flex-grow: 1;
      overflow: hidden;
      word-break: keep-all;
    }}
    .summary-box ul {{ list-style: none; margin-bottom: 3px; }}
    .summary-box li {{ position: relative; padding-left: 8px; margin-bottom: 2px; font-weight: 700; color: #0f172a; }}
    .summary-box li::before {{ content: "•"; position: absolute; left: 0; color: var(--point); }}
    .summary-box p {{ color: #475569; font-size: 10.5px; line-height: 1.4; }}

    .card-footer {{
      font-size: 10px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid var(--border);
      padding-top: 5px;
      margin-top: 4px;
    }}
    .pub-date {{
      color: #2563eb;
      font-weight: 600;
      background: #eff6ff;
      padding: 2px 6px;
      border-radius: 4px;
    }}

    .airport-summary-banner {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-left: 6px solid var(--airport);
      border-radius: 14px;
      padding: 16px 20px;
      margin-top: 20px;
      box-shadow: 0 3px 10px rgba(0, 0, 0, 0.04);
    }}
    .airport-summary-banner h3 {{
      font-size: 14.5px;
      font-weight: 800;
      color: var(--airport);
      margin-bottom: 6px;
    }}
    .airport-summary-banner .opinion-text {{
      font-size: 12.5px;
      color: #0f172a;
      line-height: 1.6;
      font-weight: 600;
      margin-bottom: 10px;
      word-break: keep-all;
    }}
    .airport-status-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      background: #f8fafc;
      border: 1px solid #edf2f7;
      border-radius: 10px;
      padding: 12px;
    }}
    @media (max-width: 768px) {{
      .airport-status-grid {{ grid-template-columns: 1fr; }}
    }}
    .airport-status-item h4 {{
      font-size: 12px;
      font-weight: 700;
      color: var(--primary);
      margin-bottom: 4px;
    }}
    .airport-status-item p {{
      font-size: 11.5px;
      color: #475569;
      line-height: 1.5;
      word-break: keep-all;
    }}
  </style>
</head>
<body>

<div class="wrapper">
  <div class="header-area">
    <h2>대구·경북 부동산 오늘 핵심 5選</h2>
    <span>매일 아침 07:00 자동 브리핑</span>
  </div>

  <div class="top-opinion-banner">
    <h3>📊 부동산 시황 한 줄 총평</h3>
    <p>{data.get('market_opinion', '')}</p>
  </div>

  <div class="card-slider">
    {cards_html}
  </div>

  <div class="airport-summary-banner">
    <h3>✈️ 대구경북통합신공항 한 줄 총평</h3>
    <p class="opinion-text">"{data.get('airport_opinion', '')}"</p>
    <div class="airport-status-grid">
      <div class="airport-status-item">
        <h4>📌 현재 진행 상황 (Fact)</h4>
        <p>{data.get('airport_fact', '')}</p>
      </div>
      <div class="airport-status-item">
        <h4>🔮 향후 예상 (Forecast)</h4>
        <p>{data.get('airport_forecast', '')}</p>
      </div>
    </div>
  </div>
</div>

</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(full_html)
print("index.html 갱신 완료!")
