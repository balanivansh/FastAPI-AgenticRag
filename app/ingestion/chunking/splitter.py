from typing import List
import logfire

def chunk_text(text: str, chunk_size: int = 1500, chunk_overlap: int = 200) -> List[str]:
    """
    Split text into chunks by paragraphs, ensuring no chunk exceeds chunk_size,
    with an overlap to preserve context between chunks.
    """
    with logfire.span("✂️ Text Chunking", text_length=len(text), chunk_size=chunk_size):
        if not text.strip():
            return []

        # Split by double newlines to preserve paragraph boundaries
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_length = 0

        for p in paragraphs:
            p_len = len(p)
            if not p.strip():
                continue

            # Case 1: Single paragraph exceeds chunk_size (e.g. massive code blocks)
            if p_len >= chunk_size:
                # Flush active chunk first
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                
                # Split this oversized paragraph by lines
                lines = p.split("\n")
                sub_chunk = []
                sub_length = 0
                for line in lines:
                    if sub_length + len(line) + 1 > chunk_size:
                        if sub_chunk:
                            chunks.append("\n".join(sub_chunk))
                        sub_chunk = [line]
                        sub_length = len(line)
                    else:
                        sub_chunk.append(line)
                        sub_length += len(line) + 1
                if sub_chunk:
                    chunks.append("\n".join(sub_chunk))
                continue

            # Case 2: Paragraph fits within active chunk
            if current_length + p_len + 2 <= chunk_size:
                current_chunk.append(p)
                current_length += p_len + 2
            else:
                # Flush the completed chunk
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                
                # Start new chunk with overlap from the end of the previous chunk
                overlap_chunk = []
                overlap_len = 0
                for prev_p in reversed(current_chunk):
                    if overlap_len + len(prev_p) + 2 <= chunk_overlap:
                        overlap_chunk.insert(0, prev_p)
                        overlap_len += len(prev_p) + 2
                    else:
                        break
                
                current_chunk = overlap_chunk + [p]
                current_length = overlap_len + p_len + 2

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        valid_chunks = [c.strip() for c in chunks if c.strip()]
        logfire.info(f"✅ Generated {len(valid_chunks)} chunks")
        return valid_chunks
