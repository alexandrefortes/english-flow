# Curadoria na nuvem

Depois de clonar ou atualizar este repositório, execute `python -B preparar_nuvem.py` na raiz antes de trabalhar com o acervo. O comando restaura a wiki completa a partir do próprio Git e verifica o manifesto. Usa apenas a biblioteca padrão do Python 3.11 ou superior. Em uma máquina que já possui a edição original, preserve-a e use `--destino` com uma pasta nova se quiser conferir a cópia de distribuição.

Para executar o MCP deste checkout, defina `INGLEST_PROJECT_DIR` como o caminho absoluto da raiz. Use `wiki/index.md` para as páginas didáticas e `wiki/local/` para as fontes. As instruções de curadoria estão em `wiki/AGENTS.md`. Siga `PLANO.md` para os próximos passos. O preparo do acervo não requer downloads das fontes nem revisão de OCR.
