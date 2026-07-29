# ===========================================================================
# ESTAGIO 4 — Join SAC x CETIP + classificacao por ativo
#
# Junta o SAC consolidado (estagio 3) com a CETIP consolidada pela chave
#   base + carteira + ativo + evento + data
# e decide o destino de cada ATIVO (nao de cada evento):
#   vencimentos | eventos | quantidades_bloqueadas | divergencias | postergados
#
# Regra central (fechada com o cliente):
#   - existencia se verifica por EVENTO (esta no join dos dois lados?)
#   - classificacao se decide por ATIVO (um evento orfao arrasta o ativo todo)
#   - postergacao/estorno (natureza do caixa) manda o ativo p/ postergados,
#     nao p/ divergencias
# ===========================================================================

import pandas as pd

CHAVE = ["base", "carteira", "ativo", "data"]

import ast
import pandas as pd


def converter_naturezas(valor):
    if isinstance(valor, list):
        return valor

    if pd.isna(valor):
        return []

    texto = str(valor).strip()

    if not texto:
        return []

    try:
        convertido = ast.literal_eval(texto)

        if isinstance(convertido, list):
            return convertido

    except (ValueError, SyntaxError):
        pass

    return [texto]


def juntar_cetip_sac(sac_consolidado, cetip_consolidada, posicao_qtd=None):
    """
    sac_consolidado  : saida de consolidar_sac (estagio 3)
    cetip_consolidada: saida de consolidar_cetip (estagio 1/3b)
    posicao_qtd      : saida de preparar_quantidades (p/ flag de bloqueio) - opcional

    Devolve um dict de DataFrames, um por categoria:
      {vencimentos, eventos, quantidades_bloqueadas, divergencias, postergados}
    """
    sac = _preparar(sac_consolidado, "sac")
    cet = _preparar(cetip_consolidada, "cetip")

    print("COLUNAS SAC:")
    print(sac_consolidado.columns.tolist())

    print("\nCOLUNAS CETIP:")
    print(cetip_consolidada.columns.tolist())

    # --- OUTER JOIN por chave + evento ---
    comparado = pd.merge(
        sac,
        cet,
        on=CHAVE + ["evento"],
        how="outer",
        suffixes=("_sac", "_cetip"),
        indicator=True,
    )

    comparado["valor_sac"] = pd.to_numeric(
        comparado.get("valor_sac"), errors="coerce"
    ).fillna(0)
    comparado["valor_cetip"] = pd.to_numeric(
        comparado.get("valor_cetip"), errors="coerce"
    ).fillna(0)
    comparado["diff"] = comparado["valor_sac"] - comparado["valor_cetip"]

    # de qual lado veio cada evento
    comparado["tem_sac"] = comparado["_merge"].isin(["both", "left_only"])
    comparado["tem_cetip"] = comparado["_merge"].isin(["both", "right_only"])
    comparado["orfao"] = comparado["_merge"] != "both"

    # naturezas do caixa (postergacao/estorno) por linha
    if "naturezas" not in comparado.columns:
        comparado["naturezas"] = [[] for _ in range(len(comparado))]
    comparado["naturezas"] = comparado["naturezas"].apply(converter_naturezas)

    # flag de bloqueio por ativo (do Posicao)
    bloqueio = _mapa_bloqueio(posicao_qtd)

    # --- DECISAO POR ATIVO ---
    baldes = {
        k: []
        for k in [
            "vencimentos",
            "eventos",
            "quantidades_bloqueadas",
            "divergencias",
            "postergados",
        ]
    }

    for chave_ativo, grupo in comparado.groupby(CHAVE, dropna=False):
        destino = _classificar_ativo(grupo, bloqueio, chave_ativo)
        baldes[destino].append(grupo)

    return {
        k: (pd.concat(v, ignore_index=True) if v else _vazio())
        for k, v in baldes.items()
    }, comparado


def _classificar_ativo(grupo, bloqueio, chave_ativo):
    """Decide o destino do ATIVO inteiro olhando todos os seus eventos."""
    orfaos = grupo[grupo["orfao"]]

    if not orfaos.empty:
        # tem evento sem par. E postergacao/estorno?
        naturezas = set()
        for lst in orfaos["naturezas"]:
            naturezas.update(lst)
        if naturezas & {"postergacao", "estorno"}:
            return "postergados"
        # orfao sem explicacao -> divergencia (arrasta o ativo todo)
        return "divergencias"

    # todos os eventos casaram -> classifica o ativo
    # chave_ativo = (base, carteira, ativo, data); bloqueio nao usa data
    base, carteira, ativo, _data = chave_ativo
    if bloqueio.get((base, carteira, ativo), False):
        return "quantidades_bloqueadas"

    if (grupo["evento"] == "Vencimento").any():
        return "vencimentos"

    return "eventos"


def _preparar(df, lado):
    if df is None or df.empty:
        return pd.DataFrame(columns=CHAVE + ["evento", "valor", "naturezas"])
    out = df.copy()
    if "qntd" in out.columns and "quantidade" not in out.columns:
        out = out.rename(columns={"qntd": "quantidade"})
    return out


def _mapa_bloqueio(posicao_qtd):
    if posicao_qtd is None or posicao_qtd.empty:
        return {}
    m = {}
    for r in posicao_qtd.itertuples(index=False):
        chave = (
            getattr(r, "base", None),
            getattr(r, "carteira", None),
            getattr(r, "ativo", None),
            None,
        )  # data nao entra no bloqueio
        m[(r.base, r.carteira, r.ativo)] = bool(getattr(r, "tem_bloqueio", False))
    return m


def _vazio():
    return pd.DataFrame(
        columns=CHAVE
        + ["evento", "valor_sac", "valor_cetip", "diff", "orfao", "naturezas"]
    )


sac_consolidado = pd.read_csv("./SAIDA/5_sac_consolidado.csv", sep=';')
cetip_consolidada = pd.read_csv("./SAIDA/2_cetip.csv", sep=";")


baldes, comparado = juntar_cetip_sac(
    sac_consolidado,
    cetip_consolidada,
)

comparado.to_excel(
    "vamostestar.xlsx",
    index=False,
)
