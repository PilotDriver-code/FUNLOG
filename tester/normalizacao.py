# ===========================================================================
# CETIP Audit — Estágio 1: PADRONIZAÇÃO (uma fonte de cada vez)
#
# Este módulo NÃO concilia. Ele só transforma cada arquivo bruto numa
# "linha comum" — o formato normalizado que todas as fontes compartilham.
# Somar, netar e comparar acontece em estágios posteriores.
#
# Começamos pelo SAC Operação, que depende da tradução lastro→CETIP_SELIC
# construída a partir do SAC Posição. Por isso as duas andam juntas.
# ===========================================================================

import pandas as pd


# ---------------------------------------------------------------------------
# De-para de eventos (por ora embutido; vira arquivo externo mapa_eventos.json)
# ---------------------------------------------------------------------------
EVENTO_SAC = {
    "I": "amortizacao",
    "J": "juros",
    "M": "juros",        # correção monetária → tratada como juros (regra de negócio)
    "V": "vencimento",   # resgate / vencimento
}


class ErroDeCarga(Exception):
    """Falha que deve PARAR a execução (arquivos incoerentes), não virar saída."""


# ---------------------------------------------------------------------------
# 1. Tradução lastro → CETIP_SELIC (a partir do SAC Posição)
# ---------------------------------------------------------------------------
def construir_traducao_lastro(caminho_posicao):
    """
    Lê o SAC Posição e devolve o dicionário:
        (base, lastro)  ->  CD_CETIP_SELIC
    É a ponte que dá ao Operação (que só conhece lastro) o código que casa
    com a CETIP. 1:1 dentro da base — confirmado no dado real.
    """
    pos = pd.read_excel(caminho_posicao, dtype=str)

    faltando = {"CD_SISTEMA", "CD_LASTRO", "CD_CETIP_SELIC"} - set(pos.columns)
    if faltando:
        raise ErroDeCarga(f"Posição sem colunas: {faltando}")

    # limpa espaços em branco que costumam vir de exportação
    for c in ["CD_SISTEMA", "CD_LASTRO", "CD_CETIP_SELIC"]:
        pos[c] = pos[c].astype(str).str.strip()

    # descarta linhas sem tradução (não deveriam existir, mas protege)
    validos = pos.dropna(subset=["CD_CETIP_SELIC"])
    validos = validos[validos["CD_CETIP_SELIC"].str.lower() != "nan"]

    # garante 1:1 dentro da base — se violar, é problema de cadastro, para tudo
    dup = validos.groupby(["CD_SISTEMA", "CD_LASTRO"])["CD_CETIP_SELIC"].nunique()
    if (dup > 1).any():
        maus = dup[dup > 1]
        raise ErroDeCarga(f"Lastro com >1 CETIP_SELIC na mesma base: {list(maus.index)}")

    traducao = {
        (r.CD_SISTEMA, r.CD_LASTRO): r.CD_CETIP_SELIC
        for r in validos.drop_duplicates(["CD_SISTEMA", "CD_LASTRO"]).itertuples()
    }
    return traducao


# ---------------------------------------------------------------------------
# 2. Normalização do SAC Operação
# ---------------------------------------------------------------------------
def _num(serie):
    """
    Converte texto de valor para número.
    Nesta amostra o "." é decimal (locale da máquina de exportação), então
    NÃO tratamos "." como milhar. Mantido simples e explícito.
    """
    return pd.to_numeric(serie.astype(str).str.strip(), errors="coerce")


