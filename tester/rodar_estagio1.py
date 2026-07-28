# ===========================================================================
# ESTAGIO 1 — PADRONIZACAO · script de conferencia
#
# Roda as 4 normalizacoes contra os arquivos reais e cospe um CSV de
# conferencia por fonte, em ./saida_conferencia/. Bata o olho em cada um.
#
# Uso:  python rodar_estagio1.py <pasta_dos_arquivos>
#   arquivos esperados na pasta:
#     VCRA_OPERACAO.csv · Operacoes_CETIP.txt · CAIXA.csv · POSICAO.xlsx
# ===========================================================================
import sys, json
from pathlib import Path
import pandas as pd

from normalizacao import (
    carregar_mapa_eventos, construir_traducao_lastro,
    normalizar_sac_operacao, normalizar_cetip, consolidar_cetip, normalizar_sac_caixa,
)
from preparar_posicao import preparar_quantidades

PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads")
SAIDA = Path("saida_conferencia"); SAIDA.mkdir(exist_ok=True)

ARQ = {
    "operacao": PASTA / "VCRA_OPERACAO.csv",
    "cetip":    PASTA / "Operacoes_CETIP.txt",
    "caixa":    PASTA / "CAIXA.csv",
    "posicao":  PASTA / "POSICAO.xlsx",
}

def salvar(nome, df):
    # a coluna origem (dict) vira texto JSON para caber no CSV
    out = df.copy()
    for c in out.columns:
        if out[c].apply(lambda x: isinstance(x, (dict, list))).any():
            out[c] = out[c].apply(lambda x: json.dumps(x, ensure_ascii=False, default=str))
    caminho = SAIDA / f"{nome}.csv"
    out.to_csv(caminho, sep=";", index=False, encoding="utf-8-sig")
    return caminho

def bloco(titulo): print("\n" + "="*68 + f"\n{titulo}\n" + "="*68)

mapa_sac, mapa_cetip, tipos_titulo = carregar_mapa_eventos("mapa_eventos.json")

bloco("1 · TRADUCAO lastro -> CETIP_SELIC (do Posicao)")
traducao = construir_traducao_lastro(ARQ["posicao"])
print(f"  {len(traducao)} pares (base, lastro) -> CETIP_SELIC")

bloco("2 · SAC OPERACAO")
op, d = normalizar_sac_operacao(ARQ["operacao"], traducao, mapa_sac, tipos_titulo)
print("  ", d); print("  ->", salvar("1_sac_operacao", op))

bloco("3 · CETIP (normalizada)")
ce, d = normalizar_cetip(ARQ["cetip"], mapa_cetip)
print("  ", d); print("  ->", salvar("2a_cetip_normalizada", ce))

bloco("3b · CETIP (consolidada: soma eventos + fusao de vencimento)")
ce_cons = consolidar_cetip(ce)
print(f"   {len(ce)} linhas -> {len(ce_cons)} apos consolidar")
print("  ->", salvar("2b_cetip_consolidada", ce_cons))

bloco("4 · SAC CAIXA")
cx, d = normalizar_sac_caixa(ARQ["caixa"])
print("  ", d); print("  ->", salvar("3_sac_caixa", cx))

bloco("5 · SAC POSICAO (quantidades)")
po, d = preparar_quantidades(ARQ["posicao"], tipos_titulo)
print("  ", d); print("  ->", salvar("4_posicao_quantidades", po))

bloco("PRONTO")
print(f"  4 fontes normalizadas · confira os CSVs em {SAIDA}/")
