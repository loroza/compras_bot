import json

CATALOGO = {}

def carregar_catalogo_dep(arquivo_json):
    global CATALOGO
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
        if not isinstance(no, dict): return None
        if chave in no: no = no[chave]
        elif "subcategorias" in no and chave in no["subcategorias"]: no = no["subcategorias"][chave]
        elif "grupos" in no and chave in no["grupos"]: no = no["grupos"][chave]
        else: return None
    return no

def obter_opcoes(caminho):
    no = obter_no(caminho)
    if no is None: return []
    if isinstance(no, dict):
        if no is CATALOGO: return list(no.keys())
        if "subcategorias" in no: return list(no["subcategorias"].keys())
        if "grupos" in no: return list(no["grupos"].keys())
        if "produtos" in no: return no["produtos"]
        return list(no.keys())
    if isinstance(no, list): return no
    return []

def identificar_escolha(caminho, texto_clicado):
    opcoes = obter_opcoes(caminho)
    texto_limpo = texto_clicado.strip().lower()
    for opt in opcoes:
        if isinstance(opt, str):
            if opt.strip().lower() == texto_limpo or formatar(opt).strip().lower() == texto_limpo:
                no_teste = obter_no(caminho + [opt])
                return ("categoria", opt) if no_teste is not None else ("produto", opt)
    return None, None

def _buscar_categoria_raiz(nome_produto):
    nome_lower = nome_produto.strip().lower()
    def buscar(no, cat_raiz):
        if isinstance(no, list):
            return cat_raiz if any(str(p).lower() == nome_lower for p in no) else None
        if isinstance(no, dict):
            if any(str(p).lower() == nome_lower for p in no.get("produtos", [])): return cat_raiz
            for k in ("subcategorias", "grupos"):
                if k in no:
                    for sub_no in no[k].values():
                        res = buscar(sub_no, cat_raiz)
                        if res: return res
        return None
    for cat, cont in CATALOGO.items():
        if buscar(cont, cat): return cat
    return None

def categorias_dos_itens(itens_lista):
    cats = []
    for i in itens_lista:
        c = _buscar_categoria_raiz(i)
        if c and c not in cats: cats.append(c)
    return cats