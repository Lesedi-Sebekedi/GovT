#!/usr/bin/env python3
"""Fetch recent DPSA vacancy circulars and publish searchable vacancy records."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "vacancies.js"
JSON_DATA_FILE = ROOT / "data" / "vacancies.json"
STATE_FILE = ROOT / "data" / "circular-state.json"
SOURCE_PAGE = "https://www.dpsa.gov.za/newsroom/psvc/"
LOOKBACK_DAYS = 60
USER_AGENT = "GovVacancySA/1.0 (GitHub Pages public vacancy index)"
MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
DATE_PATTERN = re.compile(rf"\b(\d{{1,2}}\s+(?:{MONTHS})\s+(\d{{3,4}}))\b", re.IGNORECASE)
POST_PATTERN = re.compile(r"(?im)^\s*POST\s+(\d{1,4}/\d{1,6})\s*$")
PROVINCES = {
    "eastern cape": "Eastern Cape",
    "free state": "Free State",
    "gauteng": "Gauteng",
    "kwazulu": "KwaZulu-Natal",
    "kwazulu-natal": "KwaZulu-Natal",
    "kwazulu natal": "KwaZulu-Natal",
    "kwa zulu natal": "KwaZulu-Natal",
    "limpopo": "Limpopo",
    "mpumalanga": "Mpumalanga",
    "northern cape": "Northern Cape",
    "north west": "North West",
    "western cape": "Western Cape",
}
PROVINCE_LIST = set(PROVINCES.values())
LOG = logging.getLogger("vacancy-ingestion")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.active_link: dict[str, str] | None = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        if href:
            self.active_link = {"href": href, "text": ""}
            self.links.append(self.active_link)

    def handle_data(self, data: str) -> None:
        if self.active_link is not None:
            self.active_link["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self.active_link = None


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status} downloading {url}")
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == 1:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 1:
                raise
        time.sleep(2)
    raise RuntimeError(f"Could not download {url}")


def page_text(markup: str) -> str:
    parser = TextParser()
    parser.feed(markup)
    return " ".join(" ".join(parser.parts).split())


def find_circular_links(markup: str) -> list[tuple[str, str, int, int]]:
    parser = LinkParser()
    parser.feed(markup)
    circles: dict[str, tuple[str, str, int, int]] = {}
    for link in parser.links:
        match = re.search(r"circular-(\d+)-of-(\d{4})", link["href"], re.IGNORECASE)
        if not match:
            continue
        number, year = int(match.group(1)), int(match.group(2))
        url = urllib.parse.urljoin(SOURCE_PAGE, link["href"])
        circles[url] = (link["text"].strip(), url, year, number)
    return sorted(circles.values(), key=lambda item: (item[2], item[3]), reverse=True)


def get_date(text: str, default_year: int | None = None) -> date | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    year_text = match.group(2)
    if len(year_text) == 3:
        if default_year is None or not str(default_year).endswith(year_text):
            return None
        year_text = str(default_year)
    return datetime.strptime(f"{match.group(1).rsplit(' ', 1)[0]} {year_text}".title(), "%d %B %Y").date()


def find_pdf_links(markup: str, page_url: str) -> list[tuple[str, str]]:
    parser = LinkParser()
    parser.feed(markup)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in parser.links:
        href = urllib.parse.urljoin(page_url, html.unescape(link["href"]))
        if ".pdf" not in urllib.parse.urlparse(href).path.lower():
            continue
        label = " ".join(link["text"].split())
        if "circular" in label.lower() and "click here" in label.lower():
            continue
        if href not in seen:
            result.append((label, href))
            seen.add(href)
    return result


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\ufffd", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    return text.strip()


def extract_field(text: str, label: str, next_labels: tuple[str, ...]) -> str:
    stop = "|".join(re.escape(item) for item in next_labels)
    pattern = re.compile(
        rf"(?ims)^\s*{re.escape(label)}\s*:?\s*\n\s*:?\s*(.*?)"
        rf"(?=^\s*(?:{stop})\s*:?\s*(?:\n|$)|\Z)"
    )
    match = pattern.search(text)
    return normalize_text(match.group(1)) if match else ""


def clean_department(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" :,-")
    value = re.sub(r"^(?:THE\s+)?", "", value, flags=re.IGNORECASE)
    if value.isupper():
        value = value.title()
    value = re.sub(r"\bDepartment Of\b", "Department of", value)
    value = re.sub(r"\bScm\b", "SCM", value)
    return value


def identify_department(text: str, label: str) -> tuple[str, str]:
    applications = re.search(r"\bAPPLICATIONS\b", text, re.IGNORECASE)
    header = text[: applications.start()] if applications else text[:1600]
    province = ""
    provincial = re.search(r"PROVINCIAL\s+ADMINISTRATION\s*:\s*([A-Z][A-Z ]+)", header, re.IGNORECASE)
    if provincial:
        province = PROVINCES.get(provincial.group(1).strip().lower(), provincial.group(1).strip().title())

    department = ""
    match = re.search(
        r"(?im)^\s*(DEPARTMENT OF\s+[A-Z][A-Z &,'()./-]*)",
        header,
    )
    if match:
        department = clean_department(match.group(1))
        following = header[match.end() :].splitlines()
        for line in following[:2]:
            continuation = line.strip()
            if (
                continuation
                and continuation.isupper()
                and continuation not in {"APPLICATIONS", "PROVINCIAL ADMINISTRATION"}
                and len(continuation) < 70
            ):
                department = clean_department(department + " " + continuation)
            else:
                break
    if not department:
        department = clean_department(label)
    if not re.search(r"\b(?:Department|Office|Authority|Commission|Treasury)\b", department, re.IGNORECASE):
        department = "Department of " + department

    if not province:
        clean_label = re.sub(r"^(?:Provincial Administration:\s*)", "", label, flags=re.IGNORECASE)
        province = PROVINCES.get(clean_label.strip().lower(), "National")
    return department, province


def extract_title(block: str) -> str:
    collected: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip(" \t:;")
        if not line:
            if collected:
                break
            continue
        if re.match(
            r"^(?:DIRECTORATE|SALARY|CENTRE|REQUIREMENTS|DUTIES|ENQUIRIES|APPLICATIONS|NOTE|"
            r"FOR ATTENTION|CLOSING DATE|REF(?:ERENCE)?\s*(?:NO|NUMBER))\b",
            line,
            re.IGNORECASE,
        ):
            break
        if re.match(r"^\(.*(?:advertisement|previously applied).*\)$", line, re.IGNORECASE):
            continue
        line = re.sub(r"\s+REF(?:ERENCE)?\s*(?:NO|NUMBER)\s*:?.*$", "", line, flags=re.IGNORECASE)
        if line:
            collected.append(line)
        if len(" ".join(collected)) >= 160:
            break
    return re.sub(r"\s+", " ", " ".join(collected)).strip(" :,-")


def classify(title: str, content: str) -> str:
    words = f"{title} {content}".lower()
    categories = (
        ("Healthcare", ("nurse", "medical", "clinical", "health", "doctor", "pharmac")),
        ("Information Technology", ("software", "information technology", "ict", "systems analyst", "developer", "database")),
        ("Finance", ("financial", "finance", "accountant", "audit", "budget", "treasury")),
        ("Engineering", ("engineer", "engineering", "technologist", "infrastructure")),
        ("Education", ("teacher", "educator", "education", "lecturer", "school")),
        ("Human Resources", ("human resource", "labour relations", "personnel")),
        ("Legal", ("legal", "attorney", "prosecutor", "lawyer")),
        ("Social Services", ("social worker", "social development", "community development")),
        ("Administration", ("administration", "administrative", "clerk", "office assistant")),
    )
    for category, keywords in categories:
        if any(keyword in words for keyword in keywords):
            return category
    return "Other"


def parse_pdf(
    pdf_bytes: bytes,
    circular: str,
    published: date,
    department_label: str,
    pdf_url: str,
) -> list[dict[str, object]]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        text = normalize_text("\n".join(page.get_text("text") for page in document))
    if len(text) < 200:
        raise ValueError(f"PDF has too little extractable text: {pdf_url}")

    department, province = identify_department(text, department_label)
    closing_text = extract_field(
        text,
        "CLOSING DATE",
        ("NOTE", "SALARY", "CENTRE", "REQUIREMENTS", "DUTIES", "APPLICATIONS", "FOR ATTENTION"),
    )
    closing_date = get_date(closing_text or text, published.year)
    if not closing_date:
        raise ValueError(f"No closing date found in {pdf_url}")

    matches = list(POST_PATTERN.finditer(text))
    records: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end() : end]
        title = extract_title(block)
        if len(title) < 4:
            LOG.warning("Skipping unrecognized post %s in %s", match.group(1), pdf_url)
            continue

        salary_section = extract_field(block, "SALARY", ("CENTRE", "REQUIREMENTS", "DUTIES", "ENQUIRIES"))
        salary_match = re.search(
            r"R\s*[\d][\d\s,]*(?:\s*[–-]\s*R?\s*[\d][\d\s,]*)?(?:\s*(?:per annum|per year|p\.a\.))?",
            salary_section,
            re.IGNORECASE,
        )
        salary = re.sub(r"\s+", " ", salary_match.group(0)).strip() if salary_match else "See official advertisement"
        centre = extract_field(block, "CENTRE", ("REQUIREMENTS", "DUTIES", "ENQUIRIES", "APPLICATIONS"))
        requirements = extract_field(block, "REQUIREMENTS", ("DUTIES", "ENQUIRIES", "APPLICATIONS"))
        duties = extract_field(block, "DUTIES", ("ENQUIRIES", "APPLICATIONS"))
        reference_match = re.search(
            r"\bREF(?:ERENCE)?\s*(?:NO|NUMBER)\s*:?\s*([A-Z0-9][A-Z0-9/.-]+)",
            block,
            re.IGNORECASE,
        )
        identity = f"{circular}|{pdf_url}|{match.group(1)}"
        identifier = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        summary = duties or requirements or "See the official advertisement for the duties and requirements."
        records.append(
            {
                "id": f"dpsa-{identifier}",
                "title": title,
                "department": department,
                "province": province,
                "location": centre[:120] if centre else province,
                "category": classify(title, requirements),
                "salary": salary,
                "closingDate": closing_date.isoformat(),
                "publishedDate": published.isoformat(),
                "circular": circular,
                "reference": reference_match.group(1) if reference_match else match.group(1),
                "summary": summary[:650],
                "requirements": [requirements[:600]] if requirements else ["See the official advertisement."],
                "sourceUrl": pdf_url,
                "circularPageUrl": "",
            }
        )
    return records


def load_state() -> dict[str, object]:
    if not STATE_FILE.exists():
        return {"processedCirculars": [], "lastUpdated": ""}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def load_existing_listings() -> list[dict[str, object]]:
    if not JSON_DATA_FILE.exists():
        return []
    records = json.loads(JSON_DATA_FILE.read_text(encoding="utf-8"))
    for record in records if isinstance(records, list) else []:
        if isinstance(record, dict):
            province = str(record.get("province", ""))
            record["province"] = PROVINCES.get(province.lower(), province)
    return records if isinstance(records, list) else []


def write_site_data(records: list[dict[str, object]]) -> None:
    data = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    rendered = "window.GOVVACANCY_LISTINGS = " + data.rstrip() + ";\n"
    JSON_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    JSON_DATA_FILE.write_text(data, encoding="utf-8")
    DATA_FILE.write_text(rendered, encoding="utf-8")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    today = date.today()
    state = load_state()
    processed = set(state.get("processedCirculars", []))
    page_markup = fetch(SOURCE_PAGE).decode("utf-8", errors="replace")
    circular_links = find_circular_links(page_markup)
    if not circular_links:
        raise RuntimeError("No DPSA circular links were found; refusing to update the site.")

    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    existing = load_existing_listings()
    records_by_id = {
        str(record["id"]): record
        for record in existing
        if isinstance(record, dict)
        and record.get("id")
        and record.get("closingDate")
        and str(record["closingDate"]) >= today.isoformat()
        and not str(record.get("id", "")).startswith("example-")
    }
    records_added = 0
    successful_circulars = 0
    errors: list[str] = []

    for label, page_url, year, number in circular_links:
        circular_name = f"Circular {number} of {year}"
        try:
            circular_markup = fetch(page_url).decode("utf-8", errors="replace")
            posting_match = re.search(
                r"Posting Date\s*:\s*(.{1,60}?)\s*(?:Full Document|WhatsApp|$)",
                page_text(circular_markup),
                re.IGNORECASE,
            )
            published = get_date(posting_match.group(1)) if posting_match else None
            if not published or published < cutoff or page_url in processed:
                continue

            pdf_links = find_pdf_links(circular_markup, page_url)
            if not pdf_links:
                raise RuntimeError(f"No department/province PDFs found for {circular_name}")
            LOG.info("Processing %s (%s; %d PDF links)", circular_name, published, len(pdf_links))
            circular_records = 0
            parsed_posts = 0
            circular_had_errors = False
            for department_label, pdf_url in pdf_links:
                try:
                    parsed = parse_pdf(fetch(pdf_url), circular_name, published, department_label, pdf_url)
                    for record in parsed:
                        parsed_posts += 1
                        if str(record["closingDate"]) < today.isoformat():
                            continue
                        record["circularPageUrl"] = page_url
                        records_by_id[str(record["id"])] = record
                        circular_records += 1
                except (urllib.error.URLError, TimeoutError, ValueError, fitz.FileDataError) as error:
                    LOG.warning("Could not extract %s: %s", pdf_url, error)
                    errors.append(f"{circular_name}: {pdf_url}: {error}")
                    circular_had_errors = True
            if parsed_posts and not circular_had_errors:
                processed.add(page_url)
                successful_circulars += 1
            if circular_records:
                records_added += circular_records
                LOG.info("Extracted %d active vacancies (%d total posts) from %s", circular_records, parsed_posts, circular_name)
            else:
                LOG.info("No active vacancies found in %s (%d posts parsed)", circular_name, parsed_posts)
                if not parsed_posts:
                    errors.append(f"{circular_name}: no vacancy posts could be extracted")
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as error:
            LOG.warning("Could not process %s: %s", circular_name, error)
            errors.append(f"{circular_name}: {error}")

    records = sorted(
        records_by_id.values(),
        key=lambda record: (str(record["closingDate"]), str(record["title"]).casefold()),
    )
    if not records and not successful_circulars and not existing:
        raise RuntimeError("No active vacancies were extracted; keeping the current site data unchanged.")
    if records_added == 0 and not existing and not successful_circulars:
        raise RuntimeError("No new vacancies were extracted and no existing vacancy data is available.")

    if records_added:
        state["lastUpdated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["processedCirculars"] = sorted(processed)
    state["activeVacancyCount"] = len(records)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_site_data(records)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    LOG.info(
        "Site data contains %d active vacancies; added %d from recent circulars.",
        len(records),
        records_added,
    )
    if errors:
        LOG.warning("%d extraction issue(s) remain for a later retry.", len(errors))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        LOG.exception("Vacancy ingestion failed: %s", error)
        sys.exit(1)
