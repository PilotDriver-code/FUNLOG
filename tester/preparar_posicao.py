# ---------------------------------------------------------------------------
# SAC Posicao — funcao complementar
# Ja temos construir_traducao_lastro() em normalizacao.py (lastro->CETIP_SELIC).
# Falta a parte de QUANTIDADE: agrega por ativo, neta sinais, marca bloqueio.
# Isso NAO entra na soma financeira — vira atributo do ativo na classificacao.
# ---------------------------------------------------------------------------
import pandas as pd
from normalizacao import ErroDeCarga

def preparar_quantidades(caminho_posicao):
    """
    Agrega o SAC Posicao por (base, carteira, ativo) somando as quantidades.
    A soma com sinal resolve a netagem (+61/-61). Descarta o ativo se a
    quantidade total liquida for zero (posicao inexistente).
    """
    pos = pd.read_excel(caminho_posicao, dtype=str)

    ren = {"CD_SISTEMA": "base", "CLCLI_CD": "carteira", "CD_CETIP_SELIC": "ativo"}
    faltando = set(ren) - set(pos.columns)
    if faltando:
        raise ErroDeCarga(f"Posicao sem colunas: {faltando}")
    pos = pos.rename(columns=ren)

    for c in ["base", "carteira", "ativo"]:
        pos[c] = pos[c].astype(str).str.strip()
    for c in ["QT_DISPONIVEL", "QT_BLOQUEADA", "QT_TOTAL"]:
        pos[c] = pd.to_numeric(pos[c], errors="coerce").fillna(0)

    # guarda os trades (CD) por ativo para compor a origem depois
    trades = (pos.groupby(["base", "carteira", "ativo"])["CD"]
                 .apply(lambda s: list(s.dropna().astype(str)))
                 .rename("trades"))

    agg = (pos.groupby(["base", "carteira", "ativo"])
              .agg(qt_disponivel=("QT_DISPONIVEL", "sum"),
                   qt_bloqueada=("QT_BLOQUEADA", "sum"),
                   qt_total=("QT_TOTAL", "sum"))
              .join(trades)
              .reset_index())

    # netagem: descarta ativo cuja posicao total liquida deu zero
    antes = len(agg)
    agg = agg[agg["qt_total"] != 0].copy()
    netados = antes - len(agg)

    agg["tem_bloqueio"] = agg["qt_bloqueada"] != 0

    diagnostico = {
        "linhas_lidas": len(pos),
        "ativos_apos_agregar": antes,
        "ativos_netados_a_zero": netados,
        "ativos_com_bloqueio": int(agg["tem_bloqueio"].sum()),
    }
    return agg, diagnostico
