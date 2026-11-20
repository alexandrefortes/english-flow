# English Flow

Study workplace English with real conversations from Doist and Zulip. Install English Flow in [ChatGPT Work in a browser](#install-in-chatgpt-work-in-a-browser) or [Codex on your computer](#install-in-local-codex). Both editions use the same text wiki and source IDs.

## Install in ChatGPT Work in a browser

1. Download `english-flow-work-0.7.0.zip` and keep it intact for upload. GitHub's **Source code (zip)** contains the development repository. [Download the Work ZIP](https://github.com/alexandrefortes/workplace-english-practice/raw/refs/heads/main/downloads/english-flow-work-0.7.0.zip)
2. Open **Plugins** in ChatGPT on the web. Open **New plugin**. If you manage plugins in the Admin console, select your workspace and open **Plugins → Add → Upload plugin**. The upload option requires permission in your account or workspace. [ChatGPT plugin installation](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt)
3. Drop the ZIP into the upload area or click the upload link to choose it. Select **Add plugin**. If ChatGPT shows **Install plugin**, select it. To update a plugin you uploaded before, open its details and select **Upload new version** when available.
4. To use your notebook, connect the official **Google Drive** app in ChatGPT. Choose the account that holds your notes. Saving requires permission to upload files to the notebook folder. [Google Drive setup](https://help.openai.com/en/articles/10929079-google-drive-app-and-setup-in-chatgpt)
5. Start a **Work** cloud chat on the web or Android. Type `@english-flow`, select **English Flow**, and ask “How can I ask for more time to finish a report?”

The first source search in a new cache downloads about 206 MB of published wiki text and indexes from GitHub to the Work computer. Allow about 2 GB there for the restored wiki and search index. Later searches reuse that cache while it is available. A new chat can receive a new cache. Saved notes stay in Drive.

## Install in local Codex

Use a Codex CLI with plugin support, Git, and Python 3.11 or later. To install this release from GitHub, run both commands.

```sh
codex plugin marketplace add alexandrefortes/workplace-english-practice --ref v0.7.0
codex plugin add english-flow@english-flow-local
```

To install from a clone or fork, run these commands at its root.

```sh
codex plugin marketplace add .
codex plugin add english-flow@english-flow-local
```

Start a local Codex chat. Select `@english-flow`. The local plugin includes the wiki archive. The first search restores the text and builds an index on your computer. Allow about 2 GB of disk space. Source searches and notebook operations work offline after installation.

## Study and save examples

English Flow starts in English. Ask “Explain in Portuguese” to change the explanations and feedback. Quotations, model answers, and English practice stay in English.

| What you want | What to ask |
| --- | --- |
| A source | “Show me a verified Doist example of a deadline request. Open the conversation.” |
| Practice | “You need my report on Monday. I need more time. Start the conversation.” |
| A notebook entry | “Save this example in my notebook.” |
| Review | “Open my notebook and help me practice the last lesson.” |

In Work, the notebook uses `My Drive/English Flow/notebook`. You can give the agent a different Drive folder link. In local Codex, the notebook uses `English Flow/notebook` in your home folder. For one notebook across devices, sync the Drive folder to your PC and make it available offline. Set `ENGLISH_FLOW_NOTEBOOK_DIR` to its local path before you start Codex. Drive syncs the Markdown entries when you reconnect.

## What the wiki contains

The published edition includes Zulip messages and topics, transcripts of Doist screenshots, attachment records, study pages, and review decisions. An attachment record retains its filename and its source message. It includes readable text when a transcript exists. Each source has a stable ID. [Wiki index](wiki/index.md) · [Source catalog](wiki/fontes.md)

The maintainer keeps the original screenshots, attachment files, and collection exports on the collection computer. A clone or fork contains the tools and the published text edition. Contributors can restore the wiki, edit a page, test the plugin, and build an edition using those files. [Contributor guide](CONTRIBUTING.md)

## Credits and license

Doist published the images used in the transcripts. The source records link to the original articles. [Async by Doist](https://async.twist.com/when-to-take-real-time-meetings-async/#moving-work-forward) · [Todoist](https://www.todoist.com/inspiration/remote-team-communication-tools)

Members of the Zulip community wrote the public messages and shared the attachment references. The wiki links to the original conversations. [Zulip community](https://chat.zulip.org/) · [Wiki source catalog](wiki/fontes.md)

The original software uses the PolyForm Noncommercial License 1.0.0. You can study, change, and share it for permitted purposes. Include the license text or URL and the required credit when you distribute a copy or fork. [License](LICENSE) · [Project credit](NOTICE)

The source publications retain their own terms. The local plugin includes PyYAML and its MIT license in `lib/pyyaml.zip`. [Todoist terms](https://www.todoist.com/terms-of-service) · [Zulip terms](https://zulip.com/policies/terms)
