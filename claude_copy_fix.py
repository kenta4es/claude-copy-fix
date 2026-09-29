# -*- coding: utf-8 -*-
"""
Копирование из Claude с сохранением форматирования.

Фоновый процесс следит за буфером обмена. Когда ты нажимаешь Ctrl+C в приложении
Claude (или на claude.ai в браузере), он берёт HTML-версию выделенного текста и
пересобирает из неё обычный текст: пустая строка между абзацами, каждый пункт
списка на своей строке с номером или маркером, вложенные списки с отступом,
блоки кода как есть, таблицы через табуляцию.

Запуск в фоне:      pythonw claude_copy_fix.py
Диагностика буфера: python claude_copy_fix.py --dump
Разовая правка:     python claude_copy_fix.py --once
Проверка на файле:  python claude_copy_fix.py --test fragment.html
"""
import re
import sys
import time
from html.parser import HTMLParser

# ---------------- настройки ----------------
BULLET = "• "          # маркер ненумерованного списка ("- " или "– " если нужно тире)
INDENT = "   "         # отступ для вложенных списков
KEEP_HTML = True       # оставить HTML-формат в буфере (Word/Google Docs вставят с оформлением)
POLL_SEC = 0.15        # как часто проверять буфер
SOURCE_EXE = {"claude.exe"}      # процессы-источники
SOURCE_URL_PART = "claude.ai"    # или адрес страницы в CF_HTML
MARKER_FORMAT = "ClaudeCopyFix"  # метка, чтобы не обрабатывать свою же запись


# ---------------- HTML -> текст ----------------
class HtmlToText(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
             "section", "article", "header", "footer", "figure", "details",
             "summary", "dl", "dt", "dd"}
    SKIP = {"script", "style", "svg", "button", "noscript", "template", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.pending = 0          # 0 — ничего, 1 — перевод строки, 2 — пустая строка
        self.at_line_start = True
        self.line_prefix = ""
        self.lists = []           # стек: [тип, счётчик]
        self.li_stack = []        # стек: {"cont": отступ продолжения, "has_text": bool}
        self.skip = 0
        self.pre = 0
        self.cell_index = 0

    # --- вывод ---
    def brk(self, level):
        self.pending = max(self.pending, level)

    def write(self, s, raw=False):
        if not s:
            return
        line_start = self.at_line_start or self.pending > 0
        if line_start and not raw:
            s = s.lstrip(" ")
            if not s:
                return
        if self.pending:
            if self.parts:
                self.parts.append("\n" * self.pending)
            self.pending = 0
        if line_start:
            prefix = self.line_prefix
            if not prefix and self.li_stack:
                prefix = self.li_stack[-1]["cont"]
            if prefix:
                self.parts.append(prefix)
            self.line_prefix = ""
        self.parts.append(s)
        if self.li_stack:
            self.li_stack[-1]["has_text"] = True
        self.at_line_start = s.endswith("\n")

    # --- теги ---
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag == "br":
            if self.pre:
                self.write("\n", raw=True)
            else:
                self.brk(1)
        elif tag == "hr":
            self.brk(2)
        elif tag in ("ul", "ol"):
            self.brk(1 if self.li_stack else 2)
            start = 1
            if tag == "ol":
                try:
                    start = int(a.get("start") or 1)
                except ValueError:
                    start = 1
            self.lists.append([tag, start - 1])
        elif tag == "li":
            self.brk(1)
            depth = max(len(self.lists) - 1, 0)
            indent = INDENT * depth
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                marker = f"{self.lists[-1][1]}. "
            else:
                marker = BULLET
            self.line_prefix = indent + marker
            self.li_stack.append({"cont": indent + " " * len(marker), "has_text": False})
        elif tag == "pre":
            self.brk(2)
            self.pre += 1
        elif tag == "table":
            self.brk(2)
        elif tag == "tr":
            self.brk(1)
            self.cell_index = 0
        elif tag in ("td", "th"):
            if self.cell_index:
                self.write("\t", raw=True)
            self.cell_index += 1
        elif tag == "p" and self.li_stack:
            if self.li_stack[-1]["has_text"]:
                self.brk(1)
        elif tag in self.BLOCK:
            if self.li_stack:
                if self.li_stack[-1]["has_text"]:
                    self.brk(1)
            else:
                self.brk(2)

    def handle_startendtag(self, tag, attrs):
        if tag in self.SKIP:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        if tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self.brk(1 if self.li_stack else 2)
        elif tag == "li":
            if self.li_stack:
                self.li_stack.pop()
            self.line_prefix = ""
            self.brk(1)
        elif tag == "pre":
            self.pre = max(self.pre - 1, 0)
            self.brk(2)
        elif tag == "table":
            self.brk(2)
        elif tag == "p" and self.li_stack:
            pass
        elif tag in self.BLOCK:
            self.brk(1 if self.li_stack else 2)

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre:
            self.write(data, raw=True)
        else:
            self.write(re.sub(r"\s+", " ", data))

    def result(self):
        text = "".join(self.parts)
        lines = [ln.rstrip() for ln in text.split("\n")]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip("\n")


def html_to_text(fragment):
    p = HtmlToText()
    p.feed(fragment)
    p.close()
    return p.result()


def parse_cf_html(raw):
    """raw — байты формата 'HTML Format'. Возвращает (source_url, fragment_html)."""
    head = raw[:1024].decode("ascii", "replace")
    url = ""
    m = re.search(r"SourceURL:(\S+)", head)
    if m:
        url = m.group(1)
    s = re.search(r"StartFragment:(\d+)", head)
    e = re.search(r"EndFragment:(\d+)", head)
    if s and e:
        frag = raw[int(s.group(1)):int(e.group(1))]
    else:
        frag = raw
    return url, frag.decode("utf-8", "replace")


def has_structure(fragment):
    return re.search(r"<(p|li|br|h[1-6]|pre|tr|div|blockquote)\b", fragment, re.I) is not None


# ---------------- Windows clipboard ----------------
if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.OpenClipboard.restype = wt.BOOL
    user32.CloseClipboard.restype = wt.BOOL
    user32.EmptyClipboard.restype = wt.BOOL
    user32.GetClipboardData.argtypes = [wt.UINT]
    user32.GetClipboardData.restype = wt.HANDLE
    user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    user32.SetClipboardData.restype = wt.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
    user32.IsClipboardFormatAvailable.restype = wt.BOOL
    user32.RegisterClipboardFormatW.argtypes = [wt.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wt.UINT
    user32.GetClipboardSequenceNumber.restype = wt.DWORD
    user32.EnumClipboardFormats.argtypes = [wt.UINT]
    user32.EnumClipboardFormats.restype = wt.UINT
    user32.GetClipboardFormatNameW.argtypes = [wt.UINT, wt.LPWSTR, ctypes.c_int]
    user32.GetForegroundWindow.restype = wt.HWND
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wt.HGLOBAL
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    CF_HTML = user32.RegisterClipboardFormatW("HTML Format")
    CF_MARK = user32.RegisterClipboardFormatW(MARKER_FORMAT)

    def open_clip(tries=20):
        for _ in range(tries):
            if user32.OpenClipboard(None):
                return True
            time.sleep(0.03)
        return False

    def get_bytes(fmt):
        h = user32.GetClipboardData(fmt)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.string_at(p, kernel32.GlobalSize(h))
        finally:
            kernel32.GlobalUnlock(h)

    def put_bytes(fmt, data):
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(fmt, h)

    def foreground_exe():
        hwnd = user32.GetForegroundWindow()
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hp = kernel32.OpenProcess(0x1000, False, pid.value)
        if not hp:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wt.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)):
                return buf.value.rsplit("\\", 1)[-1].lower()
            return ""
        finally:
            kernel32.CloseHandle(hp)

    def read_clip():
        """(html_raw | None, text | None, has_mark)"""
        if not open_clip():
            return None, None, False
        try:
            mark = bool(user32.IsClipboardFormatAvailable(CF_MARK))
            raw = get_bytes(CF_HTML) if user32.IsClipboardFormatAvailable(CF_HTML) else None
            t = get_bytes(CF_UNICODETEXT) if user32.IsClipboardFormatAvailable(CF_UNICODETEXT) else None
            text = t.decode("utf-16-le", "replace").split("\x00", 1)[0] if t else None
            return (raw.split(b"\x00", 1)[0] if raw else None), text, mark
        finally:
            user32.CloseClipboard()

    def write_clip(text, html_raw):
        if not open_clip():
            return False
        try:
            user32.EmptyClipboard()
            put_bytes(CF_UNICODETEXT, (text.replace("\n", "\r\n") + "\x00").encode("utf-16-le"))
            if KEEP_HTML and html_raw:
                put_bytes(CF_HTML, html_raw + b"\x00")
            put_bytes(CF_MARK, b"1")
            return True
        finally:
            user32.CloseClipboard()

    def list_formats():
        names = []
        if not open_clip():
            return names
        try:
            f = user32.EnumClipboardFormats(0)
            while f:
                buf = ctypes.create_unicode_buffer(256)
                if user32.GetClipboardFormatNameW(f, buf, 256):
                    names.append(f"{f}: {buf.value}")
                else:
                    names.append(f"{f}: (стандартный)")
                f = user32.EnumClipboardFormats(f)
        finally:
            user32.CloseClipboard()
        return names


