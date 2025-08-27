import ply.lex as lex
import ply.yacc as yacc
import sys
from typing import List, Tuple

# --- Lexer ---
tokens = (
    'HOTSTRING', 'HOTKEY', 'RUN', 'SEND', 'GUI', 'IF', 'ELSE', 'LOOP', 'STRING', 'IDENT', 'NUMBER', 'NEWLINE',
    'RETURN', 'MSGBOX', 'COLON', 'LBRACE', 'RBRACE', 'COMMENT'
)

t_ignore = ' \t'

def t_HOTSTRING(t):
    r'::[a-zA-Z0-9#@!\$%\^&\*\(\)_\+\-=]+::'
    return t

def t_HOTKEY(t):
    r'[\^!\+#]*[a-zA-Z0-9_\+\-]+::'
    return t

def t_RUN(t):
    r'Run'
    return t

def t_SEND(t):
    r'Send(Text)?'
    return t

def t_GUI(t):
    r'Gui'
    return t

def t_IF(t):
    r'if'
    return t

def t_ELSE(t):
    r'else'
    return t

def t_LOOP(t):
    r'Loop'
    return t

def t_STRING(t):
    r'"([^\"]|\\.)*"|\'([^\']|\\.)*\''
    return t

def t_IDENT(t):
    r'[a-zA-Z_][a-zA-Z0-9_]*'
    return t

def t_NUMBER(t):
    r'\d+'
    return t

def t_NEWLINE(t):
    r'\n+'
    t.lexer.lineno += len(t.value)
    return t

def t_error(t):
    # Don't print error for common AHK characters
    if t.value[0] in '^!+#{}':
        t.lexer.skip(1)
        return
    print(f"Illegal character '{t.value[0]}' at line {t.lexer.lineno}")
    t.lexer.skip(1)

lexer = lex.lex()

# --- Parser ---
def p_script(p):
    '''script : lines'''
    p[0] = p[1]

def p_lines(p):
    '''lines : line
             | lines line'''
    pass

def p_line(p):
    '''line : HOTSTRING STRING NEWLINE
            | HOTKEY SEND STRING NEWLINE
            | HOTKEY RUN STRING NEWLINE
            | HOTKEY NEWLINE
            | IF condition NEWLINE
            | ELSE NEWLINE
            | LOOP NEWLINE
            | GUI NEWLINE
            | NEWLINE
            | IDENT NEWLINE
            | STRING NEWLINE'''
    pass

def p_condition(p):
    '''condition : IDENT
                 | IDENT NUMBER'''
    pass

def p_error(p):
    # Raise an exception that we can intercept to provide richer feedback
    if p:
        raise SyntaxError(f"Syntax error at '{p.value}' (line {p.lineno})")
    else:
        raise SyntaxError("Syntax error at EOF")

parser = yacc.yacc()

def _basic_paren_check(script_text: str) -> Tuple[bool, str]:
    """Very lightweight parenthesis balance heuristic.
    Not a full parse; just ensures counts of () match and no premature closing.
    """
    count = 0
    for i, ch in enumerate(script_text, start=1):
        if ch == '(':
            count += 1
        elif ch == ')':
            count -= 1
            if count < 0:
                return False, f"Unmatched ')' at char {i}"
    if count != 0:
        return False, "Unbalanced parentheses"
    return True, "OK"

def validate_ahk_script(script_text: str) -> bool:
    """Validate an AHK v2 script snippet.

    Returns True if syntactically OK relative to our limited grammar; False otherwise.
    Prints user-friendly messages for command line usage.
    """
    # Quick structural checks first
    ok, msg = _basic_paren_check(script_text)
    if not ok:
        print(f"Validation error: {msg}")
        return False
    try:
        parser.parse(script_text)
        print("Validation: OK")
        return True
    except SyntaxError as e:
        print(f"Validation error: {e}")
        return False
    except Exception as e:  # Fallback catch
        print(f"Validation unexpected error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python AHK-Validator.py <script.ahk>")
        sys.exit(1)
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        script = f.read()
    validate_ahk_script(script)
