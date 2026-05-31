import json

CATALOGO = {}
ARQUIVO_ATUAL = None


def carregar_catalogo_dep(arquivo_json):
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


def formatar(texto):
    return texto.replace("_", " ").title()


def obter_no(caminho):
    no = CATALOGO
    for chave in caminho:
        if not isinstance(no, dict):
            return None

        if chave in no:
            no = no[chave]
        elif "subcategorias" in no and chave in no["subcategorias"]:
            no = no["subcategorias"][chave]
        elif "grupos" in no and chave in no["grupos"]:
            no = no["grupos"][chave]
        else:
            return None
    return no


def obter_opcoes(caminho):
    no = obter_no(caminho)
    if no is None:
        return []

    if isinstance(no, dict):
        if no is CATALOGO:
            return list(no.keys())
        if "subcategorias" in no:
            return list(no["subcategorias"].keys())
        if "grupos" in no:
            return list(no["grupos"].keys())
        if "produtos" in no:
            return no["produtos"]
        return list(no.keys())

    if isinstance(no, list):
        return no

    return []


def identificar_escolha(caminho, texto_clicado):
    opcoes = obter_opcoes(caminho)
    texto_limpo = texto_clicado.strip().lower()

    for opt in opcoes:
        if isinstance(opt, str):
            if (
                opt.strip().lower() == texto_limpo
                or formatar(opt).strip().lower() == texto_limpo
                or opt.replace("_", " ").strip().lower() == texto_limpo
            ):
                no_teste = obter_no(caminho + [opt])
                if no_teste is not None:
                    return "categoria", opt
                return "produto", opt

    return None, None


def _buscar_categoria_raiz(nome_produto):
    nome_lower = nome_produto.strip().lower()

    def buscar(no, cat_raiz):
        if isinstance(no, list):
            for p in no:
                if isinstance(p, str) and p.strip().lower() == nome_lower:
                    return cat_raiz
            return None

        if isinstance(no, dict):
            if "produtos" in no:
                for p in no["produtos"]:
                    if isinstance(p, str) and p.strip().lower() == nome_lower:
                        return cat_raiz

            for chave in ("subcategorias", "grupos"):
                if chave in no:
                    for _, sub_no in no[chave].items():
                        resultado = buscar(sub_no, cat_raiz)
                        if resultado:
                            return resultado

            for chave, valor in no.items():
                if chave not in ("subcategorias", "grupos", "produtos", "essencial"):
                    resultado = buscar(valor, cat_raiz)
                    if resultado:
                        return resultado

        return None

    for cat_raiz, conteudo in CATALOGO.items():
        resultado = buscar(conteudo, cat_raiz)
        if resultado:
            return cat_raiz

    return None


def categorias_dos_itens(itens_lista):
    categorias = []
    for item in itens_lista:
        cat = _buscar_categoria_raiz(item)
        if cat and cat not in categorias:
            categorias.append(cat)
    return categorias