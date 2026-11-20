# English Flow

Study English with conversations from Doist and Zulip. Use English Flow in local Codex or in ChatGPT Work. Both editions use the same wiki, sources, and notebook format. A fork includes the tools that maintain the wiki and build the plugin.

## Install in local Codex

Use Git, a Codex CLI with plugin support, and Python 3.11 or later. Use the checkout or fork that contains this edition. Run both commands at its root.

~~~sh
codex plugin marketplace add .
codex plugin add english-flow@english-flow-local
~~~

To install from a GitHub tag, use the following commands. Replace `OWNER/REPOSITORY` with the fork name. Replace `TAG` with a published tag that contains English Flow.

~~~sh
codex plugin marketplace add OWNER/REPOSITORY --ref TAG
codex plugin add english-flow@english-flow-local
~~~

Type `@english-flow` and select **English Flow** in a local Codex chat. The first search restores the wiki and builds its index. Allow about 2 GB of disk space. Later searches use that index. [Plugin guide](plugins/english-flow/README.md)

## Install in ChatGPT Work

Upload the English Flow Work plugin ZIP through your workspace plugin settings. Use the Work ZIP built with the command below. The GitHub source ZIP contains the development repository. Enable the official Google Drive app in ChatGPT. Connect the Google account that holds your notebook. The account and workspace must permit file uploads to save entries. [Google Drive app setup](https://help.openai.com/en/articles/10929079-google-drive-app-and-setup-in-chatgpt)

Select `@english-flow` in a Work cloud chat from a browser or the Android app. Work runs the wiki search on its cloud computer. The first search in a new cache downloads about 205 MB from the published GitHub revision. Allow about 2 GB on the task computer. The phone needs an internet connection. The notebook uses `My Drive/English Flow/notebook` or the Drive folder you specify.

## Work on a fork

| Path | Contents |
| --- | --- |
| `.claude-plugin/` | The marketplace catalog points to the plugin directory. |
| `plugins/english-flow/` | The MCP server, notebook panel, skills, and published wiki archive. |
| `wiki/` | Study pages, source links, and review decisions. |
| `tools/collection/` | Tools to collect and read original sources. |
| `tools/curation/` | Tools to build the wiki and check review decisions. |
| `tools/packaging/` | Tools to restore the wiki and build its archives. |
| `tests/` | Tests for the code and the offline MCP server. |

## Study in a chat

English Flow starts the conversation in English. Ask for another language to change the explanations, instructions, and feedback. For example, ask “Explique em português.” Quotations, model answers, and English practice stay in English.

| Activity | Example |
| --- | --- |
| Study a rule | “How do I ask for an update?” |
| Practice a conversation | “You need my report on Monday. I need more time. Start the conversation.” |
| Review a lesson | “Review my lesson about deadlines.” |
| Practice from memory | “Give me a situation from the last lesson. Wait for my answer.” |

Ask the agent to show the source before you save an example. Ask “Save this reference in my notebook” to keep its ID. The agent saves each new lesson in English. To open saved material, ask “Open my notebook.”

In local Codex the default notebook is `English Flow/notebook` in your home folder. Local searches and notebook operations work offline. To use one notebook on your PC and in Work, sync the same Drive folder to your PC with Google Drive for desktop. Make the folder available offline. Set `ENGLISH_FLOW_NOTEBOOK_DIR` to its local path before you start Codex. Drive syncs the Markdown files when you reconnect. Existing entries in a different folder stay there until you copy them.

For voice practice, use the ChatGPT voice control. Use dictation to send a transcript in the plugin chat. A transcript supports feedback about wording. Pronunciation feedback requires audio. [ChatGPT voice guide](https://help.openai.com/en/articles/20001274-chatgpt-voice)

## Work on the wiki

Use the published transcripts for review. Run the restore command once in a new clone. It verifies the archive and restores the source pages under `wiki/local/`.

```sh
python -B -m tools.packaging.restore_wiki
```

Open the [wiki index](wiki/index.md) or choose a [work conversation](wiki/conversas/index.md). For offline study on another computer, copy the restored `wiki/` directory. [Wiki design reference](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

To search an edited checkout, set `ENGLISH_FLOW_PROJECT_DIR` to the repository root before you start Codex.

```sh
export ENGLISH_FLOW_PROJECT_DIR="$PWD"
```

In PowerShell, use `$env:ENGLISH_FLOW_PROJECT_DIR = (Get-Location).Path`. Start Codex in that session. Ask for a verified Doist example about a deadline. Open the source and save its ID if needed.

To practice for 20 minutes, read a [Doist case](wiki/conversas/doist.md) for four minutes. Take six minutes to reply in English. Use five minutes for feedback. Try another deadline for the last five minutes.

The wiki retains its original text and command examples. Use the following commands in this checkout.

| Task | Current command |
| --- | --- |
| Check review coverage | `python -B -m tools.curation.review_items` |
| List unreviewed messages | `python -B -m tools.curation.review_items --pending mensagem` |
| Record a reviewed batch | `python -B -m tools.curation.review_items --record --reviews batch.jsonl` |
| Show graph coverage | `python -B -m tools.curation.build_graph summary` |
| Search verified deadline examples | `python -B -m tools.curation.build_graph search --situation negociar-prazo --verified-only` |
| Read a node | `python -B -m tools.curation.build_graph show zulip-msg-2552913` |
| Check the local edition | `python -B -m tools.curation.build_wiki --verify` |
| Check attachment progress | `python -B -m tools.curation.process_attachments --summary` |
| Check image review progress | `python -B -m tools.curation.review_images summary` |

## Build and test an edition

Install the development dependencies. Run the unit tests. Run the MCP checks with the restored wiki.

```sh
python -m pip install -r requirements-dev.txt
python -B -X utf8 -m unittest discover -s tests
python -B -X utf8 tests/check_wiki_mcp.py
```

After you edit study pages or decisions, add the source files to Git. Build the editorial archive. Test the plugin package with its own cache and a temporary notebook.

```sh
python -B -m tools.packaging.pack_wiki
python -B -X utf8 tests/check_wiki_mcp.py --plugin plugins/english-flow
```

Build the ZIP for ChatGPT Work from your checkout. The ZIP includes the skills and wiki reader. The package records the public corpus revision and file checksums.

```sh
python -B -m tools.packaging.pack_work dist/english-flow-work.zip
```

For a fork with a different edition, first publish the matching corpus. Set `--repository OWNER/REPOSITORY --ref COMMIT` when you build the Work ZIP.

Commit the editorial archive and its checksum with the source changes. To check a committed edition, run `python -B -m tools.packaging.pack_wiki --ref HEAD --check`. To rebuild the source archive, use `python -B -m tools.packaging.pack_sources wiki/local OUTPUT_DIRECTORY`. Use an empty output directory. Verify the new parts and manifest before you replace the files in the plugin archive.

## Collect original sources

The published wiki is sufficient for study and editorial review. Source collection requires internet access. Run `python -B -m tools.collection.collect_sources --sample` to download five examples. Open `dados/fontes.md` to read the sample.

Run `python -B -m tools.collection.collect_sources` for a full collection. Run the same command to resume. Open `dados/doist/index.html` to inspect images. Run `python -B -m tools.collection.read_zulip` to open the [local Zulip reader](http://127.0.0.1:8765/). Press Ctrl+C to stop it.

For a small Zulip collection, run the following commands.

```sh
python -B -m tools.collection.download_zulip --directory dados/zulip-piloto --max-pages 2 --export-pilot
python -B -m tools.collection.read_zulip --data dados/zulip-piloto
```

If the collector returns exit code 3, read `issues` in `dados/zulip/coleta.json`. Check `found_oldest` and `page_chain_verified` for history coverage. Inspect `dados/zulip/anexos-resumo.json` for attachment access. The original files stay on the collection computer.

The [Doist catalog](plugins/english-flow/doist-catalog.json) identifies each image and its evidence. The Doist collection records its size and SHA-256. Zulip messages contain a stream ID and topic. Attachment records identify the messages that refer to each URL. See the [wiki review guide](wiki/AGENTS.md).

## Credits and license

Doist published the images used in the wiki transcripts. The source records link to the original articles. [Async by Doist](https://async.twist.com/when-to-take-real-time-meetings-async/#moving-work-forward) · [Todoist](https://www.todoist.com/inspiration/remote-team-communication-tools)

Members of the Zulip community wrote the public messages and shared the attachment references. The wiki links to the original conversations. [Zulip community](https://chat.zulip.org/) · [Wiki source catalog](wiki/fontes.md)

The original software uses the PolyForm Noncommercial License 1.0.0. You can study, change, and share it for permitted purposes. When you distribute a fork, include the license text or URL and the required notice. [License](LICENSE) · [Project credit](NOTICE)

The source material and third-party software have their own terms. PyYAML includes its MIT license in `lib/pyyaml.zip` in the plugin. [Todoist terms](https://www.todoist.com/terms-of-service) · [Zulip terms](https://zulip.com/policies/terms)
