import re

def unescape(text):
    return re.sub(r'\\([\[\]_\-=\.])', r'\1', text)

def format_log1(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = unescape(content)
    
    prefixes = [
        r'\[\d{2}:\d{2}:\d{2}\]',
        r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - INFO -',
        r'\[Twitter\]',
        r'\[Reddit\]',
        r'\[Common LLM\]',
        r'\[attach_tools\]',
        r'\[FunctionTool\]',
        r"\{'user_profile':",
        r'\[context-patch\]',
        r'\[AgentToolRegistry\]',
    ]
    pattern = r'(?=(' + '|'.join(prefixes) + r'))'
    
    parts = re.split(pattern, content)
    
    formatted_lines = []
    current_line = ""
    for part in parts:
        if not part: continue
        if re.match('^(' + '|'.join(prefixes) + ')$', part):
            if current_line.strip():
                formatted_lines.append(current_line.strip())
            current_line = part
        else:
            current_line += part
    if current_line.strip():
        formatted_lines.append(current_line.strip())

    with open(path, 'w', encoding='utf-8') as f:
        for line in formatted_lines:
            f.write(line + '\n\n')

def format_log2(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    content = unescape(content)

    pattern = r'(?=\[R\d+\s·\s[A-Z]+\])'
    parts = re.split(pattern, content)
    
    formatted_lines = []
    for part in parts:
        if part.strip():
            formatted_lines.append(part.strip())

    with open(path, 'w', encoding='utf-8') as f:
        for line in formatted_lines:
            match = re.match(r'^(\[R\d+\s·\s[A-Z]+\])(.*?)(CREATE_POST|CREATE_COMMENT|LIKE_POST|DISLIKE_POST|LIKE_COMMENT|DISLIKE_COMMENT|FOLLOW|SEARCH_USER)(—\s)?(.*)$', line, re.DOTALL)
            if match:
                f.write(f"**{match.group(1)} {match.group(2).strip()}** `{match.group(3)}`\n")
                if match.group(5).strip():
                    f.write(f"> {match.group(5).strip()}\n")
                f.write("\n---\n\n")
            else:
                f.write(line + '\n\n')

format_log1('docs/logs/log 1 (1).md')
format_log2('docs/logs/log2 (1).md')
print("Done formatting logs")
