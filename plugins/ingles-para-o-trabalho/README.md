# Inglês para o Trabalho

O plugin inclui a wiki completa da edição textual, as decisões de curadoria e as três skills para o Codex. O caderno de cada aluno fica na sua pasta pessoal.

## Instalar pelo GitHub

Use o Codex CLI com suporte a plugins, Git e Python 3.11 ou superior disponível como `python`. Execute:

```sh
codex plugin marketplace add alexandrefortes/workplace-english-practice --ref v0.5.0
codex plugin add ingles-para-o-trabalho@workplace-english-local
```

Selecione **Inglês para o Trabalho** em uma conversa local no Codex. A instalação inclui o código Python do PyYAML 6.0.3 e a licença MIT em `lib/pyyaml.zip`. [PyYAML](https://pypi.org/project/PyYAML/6.0.3/)

Experimente **“Como peço mais tempo para entregar um relatório?”**. A primeira consulta descompacta as fontes, verifica sua integridade e cria o índice SQLite no cache do usuário. Depois do download do plugin, a busca, a leitura de fontes e o caderno funcionam offline. Reserve cerca de 2 GB para a wiki e a preparação inicial.

Para guardar uma referência, peça **“Salve esse exemplo no meu caderno”**. As notas ficam em `Inglês para o Trabalho/caderno de estudos` na pasta pessoal. Use `INGLEST_NOTEBOOK_DIR` se quiser escolher outra pasta.

A edição inclui as transcrições publicadas e os vínculos de origem da Doist e do Zulip. Os originais da coleta ficam com o mantenedor.
