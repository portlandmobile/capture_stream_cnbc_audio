import re

def chunk_transcript(text, max_chars=3000, overlap=200):
    # Split on double newlines (speaker turns / paragraphs)
    paragraphs = re.split(r'\n{2,}', text)
    chunks, current = [], ""
    
    for para in paragraphs:
        if len(current) + len(para) > max_chars:
            chunks.append(current)
            current = current[-overlap:] + para  # overlap for context
        else:
            current += "\n\n" + para
    
    if current:
        chunks.append(current)
    return chunks