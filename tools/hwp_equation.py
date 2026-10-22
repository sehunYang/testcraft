# -*- coding: utf-8 -*-
r"""Convert the project's inline LaTeX subset to native Hancom equation script.

The output follows Hancom's published equation syntax (grouping with ``{}``,
scripts with ``_``/``^``, and operators such as ``over`` and ``sqrt``).  It is
deliberately a parser rather than a sequence of substitutions: unsupported
commands and malformed groups must stop document generation instead of
silently leaking damaged LaTeX into an HML ``SCRIPT``.

Syntax reference: Hancom, *Hwp Document File Formats - Equation*, rev. 1.3,
https://cdn.hancom.com/link/docs/%ED%95%9C%EA%B8%80%EB%AC%B8%EC%84%9C%ED%8C%8C%EC%9D%BC%ED%98%95%EC%8B%9D_%EC%88%98%EC%8B%9D_revision1.3.pdf
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re


class EquationConversionError(ValueError):
    """A LaTeX equation cannot be represented as valid native HWP script."""


@dataclass
class Node:
    kind: str
    value: str = ""
    children: list["Node"] = field(default_factory=list)
    sub: list["Node"] | None = None
    sup: list["Node"] | None = None
    index: list["Node"] | None = None
    closing: str = ""


GREEK = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "zeta": "zeta", "eta": "eta", "theta": "theta",
    "iota": "iota", "kappa": "kappa", "lambda": "lambda", "mu": "mu",
    "nu": "nu", "xi": "xi", "omicron": "omicron", "pi": "pi",
    "rho": "rho", "sigma": "sigma", "tau": "tau", "upsilon": "upsilon",
    "phi": "phi", "chi": "chi", "psi": "psi", "omega": "omega",
    "Gamma": "GAMMA", "Delta": "DELTA", "Theta": "THETA",
    "Lambda": "LAMBDA", "Xi": "XI", "Pi": "PI", "Sigma": "SIGMA",
    "Upsilon": "UPSILON", "Phi": "PHI", "Psi": "PSI", "Omega": "OMEGA",
    "varepsilon": "varepsilon", "vartheta": "vartheta", "varpi": "varpi",
    "varsigma": "varsigma", "varupsilon": "varupsilon", "varphi": "varphi",
}

FUNCTIONS = {
    "sin": "sin", "cos": "cos", "tan": "tan", "cot": "cot", "sec": "sec",
    "csc": "csc", "cosec": "cosec", "arcsin": "arcsin", "arccos": "arccos",
    "arctan": "arctan", "asin": "asin", "acos": "acos", "atan": "atan",
    "sinh": "sinh", "cosh": "cosh", "tanh": "tanh", "coth": "coth",
    "log": "log", "ln": "ln", "lg": "lg", "exp": "exp", "max": "max",
    "min": "min", "lim": "lim", "det": "det", "mod": "mod", "gcd": "gcd",
    "lcm": "lcm", "arg": "arg",
}

SYMBOLS = {
    "times": "times", "cdot": "cdot", "cdotp": "cdot", "pm": "PLUSMINUS", "mp": "MINUSPLUS",
    "le": "LEQ", "leq": "LEQ", "ge": "GEQ", "geq": "GEQ", "ne": "neq",
    "neq": "neq", "approx": "APPROX", "sim": "SIM", "simeq": "SIMEQ",
    "equiv": "EQUIV", "cong": "CONG", "propto": "PROPTO", "in": "IN",
    "notin": "notin", "subset": "SUBSET", "supset": "SUPSET",
    "subseteq": "SUBSETEQ", "supseteq": "SUPSETEQ", "cup": "UNION",
    "cap": "INTER", "oplus": "OPLUS", "otimes": "OTIMES", "odot": "ODOT",
    "forall": "FORALL", "exists": "EXIST", "therefore": "THEREFORE",
    "because": "BECAUSE", "partial": "PARTIAL", "nabla": "NABLA",
    "infty": "inf", "prime": "prime", "circ": "circ", "degree": "DEG",
    "angle": "ANGLE", "perp": "BOT", "parallel": "VERT", "emptyset": "EMPTYSET",
    "triangle": "TRIANGLE", "ldots": "LDOTS", "cdots": "cdots", "dots": "cdots",
    "vdots": "VDOTS", "ddots": "DDOTS", "ell": "ELL",
    "hbar": "HBAR", "Im": "IMAG", "langle": "LANGLE",
    "rangle": "RANGLE", "lbrace": "lbrace", "rbrace": "rbrace",
    "leftarrow": "<-", "gets": "<-", "rightarrow": "->", "to": "->",
    "leftrightarrow": "<->", "uparrow": "uparrow", "downarrow": "downarrow",
    "mapsto": "mapsto", "sum": "sum", "prod": "prod", "int": "int",
    "oint": "oint", "union": "UNION", "inter": "INTER",
}

DECORATIONS = {
    "vec": "vec", "bar": "bar", "overline": "bar", "hat": "hat",
    "tilde": "tilde", "dot": "dot", "ddot": "ddot", "check": "check",
    "acute": "acute", "grave": "grave", "underline": "under", "under": "under",
}

_ESCAPED = {"%": "%", "#": "#", "&": "&", "_": "_", "$": "$", " ": " ", "~": "∼"}
NATIVE_WORDS = (
    set(GREEK.values()) | set(FUNCTIONS.values()) | set(SYMBOLS.values()) |
    set(DECORATIONS.values()) |
    {"rm", "it", "bold", "over", "atop", "sqrt", "root", "from", "to", "of",
     "int", "oint", "dint", "tint", "sum", "prod", "matrix", "pmatrix", "bmatrix",
     "dmatrix", "cases", "inf", "circ", "DEG", "LEFT", "RIGHT", "lbrace", "rbrace"}
)


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.i = 0
        self._last_right_delimiter: str | None = None

    def fail(self, message: str, at: int | None = None) -> EquationConversionError:
        pos = self.i if at is None else at
        left = max(0, pos - 12)
        right = min(len(self.source), pos + 20)
        excerpt = self.source[left:right].replace("\n", " ")
        return EquationConversionError(
            f"한글 수식으로 변환할 수 없습니다 (위치 {pos + 1}): {message}; 입력: {excerpt!r}"
        )

    def skip_space(self) -> None:
        while self.i < len(self.source) and self.source[self.i].isspace():
            self.i += 1

    def parse(self) -> list[Node]:
        nodes = self.sequence()
        if self.i != len(self.source):
            raise self.fail("예상하지 못한 닫는 중괄호")
        if not nodes:
            raise self.fail("수식이 비어 있습니다", 0)
        return nodes

    def sequence(self, in_group: bool = False, close: str | None = None,
                 stop_right: bool = False) -> list[Node]:
        nodes: list[Node] = []
        while self.i < len(self.source):
            self.skip_space()
            if self.i >= len(self.source):
                break
            ch = self.source[self.i]
            if close is not None and ch == close:
                self.i += 1
                return nodes
            if ch == "}":
                if not in_group:
                    raise self.fail("짝이 맞지 않는 닫는 중괄호")
                self.i += 1
                return nodes
            if ch in ")]":
                raise self.fail(f"짝이 맞지 않는 닫는 괄호 {ch!r}")
            if ch in "([":
                opening_at = self.i
                self.i += 1
                closing = ")" if ch == "(" else "]"
                children = self.sequence(close=closing, stop_right=stop_right)
                if self.i >= len(self.source) and (not self.source or self.source[-1] != closing):
                    raise self.fail(f"여는 괄호 {ch!r}에 대응하는 {closing!r}가 없습니다", opening_at)
                nodes.append(Node("fence", value=ch, closing=closing, children=children))
                continue
            if stop_right and self.source.startswith("\\right", self.i):
                name, at = self.command_name()
                if name != "right":
                    raise self.fail("내부 오류: 오른쪽 괄호 명령 확인 실패", at)
                self._last_right_delimiter = self.delimiter("right", at)
                return nodes
            if ch == "{":
                start = self.i
                self.i += 1
                children = self.sequence(in_group=True)
                if self.i == len(self.source) and (not self.source or self.source[-1] != "}"):
                    raise self.fail("닫히지 않은 중괄호", start)
                nodes.append(Node("group", children=children))
                continue
            if ch in "_^":
                if not nodes:
                    raise self.fail(f"첨자 {ch!r} 앞에 기준 항이 없습니다")
                marker = ch
                at = self.i
                self.i += 1
                argument = self.argument(f"첨자 {marker}")
                node = nodes[-1]
                field_name = "sub" if marker == "_" else "sup"
                if getattr(node, field_name) is not None:
                    raise self.fail(f"같은 항에 {marker} 첨자가 두 번 지정되었습니다", at)
                setattr(node, field_name, argument)
                continue
            if ch == "\\":
                nodes.append(self.command())
                continue
            if ch == "[":
                nodes.append(Node("token", "[")); self.i += 1; continue
            if ch == "]":
                nodes.append(Node("token", "]")); self.i += 1; continue
            # Native HWP script recognizes these as single relation terms.
            # Keep their characters adjacent; emitting separate '-'/'>'
            # tokens changes the displayed arrow into two operators.
            matched_operator = next((op for op in ("<->", "->", "<-", "<=", ">=", "!=", "==")
                                     if self.source.startswith(op, self.i)), None)
            if matched_operator:
                native = {"<=": "LEQ", ">=": "GEQ", "!=": "neq", "==": "EQUIV"}.get(
                    matched_operator, matched_operator)
                nodes.append(Node("token", native))
                self.i += len(matched_operator)
                continue
            if ch.isdigit():
                start = self.i
                while self.i < len(self.source) and self.source[self.i].isdigit():
                    self.i += 1
                nodes.append(Node("token", self.source[start:self.i]))
                continue
            if ch.isalpha() and ch.isascii():
                start = self.i
                while self.i < len(self.source) and self.source[self.i].isalpha() and self.source[self.i].isascii():
                    self.i += 1
                word = self.source[start:self.i]
                if word in NATIVE_WORDS:
                    nodes.append(Node("native", word))
                else:
                    nodes.extend(Node("token", letter) for letter in word)
                continue
            if ch in "~`":
                # Raw ASCII tilde is a printed glyph; spacing commands below
                # deliberately keep emitting Hancom's native `~` marker.
                nodes.append(Node("token", "∼" if ch == "~" else ch)); self.i += 1; continue
            if ch in "=#%&+-*/(),.:;!?|<>":
                nodes.append(Node("token", ch)); self.i += 1; continue
            if ch == "\n":
                nodes.append(Node("token", "#")); self.i += 1; continue
            if ch == '"':
                raise self.fail('수식에서 따옴표는 \" 안의 \text{}를 통해서만 쓸 수 있습니다')
            # Unicode symbols and Korean text inside 	ext-like authoring are
            # retained as literal native equation characters.
            nodes.append(Node("token", ch)); self.i += 1
        if close is not None:
            raise self.fail(f"여는 괄호에 대응하는 {close!r}가 없습니다", max(0, self.i - 1))
        if stop_right:
            raise self.fail("\\left 뒤에 대응하는 \\right가 없습니다", max(0, self.i - 1))
        if in_group:
            raise self.fail("닫히지 않은 중괄호", max(0, self.i - 1))
        return nodes

    def argument(self, label: str) -> list[Node]:
        self.skip_space()
        if self.i >= len(self.source):
            raise self.fail(f"{label}의 값이 없습니다")
        if self.source[self.i] == "{":
            self.i += 1
            start = self.i - 1
            result = self.sequence(in_group=True)
            # sequence() raises on end-of-input for a missing close.
            return result
        if self.source[self.i] == "\\":
            return [self.command()]
        ch = self.source[self.i]
        if ch in "_^}":
            raise self.fail(f"{label} 뒤에 유효한 항이 없습니다")
        if ch.isdigit():
            start = self.i
            while self.i < len(self.source) and self.source[self.i].isdigit():
                self.i += 1
            return [Node("token", self.source[start:self.i])]
        self.i += 1
        return [Node("token", ch)]

    def required_argument(self, command: str) -> list[Node]:
        self.skip_space()
        if self.i >= len(self.source):
            raise self.fail(f"\\{command} 인자가 없습니다")
        if self.source[self.i] == "{":
            self.i += 1
            result = self.sequence(in_group=True)
        elif self.source[self.i] == "\\":
            result = [self.command()]
        else:
            ch = self.source[self.i]
            if ch in "_^}":
                raise self.fail(f"\\{command} 뒤에 유효한 인자가 없습니다")
            self.i += 1
            result = [Node("token", ch)]
        if not result:
            raise self.fail(f"\\{command} 인자가 비어 있습니다")
        return result

    def raw_group(self, command: str) -> str:
        r"""Read literal content for \text/\mathrm without interpreting it as math."""
        self.skip_space()
        if self.i >= len(self.source) or self.source[self.i] != "{":
            raise self.fail(f"\\{command} 인자는 중괄호로 묶어야 합니다")
        self.i += 1
        start = self.i
        depth = 1
        chars: list[str] = []
        while self.i < len(self.source):
            ch = self.source[self.i]
            if ch == "\\":
                if self.i + 1 < len(self.source) and self.source[self.i + 1] in _ESCAPED:
                    chars.append(_ESCAPED[self.source[self.i + 1]])
                    self.i += 2
                    continue
                raise self.fail("텍스트 인자 안의 명령은 지원하지 않습니다", self.i)
            if ch == "{":
                depth += 1
                chars.append(ch)
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    value = "".join(chars)
                    if not value:
                        raise self.fail(f"\\{command}의 텍스트가 비어 있습니다", start)
                    return value
                chars.append(ch)
            else:
                chars.append("∼" if ch == "~" else ch)
            self.i += 1
        raise self.fail(f"\\{command}의 중괄호가 닫히지 않았습니다", start - 1)

    def command_name(self) -> tuple[str, int]:
        start = self.i
        self.i += 1
        if self.i >= len(self.source):
            raise self.fail("끝에 단독 역슬래시가 있습니다", start)
        if self.source[self.i].isalpha():
            name_start = self.i
            while self.i < len(self.source) and self.source[self.i].isalpha():
                self.i += 1
            return self.source[name_start:self.i], start
        name = self.source[self.i]
        self.i += 1
        return name, start

    def command(self) -> Node:
        name, at = self.command_name()
        if name in ("frac", "dfrac", "tfrac"):
            numerator = self.required_argument(name)
            denominator = self.required_argument(name)
            return Node("fraction", children=[Node("group", children=numerator),
                                                 Node("group", children=denominator)])
        if name == "sqrt":
            self.skip_space()
            index: list[Node] | None = None
            if self.i < len(self.source) and self.source[self.i] == "[":
                self.i += 1
                index = self.sequence_until_square()
            radicand = self.argument("\\sqrt")
            if index is None:
                return Node("root", children=radicand)
            # Hancom's published syntax represents an n-th root as ^n sqrt {...}.
            return Node("indexed_root", children=radicand, index=index)
        if name in ("text", "mathrm", "textrm", "operatorname"):
            value = self.raw_group(name)
            quoted = '"' + value + '"' if len(value) >= 9 or any(c.isspace() for c in value) else value
            return Node("roman", value=quoted)
        if name in ("mathbf", "boldsymbol"):
            return Node("bold", children=self.required_argument(name))
        if name == "mathit":
            return Node("italic", children=self.required_argument(name))
        if name in DECORATIONS:
            return Node("decoration", value=DECORATIONS[name], children=self.required_argument(name))
        if name in GREEK:
            return Node("greek", value=GREEK[name])
        if name in FUNCTIONS:
            return Node("function", value=FUNCTIONS[name])
        if name in SYMBOLS:
            return Node("token", SYMBOLS[name])
        if name == "over":
            return Node("native", "over")
        if name == "left":
            delimiter = self.delimiter(name, at)
            self._last_right_delimiter = None
            children = self.sequence(stop_right=True)
            if self._last_right_delimiter is None:
                raise self.fail("\\left 뒤에 대응하는 \\right가 없습니다", at)
            closing = self._last_right_delimiter
            self._last_right_delimiter = None
            return Node("fence", value="LEFT " + delimiter,
                        closing="RIGHT " + closing, children=children)
        if name == "right":
            raise self.fail("대응하는 \\left 없이 \\right가 나왔습니다", at)
        if name in ("quad", "qquad"):
            return Node("token", "~~" if name == "quad" else "~~~~")
        if name in (",", ";", ":", " "):
            return Node("token", "~" if name != "," else "`")
        if name == "!":
            return Node("token", "")
        if name in _ESCAPED:
            value = _ESCAPED[name]
            if value in "#&_":
                return Node("roman", value='"' + value + '"')
            return Node("token", value)
        if name == "{":
            return Node("token", "lbrace")
        if name == "}":
            return Node("token", "rbrace")
        raise self.fail(f"알 수 없거나 지원하지 않는 LaTeX 명령 \\{name}", at)

    def sequence_until_square(self) -> list[Node]:
        # Optional root index only accepts a simple balanced [] group. Braces
        # remain normal equation grouping inside it.
        start = self.i
        depth = 0
        brace_depth = 0
        while self.i < len(self.source):
            ch = self.source[self.i]
            if ch == "\\":
                self.i += 1
                if self.i < len(self.source): self.i += 1
                continue
            if ch == "{": brace_depth += 1
            elif ch == "}": brace_depth -= 1
            elif brace_depth == 0 and ch == "[": depth += 1
            elif brace_depth == 0 and ch == "]":
                if depth == 0:
                    raw = self.source[start:self.i]
                    self.i += 1
                    if not raw.strip(): raise self.fail("근 지수가 비어 있습니다", start)
                    return _Parser(raw).parse()
                depth -= 1
            self.i += 1
        raise self.fail("\\sqrt의 근 지수 대괄호가 닫히지 않았습니다", start - 1)

    def delimiter(self, command: str, at: int) -> str:
        self.skip_space()
        if self.i >= len(self.source):
            raise self.fail(f"\\{command} 뒤에 괄호가 없습니다", at)
        if self.source[self.i] == "\\":
            node = self.command()
            if node.kind != "token":
                raise self.fail(f"\\{command}에서 지원하지 않는 괄호입니다", at)
            return node.value
        ch = self.source[self.i]
        self.i += 1
        if ch == ".":
            return "."
        if ch in "()[]|":
            return ch
        raise self.fail(f"\\{command}에서 지원하지 않는 괄호 {ch!r}", self.i - 1)


def _serialize_nodes(nodes: list[Node]) -> str:
    return " ".join(part for node in nodes if (part := _serialize(node)))


def _serialize(node: Node) -> str:
    if node.kind == "group":
        body = "{ " + _serialize_nodes(node.children) + " }"
    elif node.kind == "fraction":
        body = _serialize(node.children[0]) + " over " + _serialize(node.children[1])
    elif node.kind == "root":
        body = "sqrt { " + _serialize_nodes(node.children) + " }"
    elif node.kind == "indexed_root":
        index = node.index or []
        index_script = _serialize_nodes(index)
        # Hancom's public PDF shows `^3sqrt{x}`, but all indexed-SQRT forms
        # tested in the installed HWP engine rendered blank. The engine does
        # render `root { 3 } of { x }`, so use that validated native form.
        body = "root { " + index_script + " } of { " + _serialize_nodes(node.children) + " }"
    elif node.kind == "decoration":
        body = node.value + " { " + _serialize_nodes(node.children) + " }"
    elif node.kind == "bold":
        body = "bold { " + _serialize_nodes(node.children) + " }"
    elif node.kind == "italic":
        body = "it { " + _serialize_nodes(node.children) + " }"
    elif node.kind == "fence":
        body = node.value + " " + _serialize_nodes(node.children) + " " + node.closing
    elif node.kind == "roman":
        body = "rm { " + node.value + " }"
    elif node.kind == "native":
        body = node.value
    else:
        body = node.value

    has_scripts = node.sub is not None or node.sup is not None
    if has_scripts and node.kind in ("group", "fence", "fraction", "root", "indexed_root",
                                     "decoration", "bold", "italic", "roman"):
        body = "{ " + body + " }"
    if node.sub is not None:
        body += " _ { " + _serialize_nodes(node.sub) + " }"
    if node.sup is not None:
        body += " ^ { " + _serialize_nodes(node.sup) + " }"

    # Hancom treats braces as a term-scope operator. Explicitly scope every
    # scripted one-letter/Greek/vector variable so the next variable can never
    # be swallowed into its subscript by the equation editor.
    if has_scripts:
        body = "{ " + body + " }"
    return body


def latex_to_hwp(source: str) -> str:
    """Convert a LaTeX math fragment into native Hancom equation script.

    Raises :class:`EquationConversionError` with the offending command or
    malformed construct. The result is guaranteed not to contain a backslash.
    """
    if not isinstance(source, str):
        source = str(source)
    result = _serialize_nodes(_Parser(source).parse())
    if "\\" in result:
        raise EquationConversionError("내부 오류: 결과 SCRIPT에 역슬래시가 남았습니다")
    return re.sub(r"\s+", " ", result).strip()

