"""Script de perguntas RAG.

Uso interativo:
    python ask.py

Pergunta única:
    python ask.py "Qual é a pergunta?"
"""

from __future__ import annotations

import sys

from modules.rag import answer


def interactive():
    print("Modo interativo RAG. Ctrl+C para sair.")
    while True:
        try:
            q = input("Pergunta: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaindo...")
            break
        if not q:
            continue
        try:
            resp = answer(q)
            print("Resposta:\n" + resp + "\n")
        except Exception as e:  # noqa: BLE001
            print(f"Erro: {e}")


def main():
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        print(answer(q))
    else:
        interactive()


if __name__ == "__main__":  # pragma: no cover
    main()
