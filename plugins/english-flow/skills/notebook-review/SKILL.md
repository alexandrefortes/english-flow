---
name: notebook-review
description: Use for notebook review, practice from memory, source search, or a request to save a note or source reference.
---

# Use the notebook

## Conversation language

Start each new conversation in English. A search request can be in Portuguese or English. Its language alone does not change the reply language.

If the learner asks for another language, use it for explanations, instructions, feedback, and notebook confirmations. Keep this preference for the conversation until the learner changes it. Use English for source quotations in English, model sentences, exercise answers, and the turns of a role-play. Use natural workplace English for study. Preserve the source wording.

## Open and review an entry

Use `read_entry` for a specific entry ID. For a list or the notebook panel, use `open_notebook`. Open the title the learner selects with `read_entry`.

For review from the first lesson, read the `lesson` entries in order. Explain one rule at a time. Use an English example from the lesson. End there if the learner asked only for an explanation.

For practice from memory, select the requested skill or use `Next practice` from the saved entry. Ask for an English sentence in a new situation. Wait for the attempt before you show the rule or model. Give a hint if needed. Explain the most useful correction. Ask the learner to try again. Suggest a review in a few days.

## Consult a source

1. Interpret the learner's request. Use `search_wiki` with the requested situation and filters. For “more time to finish” or “mais tempo para entregar”, use `situation: negociar-prazo` and `function: pedido`. Prefer verified examples. Keep each required source, material type, and review state on every attempt.
2. Open a result with `read_wiki_item`. Check the quotation, speaker, preceding message, and reply when available. If the first search meets the request, cite the result and stop. Check that a deadline example shows a request for a change.
3. If needed, try another English expression. If evidence is still missing, widen one optional filter on the third attempt. If every filter is required, keep them all and try another expression. Explain the gap after three unsuccessful searches.
4. For attachments, check `correspondencia`, the transcript, and `origens`. A filename or label can locate an item. If the words occur in the source message, open and cite `citar_id` or the message in `origens`. Quote only legible words from a partial transcript.
5. Give the literal passage, stable ID, wiki page, and available source link. Identify study pages written by the project. Label British English adaptations. To save a requested reference, pass its ID in `sources` to `save_entry`. To open it again, use `read_entry` and then `read_wiki_item`.

If the wiki is unavailable, try `search_graph` and `read_graph_node` or use `list_sources` and `read_source` for a sample. Keep the same required filters. Offer **Download sample** if the data is missing. Use `download_sources` only when requested.

## Save a review or note

For a review, use `kind: review`. Write the objective, observations, and next task in English. Use `Next practice` for the next task and its agreed date. For a note or reference, use `kind: note`. Include the source IDs in `sources`. Confirm the save after `save_entry` returns the entry ID.
