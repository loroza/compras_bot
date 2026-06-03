import json
from typing import Any, Dict, List, Optional, Tuple

CATALOGO: Dict[str, Any] = {}
ARQUIVO_ATUAL: Optional[str] = None


def carregar_catalogo_dep(arquivo_json: Optional[str]):
    global CATALOGO, ARQUIVO_ATUAL
    ARQUIVO_ATUAL = arquivo_json
    if not arquivo_json:
        CATALOGO = {}
        return

    try:
        with open(arquivo_json, "r", encoding="utf-8") as f:
            CATALOGO = json.load(f)
    except FileNotFoundError:
        CATALOGO = {}


def formatar(texto: str) -> str:
    return texto.replace("_", " ").title() if texto else texto


def obter_no(caminho: List[str]):
    no = CATALOGO
    for chave in caminho:
        if isinstance(no, dict):
            # chave direta
            if chave in no:
                no = no[chave]
                continue
            # subcategorias / grupos
            if "subcategorias" in no and chave in no["subcategorias"]:
                no = no["subcategorias"][chave]
                continue
            if "grupos" in no and chave in no["grupos"]:
                no = no["grupos"][chave]
                continue
            # não encontrou
            return None
        else:
            # se no não é dicionário, não há chaves subsequentes
            return None
    return no


def obter_opcoes(caminho: List[str]):
    no = obter_no(caminho)
    if no is None:
        return []

    # Se é o nó raiz (dicionário de departamentos/categorias principais)
    if isinstance(no, dict):
        # prioriza subcategorias -> grupos -> produtos -> chaves diretas
        if no is CATALOGO:
            return list(no.keys())
        if "subcategorias" in no:
            return list(no["subcategorias"].keys())
        if "grupos" in no:
            return list(no["grupos"].keys())
        if "produtos" in no:
            return list(no["produtos"])
        return list(no.keys())

    if isinstance(no, list):
        return no

    return []


def identificar_escolha(caminho: List[str], texto_clicado: str) -> Tuple[Optional[str], Optional[str]]:
    opcoes = obter_opcoes(caminho)
    texto_limpo = texto_clicado.strip().lower()

    for opt in opcoes:
        if isinstance(opt, str):
            opt_variants = {
                opt.strip().lower(),
                formatar(opt).strip().lower(),
                opt.replace("_", " ").strip().lower(),
            }
            if texto_limpo in opt_variants:
                # se ao avançar esse opt existe um nó -> é categoria, caso contrário, produto
                no_teste = obter_no(caminho + [opt])
                if no_teste is not None:
                    # se o nó contém produtos/subcategorias -> categoria
                    if isinstance(no_teste, dict) and any(k in no_teste for k in ("subcategorias", "grupos", "produtos")):
                        return "categoria", opt
                    # se for lista -> produtos
                    if isinstance(no_teste, list):
                        return "produto", opt
                    # caso ambíguo, considera categoria
                    return "categoria", opt
                else:
                    # não existe nó: considera produto final
                    return "produto", opt

    return None, None


def _buscar_categoria_raiz(nome_produto: str) -> Optional[str]:
    nome_lower = nome_produto.strip().lower()

    def buscar(no: Any, cat_raiz: Optional[str]) -> Optional[str]:
        if isinstance(no, list):
            for p in no:
                if isinstance(p, str) and p.strip().lower() == nome_lower:
                    return cat_raiz
            return None

        if isinstance(no, dict):
            # lista direta de produtos em chave 'produtos'
            if "produtos" in no:
                for p in no["produtos"]:
                    if isinstance(p, str) and p.strip().lower() == nome_lower:
                        return cat_raiz

            # busca recursiva em subcategorias e grupos
            for chave in ("subcategorias", "grupos"):
                if chave in no:
                    for sub_nome, sub_no in no[chave].items():
                        resultado = buscar(sub_no, cat_raiz)
                        if resultado:
                            return resultado

            # busca em outras chaves (caso a estrutura seja diferente)
            for chave, valor in no.items():
                if chave not in ("subcategorias", "grupos", "produtos", "essencial"):
                    resultado = buscar(valor, cat_raiz or chave)
                    if resultado:
                        return resultado

        return None

    for cat_raiz, conteudo in CATALOGO.items():
        resultado = buscar(conteudo, cat_raiz)
        if resultado:
            return resultado

    return None


