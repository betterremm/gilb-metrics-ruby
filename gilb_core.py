#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ядро анализатора метрик Джилба (метрик сложности потока управления)
для исходного кода на языке Ruby.

Парсер написан на Python. Данный модуль НЕ зависит от графического
интерфейса и может использоваться как из GUI (gilb_gui.py), так и из
командной строки:

    python3 gilb_core.py <файл.rb>

------------------------------------------------------------------------
ОПРЕДЕЛЕНИЯ (метрика Джилба)
------------------------------------------------------------------------
  CL  — абсолютная сложность = количество условных операторов.
  cl  — относительная сложность = CL / N, где N — общее число операторов
        программы (оператор языка в классическом понимании).
  CLI — максимальный уровень вложенности условного оператора.

ПРАВИЛА ПОДСЧЁТА (в соответствии с требованиями задания):

Абсолютная сложность CL (вклад условных операторов):
  * каждый оператор ветвления if и каждый elsif — по 1
    (ветка else НЕ учитывается);
  * каждый unless — 1;
  * каждый тернарный оператор (cond ? a : b) — 1;
  * каждый оператор цикла (while, until, for, loop, а также итераторы
    each/times/upto/downto/step/map/… с блоком) — 1;
  * оператор множественного выбора case: учитывается КАЖДАЯ ветка when
    (ветка else НЕ учитывается). Три when → вклад 3.

Общее число операторов N:
  N = (число простых операторов-инструкций) + CL.
  Простые операторы — присваивания, вызовы, return/break/next/… (всё,
  что не является управляющей конструкцией). Определения def/class/module
  не считаются операторами. Таким образом CL ⊆ N и 0 ≤ cl ≤ 1.

Максимальный уровень вложенности CLI (отсчёт ОТ НУЛЯ):
  * управляющая конструкция на верхнем уровне имеет уровень 0
    (например, одиночный цикл — вложенность 0);
  * условный оператор внутри цикла имеет уровень 1 и т.д.
    (уровень = число охватывающих условных/циклических конструкций);
  * в операторе case каждая следующая ветка when увеличивает уровень
    вложенности на 1: первый when — уровень базовый, второй — базовый+1,
    третий — базовый+2. Поэтому три when дают максимальный уровень 2.
  Определения def/class/module/begin уровень вложенности НЕ увеличивают.

