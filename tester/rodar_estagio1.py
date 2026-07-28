# ===========================================================================
# ESTAGIO 1 — PADRONIZACAO · script de conferencia
# ===========================================================================

import json
from pathlib import Path

import pandas as pd

from normalizacao import (
    carregar_mapa_eventos,
    construir_traducao_lastro,
    normalizar_sac_operacao,
    normalizar_cetip,
    consolidar_cetip,          # <-- NOVO import
    normalizar_sac_caixa,
)
from preparar_posicao import preparar_quantidades

BASE = Path(__file__).resolve().parent

PASTA = Path(r"C:\Users\Michael\Downloads\tester\UPLOAD")
SAIDA = Path(r"C:\Users\Michael\Downloads\tester\SAIDA")

SAIDA.mkdir(parents=True, exist_ok=True)

ARQ = {
    "operacao": PASTA / "VCRA_OPERACAO.csv",
    "cetip": PASTA / "Operacoes_CETIP.txt",
    "caixa": PASTA / "CAIXA.csv",
    "posicao": PASTA / "POSICAO.xlsx",
}


def salvar(nome, df):
    # A coluna origem, quando for dict ou lista, vira texto JSON para caber no CSV
    out = df.copy()

    for coluna in out.columns:
        possui_objeto = (
            out[coluna].apply(lambda valor: isinstance(valor, (dict, list))).any()
        )

        if possui_objeto:
            out[coluna] = out[coluna].apply(
                lambda valor: json.dumps(
                    valor,
                    ensure_ascii=False,
                    default=str,
                )
            )

    caminho = SAIDA / f"{nome}.csv"

    out.to_csv(
        caminho,
        sep=";",
        index=False,
        encoding="utf-8-sig",
    )

    return caminho


def bloco(titulo):
    print("\n" + "=" * 68)
    print(titulo)
    print("=" * 68)


# Procura primeiro na pasta conciliacao e depois ao lado deste script
mapa_conciliacao = PASTA.parent / "conciliacao" / "mapa_eventos.json"
mapa_local = BASE / "mapa_eventos.json"

if mapa_conciliacao.exists():
    caminho_mapa = mapa_conciliacao
elif mapa_local.exists():
    caminho_mapa = mapa_local
else:
    raise FileNotFoundError(
        "O arquivo mapa_eventos.json não foi encontrado.\n"
        f"Caminhos verificados:\n"
        f"  - {mapa_conciliacao}\n"
        f"  - {mapa_local}"
    )


# <-- MUDOU: agora devolve TRES valores (o terceiro e a lista tipo_titulo_sac)
mapa_sac, mapa_cetip, tipos_titulo = carregar_mapa_eventos(caminho_mapa)


bloco("1 · TRADUCAO lastro -> CETIP_SELIC (do Posicao)")

traducao = construir_traducao_lastro(ARQ["posicao"])

print(f"  {len(traducao)} pares (base, lastro) -> CETIP_SELIC")


bloco("2 · SAC OPERACAO")

# <-- MUDOU: passa mapa_sac e tipos_titulo
op, diagnostico = normalizar_sac_operacao(
    ARQ["operacao"],
    traducao,
    mapa_sac,
    tipos_titulo,
)

print("  ", diagnostico)
print("  ->", salvar("1_sac_operacao", op))


bloco("3 · CETIP (normalizada)")

ce, diagnostico = normalizar_cetip(
    ARQ["cetip"],
    mapa_cetip,
)

print("  ", diagnostico)
print("  ->", salvar("2a_cetip_normalizada", ce))


bloco("3b · CETIP (consolidada: soma eventos iguais + fusao de vencimento)")

# <-- NOVO passo: soma 74+874 e funde vencimento (premio fica separado)
ce_cons = consolidar_cetip(ce)

print(f"   {len(ce)} linhas -> {len(ce_cons)} apos consolidar")
print("  ->", salvar("2b_cetip_consolidada", ce_cons))


bloco("4 · SAC CAIXA")

cx, diagnostico = normalizar_sac_caixa(ARQ["caixa"])

print("  ", diagnostico)
print("  ->", salvar("3_sac_caixa", cx))


bloco("5 · SAC POSICAO (quantidades)")

# <-- MUDOU: passa tipos_titulo (filtro por RFTP_CD)
po, diagnostico = preparar_quantidades(
    ARQ["posicao"],
    tipos_titulo,
)

print("  ", diagnostico)
print("  ->", salvar("4_posicao_quantidades", po))


bloco("PRONTO")

print(f"  4 fontes normalizadas · confira os CSVs em {SAIDA}")