def encontrar_caminho_produto(nome_produto: str) -> Optional[List[str]]:
    """
    Retorna o caminho até o produto como lista: [categoria, (subcategoria|grupo)*, produto]
    Retorna None se não encontrado.
    """
    target = nome_produto.strip().lower()

    def buscar(no: Any, caminho_atual: List[str]) -> Optional[List[str]]:
        if isinstance(no, list):
            for p in no:
                if isinstance(p, str) and p.strip().lower() == target:
                    return caminho_atual + [p]
            return None

        if isinstance(no, dict):
            # se existe chave 'produtos'
            if "produtos" in no:
                for p in no["produtos"]:
                    if isinstance(p, str) and p.strip().lower() == target:
                        return caminho_atual + [p]
            # verificar subcategorias e grupos
            for chave in ("subcategorias", "grupos"):
                if chave in no:
                    for sub_nome, sub_no in no[chave].items():
                        resultado = buscar(sub_no, caminho_atual + [sub_nome])
                        if resultado:
                            return resultado
            # checar outros ramos (estruturas diferentes)
            for chave, valor in no.items():
                if chave not in ("subcategorias", "grupos", "produtos", "essencial"):
                    resultado = buscar(valor, caminho_atual + [chave])
                    if resultado:
                        return resultado
        return None

    for cat_raiz, conteudo in CATALOGO.items():
        res = buscar(conteudo, [cat_raiz])
        if res:
            return res
    return None


def formatar_extrato(itens_lista: List[str]) -> str:
    """
    Recebe lista de nomes de itens (strings) e retorna um texto agrupado por categoria/subcategoria.
    Ordena produtos alfabeticamente.
    """
    if not itens_lista:
        return "Lista vazia."

    # estrutura: { categoria: { subcategoria: [produtos...] } }
    estrutura: Dict[str, Dict[str, List[str]]] = {}

    for raw in itens_lista:
        if not raw:
            continue
        nome = raw.strip()
        caminho = encontrar_caminho_produto(nome)
        if caminho and len(caminho) >= 2:
            categoria = formatar(caminho[0])
            # subcategoria é o segundo elemento se existir mais de 2 (categoria + sub + ... + produto)
            if len(caminho) >= 3:
                subcategoria = formatar(caminho[1])
            else:
                # diretório categoria -> produto (sem subcategoria)
                subcategoria = "Geral"
            produto = formatar(caminho[-1])
        else:
            # produto não encontrado no catálogo
            categoria = "Sem Categoria"
            subcategoria = "Geral"
            produto = formatar(nome)

        estrutura.setdefault(categoria, {}).setdefault(subcategoria, []).append(produto)

    # ordenar categorias, subcategorias e produtos
    categorias_ordenadas = sorted(estrutura.keys(), key=lambda s: s.lower())

    partes: List[str] = []
    for cat in categorias_ordenadas:
        partes.append("*" * 26)
        partes.append(cat.upper())
        partes.append("*" * 26)
        partes.append("")  # linha em branco

        subs = estrutura[cat]
        subs_ordenadas = sorted(subs.keys(), key=lambda s: s.lower())
        for sub in subs_ordenadas:
            if sub != "Geral":
                partes.append(f"{sub}:")
            # lista de produtos em ordem alfabética
            produtos = sorted(subs[sub], key=lambda s: s.lower())
            for p in produtos:
                partes.append(f" ➥{p}")
            partes.append("")  # linha em branco entre subcategorias

        partes.append("")  # espaço extra entre categorias

    return "\n".join(partes).strip()


def categorias_dos_itens(itens_lista: List[str]) -> List[str]:
    categorias = []
    for item in itens_lista:
        cat = _buscar_categoria_raiz(item)
        if cat and cat not in categorias:
            categorias.append(cat)
    return categorias