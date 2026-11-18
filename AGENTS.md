# Curadoria na nuvem

Em um clone novo, execute `python -B preparar_nuvem.py` na raiz. O comando usa Python 3.11 ou superior para restaurar a wiki em `wiki/local/` e verificar o manifesto. Na máquina da coleta, trabalhe na edição que já está nessa pasta.

Para executar o MCP deste checkout, defina `INGLEST_PROJECT_DIR` como o caminho absoluto da raiz. Use `wiki/index.md` para as páginas didáticas e `wiki/local/` para as fontes. As instruções de curadoria estão em `wiki/AGENTS.md`. Siga `PLANO.md` para os próximos passos. O preparo do acervo não requer downloads das fontes nem revisão de OCR.

## Código do plugin

Escreva o código em `plugins/ingles-para-o-trabalho/` sem comentários ou docstrings explicativas. Registre explicações de implementação na documentação do projeto.
