import ast
from io import StringIO
import subprocess
import tokenize
import unittest

from tools import ROOT


class ProjectRules(unittest.TestCase):
    def test_project_scripts_have_no_comments_or_docstrings(self):
        paths = subprocess.check_output(
            ["git", "ls-files", "-coz", "--exclude-standard", "--", "*.py"], cwd=ROOT
        ).decode().split("\0")
        for relative in filter(None, paths):
            path = ROOT / relative
            if not path.is_file():
                continue
            with self.subTest(script=relative):
                source = path.read_text(encoding="utf-8")
                tokens = tokenize.generate_tokens(StringIO(source).readline)
                self.assertFalse([t.start for t in tokens if t.type == tokenize.COMMENT])
                scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                self.assertFalse(any(ast.get_docstring(n) is not None
                                     for n in ast.walk(ast.parse(source)) if isinstance(n, scopes)))
