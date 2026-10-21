# Fixtures SSE

Respostas **reais** do `GET /api/ask` do Stego, gravadas com `curl -sN`
contra `stego serve` (Stego commit atual, Python 3.13), usando um Ollama
falso determinístico para que as gravações sejam reproduzíveis.

| arquivo                 | cenário                                                       |
|-------------------------|---------------------------------------------------------------|
| `ask_ok.sse`            | hits → 3 tokens → done                                        |
| `ask_indice_vazio.sse`  | índice vazio: hits `[]` → token com a recusa → done(refused)  |
| `ask_erro_no_meio.sse`  | hits → 1 token → error (Ollama caiu durante a geração)        |
| `ask_ollama_fora.sse`   | só error (Ollama fora do ar já no embedding da pergunta)      |

Se o contrato do Stego mudar, regrave estes arquivos: os testes do
cliente tocam exatamente esses bytes.
