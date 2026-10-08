"""Function declarations in C, C++ and Java, where no keyword (`fn`, `def`,
`func`) marks them: the return type comes first, then the name.

Shared by verify_spec.py (which lines declare what) and render.py (where a
declaration's parameter list starts and what its return type is), so both
read a declaration the same way.

A line declares a function when, after optional annotations, `template<…>`
and modifiers, it reads `<return type> <Qualifier::>name(` — or, with no
return type, `<modifier> Name(` (a Java constructor) or `Qual::Name(` at
column 0 (a C++ constructor/destructor defined out of line) — AND the
parameter list is followed by a body `{` (or a C++ initializer list `:`)
before any `;`. So prototypes, calls, object constructions
(`Foo bar(1);`) and control statements (`if (…) {`) never count. GNU style,
where the return type sits alone on the line above (`static int` / `foo(…)`),
counts too, with the name line as the declaration line.
"""
import re

CLIKE_EXT = (".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".java")

_ANN = r"(?:@[\w.]+(?:\([^)]*\))?\s+)*"
_TMPL = r"(?:template\s*<.*?>\s*)?"
_MOD = (r"(?:public|private|protected|static|final|abstract|synchronized|native|inline|__inline|"
        r"virtual|explicit|extern|constexpr|consteval|friend|default|strictfp)")
_MODS = rf"(?:{_MOD}\s+)*"
_GEN = r"(?:<[^;(){{}}=]*?>\s+)?"  # a Java generic method's `<T>`
_TYPE = (r"(?:(?:const|volatile|unsigned|signed|struct|enum|union|long|short|typename)\s+)*"
         r"[A-Za-z_][\w:]*(?:\s*<[^;(){}=]*>)?(?:\s*\[\s*\])*(?:\s*(?:\bconst\b|\*|&&?))*")
_QUAL = r"(?:[A-Za-z_]\w*(?:<[^;(){}=]*?>)?::)*"
_NAME = r"(?P<name>~?[A-Za-z_]\w*|operator\s*[^\s(]+)"

_WITH_RET = re.compile(rf"^\s*{_ANN}{_TMPL}{_MODS}{_GEN}(?P<ret>{_TYPE})(?:\s+|(?<=[*&])){_QUAL}{_NAME}\s*\(")
_CTOR = re.compile(rf"^\s*{_ANN}{_TMPL}(?:{_MOD}\s+)+{_QUAL}{_NAME}\s*\(")
_OUT_OF_LINE = re.compile(rf"^{_TMPL}(?P<qual>(?:[A-Za-z_]\w*(?:<[^;(){{}}=]*?>)?::)+){_NAME}\s*\(")
_BARE = re.compile(rf"^{_NAME}\s*\(")  # GNU style name line
_RET_ONLY = re.compile(rf"^\s*{_ANN}{_TMPL}{_MODS}(?P<ret>{_TYPE})\s*$")

# Words that start a statement, never a return type or a function name.
_NOT_TYPE = {"return", "else", "new", "delete", "throw", "case", "goto", "co_return", "co_yield",
             "co_await", "using", "typedef", "namespace", "do", "sizeof"}
_NOT_NAME = {"if", "for", "while", "switch", "catch", "return", "sizeof", "else", "do", "new",
             "delete", "throw", "case", "typeid", "alignof", "decltype", "static_assert", "defined",
             "synchronized", "try"}


def is_clike(path):
    return path.endswith(CLIKE_EXT)


def _is_definition(lines, i, col):
    """The parameter list opening at lines[i][col] closes and is followed
    by `{` (or `:` for an initializer list) before any `;` or `=`."""
    text = "\n".join(lines[i:i + 40])
    depth = 0
    for j in range(col, len(text)):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                rest = text[j + 1:]
                m = re.search(r"[{;=]|(?<!:):(?!:)", rest)
                return bool(m) and m.group(0) in "{:"
    return False


def function(lines, i):
    """(name, return type, column of the opening paren) when lines[i]
    declares a C/C++/Java function (see the module doc), else None. The
    return type is "" for a constructor/destructor."""
    line = lines[i]
    if line.rstrip().endswith(";"):
        return None
    ret = None
    m = _WITH_RET.match(line)
    if m and m.group("ret").split()[0].split("::")[0] not in _NOT_TYPE \
            and m.group("ret").strip() not in _NOT_NAME:
        ret = " ".join(m.group("ret").split())
        if re.fullmatch(_MOD, ret.split()[0]):
            ret = ""  # `public Foo(`: a constructor, the modifier is not a type
    else:
        m = _CTOR.match(line) or _OUT_OF_LINE.match(line)
        if m:
            ret = ""
        else:
            m = _BARE.match(line)
            prev = next((lines[k] for k in range(i - 1, max(i - 3, -1), -1) if lines[k].strip()), "")
            r = _RET_ONLY.match(prev) if m else None
            if not r or r.group("ret").split()[0] in _NOT_TYPE or prev.rstrip().endswith((";", "{", "}", ")", ",")):
                return None
            ret = " ".join(r.group("ret").split())
    name = m.group("name")
    if name in _NOT_NAME or name.split()[0] in _NOT_NAME:
        return None
    col = m.end() - 1
    if not _is_definition(lines, i, col):
        return None
    return name, ret, col
