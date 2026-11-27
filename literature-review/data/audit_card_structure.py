"""Recognize the two existing eleven-item card formats without rewriting cards.

This checks numbering only. It does not accept content, fulltext access, or evidence.
"""
import re

def inspect(text):
    headings = [int(x) for x in re.findall(r'^##\s+(\d+)\.', text, re.M)]
    inline = [int(x) for x in re.findall(r'^\s*(\d+)\.\s+\*\*', text, re.M)]
    expected = list(range(1, 12))
    return dict(heading_numbers=headings, inline_numbers=inline,
                recognized11=headings == expected or inline == expected,
                format='heading' if headings == expected else 'inline' if inline == expected else 'review')
