"""
Ultimate Markdown Tester

Sends a comprehensive Markdown prompt to the AI and logs the response
in detail so rendering issues can be diagnosed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.providers.deepseek import DeepSeekProvider

# The ultimate Markdown prompt – covers every common element.
MARKDOWN_PROMPT = """\
You are a markdown rendering assistant.  Reply with the **exact**
Markdown content below – do not modify, summarise, or explain it.
Just output the raw Markdown as your answer.

# The Ultimate Markdown Coding Guide

Welcome! This guide is **not just a tutorial**—it is itself a **living example** of every Markdown element you can use. Read it to learn, and study its source to see how each feature is implemented.

---

## Table of Contents
- [Text Formatting](#text-formatting)
- [Lists](#lists)
  - [Ordered & Unordered](#ordered--unordered)
  - [Task Lists](#task-lists)
  - [Nested Lists](#nested-lists)
- [Links & Images](#links--images)
- [Code](#code)
- [Blockquotes](#blockquotes)
- [Tables](#tables)
- [Advanced Features](#advanced-features)
  - [Footnotes](#footnotes)
  - [Strikethrough & Emoji](#strikethrough--emoji)
  - [HTML Tags](#html-tags)
  - [Horizontal Rules](#horizontal-rules)
- [Escaping Characters](#escaping-characters)
- [Conclusion](#conclusion)

---

## Text Formatting

### Headings
# H1 – The Biggest
## H2 – Still Big
### H3 – Medium
#### H4 – Smaller
##### H5 – Quite Small
###### H6 – The Smallest

### Paragraphs and Line Breaks
This is a paragraph. It wraps naturally.
If you want a line break, end a line with two spaces (like this line does).
Otherwise, just keep typing.

### Emphasis
- *Italic* – surround with `*` or `_`
- **Bold** – surround with `**` or `__`
- ***Bold and Italic*** – triple `*` or `___`
- ~~Strikethrough~~ – use `~~` (GFM)

---

## Lists

### Ordered & Unordered
**Unordered:**
- Apples
- Oranges
- Bananas

**Ordered:**
1. First step
2. Second step
3. Third step

### Nested Lists
- Fruit
  - Apples
    - Granny Smith
    - Fuji
  - Oranges
- Vegetables
  1. Carrots
  2. Broccoli

### Task Lists (GFM)
- [x] Write the guide
- [x] Include all Markdown types
- [ ] Publish it
- [ ] Celebrate 🎉

---

## Links & Images

### Inline Links
Visit [GitHub](https://github.com) for more.

### Reference Links
This is [a reference link][ref].
[ref]: https://example.com "Example Domain"

### Automatic Links
- <https://www.markdownguide.org>
- <fake@example.com> (email)

### Images
Inline image:
![Markdown logo](https://markdown-here.com/img/icon256.png "Markdown Here logo")

Reference image:
![The Markdown Guide][logo]
[logo]: https://markdown-here.com/img/icon256.png "Logo"

### Image as a Link
[![Markdown logo](https://markdown-here.com/img/icon256.png)](https://markdownguide.org)

---

## Code

### Inline Code
Use `console.log('Hello')` to print to the console.

### Fenced Code Blocks with Syntax Highlighting
```python
def greet(name):
    print(f"Hello, {name}!")

greet("World")
```

```javascript
const greet = (name) => {
  console.log(`Hello, ${name}!`);
};
greet("World");
```

### Indented Code Block
    // This is an indented code block (four spaces)
    #include <iostream>
    int main() {
        std::cout << "Hello!";
        return 0;
    }

---

## Blockquotes

> This is a blockquote.
> It can span multiple lines.
>> And it can be nested.
>>> Even deeper.

You can also mix with other elements:
> ### A heading inside a blockquote
> - List item
> - Another item
>
> ```js
> // code inside blockquote
> console.log("Nested!");
> ```

---

## Tables

| Syntax      | Description | Test |
| :---        |    :----:   | ---: |
| Header      | Title       | 100  |
| Paragraph   | Text        | 200  |
| **Bold**    | *Italic*    | 300  |

Alignment: left (`:---`), center (`:---:`), right (`---:`).

---

## Advanced Features

### Footnotes
Here is a footnote reference.[^1]
And another.[^2]

[^1]: This is the first footnote.
[^2]: This is the second footnote, which can be longer and contain **markdown** as well.

### Strikethrough & Emoji
- ~~This is deleted~~
- :smile: :rocket: :heart: – emoji shortcuts (GFM)
- ℹ️ You can also copy emoji directly.

### HTML Tags
You can use raw HTML for extra styling:
- <kbd>Ctrl</kbd> + <kbd>C</kbd> to copy
- H<sub>2</sub>O (subscript)
- E = mc<sup>2</sup> (superscript)
- <span style="color: red;">Red text</span> (inline style)

### Horizontal Rules
Use three or more hyphens, asterisks, or underscores:

---
***
___

---

## Escaping Characters
Use backslashes to escape Markdown syntax:
\\*not italic\\*
\\# Not a heading
\\[not a link\\]\\(not a url\\)

---

## Conclusion
You've now seen **every common Markdown element** in action. This guide itself is a complete cheat sheet—copy its source and use it as a reference.

Happy coding! 🚀

---

*Created with ❤️ using pure Markdown.*
"""


def main():
    provider = DeepSeekProvider()
    try:
        print("[Tester] Connecting to DeepSeek...")
        provider.connect()

        print("[Tester] Sending ultimate Markdown prompt...")
        provider.send_prompt(MARKDOWN_PROMPT)
        response = provider.get_response()

        thinking = response.get("thinking", "")
        answer = response.get("answer", "")

        print("\n" + "=" * 70)
        print("DIAGNOSTICS: Thinking")
        print("=" * 70)
        print(f"Length: {len(thinking)} chars")
        print("First 500 chars:")
        print(thinking[:500])
        if len(thinking) > 500:
            print(f"... (truncated, total {len(thinking)} chars)")

        print("\n" + "=" * 70)
        print("DIAGNOSTICS: Answer (raw markdown)")
        print("=" * 70)
        print(f"Length: {len(answer)} chars")
        print("Full answer:")
        print(answer)

        print("\n" + "=" * 70)
        print("ELEMENT COUNTS")
        print("=" * 70)
        elements = {
            "headings (#)": answer.count("\n#"),
            "bold (**)": answer.count("**"),
            "italic (*)": answer.count("*"),
            "code fences (```)": answer.count("```"),
            "inline code (`)": answer.count("`"),
            "blockquotes (>)": answer.count("\n>"),
            "tables (|)": answer.count("|"),
            "links ([...](...))": answer.count("]("),
            "images (![...](...))": answer.count("!["),
            "horizontal rules (---)": answer.count("\n---"),
            "strikethrough (~~)": answer.count("~~"),
            "task lists (- [ ])": answer.count("- [ ]") + answer.count("- [x]"),
        }
        for name, count in elements.items():
            print(f"  {name}: {count}")

    except Exception as e:
        print(f"[Tester] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        provider.close()


if __name__ == "__main__":
    main()
