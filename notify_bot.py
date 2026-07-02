# =============================================
# 문화재단 채용공고 텔레그램 알림 봇 (GitHub Actions용)
# job_tracker.py의 scrape_jobs/parse_html 로직을 그대로 재사용
# =============================================

import json, os, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

# ── 텔레그램 설정 (GitHub Secrets에서 읽어옴) ──
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── 기관 목록 (job_tracker.py와 동일) ──
DEFAULT_FOUNDATIONS = [
    {"name": "서울문화재단",          "category": "광역", "url": "https://www.sfac.or.kr/opensquare/notice/recruit_list.do"},
    {"name": "인천문화재단",          "category": "광역", "url": "https://www.ifac.or.kr/bbs/list.do?key=m2501152808232&bbsCtgrySn=74"},
    {"name": "경기문화재단",          "category": "광역", "url": "https://recruit.incruit.com/ggcf/job/"},
    {"name": "한국문화예술위원회",    "category": "국가", "url": "https://www.arko.or.kr/board/list/4054"},
    {"name": "한국문화예술교육진흥원","category": "국가", "url": "https://arte.or.kr/notice/job/notice/Job_BoardList.do"},
    {"name": "한국예술인복지재단",    "category": "국가", "url": "https://www.kawf.kr/notice/sub01.do"},
    {"name": "김포문화재단",          "category": "지역", "url": "https://www.gcf.or.kr/main/pst/list.do?pst_id=recruit&pst_se=C"},
    {"name": "파주문화재단",          "category": "지역", "url": "https://www.pajucf.or.kr/community/notice.php?make=title&search=%EC%B1%84%EC%9A%A9"},
    {"name": "고양문화재단",          "category": "지역", "url": "https://www.artgy.or.kr/CU/CU0101M.aspx?cat=1"},
    {"name": "경기콘텐츠진흥원",      "category": "지역", "url": "https://www.gcon.or.kr/gcon/bbs/B0000023/list.do?menuNo=200123&pageIndex=1"},
    {"name": "인천영상위원회",        "category": "지역", "url": "https://www.ifc.or.kr/user/board/list.php?TP=&sq=&board_code=notice&search=&page=1&srchKey=A&srchValue=%EC%B1%84%EC%9A%A9"},
    {"name": "노무현재단",            "category": "기타", "url": "https://www.knowhow.or.kr/util/search_result.php?sword=%EC%B1%84%EC%9A%A9"},
    {"name": "서울영상위원회",        "category": "지역", "url": "https://www.seoulfc.or.kr/ReferenceLibrary/Notice/"},
    {"name": "영화진흥위원회",        "category": "국가", "url": "https://www.kofic.or.kr/kofic/business/board/selectBoardList.do?boardNumber=4"},
]

