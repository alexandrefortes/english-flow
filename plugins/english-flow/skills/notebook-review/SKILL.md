---
name: notebook-review
description: Use for notebook review, practice from memory, source search, or a request to save a note or source reference.
---

# Use the notebook

## Select the study environment

Select the environment at the start of each conversation. Use the host's execution context and the English Flow tools available in this chat.

1. In a cloud Work chat, use the [Work procedure](references/work.md). Use Google Drive for the notebook. This applies even when the cloud task can reach a desktop computer.
2. In a local chat, call the English Flow tool `study_environment`. A response with `execution: local` and `notebook: filesystem` selects the local MCP. Use its wiki and notebook tools. Local study works offline. If the tool is missing in an explicitly local chat, tell the learner that this chat needs the local edition.
3. If the host omits the context, look for the English Flow MCP in the available tools. Call its probe when present. If only the Work package is present, use the Work procedure.
4. If an advertised local MCP fails, report the local error. Keep the selected notebook when a tool or connection fails. A Drive connection, the device name, and the operating system cannot identify the execution context.

Apply this selection to lessons, practice, source lookups, saves, and reviews. Check again if the chat moves to a different execution context.

## Conversation language

Start each new conversation in English. A search request can be in Portuguese or English. Its language alone does not change the reply language.

If the learner asks for another language, use it for explanations, instructions, feedback, and notebook confirmations. Keep this preference for the conversation until the learner changes it. Use English for source quotations in English, model sentences, exercise answers, and the turns of a role-play. Use natural workplace English for study. Preserve the source wording.

## Open and review an entry

In local mode, use `read_entry` for a specific entry ID. Use `open_notebook` for the list or panel. In cloud mode, list or read the Markdown files in the selected Drive folder. Follow the [Work procedure](references/work.md).

For review from the first lesson, read the `lesson` entries in order. Explain one rule at a time. Use an English example from the lesson. End there if the learner asked only for an explanation.

For practice from memory, select the requested skill or use `Next practice` from the saved entry. Ask for an English sentence in a new situation. Wait for the attempt before you show the rule or model. Give a hint if needed. Explain the most useful correction. Ask the learner to try again. Suggest a review in a few days.

## Consult a source

Use the local MCP for these operations in a local chat. Use the packaged Work script for the same operations in a cloud chat.

1. Interpret the learner's request. Use `search_wiki` with the requested situation and filters. For “more time to finish” or “mais tempo para entregar”, use `situation: negociar-prazo` and `function: pedido`. Prefer verified examples. Keep each required source, material type, and review state on every attempt.
2. Open a result with `read_wiki_item`. Check the quotation, speaker, preceding message, and reply when available. If the first search meets the request, cite the result and stop. Check that a deadline example shows a request for a change.
3. If needed, try another English expression. If evidence is still missing, widen one optional filter on the third attempt. If every filter is required, keep them all and try another expression. Explain the gap after three unsuccessful searches.
4. For attachments, check `correspondencia`, the transcript, and `origens`. A filename or label can locate an item. If the words occur in the source message, open and cite `citar_id` or the message in `origens`. Quote only legible words from a partial transcript.
5. Give the literal passage, stable ID, wiki page, and available source link. Identify study pages written by the project. Label British English adaptations. Include the stable ID in `sources` when saving. To reopen a reference, read the notebook entry and pass the source ID to `read_wiki_item`.

In local mode, you can also use `search_graph` and `read_graph_node`. Keep the required filters. Use the published transcripts for study in both modes. Keep source collection on the maintainer's collection computer. When a transcript is missing, check the linked message or report the gap.

## Save a review or note

For a review, use `kind: review`. Write the objective, observations, and next task in English. Use `Next practice` for the next task and its agreed date. For a note or reference, use `kind: note`. Include the source IDs in `sources`.

In local mode, call `save_entry` and confirm the returned entry ID. In cloud mode, follow [Save to Drive](references/work.md#save-to-drive). Confirm the save only after Drive returns and verifies the file.
