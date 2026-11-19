# Project instructions

Use English for project documentation, command help, and instructions for contributors. Apply ASD-STE100, Issue 9, to this text. Use approved words and consistent technical terms. Give one instruction per step. Use the active voice. Use short sentences. Refer to the [ASD-STE100 specification](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf).

Do not add comments or explanatory docstrings to scripts, tests, or embedded scripts. Keep third-party license notices. Put explanations in the README. Put command help in the argument parser.

Keep the wiki in its source language. Keep source quotations, technical IDs, anchors, and saved references intact. Follow the [wiki instructions](wiki/AGENTS.md) for collection and review work.

ASD-STE100 applies to development. Use natural language in learner conversations. Start in English. Change the language of instructions, explanations, and feedback only at the learner's request. Keep the English material for study in English.

Edit the plugin in `plugins/english-flow/`. Use Python 3.11 or later. Run these commands at the repository root.

```sh
python -m pip install -r requirements-dev.txt
python -B -m tools.packaging.restore_wiki
python -B -X utf8 -m unittest discover -s tests
python -B -X utf8 tests/check_wiki_mcp.py
```

Mass image review and OCR are on hold. Use the published transcripts. See the [README](README.md) for installation, collection, and packaging.
