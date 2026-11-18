# Workplace English Practice

Use o plugin **Inglês para o Trabalho** para estudar gramática, simular conversas e revisar o que você salvou no caderno. Os exemplos vêm de conversas escritas da Doist e do Zulip.

## Instalar o plugin no Codex

Use Python 3.11 ou superior. Execute os comandos na raiz do repositório.

1. Instale a dependência do plugin no Python que o Codex usa.

   ```sh
   python -m pip install -r plugins/ingles-para-o-trabalho/requirements.txt
   ```

2. Registre o catálogo local de plugins no Codex.

   ```sh
   codex plugin marketplace add .
   ```

3. Instale o plugin.

   ```sh
   codex plugin add ingles-para-o-trabalho@workplace-english-local
   ```

## Abrir o caderno

1. Abra uma conversa local no Codex.
2. Selecione **Inglês para o Trabalho**.
3. Peça “Abra meu caderno de estudos”. O painel mostra as aulas, as práticas e as revisões salvas.
4. Se quiser começar com cinco exemplos, selecione **Baixar amostra**. O download precisa de internet.

Por padrão, o caderno fica em `Inglês para o Trabalho/caderno de estudos` na sua pasta pessoal. Se já tem um caderno em outra pasta, defina `INGLEST_NOTEBOOK_DIR` com o caminho completo dessa pasta antes de iniciar o Codex.

## Escolher uma atividade

| O que você quer fazer | Botão do painel | Exemplo de pedido |
| --- | --- | --- |
| Estudar uma regra de gramática | **Gramática** | “Explique em português como pedir uma atualização em inglês. Vá devagar.” |
| Simular uma conversa | **Prática de inglês** | “Você precisa do relatório na segunda. Eu preciso de mais tempo. Comece a conversa em inglês.” |
| Reler uma aula | **Rever explicações** | “Repita a aula sobre prazos em português.” |
| Testar o que lembra | **Praticar sem consulta** | “Dê uma situação da última aula. Espere minha resposta antes de mostrar o exemplo.” |

O plugin salva cada aula nova em inglês, em um arquivo Markdown com cabeçalho YAML. Para salvar uma prática ou revisão, peça “Salve no caderno”. Para reler o registro, selecione o título no painel.

**Para conversar por voz**, use o controle de voz do ChatGPT. Se o caderno estiver indisponível na conversa por voz, leve o trecho que quer salvar ao chat do plugin no Codex. [Voz no ChatGPT](https://help.openai.com/en/articles/20001274-chatgpt-voice)

**Para ditar uma mensagem**, use o microfone de ditado. Confira a transcrição antes de enviar. O agente recebe o texto para correção.

## Usar a wiki completa

1. Se `wiki/local/` ainda não existir, restaure a wiki a partir da raiz do repositório. O comando verifica os arquivos e grava as transcrições nessa pasta.

   ```sh
   python -B preparar_nuvem.py
   ```

2. Abra o [índice da wiki](wiki/index.md).
3. Escolha um [caso de trabalho](wiki/conversas/index.md). Cada caso mostra o contexto e o que ficou decidido ou em aberto.

Para estudar offline em outro computador, copie a pasta `wiki/` inteira após a restauração. A wiki segue a ideia de manter o material de estudo em páginas ligadas às fontes. [LLM Wiki, de Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

### Buscar exemplos da wiki pelo plugin

1. Na raiz do repositório, defina `INGLEST_PROJECT_DIR` com o comando do seu ambiente.

   **Windows · PowerShell**

   ```powershell
   [Environment]::SetEnvironmentVariable('INGLEST_PROJECT_DIR', (Get-Location).Path, 'User')
   ```

   **Linux · terminal da sessão**

   ```sh
   export INGLEST_PROJECT_DIR="$PWD"
   ```

2. No Windows, reinicie o Codex. No Linux, inicie o plugin no ambiente que recebeu a variável.
3. Peça “Busque exemplos conferidos da Doist sobre negociar um prazo”. Você também pode fazer o pedido em inglês.
4. Peça “Mostre a conversa de origem” para ler o trecho em contexto.

O plugin busca mensagens do Zulip e transcrições da Doist no grafo da wiki. Para ler a transcrição de um anexo, abra o índice de anexos pelo [guia da wiki](wiki/grafo.md#anexos-do-zulip). Ao definir `INGLEST_PROJECT_DIR`, o caderno padrão passa a ser a pasta `caderno de estudos` desse repositório.

## Praticar por 20 minutos

| Tempo | Ação |
| --- | --- |
| 4 min | Identifique o pedido em uma [conversa da Doist](wiki/conversas/doist.md). |
| 6 min | Responda em inglês como se o pedido fosse para você. |
| 5 min | Peça feedback sobre a frase que comunica o prazo. |
| 5 min | Tente outra vez com uma data diferente, sem consultar o modelo. |

## Baixar e abrir a coleta

Use esta seção se quiser consultar os arquivos públicos fora da wiki. A coleta requer internet.

| O que você quer fazer | Ação na raiz do repositório |
| --- | --- |
| Baixar a amostra pelo terminal | Execute `python baixar_conversas.py --amostra`. |
| Ler a amostra | Abra `dados/fontes.md`. |
| Baixar ou retomar a coleta completa | Execute `python baixar_conversas.py`. |
| Ver as capturas da Doist | Abra `dados/doist/index.html`. |
| Iniciar o leitor local do Zulip | Execute `python ler_zulip.py`. |
| Ler as mensagens no navegador | Abra o [leitor local](http://127.0.0.1:8765/). |
| Encerrar o leitor local | Pressione `Ctrl+C` no terminal. |
| Criar uma coleta pequena do Zulip | Execute `python baixar_zulip.py --diretorio dados/zulip-piloto --max-paginas 2 --exportar-piloto`. |
| Abrir essa coleta no leitor local | Execute `python ler_zulip.py --dados dados/zulip-piloto`. |

Se a coleta terminar com o código `3`, consulte `issues` em `dados/zulip/coleta.json`. O arquivo `mensagens.jsonl` foi exportado com ressalvas de cobertura. Para verificar o acesso aos anexos, consulte `dados/zulip/anexos-resumo.json`. Antes de redistribuir material da coleta, consulte os termos da fonte. [Termos do Todoist](https://www.todoist.com/terms-of-service) · [Termos do Zulip](https://zulip.com/policies/terms)

### Conferir os dados da coleta

| O que você quer conferir | Onde consultar |
| --- | --- |
| Por que uma captura da Doist entrou no acervo | Campos `estado` e `evidencia` em [fontes/doist.json](fontes/doist.json). |
| Se o arquivo da captura foi baixado inteiro | Tamanho em bytes e SHA-256 em `dados/doist/coleta.json`. |
| Quais mensagens do Zulip pertencem à mesma conversa | Campos `stream_id` e `topic` em `dados/zulip/mensagens.jsonl`. Cada linha é uma mensagem. |
| Qual mensagem contém a referência a um anexo | Lista `mensagens` da URL em `dados/zulip/anexos.jsonl`. |
| Se a coleta alcançou o início do histórico público | Campos `found_oldest`, `page_chain_verified` e `issues` em `dados/zulip/coleta.json`. |

## Conferir mudanças no projeto

1. Instale as dependências de teste.

   ```sh
   python -m pip install -r requirements-dev.txt
   ```

2. Execute os testes sem rede.

   ```sh
   python -B -m unittest discover -s testes -v
   ```

Para continuar a curadoria na nuvem, siga o [plano de trabalho](PLANO.md). Para incorporar uma fonte à wiki, siga as [instruções de curadoria](wiki/AGENTS.md).
