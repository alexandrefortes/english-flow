# Work on English Flow

Use Python 3.11 or later. Run the commands at the repository root. A checkout contains the code, the study pages, and the published text archive. These files support the work described below. [Project instructions](AGENTS.md) · [Wiki review procedure](wiki/AGENTS.md)

| Path | Purpose |
| --- | --- |
| `.claude-plugin/` | Marketplace entry for the local Codex plugin. |
| `plugins/english-flow/` | Local MCP server, study skills, notebook panel, and wiki archive. |
| `wiki/` | Editable study pages, source catalog, and review decisions. |
| `tools/packaging/` | Restore the published wiki and build the plugin packages. |
| `tools/curation/` | Check the graph, review examples, and build editions. |
| `tools/collection/` | Tools the maintainer uses on the collection computer. |
| `tests/` | Unit tests and offline MCP checks. |
| `downloads/` | Versioned Work ZIP for browser installation. |

## Restore the text edition

```sh
python -m pip install -r requirements-dev.txt
python -B -m tools.packaging.restore_wiki
```

The restore command checks the published files and builds `wiki/local/` and its search index. Links to `wiki/local/` open in a restored checkout. GitHub holds this content in `plugins/english-flow/corpus/`.

If the checkout already has a different edition, move its `wiki/local/` directory to a backup outside `wiki/` before you restore the new edition.

- `wiki-001.bin` through `wiki-005.bin` are parts of one compressed text archive. It contains the source pages, transcripts, attachment records, and graph. `manifest.json` records the size and hash of each part.
- `project.tar.gz` contains the editable wiki pages, evidence, and review decisions. `project.sha256` records its checksum. In a checkout, edit the files under `wiki/`. The installed local plugin restores the editorial pages from this archive.

The original collection stays on the maintainer's collection computer in `dados/`. This directory is excluded from Git. Keep original screenshots, attachments, and collection exports there. Use the published transcripts for study, review, builds, and tests. The project has paused mass image review and OCR.

## Edit and check the wiki

Open the [wiki index](wiki/index.md). Follow the [review procedure](wiki/grafo.md#decisões-por-id) when an edit changes an item's text or context. Keep its ID, evidence, and source links. Use these commands to check the result.

| Task | Command |
| --- | --- |
| Check inventory and review coverage | `python -B -m tools.curation.review_items` |
| List pending message IDs | `python -B -m tools.curation.review_items --pending mensagem --limit 50` |
| Record a reviewed batch | `python -B -m tools.curation.review_items --record --reviews batch.jsonl` |
| Search the graph | `python -B -m tools.curation.build_graph search --situation negociar-prazo --verified-only` |
| Open a graph node | `python -B -m tools.curation.build_graph show zulip-msg-2552913` |
| Verify the restored files | `python -B -m tools.curation.build_wiki --verify` |

To search an edited wiki with local Codex, set `ENGLISH_FLOW_PROJECT_DIR` to the repository root before you start Codex. Use `export ENGLISH_FLOW_PROJECT_DIR="$PWD"` in a shell or `$env:ENGLISH_FLOW_PROJECT_DIR = (Get-Location).Path` in PowerShell.

## Test the local plugin

```sh
python -B -X utf8 -m unittest discover -s tests
python -B -X utf8 tests/check_wiki_mcp.py
```

After editing a wiki page or a review decision, stage the changed files under `wiki/`. Build the editorial archive from the Git index. Test the bundled plugin with its own cache and a temporary notebook.

```sh
python -B -m tools.packaging.pack_wiki
python -B -X utf8 tests/check_wiki_mcp.py --plugin plugins/english-flow
```

Commit `project.tar.gz` and `project.sha256` with the wiki changes. To check the committed edition, run `python -B -m tools.packaging.pack_wiki --ref HEAD --check`.

## Build the Work ZIP

```sh
python -B -m tools.packaging.pack_work dist/english-flow-work-0.7.4.zip
```

The ZIP includes the study skills, the wiki reader, the Drive app reference, and the checksums for the public corpus. Work fetches the text archive from the GitHub commit recorded in the ZIP. For a fork with a different corpus, first publish that corpus in your fork. Pass `--repository OWNER/REPOSITORY --ref COMMIT` when you build.

Build the Work ZIP for the release and put it in `downloads/`. Commit the file and its README download link. Push a tag that matches the plugin version, such as `v0.7.4`. GitHub Actions tests the Work package, builds the ZIP from that tag, and attaches it to the release. To run the job again, open **Actions → Publish the Work ZIP → Run workflow**. The README link also serves the file directly from GitHub. The Codex CLI installs from the tag. [Installation instructions](README.md)
