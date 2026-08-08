"""Debug TypeScript analysis."""
from app.services.code_analysis import CodeAnalysisService

svc = CodeAnalysisService()
content = """
import { Component, OnInit } from '@angular/core';

export class AppComponent implements OnInit {
  title = 'novaforge';

  constructor() {
    console.log('App initialized');
  }

  ngOnInit(): void {
    this.loadData();
  }

  private loadData(): Promise<void> {
    return Promise.resolve();
  }
}
"""
result = svc.analyze_file(content, "typescript")
print(f"Functions: {result['functions']}")
print(f"Has syntax tree: {result['has_syntax_tree']}")

# Also test regex directly
import re
pattern = r"(?:function\s+(\w+)\s*\(|(\w+)\s*=\s*(?:async\s+)?function\s*\(|^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*(?::|{))"
for i, line in enumerate(content.splitlines(), 1):
    m = re.search(pattern, line)
    if m:
        name = m.group(1) or m.group(2) or m.group(3) or ""
        print(f"  Regex line {i}: {name!r}")
