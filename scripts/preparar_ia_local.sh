#!/usr/bin/env bash
# Prepara a IA local (Ollama + modelo aberto) em SEGUNDO PLANO no GitHub Actions.
# Enquanto isso o agente já coleta cotações e usa as APIs gratuitas; só se todas esgotarem
# ele espera por esta IA. O resultado ("pronto" ou "falhou") vai para o arquivo de status.
set -u
MODELO="${1:-qwen2.5:7b}"
STATUS="${2:-/tmp/ia_local_status}"
echo "preparando" > "$STATUS"
falhar() { echo "✖ $1"; echo "falhou" > "$STATUS"; exit 1; }

if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh || falhar "não consegui instalar o Ollama"
fi
sudo systemctl stop ollama 2>/dev/null || true
OLLAMA_CONTEXT_LENGTH=12288 OLLAMA_KEEP_ALIVE=2h nohup ollama serve > "${RUNNER_TEMP:-/tmp}/ollama_serve.log" 2>&1 &
for _ in $(seq 1 60); do curl -sf http://localhost:11434/api/version >/dev/null && break; sleep 1; done
curl -sf http://localhost:11434/api/version >/dev/null || falhar "o servidor do Ollama não subiu"

for tentativa in 1 2 3; do
  if ollama pull "$MODELO"; then
    echo "pronto" > "$STATUS"
    echo "✔ IA local pronta: $MODELO"
    exit 0
  fi
  echo "download falhou (tentativa $tentativa), tentando de novo..."
  sleep 10
done
falhar "não consegui baixar o modelo $MODELO"
