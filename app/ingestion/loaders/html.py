import logfire
from bs4 import BeautifulSoup
from markdownify import markdownify as md

def extract_main_content(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    
    # Try to find the primary content container using standard layouts
    content_area = None
    for selector in [
        ("article", {"class": "md-content__inner"}), 
        ("article", {}),                             
        ("main", {}),                                
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
            
    if not content_area:
        content_area = soup.find("body") or soup

    # De-clutter
    for tag_name in ["script", "style", "nav", "header", "footer", "aside"]:
        for element in content_area.find_all(tag_name):
            element.decompose()
            
    for cls in ["md-sidebar", "md-header", "md-footer", "md-nav", "announce-wrapper"]:
        for element in content_area.find_all(class_=cls):
            element.decompose()

    return str(content_area)

def parse_html(file_path: str) -> str:
    """
    Parses HTML documents locally, extracting only the main content article 
    and converting it to Markdown text to minimize tokens and noise.
    """
    with logfire.span("🌐 HTML Parsing & Cleaning", filename=file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                html_content = f.read()
                
            clean_html = extract_main_content(html_content)
            markdown_content = md(clean_html, heading_style="ATX")
            
            if not markdown_content.strip():
                logfire.warning(f"⚠️ HTML parser returned empty text for {file_path}")
            else:
                logfire.info(f"✅ Successfully parsed HTML and extracted {len(markdown_content)} characters")

            return markdown_content
        except Exception as e:
            logfire.error(f"❌ HTML Parse Failed: {e}")
            raise e
