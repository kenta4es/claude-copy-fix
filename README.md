# claude-copy-fix

Копирование ответов Claude через Ctrl+C с сохранением абзацев, списков и отступов.

*English below.*

## Проблема

При выделении ответа в приложении Claude или на claude.ai и нажатии Ctrl+C в простом тексте пропадает структура: абзацы, пункты списков и переносы строк сливаются в сплошной текст. В Блокнот, мессенджеры и поля ввода вставляется каша.

## Как работает

При копировании браузер кладёт в буфер обмена две версии: оформленную (HTML) и простой текст. В HTML структура сохраняется, а простой текст склеен.

Скрипт работает в фоне и следит за буфером обмена Windows. Когда копирование пришло из Claude (процесс `claude.exe` или страница `claude.ai` в любом браузере), он собирает простой текст заново из HTML:

- пустая строка между абзацами;
- каждый пункт списка с новой строки, с номером (`1.`) или маркером (`•`);
- вложенные списки с отступом;
- блоки кода без изменений;
- таблицы через табуляцию, поэтому вставляются в Excel по ячейкам.

HTML-версия остаётся в буфере, так что Word и Google Docs по-прежнему вставляют текст с оформлением. Копирование из других программ скрипт не трогает.

## Требования

- Windows 10/11
- Python 3.8+ (сторонние пакеты не нужны)

## Установка

1. Скачай `claude_copy_fix.py` в любую папку.
2. Запусти в фоне без окна:
   ```
   pythonw claude_copy_fix.py
   ```
3. Автозапуск: нажми Win+R, введи `shell:startup` и создай в открывшейся папке ярлык:
   ```
   "C:\Путь\к\pythonw.exe" "C:\Путь\к\claude_copy_fix.py"
   ```

Второй экземпляр не запустится: скрипт это проверяет.

## Настройки

В начале файла:

| Параметр | По умолчанию | Что делает |
|---|---|---|
| `BULLET` | `"• "` | маркер ненумерованного списка, можно `"- "` или `"– "` |
| `INDENT` | 3 пробела | отступ вложенных списков |
| `KEEP_HTML` | `True` | оставлять HTML-версию в буфере |
| `SOURCE_EXE` | `{"claude.exe"}` | процессы, копирование из которых обрабатывается |
| `SOURCE_URL_PART` | `"claude.ai"` | адрес страницы, копирование с которой обрабатывается |

## Диагностика

```
python claude_copy_fix.py --dump        # что лежит в буфере и во что это превратится
python claude_copy_fix.py --once        # разово обработать текущий буфер (любой источник)
python claude_copy_fix.py --test x.html # преобразовать HTML-файл и вывести текст
```

## Удаление

Удали ярлык из `shell:startup` и заверши процесс `pythonw.exe`, у которого в командной строке `claude_copy_fix.py`.

---

## English

Background clipboard fixer for Windows. When you copy a Claude reply with Ctrl+C (Claude desktop app or claude.ai in any browser), the plain-text flavor loses paragraphs and list structure. This script watches the clipboard, takes the HTML flavor and rebuilds the plain text: blank lines between paragraphs, one list item per line with numbers or bullets, indented nested lists, code blocks verbatim, tables as tab-separated rows. The HTML flavor is kept, so rich-text targets are unaffected. Clipboard content from other apps is left untouched.

Requirements: Windows, Python 3.8+, no dependencies.

Run: `pythonw claude_copy_fix.py`. Autostart: put a shortcut to `pythonw.exe "path\to\claude_copy_fix.py"` into `shell:startup`.

Settings and diagnostics flags are described in the table and the section above.

## License

MIT
