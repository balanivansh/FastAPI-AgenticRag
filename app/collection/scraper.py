"""Crawl rendered documentation pages and save the raw HTML locally.

Install dependencies first:
    pip install playwright beautifulsoup4 logfire
    playwright install chromium
"""

import asyncio
import os
import sys
from collections import deque
from urllib.parse import quote, urldefrag, urljoin, urlsplit, urlunsplit

import logfire
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


logfire.configure(service_name="documentation-collection-service")

# Default documentation source and local folder for raw rendered HTML pages.
START_URL = "https://fastapi.tiangolo.com/"
RAW_DATA_DIR = "DATA"
NAVIGATION_TIMEOUT_MS = 10_000

# Direct downloads and static assets are not documentation pages.
NON_HTML_SUFFIXES = {
    ".7z", ".avi", ".bin", ".bmp", ".css", ".csv", ".doc", ".docx",
    ".exe", ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".js", ".json",
    ".map", ".mov", ".mp3", ".mp4", ".pdf", ".png", ".ppt", ".pptx",
    ".rar", ".svg", ".tar", ".tgz", ".tif", ".tiff", ".txt", ".webm",
    ".webp", ".woff", ".woff2", ".xls", ".xlsx", ".xml", ".zip",
}
LANGUAGE_PREFIXES = {
    "de", "es", "fr", "hi", "ja", "ko",
    "pt", "ru", "tr", "uk", "zh", "zh-hant",
}
ALLOWED_DOC_PREFIXES = (
    "/tutorial/",
    "/advanced/",
    "/deployment/",
    "/how-to/",
    "/reference/",
    "/async/",
    "/python-types/",
    "/environment-variables/",
    "/virtual-environments/",
)

def normalize_url(url: str) -> str:
    """Remove query parameters and fragments so each page is crawled once."""
    url, _ = urldefrag(url)
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))


def is_valid_page_url(url: str, target_netloc: str) -> bool:
    """Allow only same-domain English HTTP(S) documentation pages."""
    parts = urlsplit(url)
    first_path_segment = parts.path.strip("/").split("/", 1)[0]
    extension = os.path.splitext(parts.path)[1].lower()

    if first_path_segment in LANGUAGE_PREFIXES:
        return False

    return (
        parts.scheme in ("http", "https")
        and parts.netloc.lower() == target_netloc
        and extension not in NON_HTML_SUFFIXES
    )

def is_useful_doc_url(url: str) -> bool:
    """Keep only the FastAPI documentation sections selected for this RAG corpus."""
    path = urlsplit(url).path or "/"

    # Allow the home page so the crawler can discover documentation links.
    if path == "/":
        return True

    return path.startswith(ALLOWED_DOC_PREFIXES)

def extract_main_content(html: str) -> str:
    """Extract the primary body/article content from a page, removing boilerplate."""
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Try to find the primary content container using standard documentation layouts
    content_area = None
    for selector in [
        ("article", {"class": "md-content__inner"}), # MkDocs (FastAPI default)
        ("article", {}),                             # HTML5 Article
        ("main", {}),                                # HTML5 Main
        ("div", {"id": "content"}),
        ("div", {"class": "content"}),
        ("div", {"id": "main"}),
        ("div", {"class": "main"}),
    ]:
        tag, attrs = selector
        found = soup.find(tag, attrs=attrs)
        if found:
            content_area = found
            break
            
    # Fallback to body if no specific content area is identified
    if not content_area:
        content_area = soup.find("body") or soup

    # Make a copy so we don't mutate the original soup used in link discovery
    import copy
    content_area = copy.copy(content_area)

    # 2. De-clutter: Remove common boilerplate elements if they exist inside the content area
    for tag_name in ["script", "style", "nav", "header", "footer", "aside"]:
        for element in content_area.find_all(tag_name):
            element.decompose()
            
    # Also strip known class-based boilerplate (like navigation sidebars, headers, banners)
    for cls in ["md-sidebar", "md-header", "md-footer", "md-nav", "announce-wrapper"]:
        for element in content_area.find_all(class_=cls):
            element.decompose()

    return str(content_area)