SEEN_FILE = "seen_jobs.json"  # 이전에 알림 보낸 공고 제목 기록 (저장소에 커밋됨)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
DATE_RE  = re.compile(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{2}[-./]\d{1,2}[-./]\d{1,2}')

GARBAGE = {"본문 바로가기","주메뉴 바로가기","서비스 전체보기","위로가기","레이어 닫기","초기화","메뉴등록하기","현재주소 복사하기","개인정보처리방침","찾아오시는 길","부조리통합신고센터"}
SKIP_WORDS = ["최종합격","최종 합격","면접심사","면접 심사","면접전형","서류심사","서류 심사","필기시험","필기 시험","합격자","결과발표","결과 발표","우선협상","입찰공고","입찰 공고","특강","서포터즈","임원","취소공고","정정공고","연기"]
MUST_WORDS = ["채용"]
NAV_WORDS = {"로그인","회원가입","바로가기","주메뉴","본문","사이트맵","ENG","english","더보기","TOP","홈","home","이전","다음","재단정보공개","인권경영","기부","문의","아카이브","프린트하기","즐겨찾기","공유","페이스북","트위터","블로그","복사하기","인스타그램","유튜브","네이버","카카오"}

def is_bad(text):
    if len(text) < 4 or text in NAV_WORDS or text in GARBAGE: return True
    if any(w in text for w in SKIP_WORDS): return True
    if not any(w in text for w in MUST_WORDS): return True
    return False

def normalize_date(date_str):
    if not date_str: return date_str
    d = re.sub(r'[./]', '-', date_str.strip())
    m = re.match(r'^(\d{2})-(\d{1,2})-(\d{1,2})$', d)
    if m:
        yy, mm, dd = m.groups()
        year = int(yy)
        full_year = 2000 + year if year <= 50 else 1900 + year
        d = f"{full_year}-{mm.zfill(2)}-{dd.zfill(2)}"
    return d

def is_too_old(date_str, max_days=730):
    if not date_str: return False
    try:
        return (datetime.now() - datetime.strptime(normalize_date(date_str), "%Y-%m-%d")).days > max_days
    except:
        return False

def parse_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_titles = set()

    if "kawf.kr" in base_url:
        for p_el in soup.select("p.Common_Bbs_Table_Type1_Item[data-pidx]"):
            pidx = p_el.get("data-pidx", "")
            if not pidx: continue
            a = p_el.find("a")
            if not a: continue
            raw = re.sub(r'\s+', ' ', a.get_text(strip=True)).strip()
            title = re.sub(r'^\[[^\]]+\]\s*', '', raw).strip()
            if len(title) < 6: continue
            KAWF_SKIP = ["합격자", "서류전형", "면접", "심의", "결과", "최종합격", "우선협상", "입찰"]
            if "채용" not in title: continue
            if any(w in title for w in KAWF_SKIP): continue
            if title in NAV_WORDS or title in GARBAGE: continue
            link = f"https://www.kawf.kr/notice/sub01View.do?selIdx={pidx}"
            li_el = p_el.find_parent("li")
            date = ""
            if li_el:
                m_d = DATE_RE.search(li_el.get_text())
                if m_d: date = m_d.group()
            if title not in seen_titles:
                seen_titles.add(title)
                results.append({"title": title, "date": date, "link": link})
            if len(results) >= 10: break
        if results: return results

    if "kofic.or.kr" in base_url:
        for a in soup.find_all("a", onclick=re.compile(r"fn_goDetailPage")):
            title = re.sub(r'\s+', ' ', a.get_text(strip=True)).strip()
            if not title or is_bad(title): continue
            m = re.search(r"fn_goDetailPage\((\d+)", a.get("onclick",""))
            link = f"https://www.kofic.or.kr/kofic/business/board/selectBoardDetail.do?boardNumber=4&boardSeqNumber={m.group(1)}" if m else base_url
            p_tr = a.find_parent("tr")
            date = ""
            if p_tr:
                date_td = p_tr.select_one("td.date")
                date = date_td.get_text(strip=True) if date_td else ""
            if not is_too_old(date) and title not in seen_titles:
                seen_titles.add(title)
                results.append({"title": title, "date": date, "link": link})
            if len(results) >= 10: break
        if results: return results

    if "sfac.or.kr" in base_url:
        for a in soup.find_all("a", onclick=re.compile(r"doView\(")):
            title_el = a.select_one("dl.subject dd p, .subject p, span")
            title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
            title = re.sub(r'\s+', ' ', title).strip()
            if not title or is_bad(title): continue
            m = re.search(r"doView\('(\d+)','(\d+)','([^']+)'\)", a.get("onclick",""))
            link = f"https://www.sfac.or.kr{m.group(3)}?cbIdx={m.group(1)}&bcIdx={m.group(2)}&type=" if m else base_url
            tr = a.find_parent("tr")
            date = ""
            if tr:
                date_td = tr.select_one("td.date, dl.date dd")
                date = date_td.get_text(strip=True) if date_td else ""
            if not date:
                parent_el = a.find_parent(["tr","li"])
                if parent_el:
                    m_date = DATE_RE.search(parent_el.get_text())
                    if m_date: date = m_date.group()
            if title not in seen_titles:
                if not is_too_old(date):
                    seen_titles.add(title)
                    results.append({"title": title, "date": date, "link": link})
            if len(results) >= 10: break
        if results: return results

    for tag in soup.find_all(['nav', 'header', 'footer']):
        tag.decompose()

    for a in soup.find_all("a"):
        raw_title = a.get_text(" ", strip=True)
        title = re.sub(r'\s+', ' ', raw_title).strip()

        if "자세히 보기" in title or "상세보기" in title:
            p = a.find_parent(["tr", "li", "div"])
            if p: title = re.sub(r'\s+', ' ', p.get_text(" ", strip=True)).strip()

        clean_title = re.sub(r'(대기중|모집중|마감|접수중|예정|자세히 보기|상세보기|NEW|new|\d{4}\.\d{2}\.\d{2})', '', title).strip()

        if len(clean_title) < 10 and any(w in clean_title for w in MUST_WORDS):
            continue

        if not clean_title or is_bad(clean_title) or clean_title in seen_titles:
            continue

        seen_titles.add(clean_title)

        href = a.get("href", "")
        onclick = a.get("onclick", "")
        p_tr = a.find_parent("tr") or a.find_parent("li")
        row_html = str(p_tr) if p_tr else str(a)

        combined = f"{href} {onclick} {row_html}"
        link = href

        if "kawf.kr" in base_url:
            m = re.search(r"selIdx=(\d+)", combined)
            if m: link = f"https://www.kawf.kr/notice/sub01View.do?selIdx={m.group(1)}"
            else:
                ids = re.findall(r"['\"\(](\d{4,6})['\"\)]", combined)
                v_ids = [i for i in ids if not i.startswith("20")]
                if v_ids: link = f"https://www.kawf.kr/notice/sub01View.do?selIdx={v_ids[0]}"
                else: link = base_url

        elif "artgy.or.kr" in base_url:
            m = re.search(r"code=(\d+)", combined)
            if m:
                link = f"https://www.artgy.or.kr/CU/CU0101M.aspx?mode=V&boardid=cs_notice&code={m.group(1)}&depth=a&cat=1"
            else:
                link = base_url

        elif "ifac.or.kr" in base_url:
            m = re.search(r"bbsSn=(\d+)", combined)
            if m: link = f"https://www.ifac.or.kr/bbs/view.do?bbsSn={m.group(1)}&key=m2501152808232&bbsCtgrySn=74"
            else:
                ids = re.findall(r"['\"\(](\d{4,6})['\"\)]", combined)
                v_ids = [i for i in ids if not i.startswith("20")]
                if v_ids: link = f"https://www.ifac.or.kr/bbs/view.do?bbsSn={v_ids[0]}&key=m2501152808232&bbsCtgrySn=74"
                else: link = base_url

        elif "sfac.or.kr" in base_url:
            m = re.search(r"doView\('(\d+)','(\d+)','([^']+)'\)", combined)
            if m: link = f"https://www.sfac.or.kr{m.group(3)}?cbIdx={m.group(1)}&bcIdx={m.group(2)}&type="

        elif "arte.or.kr" in base_url:
            m = re.search(r"fnView\('([^']+)'\)", combined)
            if m: link = f"https://arte.or.kr/notice/job/notice/Job_BoardView.do?board_id={m.group(1)}"

        elif "arko.or.kr" in base_url:
            if not link.startswith("http"):
                link = urljoin(base_url, link) if link and not link.startswith("javascript") else base_url

        elif "kofic.or.kr" in base_url:
            m = re.search(r"fn_goDetailPage\((\d+)\s*,\s*'([^']+)'", combined)
            if m: link = f"https://www.kofic.or.kr/kofic/business/board/selectBoardDetail.do?boardNumber=4&boardSeqNumber={m.group(1)}"
            elif not link.startswith("http"):
                link = urljoin(base_url, link) if link and not link.startswith("javascript") else base_url

        else:
            if not link.startswith("http"):
                if link in ["", "#", "#none"] or link.startswith("javascript"):
                    m_loc = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", combined)
                    link = urljoin(base_url, m_loc.group(1)) if m_loc else base_url
                else:
                    link = urljoin(base_url, link)

        date = ""
        if p_tr:
            date_td = p_tr.select_one("td.date, td.reg-date, td.regDate, td.write-date")
            if date_td:
                m_date = DATE_RE.search(date_td.get_text(" ", strip=True))
                if m_date: date = m_date.group()
            if not date:
                m_date = DATE_RE.search(p_tr.get_text(" ", strip=True))
                if m_date: date = m_date.group()
        if not date:
            m_date = DATE_RE.search(raw_title)
            if m_date: date = m_date.group()

        results.append({"title": title, "date": date, "link": link})

        if len(results) >= 15:
            break

    return results

def scrape_jobs(url):
    if not url or not url.startswith("http"): return []

    if "kawf.kr" in url:
        try:
            all_html = ""
            for page in range(1, 4):
                r = requests.post(url, data={
                    "searchCondition": "0", "search": "",
                    "searchKeyword": "채용", "cpg": str(page)
                }, headers=HEADERS, timeout=10)
                r.raise_for_status()
                r.encoding = r.apparent_encoding
                all_html += r.text
            results = parse_html(all_html, url)
            if results: return results
        except Exception:
            pass

    if "kofic.or.kr" in url:
        try:
            post_data = {
                "categorySelectValue": "-1", "boardSeqNumber": "", "boardPassword": "",
                "viewType": "", "curPage": "1", "searchTitle": "", "searchUser": "",
                "categoryList": "10011003", "searchSelectBox": "title", "searchInput": "",
            }
            r = requests.post(url, data=post_data, headers=HEADERS, timeout=10)
            r.raise_for_status()
            r.encoding = r.apparent_encoding
            results = parse_html(r.text, url)
            if results: return results
        except Exception:
            pass

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        results = parse_html(r.text, url)
        if results: return results
    except Exception:
        pass

    # GitHub Actions에서는 Playwright 브라우저가 별도 설치되어 있어야 함
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if "kawf.kr" in url:
                try: page.wait_for_load_state("networkidle", timeout=15000)
                except: page.wait_for_timeout(8000)
            elif "sfac.or.kr" in url:
                try: page.wait_for_selector('a[onclick*="doView"]', timeout=15000)
                except: page.wait_for_timeout(5000)
            else:
                try: page.wait_for_selector('table tbody tr, ul.board-list li, a[onclick*="fnView"]', timeout=10000)
                except: page.wait_for_timeout(8000)
            html = page.content()
            browser.close()
        return parse_html(html, url)
    except Exception:
        return []

# ── 텔레그램 전송 ──
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("텔레그램 토큰/채팅ID가 설정되지 않았습니다.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }, timeout=10)
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

# ── 이전에 본 공고 기록 ──
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

# ── 메인 ──
def main():
    seen = load_seen()
    new_count = 0

    for f in DEFAULT_FOUNDATIONS:
        name = f["name"]
        print(f"확인 중: {name}")
        jobs = scrape_jobs(f["url"])
        prev_titles = set(seen.get(name, []))
        current_titles = {j["title"] for j in jobs}

        new_jobs = [j for j in jobs if j["title"] not in prev_titles]

        for job in new_jobs:
            msg = (
                f"🆕 <b>{name}</b>\n"
                f"{job['title']}\n"
                f"📅 {job.get('date','')}\n"
                f"{job.get('link','')}"
            )
            send_telegram(msg)
            new_count += 1

        # 이번 결과를 기록 (최대 200개까지만 저장해서 파일 비대화 방지)
        seen[name] = list(current_titles)[:200]

    save_seen(seen)
    print(f"완료. 새 공고 {new_count}건 알림 전송")

if __name__ == "__main__":
    main()