def process_once(force=False):
    raw, text, mark = read_clip()
    if mark or not raw:
        return False
    url, frag = parse_cf_html(raw)
    from_claude = SOURCE_URL_PART in url.lower() or foreground_exe() in SOURCE_EXE
    if not (from_claude or force) or not has_structure(frag):
        return False
    new_text = html_to_text(frag)
    if not new_text.strip():
        return False
    return write_clip(new_text, raw)


def run_loop():
    mutex = kernel32.CreateMutexW(None, False, "Local\\ClaudeCopyFix")
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS — уже запущен
        return
    last = user32.GetClipboardSequenceNumber()
    while True:
        time.sleep(POLL_SEC)
        seq = user32.GetClipboardSequenceNumber()
        if seq == last:
            continue
        time.sleep(0.08)                  # дать источнику дописать все форматы
        try:
            process_once()
        except Exception:
            pass
        last = user32.GetClipboardSequenceNumber()


def dump():
    print("Форматы в буфере:")
    for n in list_formats():
        print("  ", n)
    raw, text, mark = read_clip()
    print("\nАктивное окно:", foreground_exe())
    print("Наша метка:", mark)
    print("\n--- text/plain (как есть) ---")
    print(repr(text))
    if raw:
        url, frag = parse_cf_html(raw)
        print("\nSourceURL:", url)
        print("\n--- HTML-фрагмент ---")
        print(frag[:4000])
        print("\n--- после преобразования ---")
        print(html_to_text(frag))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--test"]:
        with open(args[1], encoding="utf-8") as f:
            print(html_to_text(f.read()))
    elif args[:1] == ["--dump"]:
        dump()
    elif args[:1] == ["--once"]:
        print("Готово" if process_once(force=True) else "Нечего менять")
    else:
        run_loop()
