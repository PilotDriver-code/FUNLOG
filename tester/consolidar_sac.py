# ===========================================================================
# ESTAGIO 3 — Consolidar o SAC ate o nivel da CETIP
#
# Junta SAC Operacao + SAC Caixa (MT) e soma por
#   base + carteira + ativo + evento + data
# Os varios trades/lastros colapsam num valor unico, prontos para bater
# com a CETIP (que ja vem no nivel de topo). A origem viaja numa lista.
#
# NAO faz join com a CETIP ainda — isso e o estagio 4.
# ===========================================================================

import pandas as pd


def consolidar_sac(op_normalizado, caixa_normalizado):
    """
    op_normalizado    : DataFrame de normalizar_sac_operacao
    caixa_normalizado : DataFrame de normalizar_sac_caixa (so MT)

    Devolve 1 linha por (base, carteira, ativo, evento, data) com:
      valor    = soma dos pedacos (trades, lastros, operacao+caixa)
      origem   = lista de todos os pedacos que formaram o valor
      naturezas= naturezas do caixa presentes (premio/ajuste/postergacao/estorno)
    """
    partes = []
    if op_normalizado is not None and not op_normalizado.empty:
        partes.append(op_normalizado)
    if caixa_normalizado is not None and not caixa_normalizado.empty:
        partes.append(caixa_normalizado)

    if not partes:
        return pd.DataFrame(
            columns=[
                "base",
                "carteira",
                "ativo",
                "evento",
                "data",
                "valor",
                "qntd",
                "origem",
                "naturezas",
            ]
        )

    sac = pd.concat(partes, ignore_index=True, sort=False)
    sac["valor"] = pd.to_numeric(sac["valor"], errors="coerce")
    sac["qntd"] = pd.to_numeric(sac["qntd"],errors="coerce")
    chave = ["base", "carteira", "ativo", "evento", "data"]

    def juntar(grupo):
        # quantidade = soma dos trades DISTINTOS deste evento.
        # cada trade conta 1x (se um trade tem varios eventos, nao multiplica);
        # trades diferentes somam (inclui netagem +61/-61 = 0, sinais opostos).
        if "trade" in grupo.columns and grupo["trade"].notna().any():
            qt = grupo.dropna(subset=["trade"]).drop_duplicates("trade")["qntd"].sum()
        else:
            qt = grupo["qntd"].sum() if "qntd" in grupo.columns else None

        return pd.Series(
            {
                "valor": grupo["valor"].sum(),
                "qntd": qt,
                "origem": list(grupo["origem"]),
                "naturezas": (
                    sorted(set(grupo["natureza"].dropna()))
                    if "natureza" in grupo.columns
                    else []
                ),
            }
        )

    consolidado = sac.groupby(chave, dropna=False).apply(juntar).reset_index()

    return consolidado