def normalizar_sac_operacao(caminho_operacao, traducao):
    """
    Lê o SAC Operação e devolve um DataFrame no formato comum.
    Cada linha bruta vira uma linha normalizada; nada é somado aqui.
    """
    df = pd.read_csv(caminho_operacao, sep="\t", encoding="utf-8-sig", dtype=str)
    df = df[df["IC_PUB_PRIV"] == "I"]

    obrig = {"CD_SISTEMA", "CLCLI_CD", "DT", "CD", "CD_LASTRO",
             "SG_OPERACAO", "DS_TP_TRANSACAO", "QT", "VL_PU_OPERACAO", "VL_BRUTO"}
    faltando = obrig - set(df.columns)
    if faltando:
        raise ErroDeCarga(f"Operação sem colunas: {faltando}")

    for c in ["CD_SISTEMA", "CLCLI_CD", "CD_LASTRO", "SG_OPERACAO"]:
        df[c] = df[c].astype(str).str.strip()

    linhas = []
    nao_traduzidos = []   # eventos fora do de-para → viram aviso
    lastros_ausentes = [] # lastro sem match no Posição → ERRO (arquivos de dias diferentes)

    for r in df.itertuples():
        # --- traduzir evento ---
        evento = EVENTO_SAC.get(r.SG_OPERACAO)
        if evento is None:
            nao_traduzidos.append(r.SG_OPERACAO)
            continue  # decisão: fora do de-para vai pra avisos, não entra

        # --- achar o ativo (CETIP_SELIC) via lastro ---
        ativo = traducao.get((r.CD_SISTEMA, r.CD_LASTRO))
        if ativo is None:
            lastros_ausentes.append((r.CD_SISTEMA, r.CD_LASTRO))
            ativo = None  # marca; decidimos o que fazer com a lista depois

        linhas.append({
            "base":     r.CD_SISTEMA,
            "carteira": r.CLCLI_CD,          # vira "fundo" (já é o identificador do SAC)
            "ativo":    ativo,               # CETIP_SELIC — None se lastro não casou
            "evento":   evento,
            "data":     r.DT,
            "valor":    pd.to_numeric(str(r.VL_BRUTO).strip(), errors="coerce"),
            # origem: preserva TUDO para auditoria posterior
            "origem": {
                "sistema":        "sac_operacao",
                "lastro":         r.CD_LASTRO,
                "trade":          r.CD,
                "id":             r.ID,
                "evento_cru":     r.SG_OPERACAO,          # preserva o "M" original
                "descricao":      r.DS_TP_TRANSACAO,
                "pub_priv":       r.IC_PUB_PRIV,
                "qt":             pd.to_numeric(str(r.QT).strip(), errors="coerce"),
                "pu":             pd.to_numeric(str(r.VL_PU_OPERACAO).strip(), errors="coerce"),
                "valor_original": pd.to_numeric(str(r.VL_BRUTO).strip(), errors="coerce"),
            },
        })

    resultado = pd.DataFrame(linhas)

    diagnostico = {
        "linhas_lidas":       len(df),
        "linhas_normalizadas": len(resultado),
        "eventos_nao_mapeados": sorted(set(nao_traduzidos)),
        "lastros_ausentes":    sorted(set(lastros_ausentes)),
    }
    return resultado, diagnostico


# ---------------------------------------------------------------------------
# De-para de eventos externo (substitui o EVENTO_SAC embutido lá em cima)
# ---------------------------------------------------------------------------
import json
from pathlib import Path

