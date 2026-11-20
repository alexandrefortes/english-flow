# English Flow

Study grammar, practice a workplace conversation, or review your notebook. Both editions use the same wiki and source IDs.

## Install in ChatGPT Work in a browser

1. Get `english-flow-work-0.7.0.zip` from the release assets or the person who supplied this edition. Keep it as a ZIP. GitHub's **Source code (zip)** is a copy of the repository. [English Flow releases](https://github.com/alexandrefortes/workplace-english-practice/releases)
2. Open **Plugins** in ChatGPT on the web. Open **New plugin**. In a managed workspace, an administrator with upload permission can select **Plugins → Add → Upload plugin** in the Admin console. [ChatGPT plugin installation](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt)
3. Drop the Work ZIP into the dialog or click the upload link to select it. Select **Add plugin**. Select **Install plugin** if prompted. For an existing manual upload, use **Upload new version** in the plugin details when available.
4. Connect the official **Google Drive** app if you want to use a notebook. Select the account that owns the folder. Saving requires permission to upload files. [Google Drive setup](https://help.openai.com/en/articles/10929079-google-drive-app-and-setup-in-chatgpt)
5. Start a **Work** cloud chat in your browser or on Android. Select `@english-flow` and ask “How can I ask for more time to finish a report?”

The first wiki search in a new cache downloads about 206 MB to the Work computer. Allow about 2 GB there for the restored wiki and index. The cache can change between chats. Your notebook stays in `My Drive/English Flow/notebook` or the Drive folder you specify.

## Install in local Codex

Use Git, a Codex CLI with plugin support, and Python 3.11 or later. Run both commands at the root of the repository checkout.

```sh
codex plugin marketplace add .
codex plugin add english-flow@english-flow-local
```

Select `@english-flow` in a local chat. The local plugin includes the text wiki. Allow about 2 GB for the restored files and index. The local wiki and notebook work offline. The default notebook is `English Flow/notebook` in your home folder.

## Use the wiki and notebook

Ask “Show me a verified example” to read a passage in context. The wiki includes messages, transcripts, attachment records, and study pages. The source ID opens the passage again. Links to the publishers identify the original articles and conversations. Original screenshots, attachment files, and collection exports stay on the maintainer's collection computer.

Ask “Save this example in my notebook” to keep a reference. Ask “Open my notebook” to review it. To use one notebook across devices, sync your Drive notebook folder to the PC and make it available offline. Set `ENGLISH_FLOW_NOTEBOOK_DIR` to that local path before you start Codex.

English Flow starts in English. Ask “Explain in Portuguese” to change the language of explanations and feedback. Examples, model answers, and speaking practice stay in English.

## Credits and license

Doist published the images used in the transcripts. Members of the Zulip community wrote the public messages. The wiki records the source for each example. [Doist](https://www.todoist.com/inspiration/remote-team-communication-tools) · [Zulip community](https://chat.zulip.org/)

The original software uses the PolyForm Noncommercial License 1.0.0. Include the license text or its URL and the required notice with each copy you distribute. The source publications retain their own terms. The local plugin includes PyYAML 6.0.3 and its MIT license in `lib/pyyaml.zip`. [Project license](https://polyformproject.org/licenses/noncommercial/1.0.0) · [PyYAML](https://pypi.org/project/PyYAML/6.0.3/)

Required Notice: Original project: English Flow (https://github.com/alexandrefortes/workplace-english-practice).
