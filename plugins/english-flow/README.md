# English Flow

Use English Flow to study grammar, practice a work conversation, or review your notebook. The local edition and the ChatGPT Work edition use the same source IDs and Markdown files.

## Install in local Codex

Use a Codex CLI with plugin support, Git, and Python 3.11 or later. From the root of your checkout, run these commands.

~~~sh
codex plugin marketplace add .
codex plugin add english-flow@english-flow-local
~~~

## Install in ChatGPT Work

Upload the English Flow Work ZIP in your workspace plugin settings. Connect the official Google Drive app in ChatGPT. To save entries, enable file uploads to your notebook folder. Select English Flow in a Work cloud chat. The task computer downloads the wiki on the first search in a new cache. A browser or Android phone can use this chat without a connected PC. [Google Drive app setup](https://help.openai.com/en/articles/10929079-google-drive-app-and-setup-in-chatgpt)

## Use the plugin

Type `@english-flow` and select **English Flow**. Ask “How can I ask for more time to finish a report?” The plugin starts in English. Ask “Explain in Portuguese” to change the language of the conversation. Examples, model answers, and speaking practice stay in English.

English Flow selects the notebook from the execution environment. In local Codex, the plugin expands the bundled wiki into its cache. Allow about 2 GB of disk space. You can search, open sources, and use your notebook offline. In a Work cloud chat, the first search downloads about 205 MB of wiki data to the cloud computer. Drive access requires an internet connection.

Ask “Save this example in my notebook” to keep a reference. Ask “Open my notebook” to review it. In Work the default is `My Drive/English Flow/notebook`. You can give the agent a folder link instead. On the PC the default is `English Flow/notebook` in your home folder. For one notebook across devices, sync your Drive notebook folder to the PC and make it available offline. Set `ENGLISH_FLOW_NOTEBOOK_DIR` to that local folder before you start Codex.

## Credits and license

Doist published the images used in the transcripts. Members of the Zulip community wrote the public messages. Source records in the wiki link to the original publications and conversations. [Doist](https://www.todoist.com/inspiration/remote-team-communication-tools) · [Zulip community](https://chat.zulip.org/)

The original project software uses the PolyForm Noncommercial License 1.0.0. Include the license text or its URL and the required notice with each copy you distribute. The source publications keep their own terms. The local plugin includes PyYAML 6.0.3 and its MIT license in `lib/pyyaml.zip`. [Project license](https://polyformproject.org/licenses/noncommercial/1.0.0) · [PyYAML](https://pypi.org/project/PyYAML/6.0.3/)

Required Notice: Original project: English Flow (https://github.com/alexandrefortes/workplace-english-practice).