def get_filename(url: str) -> str:
    """Map a URL path to a flat, safe, distinct Markdown filename."""
    path = urlsplit(url).path or "/"
    if path == "/":
        return "index.md"

    # Escape literal underscores so /a_b/ and /a/b/ cannot collide.
    path_parts = path[1:].split("/")
    has_trailing_slash = path_parts[-1] == ""
    if has_trailing_slash:
        path_parts.pop()

    safe_parts = [
        quote(part, safe="-.~").replace("_", "%5F") or "%00"
        for part in path_parts
    ]
    filename = "_".join(safe_parts) or "index"

    # Preserve the distinction between /docs and /docs/.
    if not has_trailing_slash:
        filename += "_file"
    if filename.startswith("."):
        filename = f"path{filename}"

    return f"{filename}.md"


def discover_links(html: str, current_url: str, target_netloc: str) -> list[str]:
    """Extract unique same-domain page URLs from rendered HTML."""
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for anchor in soup.find_all("a", href=True):
        candidate = normalize_url(urljoin(current_url, str(anchor["href"])))

        if (
            is_valid_page_url(candidate, target_netloc)
            and is_useful_doc_url(candidate)
        ):
            links.append(candidate)    

    return links


async def crawl_website(start_url: str, output_dir: str):
    """Breadth-first crawl every discovered same-domain rendered HTML page."""
    with logfire.span("Documentation Crawl", start_url=start_url, output_dir=output_dir):
        start_url = normalize_url(start_url)
        start_parts = urlsplit(start_url)

        if start_parts.scheme not in ("http", "https") or not start_parts.netloc:
            raise ValueError("START_URL must be an absolute http(s) URL")

        target_netloc = start_parts.netloc.lower()
        os.makedirs(output_dir, exist_ok=True)

        queue = deque([start_url])
        visited_urls = {start_url}
        saved_pages = 0

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

            try:
                while queue:
                    current_url = queue.popleft()

                    with logfire.span("Scraping Page", url=current_url):
                        try:
                            # First try to wait for the fully rendered SPA.
                            await page.goto(current_url, wait_until="networkidle")

                        except PlaywrightTimeoutError:
                            # FastAPI keeps some background requests open. The visible page is still
                            # normally rendered, so continue and capture its HTML.
                            logfire.warning(
                                f"Network idle timed out; using rendered-page fallback: {current_url}"
                            )

                        except Exception as e:
                            logfire.error(f"Failed to scrape {current_url}: {e}")
                            continue

                        # Do not collect a page that redirects outside the target site.
                        if not is_valid_page_url(normalize_url(page.url), target_netloc):
                            logfire.warning(f"Redirected outside target domain: {current_url}")
                            continue

                        try:
                            html = await page.content()
                        except Exception as e:
                            logfire.error(f"Failed to read rendered HTML from {current_url}: {e}")
                            continue

                        filename = get_filename(current_url)
                        destination = os.path.join(output_dir, filename)

                        # Clean HTML by extracting main content block and stripping boilerplate
                        clean_html = extract_main_content(html)
                        content_to_save = md(clean_html, heading_style="ATX")

                        try:
                            with open(destination, "w", encoding="utf-8") as file:
                                file.write(content_to_save)
                            saved_pages += 1
                            logfire.info(f"Saved cleaned Markdown → {destination}")
                        except OSError as e:
                            logfire.error(f"Failed to save {destination}: {e}")
                            continue

                        for link in discover_links(html, current_url, target_netloc):
                            if link not in visited_urls:
                                visited_urls.add(link)
                                queue.append(link)
            finally:
                await context.close()
                await browser.close()

        logfire.info(
            f"Crawl complete. Saved {saved_pages} pages "
            f"from {len(visited_urls)} discovered internal URLs."
        )


if __name__ == "__main__":
    # Usage:
    #   python -m app.ingestion.scraper
    #   python -m app.ingestion.scraper https://fastapi.tiangolo.com/ DATA
    target_url = sys.argv[1] if len(sys.argv) > 1 else START_URL
    target_dir = sys.argv[2] if len(sys.argv) > 2 else RAW_DATA_DIR

    try:
        asyncio.run(crawl_website(target_url, target_dir))
    except KeyboardInterrupt:
        logfire.warning("Crawl stopped by user.")
    except Exception as e:
        logfire.error(f"Documentation crawl failed: {e}")
        sys.exit(1)
