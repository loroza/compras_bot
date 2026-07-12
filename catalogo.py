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
        # Busca na raiz conforme confirmado anteriormente
        with open(arquivo_json, "r", encoding="utf-8") as f:
            CATALOGO = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        CATALOGO = {}

def formatar(texto: str) -> str:
    if not texto: return ""
    return texto.replace("_", " ").title()

def obter_no(caminho: List[str]):
    no = CATALOGO
    for chave in caminho:
        if isinstance(no, dict):
            if chave in no:
                no = no[chave]
                continue
            if "subcategorias" in no and chave in no["subcategorias"]:
                no = no["subcategorias"][chave]
                continue
            if "grupos" in no and chave in no["grupos"]:
                no = no["grupos"][chave]
                continue
            return None
        else:
            return None
    return no

def obter_opcoes(caminho: List[str]):
    no = obter_no(caminho)
    if no is None:
        return []

    if isinstance(no, dict):
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
                no_teste = obter_no(caminho + [opt])
                if no_teste is not None:
                    # Correção da indentação dos retornos que estavam quebrados
                    if isinstance(no_teste, dict) and any(k in no_teste for k in ("subcategorias", "grupos", "produtos")):
                        return "categoria", opt
                    if isinstance(no_teste, list):
                        return "produto", opt
                    return "categoria", opt
                else:
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
            if "produtos" in no:
                for p in no["produtos"]:
                    if isinstance(p, str) and p.strip().lower() == nome_lower:
                        return cat_raiz

            for chave in ("subcategorias", "grupos"):
                if chave in no and isinstance(no[chave], dict):
                    for sub_nome, sub_no in no[chave].items():
                        resultado = buscar(sub_no, cat_raiz)
                        if resultado: return resultado

            for chave, valor in no.items():
                if chave not in ("subcategorias", "grupos", "produtos", "essencial", "emoji"):
                    resultado = buscar(valor, cat_raiz or chave)
                    if resultado: return resultado
        return None

    for cat_raiz, conteudo in CATALOGO.items():
        resultado = buscar(conteudo, cat_raiz)
        if resultado: return resultado
    return None

def encontrar_caminho_produto(nome_produto: str) -> Optional[List[str]]:
    target = nome_produto.strip().lower()

    def buscar(no: Any, caminho_atual: List[str]) -> Optional[List[str]]:
        if isinstance(no, list):
            for p in no:
                if isinstance(p, str) and p.strip().lower() == target:
                    return caminho_atual + [p]
            return None

        if isinstance(no, dict):
            if "produtos" in no:
                for p in no["produtos"]:
                    if isinstance(p, str) and p.strip().lower() == target:
                        return caminho_atual + [p]
            
            for chave in ("subcategorias", "grupos"):
                if chave in no and isinstance(no[chave], dict):
                    for sub_nome, sub_no in no[chave].items():
                        resultado = buscar(sub_no, caminho_atual + [sub_nome])
                        if resultado: return resultado
            
            for chave, valor in no.items():
                if chave not in ("subcategorias", "grupos", "produtos", "essencial", "emoji"):
                    resultado = buscar(valor, caminho_atual + [chave])
                    if resultado: return resultado
        return None

    for cat_raiz, conteudo in CATALOGO.items():
        res = buscar(conteudo, [cat_raiz])
        if res: return res
    return None

def formatar_extrato(itens_lista: List[str]) -> str:
    if not itens_lista:
        return "Lista vazia."

    estrutura: Dict[str, Dict[str, List[str]]] = {}

    for raw in itens_lista:
        if not raw: continue
        nome = raw.strip()
        caminho = encontrar_caminho_produto(nome)
        
        if caminho and len(caminho) >= 2:
            categoria = formatar(caminho[0])
            subcategoria = formatar(caminho[1]) if len(caminho) >= 3 else "Geral"
            produto = formatar(caminho[-1])
        else:
            categoria = "Sem Categoria"
            subcategoria = "Geral"
            produto = formatar(nome)

        estrutura.setdefault(categoria, {}).setdefault(subcategoria, []).append(produto)

    linhas: List[str] = []
    for cat in sorted(estrutura.keys()):
        linhas.append("-" * 20)
        linhas.append(f"📦 {cat.upper()}")
        linhas.append("-" * 20)

        for sub in sorted(estrutura[cat].keys()):
            if sub != "Geral":
                linhas.append(f"\n🔹 {sub}:")
            for p in sorted(estrutura[cat][sub]):
                linhas.append(f"  • {p}")
        linhas.append("")

    return "\n".join(linhas).strip()

def categorias_dos_itens(itens_lista: List[str]) -> List[str]:
    categorias = []
    for item in itens_lista:
        cat = _buscar_categoria_raiz(item)
        if cat and cat not in categorias:
            categorias.append(cat)
    return categorias