import logfire

def parse_text(file_path: str) -> str:
    """
    Reads plain text/markdown documents locally.
    """
    with logfire.span("📝 Plain Text/Markdown Parsing", filename=file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            
            if not text.strip():
                logfire.warning(f"⚠️ Text file is empty: {file_path}")
            else:
                logfire.info(f"✅ Successfully read {len(text)} characters")
                
            return text
        except Exception as e:
            logfire.error(f"❌ Text Parse Failed: {e}")
            raise e