Содержимое комментариев и строк не анализируется. Предполагается
стандартный стиль оформления (управляющие ключевые слова в начале строки,
закрытие блока — end на отдельной строке).
"""

from __future__ import annotations
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional


# Итераторы Ruby, которые трактуются как операторы цикла.
ITERATORS = (
    "each_with_index", "each_with_object", "each_pair", "each_key",
    "each_value", "each_char", "each_line", "each_slice", "each_cons",
    "each", "times", "upto", "downto", "step", "map", "collect",
    "select", "filter", "reject", "detect", "find_all", "flat_map",
    "inject", "reduce", "cycle",
)

# Ключевые слова, открывающие структурный (не условный) блок.
STRUCT_OPENERS = ("def", "class", "module", "begin")


@dataclass
class BreakdownEntry:
    construct: str
    count: int
    contribution_to_cl: int
    note: str = ""


@dataclass
class GilbResult:
    cl: int = 0
    n: int = 0
    cli: int = 0
    if_count: int = 0
    elsif_count: int = 0
    unless_count: int = 0
    loop_count: int = 0
    case_count: int = 0
    when_count: int = 0
    ternary_count: int = 0
    simple_statements: int = 0
    breakdown: List[BreakdownEntry] = field(default_factory=list)

    @property
    def cl_relative(self) -> float:
        return self.cl / self.n if self.n > 0 else 0.0


# ------------------------------------------------------------------ #
# Очистка исходного текста: удаление комментариев и содержимого строк  #
# ------------------------------------------------------------------ #

def _strip_line(line: str) -> str:
    """Убирает комментарии '#...' и заменяет содержимое строковых литералов
    пробелами, сохраняя кавычки, чтобы ключевые слова внутри строк и
    комментариев не распознавались как операторы."""
    out = []
    i = 0
    n = len(line)
    quote: Optional[str] = None
    while i < n:
        ch = line[i]
        if quote is not None:
            if ch == "\\" and i + 1 < n:      # экранированный символ
                out.append("  ")
                i += 2
                continue
            if ch == quote:
                out.append(ch)               # закрывающая кавычка
                quote = None
            else:
                out.append(" ")              # содержимое строки -> пробел
            i += 1
            continue
        # вне строки
        if ch == "#":
            break                             # начало комментария
        if ch == '"' or ch == "'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _logical_lines(source: str) -> List[str]:
    """Возвращает список логических строк-инструкций: удаляет блочные
    комментарии =begin/=end, построчные комментарии и содержимое строк,
    разбивает по ';' и отбрасывает пустые строки."""
    result: List[str] = []
    in_block_comment = False
    for raw in source.splitlines():
        stripped = raw.strip()
        if in_block_comment:
            if stripped.startswith("=end"):
                in_block_comment = False
            continue
        if stripped.startswith("=begin"):
            in_block_comment = True
            continue
        cleaned = _strip_line(raw)
        for part in cleaned.split(";"):
            part = part.strip()
            if part:
                result.append(part)
    return result


# ------------------------------------------------------------------ #
# Распознавание конструкций                                           #
# ------------------------------------------------------------------ #

def _first_word(line: str) -> str:
    word = []
    for ch in line:
        if ch.isalnum() or ch == "_":
            word.append(ch)
        else:
            break
    return "".join(word)


def _has_modifier(line: str):
    """Определяет модификатор (постфиксные if/unless/while/until).
    Возвращает ('if'|'unless'|'while'|'until') или None.
    Модификатором считается ключевое слово, стоящее НЕ в начале строки."""
    tokens = line.replace("(", " ").replace(")", " ").split()
    for kw in ("if", "unless", "while", "until"):
        # ищем kw среди токенов, но не как первый токен
        for idx in range(1, len(tokens)):
            if tokens[idx] == kw:
                return kw
    return None


def _count_ternary(line: str) -> int:
    """Грубая, но надёжная для обычного кода оценка числа тернарных
    операторов в строке: количество пар ' ? ' … ' : ' (с пробелами)."""
    q = line.count(" ? ")
    c = line.count(" : ")
    return min(q, c)


def _ends_with_do_block(line: str) -> bool:
    """Строка открывает блок do…end: заканчивается на 'do' или 'do |args|'."""
    s = line.rstrip()
    if re.search(r'(^|\s)do$', s):
        return True
    if re.search(r'(^|\s)do\s*\|[^|]*\|\s*$', s):
        return True
    return False


def _is_iterator_loop(line: str) -> bool:
    """Строка открывает цикл-итератор (…each do / …times do / … { |x| …)?"""
    ends_with_block = _ends_with_do_block(line) or _opens_brace_block(line)
    if not ends_with_block:
        return False
    for it in ITERATORS:
        if ("." + it) in line or line.startswith(it + " ") or (" " + it + " ") in line:
            return True
    return False


def _opens_brace_block(line: str) -> bool:
    """Однострочный блок-итератор вида arr.each { |x| ... } — считаем циклом,
    если есть '{' с параметром блока '|...|' и он не закрыт '}' … (упрощённо
    считаем такой '{' открытием блока-итератора на одной строке)."""
    s = line
    return "{" in s and "|" in s.split("{", 1)[1][:40]


@dataclass
class _Frame:
    kind: str          # 'if' | 'loop' | 'case' | 'struct'
    base: int          # уровень вложенности снаружи конструкции
    when_count: int = 0


def analyze(source: str) -> GilbResult:
    lines = _logical_lines(source)

    cl = 0
    simple = 0
    cli = 0
    if_count = elsif_count = unless_count = 0
    loop_count = case_count = when_count = ternary_count = 0

    cond_depth = 0            # текущий уровень вложенности (0 — верхний)
    stack: List[_Frame] = []

    def note_level(level: int):
        nonlocal cli
        if level > cli:
            cli = level

    for line in lines:
        word = _first_word(line)

        # ---- закрытие блока ----
        if word == "end":
            if stack:
                fr = stack.pop()
                cond_depth = fr.base
            continue

        # ---- ветки case ----
        if word == "when":
            # найти ближайший case-кадр
            fr = _innermost(stack, "case")
            if fr is not None:
                fr.when_count += 1
                level = fr.base + (fr.when_count - 1)   # 1-я ветка: base, 2-я: base+1 …
                cl += 1
                when_count += 1
                note_level(level)
                cond_depth = level + 1                  # тело этой ветки глубже
            continue

        # ---- ветки if/elsif/else ----
        if word == "elsif":
            fr = _innermost(stack, "if")
            base = fr.base if fr is not None else cond_depth
            cl += 1
            elsif_count += 1
            note_level(base)
            cond_depth = base + 1
            continue
        if word == "else":
            fr = stack[-1] if stack else None
            if fr is not None and fr.kind == "case":
                cond_depth = fr.base + fr.when_count     # продолжение каскада
            elif fr is not None:
                cond_depth = fr.base + 1
            continue

        # ---- открытие условных/циклических конструкций ----
        if word == "if":
            level = cond_depth
            cl += 1
            if_count += 1
            note_level(level)
            stack.append(_Frame("if", cond_depth))
            cond_depth = level + 1
            continue
        if word == "unless":
            level = cond_depth
            cl += 1
            unless_count += 1
            note_level(level)
            stack.append(_Frame("if", cond_depth))
            cond_depth = level + 1
            continue
        if word in ("while", "until", "for"):
            level = cond_depth
            cl += 1
            loop_count += 1
            note_level(level)
            stack.append(_Frame("loop", cond_depth))
            cond_depth = level + 1
            continue
        if word == "loop":                               # loop do … end
            level = cond_depth
            cl += 1
            loop_count += 1
            note_level(level)
            stack.append(_Frame("loop", cond_depth))
            cond_depth = level + 1
            continue
        # case может быть как отдельной строкой (case / case x), так и
        # выражением-присваиванием (grade = case ... when ... end).
        _tokens = line.split()
        if word == "case" or (_tokens and _tokens[-1] == "case"):
            note_level(cond_depth)                       # сам case — на текущем уровне
            case_count += 1
            stack.append(_Frame("case", cond_depth))
            # cond_depth не меняем — им управляют ветки when
            continue

        # ---- структурные блоки (не влияют на условную вложенность) ----
        if word in STRUCT_OPENERS:
            stack.append(_Frame("struct", cond_depth))
            continue
        if word in ("rescue", "ensure"):
            # часть begin/def — не условный оператор
            continue

        # ---- итератор-цикл (…each do / …times do / … { |x| …) ----
        if _is_iterator_loop(line):
            level = cond_depth
            cl += 1
            loop_count += 1
            note_level(level)
            # многострочный блок do…end создаёт кадр; однострочный { } — нет
            if line.rstrip().endswith("do"):
                stack.append(_Frame("loop", cond_depth))
                cond_depth = level + 1
            # но простую инструкцию с однострочным блоком тоже учтём в N:
            if _opens_brace_block(line) and not line.rstrip().endswith("do"):
                simple += 1
            # тернарник внутри такой строки
            t = _count_ternary(line)
            if t:
                cl += t
                ternary_count += t
                note_level(cond_depth)
            continue

        # ---- прочие блоки do (например, File.open(...) do) — структурные ----
        if _ends_with_do_block(line):
            stack.append(_Frame("struct", cond_depth))
            # это также инструкция (вызов) — учтём как простой оператор
            simple += 1
            t = _count_ternary(line)
            if t:
                cl += t
                ternary_count += t
                note_level(cond_depth)
            continue

        # ---- простая инструкция (возможно, с модификатором/тернарником) ----
        simple += 1
        mod = _has_modifier(line)
        if mod is not None:
            cl += 1
            note_level(cond_depth)
            if mod in ("if", "unless"):
                if mod == "if":
                    if_count += 1
                else:
                    unless_count += 1
            else:
                loop_count += 1
        t = _count_ternary(line)
        if t:
            cl += t
            ternary_count += t
            note_level(cond_depth)

    n = simple + cl

    res = GilbResult(
        cl=cl, n=n, cli=cli,
        if_count=if_count, elsif_count=elsif_count, unless_count=unless_count,
        loop_count=loop_count, case_count=case_count, when_count=when_count,
        ternary_count=ternary_count, simple_statements=simple,
    )
    res.breakdown = [
        BreakdownEntry("if", if_count, if_count, "ветвление"),
        BreakdownEntry("elsif", elsif_count, elsif_count, "ветка условия (else не считается)"),
        BreakdownEntry("unless", unless_count, unless_count, "ветвление"),
        BreakdownEntry("циклы (while/until/for/loop/итераторы)", loop_count, loop_count, "цикл"),
        BreakdownEntry("case", case_count, 0, "сам оператор выбора"),
        BreakdownEntry("when (ветки case)", when_count, when_count, "каждая ветка when; else не считается"),
        BreakdownEntry("тернарный ?:", ternary_count, ternary_count, ""),
        BreakdownEntry("прочие операторы-инструкции", simple, 0, "не условные; входят только в N"),
    ]
    return res


def _innermost(stack: List[_Frame], kind: str) -> Optional[_Frame]:
    for fr in reversed(stack):
        if fr.kind == kind:
            return fr
    return None


# ------------------------------------------------------------------ #
# Запуск из командной строки                                          #
# ------------------------------------------------------------------ #

def _format_report(path: str, r: GilbResult) -> str:
    lines = []
    lines.append(f"Файл: {path}")
    lines.append("=" * 60)
    lines.append("Детализация управляющих конструкций:")
    lines.append(f"  {'Конструкция':<40}{'Кол-во':>8}{'Вклад в CL':>12}")
    lines.append("  " + "-" * 58)
    for b in r.breakdown:
        lines.append(f"  {b.construct:<40}{b.count:>8}{b.contribution_to_cl:>12}   {b.note}")
    lines.append("")
    lines.append("РЕЗУЛЬТАТ (метрики Джилба):")
    lines.append(f"  Абсолютная сложность      CL  = {r.cl}")
    lines.append(f"  Общее число операторов    N   = {r.n}")
    lines.append(f"  Относительная сложность    cl  = CL / N = {r.cl} / {r.n} = {r.cl_relative:.3f}")
    lines.append(f"  Макс. уровень вложенности  CLI = {r.cli}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Использование: python3 gilb_core.py <путь к .rb файлу>")
        return 1
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        print(f"Не удалось открыть файл: {e}")
        return 1
    print(_format_report(path, analyze(source)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