def carregar_mapa_eventos(caminho="mapa_eventos.json"):
    """Le o de-para editavel. Cobre os dois lados (sac e cetip)."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return dados["sac"], dados["cetip"]


# ---------------------------------------------------------------------------
# Parser de data por extenso em portugues ("5 de set. de 2025")
# ---------------------------------------------------------------------------
_MESES = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
    "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12",
}

def _data_extenso(texto):
    """'5 de set. de 2025' -> '05/09/2025'. Devolve o original se nao casar."""
    if not isinstance(texto, str):
        return texto
    partes = texto.replace(".", "").split(" de ")
    if len(partes) != 3:
        return texto
    dia, mes_txt, ano = (p.strip() for p in partes)
    mes = _MESES.get(mes_txt.lower()[:3])
    if not mes:
        return texto
    return f"{int(dia):02d}/{mes}/{ano}"


# ---------------------------------------------------------------------------
# 3. Normalizacao do CETIP
# ---------------------------------------------------------------------------
def normalizar_cetip(caminho_cetip, mapa_cetip):
    """
    Le o arquivo de operacoes da CETIP (TAB, encoding latin-1/ANSI) e devolve
    o DataFrame no formato comum. Ja e o "nivel de topo": 1 linha por
    papel+evento, sem trade nem lastro.
    """
    df = pd.read_csv(caminho_cetip, sep="\t", encoding="latin-1", dtype=str)

    # nomes com acento vindos do arquivo
    C = {
        "conta": "Conta",
        "carteira": "Carteira",
        "titulo": "Título",
        "tipo_titulo": "Tipo Título",
        "cod": "CódOperação",
        "tipo_op": "Tipo Operação",
        "qt": "Quantidade",
        "pu": "PU",
        "valor": "Valor",
        "status": "Status",
        "data_liq": "Data Liquidação",
        "data_venc": "Data Vencimento",
        "base": "Base",
    }
    faltando = {v for v in C.values()} - set(df.columns)
    if faltando:
        raise ErroDeCarga(f"CETIP sem colunas: {faltando}")

    for k in ["carteira", "titulo", "cod"]:
        df[C[k]] = df[C[k]].astype(str).str.strip()

    linhas = []
    sem_depara_carteira = []   # carteira nao resolvida -> AVISOS
    eventos_nao_mapeados = []  # codigo fora do de-para -> AVISOS

    def n(v):  # texto de valor -> numero
        return pd.to_numeric(str(v).strip(), errors="coerce")

    for _, row in df.iterrows():
        carteira = str(row[C["carteira"]]).strip()
        cod      = str(row[C["cod"]]).strip()

        # PORTAO 1 — carteira sem de-para sai antes de tudo
        if not carteira or carteira.lower() in ("nan", "----", "conta-sem-depara"):
            sem_depara_carteira.append(row[C["conta"]])
            continue

        # PORTAO 2 — evento nao mapeado vira aviso
        evento = mapa_cetip.get(cod)
        if evento is None:
            eventos_nao_mapeados.append((cod, row[C["tipo_op"]]))
            continue

        linhas.append({
            "base":     str(row[C["base"]]).strip(),                 # base vem da carteira no dado real (merge)
            "carteira": carteira,
            "ativo":    str(row[C["titulo"]]).strip(),   # == CD_CETIP_SELIC do SAC
            "evento":   evento,
            "data":     row[C["data_liq"]],
            "valor":    n(row[C["valor"]]),
            "origem": {
                "sistema":     "cetip",
                "conta":       row[C["conta"]],
                "tipo_titulo": row[C["tipo_titulo"]],
                "cod":         cod,
                "descricao":   row[C["tipo_op"]],
                "status":      row[C["status"]],
                "qt":          n(row[C["qt"]]),
                "pu":          n(row[C["pu"]]),
                "data_venc":   row[C["data_venc"]],
            },
        })

    resultado = pd.DataFrame(linhas)
    diagnostico = {
        "linhas_lidas": len(df),
        "linhas_normalizadas": len(resultado),
        "sem_depara_carteira": sorted(set(sem_depara_carteira)),
        "eventos_nao_mapeados": sorted(set(eventos_nao_mapeados)),
    }
    return resultado, diagnostico


# ---------------------------------------------------------------------------
# 4. Normalizacao do SAC Caixa
# ---------------------------------------------------------------------------
import re
import unicodedata

def _sem_acento(txt):
    """Remove acentos p/ comparar comentario sem depender de encoding."""
    if not isinstance(txt, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", txt)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _parse_ds_caixa(ds):
    """
    Padrao fixo:  ACAO [tipo] - ATIVO
    Devolve (acao, ativo). O [tipo] entre colchetes e descartado (paradigma interno).
    Ex: 'POSTERGACAO DE PAGAMENTO DE JUROS [CRI-I] - 23K3123M83'
        -> acao='POSTERGACAO DE PAGAMENTO DE JUROS', ativo='23K3123M83'
    """
    if not isinstance(ds, str):
        return None, None
    # ativo = tudo depois do ultimo " - "
    if " - " in ds:
        antes, ativo = ds.rsplit(" - ", 1)
        ativo = ativo.strip()
    else:
        antes, ativo = ds, None
    # acao = texto antes do "[" (remove o [tipo])
    acao = antes.split("[")[0].strip()
    return acao, ativo


# tipo de evento a partir da acao do comentario
def _evento_do_comentario(acao):
    a = _sem_acento(acao).upper()
    if "PREMIO" in a:      return "premio"
    if "JUROS" in a:       return "juros"
    if "AMORTIZACAO" in a: return "amortizacao"
    if "CORRECAO" in a:    return "juros"     # correcao monetaria -> juros
    if "RENDIMENTO" in a:  return "juros"
    if "VENCIMENTO" in a:  return "vencimento"
    if "RESGATE" in a:     return "vencimento"
    return None  # nao reconhecido -> avisos


# natureza do lancamento (o que decide a tela de destino)
def _natureza_caixa(mttp, acao):
    a = _sem_acento(acao).upper()
    if mttp == "960":
        return "premio"
    if mttp == "803":
        if a.startswith("POSTERGACAO"): return "postergacao"
        if a.startswith("ESTORNO"):     return "estorno"      # familia postergacao
        if a.startswith("AJUSTE"):      return "ajuste"
    return None


def normalizar_sac_caixa(caminho_caixa):
    """
    Le o SAC Caixa e devolve o DataFrame no formato comum.
    So ORIGEM=MT com MTTP_CD em {960,803} entra. O resto e descartado.
    """
    df = pd.read_csv(caminho_caixa, sep=";", encoding="utf-8-sig", dtype=str)

    obrig = {"CD_SISTEMA", "CLCLI_CD", "DT", "VL", "DS", "MTTP_CD", "ORIGEM"}
    faltando = obrig - set(df.columns)
    if faltando:
        raise ErroDeCarga(f"Caixa sem colunas: {faltando}")

    for c in ["CD_SISTEMA", "CLCLI_CD", "MTTP_CD", "ORIGEM"]:
        df[c] = df[c].astype(str).str.strip()

    CODIGOS_MT = {"960", "803"}

    linhas = []
    ativos_nao_extraidos = []   # DS sem ativo apos " - " -> aviso
    eventos_nao_reconhecidos = []
    descartados = {"origem_nao_mt": 0, "codigo_ignorado": 0}

    for _, row in df.iterrows():
        # PORTAO 1 — so MT
        if row["ORIGEM"] != "MT":
            descartados["origem_nao_mt"] += 1
            continue
        # PORTAO 2 — so 960 e 803
        if row["MTTP_CD"] not in CODIGOS_MT:
            descartados["codigo_ignorado"] += 1
            continue

        acao, ativo = _parse_ds_caixa(row["DS"])
        natureza = _natureza_caixa(row["MTTP_CD"], acao or "")
        evento = _evento_do_comentario(acao or "")

        if not ativo:
            ativos_nao_extraidos.append(row["DS"])
            continue
        if evento is None:
            eventos_nao_reconhecidos.append(acao)
            continue

        linhas.append({
            "base":     row["CD_SISTEMA"],
            "carteira": row["CLCLI_CD"],
            "ativo":    ativo,                       # CD_CETIP_SELIC (casa direto)
            "evento":   evento,
            "data":     row["DT"],
            "valor":    pd.to_numeric(str(row["VL"]).strip(), errors="coerce"),
            "natureza": natureza,                    # premio/postergacao/estorno/ajuste
            "origem": {
                "sistema":   "sac_caixa",
                "mttp_cd":   row["MTTP_CD"],
                "acao":      acao,
                "comentario": row["DS"],
                "natureza":  natureza,
                "id":        row.get("ID"),
                "valor_original": pd.to_numeric(str(row["VL"]).strip(), errors="coerce"),
            },
        })

    resultado = pd.DataFrame(linhas)
    diagnostico = {
        "linhas_lidas": len(df),
        "linhas_normalizadas": len(resultado),
        "descartados": descartados,
        "ativos_nao_extraidos": ativos_nao_extraidos,
        "eventos_nao_reconhecidos": sorted(set(x for x in eventos_nao_reconhecidos if x)),
    }
    return resultado, diagnostico
