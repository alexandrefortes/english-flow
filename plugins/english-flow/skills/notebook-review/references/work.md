# Study in ChatGPT Work

Use a Work task with a cloud computer for source searches. The wiki contains published transcripts and source references. The original collection stays on the maintainer's collection computer. Use the official Google Drive app for the learner's notebook. The chat can run in a browser or on a phone.

## Open the wiki

1. Locate `scripts/work_study.py` in the packaged notebook review skill. If the host presents skill resources separately, copy the files from its `scripts/` directory into one folder on the task computer. Keep their contents and names.
2. Use Python 3.11 or later. Supply one JSON object on standard input. Pass learner text as data. To identify the packaged runtime, run `python -B scripts/work_study.py study_environment` with `{}`. The Work edition returns `execution: work-cloud` and `notebook: google-drive`. This operation does not test Drive access. Select a task directory for the wiki cache. Use it for each query.
3. Run `python -B scripts/work_study.py search_wiki --cache CACHE`. For a verified Doist deadline request, use `{"situation":"negociar-prazo","function":"pedido","source":"Doist","curation":"conferido"}`. The first search downloads the published edition. The script checks the archive before use.
4. Run `python -B scripts/work_study.py read_wiki_item --cache CACHE` with `{"item_id":"doist-combinar-prazo"}` to open that example. Use the ID from the search for other requests. Read the context before you quote a passage. Keep the [source procedure](../SKILL.md#consult-a-source) for all searches.

The Work package supplies `work_study.py`, `edition.py`, `graph_reader.py`, `wiki_index.py`, `wiki_search.py`, `notebook_format.py`, `tool_inputs.py`, and `corpus.json` in the same `scripts/` directory. The script reads the release information from that directory.

If the cloud computer or the edition is unavailable, explain which source you could not open. You can still review material already open in the chat or read a saved note through Drive. Identify your own practice examples.

## Find the notebook

Use the Google Drive account connected to this chat. If the learner gives a folder link, get its metadata and check that it is an accessible folder. Use its ID for this notebook. The learner can keep a custom folder link in their project instructions for future chats.

The default location is `My Drive/English Flow/notebook`. Resolve one folder at a time. Start at `root`. Use Drive search with the exact name, parent, `trashed = false`, and folder MIME type. For the second search, use the ID of the first folder. Follow each next page token. If several folders match at one level, ask for the intended folder link. Keep the selected ID for the chat.

On a read request, report an empty or missing notebook. Create missing folders at the first save. Give each new folder the verified parent. Never create a replacement for an inaccessible folder supplied by the learner. Use the selected notebook folder ID for each file operation.

## Save to Drive

1. Prepare the entry with `python -B scripts/work_study.py prepare_entry --cache CACHE --output-dir STAGING`. Use a private task directory for staging. Supply `kind`, `title`, `content`, and any stable source IDs in `sources`. The script opens each source and returns a Markdown filename, local upload path, and SHA-256. A prepared file is a draft.
2. Search for the exact filename under the selected notebook folder ID. Use the filter `'<folder ID>' in parents and trashed = false and name = '<filename>'`. Follow each next page token. If a file exists, read it. Compare the kind, title, body, and source IDs. The creation time can differ. Reuse the link for a matching entry. Ask the learner to resolve conflicting files or duplicate matches before you write.
3. When the search is empty, use the Google Drive upload action. Set `file_uri` to the absolute path from the script, `file_name` to its filename, `mime_type` to `text/markdown`, and `parent_folder_id` to the selected folder ID. Keep the Markdown format.
4. Get the returned file's metadata. Check its filename and parent. Open its returned link with the Drive fetch action. Compare the downloaded bytes with the draft. When the connector returns readable text, compare the complete text. Repeat the search and check that there is one matching file. Confirm the save with the verified link. If an upload has an uncertain result, search the same folder and check the content before any retry.

If Drive is disconnected or write access is missing, explain the condition. The learner can keep studying. Offer the prepared Markdown file if they requested a save.

## Review a saved entry

List the Markdown entries under the selected folder with `trashed = false`. Read every result page needed for the request. For a known entry ID, search for its exact filename in that folder. Check the file metadata, then fetch the file. Use the title, kind, and creation time for review. Pass the IDs in `sources` to `read_wiki_item` to reopen the original references. Use the chat to present the notebook and its Drive links.
