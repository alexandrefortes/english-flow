# English Flow

Use this Codex plugin to study grammar, practice a work conversation, or review your notebook. The plugin includes the text edition of the wiki and its review decisions.

## Install the plugin

Use a Codex CLI with plugin support, Git, and Python 3.11 or later. From the root of your checkout, run these commands.

~~~sh
codex plugin marketplace add .
codex plugin add english-flow@english-flow-local
~~~

## Use the plugin

Type `@english-flow` and select **English Flow** in a local Codex chat. Ask “How can I ask for more time to finish a report?” The plugin starts in English. Ask “Explain in Portuguese” to change the language of the conversation. Examples, model answers, and speaking practice stay in English.

The first search expands the wiki into your cache and builds its search index. Allow about 2 GB of disk space. You can search, open a source, and use your notebook offline after installation.

Ask “Save this example in my notebook” to keep a reference. Use `ENGLISH_FLOW_NOTEBOOK_DIR` to set the notebook folder. The default folder is `English Flow/notebook` in your home folder.

## Credits and license

Doist published the images used in the transcripts. Members of the Zulip community wrote the public messages. Source records in the wiki link to the original publications and conversations. [Doist](https://www.todoist.com/inspiration/remote-team-communication-tools) · [Zulip community](https://chat.zulip.org/)

The original project software uses the PolyForm Noncommercial License 1.0.0. Include the license text or its URL and the required notice with each copy you distribute. The source publications keep their own terms. The plugin includes PyYAML 6.0.3 and its MIT license in `lib/pyyaml.zip`. [Project license](https://polyformproject.org/licenses/noncommercial/1.0.0) · [PyYAML](https://pypi.org/project/PyYAML/6.0.3/)

Required Notice: Original project: English Flow (https://github.com/alexandrefortes/workplace-english-practice).
