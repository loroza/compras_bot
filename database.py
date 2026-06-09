import asyncpg
import os
from dotenv import load_dotenv
import json

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


async def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não está definida. Configure a variável de ambiente DATABASE_URL (ex: postgres://user:pass@host:port/dbname).")
    return await asyncpg.connect(DATABASE_URL)


# ─── INIT ────

async def init_db():
    conn = await get_conn()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS departamentos (
                id SERIAL PRIMARY KEY,
                nome TEXT UNIQUE NOT NULL,
                emoji TEXT DEFAULT '📦',
                catalogo_json TEXT,
                ativo BOOLEAN DEFAULT TRUE
            );

            CREATE TABLE IF NOT EXISTS categorias (
                id SERIAL PRIMARY KEY,
                departamento_id INTEGER REFERENCES departamentos(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                emoji TEXT DEFAULT '🏷️',
                UNIQUE(departamento_id, nome)
            );

            CREATE TABLE IF NOT EXISTS produtos (
                id SERIAL PRIMARY KEY,
                departamento_id INTEGER REFERENCES departamentos(id) ON DELETE CASCADE,
                categoria_id INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                nome TEXT NOT NULL,
                UNIQUE(departamento_id, nome)
            );

            CREATE TABLE IF NOT EXISTS listas (
                id SERIAL PRIMARY KEY,
                departamento_id INTEGER REFERENCES departamentos(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                tipo TEXT DEFAULT 'avulsa',
                UNIQUE(departamento_id, nome)
            );

            CREATE TABLE IF NOT EXISTS lista_itens (
                id SERIAL PRIMARY KEY,
                lista_id INTEGER REFERENCES listas(id) ON DELETE CASCADE,
                item_nome TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS carrinho (
                id SERIAL PRIMARY KEY,
                departamento_id INTEGER REFERENCES departamentos(id) ON DELETE CASCADE,
                adicionado_por BIGINT NOT NULL,
                item_nome TEXT NOT NULL,
                quantidade REAL,
                valor_unitario REAL
            );

            CREATE TABLE IF NOT EXISTS historico_compras (
                id SERIAL PRIMARY KEY,
                departamento_id INTEGER REFERENCES departamentos(id),
                data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lista_nome TEXT,
                mercado TEXT,
                total REAL
            );

            CREATE TABLE IF NOT EXISTS historico_itens (
                id SERIAL PRIMARY KEY,
                compra_id INTEGER REFERENCES historico_compras(id) ON DELETE CASCADE,
                item_nome TEXT,
                quantidade REAL,
                valor_unitario REAL
            );
        """)

        await conn.execute("""
            INSERT INTO departamentos (nome, emoji, catalogo_json)
            VALUES ('Supermercado', '🛒', 'supermercado.json')
            ON CONFLICT (nome) DO NOTHING
        """)
    finally:
        await conn.close()


# ─── DEPARTAMENTOS ────

async def listar_departamentos():
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT * FROM departamentos WHERE ativo = TRUE ORDER BY nome")
        return rows
    finally:
        await conn.close()


async def buscar_departamento(dep_id):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT * FROM departamentos WHERE id = $1", dep_id)
        return row
    finally:
        await conn.close()


async def buscar_departamento_por_nome(nome):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT * FROM departamentos WHERE nome = $1", nome)
        return row
    finally:
        await conn.close()


# ─── CATEGORIAS ────

async def criar_categoria(dep_id, nome, emoji="🏷️"):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO categorias (departamento_id, nome, emoji) VALUES ($1, $2, $3)",
            dep_id, nome, emoji
        )
        return True
    except Exception:
        return False
    finally:
        await conn.close()


async def listar_categorias(dep_id):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            "SELECT * FROM categorias WHERE departamento_id = $1 ORDER BY nome",
            dep_id
        )
        return rows
    finally:
        await conn.close()


async def buscar_categoria(cat_id):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT * FROM categorias WHERE id = $1", cat_id)
        return row
    finally:
        await conn.close()


async def buscar_categoria_por_nome(dep_id, nome):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM categorias WHERE departamento_id = $1 AND LOWER(nome) = LOWER($2)",
            dep_id, nome
        )
        return row
    finally:
        await conn.close()


async def atualizar_categoria(cat_id, nome=None, emoji=None):
    conn = await get_conn()
    try:
        updates = []
        valores = []
        idx = 1

        if nome is not None:
            updates.append(f"nome = ${idx}")
            valores.append(nome)
            idx += 1

        if emoji is not None:
            updates.append(f"emoji = ${idx}")
            valores.append(emoji)
            idx += 1

        if not updates:
            return False

        valores.append(cat_id)
        query = f"UPDATE categorias SET {', '.join(updates)} WHERE id = ${idx}"
        await conn.execute(query, *valores)
        return True
    finally:
        await conn.close()


async def deletar_categoria(cat_id):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM categorias WHERE id = $1", cat_id)
    finally:
        await conn.close()


# ─── PRODUTOS ────

async def criar_produto(dep_id, nome, cat_id=None):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO produtos (departamento_id, nome, categoria_id) VALUES ($1, $2, $3)",
            dep_id, nome, cat_id
        )
        return True
    except Exception:
        return False
    finally:
        await conn.close()


async def listar_produtos(dep_id):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT p.*, c.nome AS categoria_nome, c.emoji AS categoria_emoji
            FROM produtos p
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE p.departamento_id = $1
            ORDER BY p.nome
            """,
            dep_id
        )
        return rows
    finally:
        await conn.close()


async def buscar_produto(prod_id):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT * FROM produtos WHERE id = $1", prod_id)
        return row
    finally:
        await conn.close()


async def buscar_produto_por_nome(dep_id, nome):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM produtos WHERE departamento_id = $1 AND LOWER(nome) = LOWER($2)",
            dep_id, nome
        )
        return row
    finally:
        await conn.close()


async def atualizar_produto(prod_id, nome=None, cat_id=None):
    conn = await get_conn()
    try:
        updates = []
        valores = []
        idx = 1

        if nome is not None:
            updates.append(f"nome = ${idx}")
            valores.append(nome)
            idx += 1

        if cat_id is not None or cat_id is None:
            updates.append(f"categoria_id = ${idx}")
            valores.append(cat_id)
            idx += 1

        if not updates:
            return False

        valores.append(prod_id)
        query = f"UPDATE produtos SET {', '.join(updates)} WHERE id = ${idx}"
        await conn.execute(query, *valores)
        return True
    finally:
        await conn.close()


async def deletar_produto(prod_id):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM produtos WHERE id = $1", prod_id)
    finally:
        await conn.close()


# ─── CARRINHO ────

async def adicionar_ao_carrinho(user_id, dep_id, nome, qtd, valor=None):
    """
    Valor agora opcional (defeito temporário tratado). Se valor for None,
    grava 0.0 e loga warning — ideal é corrigir o caller para sempre passar valor.
    """
    if valor is None:
        print("[WARN] adicionar_ao_carrinho chamado sem 'valor' — atribuindo valor=0.0")
        valor = 0.0

    # garantir tipos numéricos
    try:
        qtd_val = float(qtd) if qtd is not None else None
    except Exception:
        qtd_val = None

    try:
        valor_val = float(valor) if valor is not None else None
    except Exception:
        valor_val = None

    conn = await get_conn()
    try:
        await conn.execute(
            """
            INSERT INTO carrinho
            (adicionado_por, departamento_id, item_nome, quantidade, valor_unitario)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id, dep_id, nome, qtd_val, valor_val
        )
    finally:
        await conn.close()


async def pegar_carrinho(user_id=None, dep_id=None):
    conn = await get_conn()
    try:
        if user_id is not None and dep_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM carrinho WHERE adicionado_por = $1 AND departamento_id = $2",
                user_id, dep_id
            )
        elif dep_id is not None:
            rows = await conn.fetch(
                "SELECT * FROM carrinho WHERE departamento_id = $1",
                dep_id
            )
        else:
            rows = await conn.fetch("SELECT * FROM carrinho")
        return rows
    finally:
        await conn.close()


async def remover_item_carrinho(user_id, dep_id, item_nome):
    """Remove a primeira ocorrência do item no carrinho do usuário."""
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            """
            SELECT id FROM carrinho
            WHERE adicionado_por = $1 AND departamento_id = $2 AND item_nome = $3
            LIMIT 1
            """,
            user_id, dep_id, item_nome
        )
        if row:
            await conn.execute("DELETE FROM carrinho WHERE id = $1", row["id"])
    finally:
        await conn.close()


async def limpar_carrinho(user_id=None, dep_id=None):
    conn = await get_conn()
    try:
        if user_id is not None and dep_id is not None:
            await conn.execute(
                "DELETE FROM carrinho WHERE adicionado_por = $1 AND departamento_id = $2",
                user_id, dep_id
            )
        elif dep_id is not None:
            await conn.execute("DELETE FROM carrinho WHERE departamento_id = $1", dep_id)
        else:
            await conn.execute("DELETE FROM carrinho")
    finally:
        await conn.close()


# ─── LISTAS ────

async def criar_lista(dep_id, nome, tipo="avulsa"):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO listas (departamento_id, nome, tipo) VALUES ($1, $2, $3)",
            dep_id, nome, tipo
        )
        return True
    except Exception:
        return False
    finally:
        await conn.close()


async def pegar_listas_disponiveis(dep_id):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            "SELECT * FROM listas WHERE departamento_id = $1 ORDER BY id",
            dep_id
        )
        return rows
    finally:
        await conn.close()


async def buscar_lista(lista_id):
    conn = await get_conn()
    try:
        row = await conn.fetchrow("SELECT * FROM listas WHERE id = $1", lista_id)
        return row
    finally:
        await conn.close()


async def buscar_lista_por_nome(dep_id, nome):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM listas WHERE departamento_id = $1 AND LOWER(nome) = LOWER($2)",
            dep_id, nome
        )
        return row
    finally:
        await conn.close()


async def adicionar_item_lista(lista_id, item_nome):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO lista_itens (lista_id, item_nome) VALUES ($1, $2)",
            lista_id, item_nome
        )
    finally:
        await conn.close()


async def pegar_itens_da_lista(lista_id):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            "SELECT item_nome FROM lista_itens WHERE lista_id = $1 ORDER BY id",
            lista_id
        )
        return [r["item_nome"] for r in rows]
    finally:
        await conn.close()


async def remover_item_lista(lista_id, item_nome):
    conn = await get_conn()
    try:
        await conn.execute(
            "DELETE FROM lista_itens WHERE item_nome = $1 AND lista_id = $2",
            item_nome, lista_id
        )
    finally:
        await conn.close()


async def deletar_lista(lista_id):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM listas WHERE id = $1", lista_id)
        return True
    except Exception:
        return False
    finally:
        await conn.close()


# ─── HISTÓRICO ────

async def salvar_historico(dep_id, lista_nome, mercado, itens_comprados_dict, total):
    conn = await get_conn()
    try:
        compra_id = await conn.fetchval(
            """
            INSERT INTO historico_compras (departamento_id, lista_nome, mercado, total)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            dep_id, lista_nome, mercado, total
        )
        for item in itens_comprados_dict:
            await conn.execute(
                """
                INSERT INTO historico_itens (compra_id, item_nome, quantidade, valor_unitario)
                VALUES ($1, $2, $3, $4)
                """,
                compra_id, item["nome"], item["quantidade"], item["valor_unitario"]
            )
        return compra_id
    finally:
        await conn.close()


async def listar_historico(dep_id, limite=20):
    """Retorna as últimas compras do departamento, mais recentes primeiro."""
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT id, mercado, total, data, lista_nome
            FROM historico_compras
            WHERE departamento_id = $1
            ORDER BY data DESC
            LIMIT $2
            """,
            dep_id, limite
        )
        return rows
    finally:
        await conn.close()


async def listar_itens_historico(compra_id):
    """Retorna os itens de uma compra específica do histórico."""
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT item_nome, quantidade, valor_unitario
            FROM historico_itens
            WHERE compra_id = $1
            ORDER BY item_nome
            """,
            compra_id
        )
        return rows
    finally:
        await conn.close()


# --- IMPORTAÇÃO DE CATÁLOGO JSON PARA DB ---

async def importar_catalogo_para_departamento(dep_id: int, arquivo_json: str, catalogos_dir: str = "catalogos"):
    """
    Importa categorias e produtos a partir do JSON do catálogo.
    Suporta automaticamente tanto o formato antigo (top -> subcategoria -> produtos) quanto
    o novo formato com 3 níveis (top -> categoria -> subcategoria -> produtos).

    Normalizações e regras:
    - Aceita 'subcategoria' ou 'subcategorias' como chaves.
    - Aceita produtos como lista de strings ou lista de objetos com campo 'nome'/'name'.
    - Cria categorias com o nome composto pelas partes do caminho separadas por " / ".
    - Operações idempotentes: categorias e produtos usam ON CONFLICT para não duplicar.

    Retorna dict {'ok': bool, 'msg': str}
    """
    if not arquivo_json:
        return {"ok": False, "msg": "arquivo_json vazio"}

    caminho = os.path.join(catalogos_dir, arquivo_json)
    if not os.path.isfile(caminho):
        return {"ok": False, "msg": f"arquivo não encontrado: {caminho}"}

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"ok": False, "msg": f"erro ao ler JSON: {e}"}

    conn = await get_conn()
    try:
        async def _ensure_categoria(path_parts):
            """Cria/retorna categoria cujo nome é a junção das partes por ' / '."""
            nome = " / ".join([p.strip() for p in path_parts if p and str(p).strip()])
            if not nome:
                nome = "Sem categoria"
            cat_id = await conn.fetchval(
                """
                INSERT INTO categorias (departamento_id, nome)
                VALUES ($1, $2)
                ON CONFLICT (departamento_id, nome) DO UPDATE
                SET nome = EXCLUDED.nome
                RETURNING id
                """,
                dep_id, nome
            )
            return cat_id

        def _normalize_produtos(produtos_node):
            """Retorna lista de nomes de produtos (strings) normalizados."""
            items = []
            if isinstance(produtos_node, list):
                raw = produtos_node
            elif isinstance(produtos_node, dict):
                raw = produtos_node.get("produtos") or []
            else:
                raw = []

            for p in raw:
                if isinstance(p, str):
                    name = p.strip()
                elif isinstance(p, dict):
                    name = p.get("nome") or p.get("name") or ""
                    if isinstance(name, str):
                        name = name.strip()
                else:
                    continue
                if name:
                    items.append(name)
            return items

        async def _process_node(path_parts, node):
            """Processa recursivamente o nó do JSON até encontrar listas de produtos.
            Quando encontra 'produtos', insere a categoria (nome = caminho) e produtos.
            """
            # caso: node é lista direta de produtos
            if isinstance(node, list):
                produtos = _normalize_produtos(node)
                if not produtos:
                    return
                cat_id = await _ensure_categoria(path_parts)
                for prod in produtos:
                    await conn.execute(
                        """
                        INSERT INTO produtos (departamento_id, categoria_id, nome)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (departamento_id, nome) DO NOTHING
                        """,
                        dep_id, cat_id, prod
                    )
                return

            # caso: node é dict
            if isinstance(node, dict):
                # caso comum: node contém chave 'produtos'
                if "produtos" in node and isinstance(node.get("produtos"), list):
                    produtos = _normalize_produtos(node)
                    if produtos:
                        cat_id = await _ensure_categoria(path_parts)
                        for prod in produtos:
                            await conn.execute(
                                """
                                INSERT INTO produtos (departamento_id, categoria_id, nome)
                                VALUES ($1, $2, $3)
                                ON CONFLICT (departamento_id, nome) DO NOTHING
                                """,
                                dep_id, cat_id, prod
                            )
                    return

                # caso: node tem subcategorias em chaves conhecidas
                subs = node.get("subcategoria") or node.get("subcategorias") or node.get("subcategories")
                if isinstance(subs, dict):
                    for k, v in subs.items():
                        await _process_node(path_parts + [k], v)
                    return

                # heurística: se os valores do dict forem dicts ou listas, tratamos como níveis aninhados
                nested = False
                for k, v in node.items():
                    if isinstance(v, (dict, list)):
                        nested = True
                        break
                if nested:
                    for k, v in node.items():
                        await _process_node(path_parts + [k], v)
                    return

                # caso: dict sem produtos nem subcategorias -- nada a fazer
                return

            # caso contrário: nada a fazer
            return

        # percorre os nós top-level
        for top_key, top_node in data.items():
            if isinstance(top_node, dict):
                subs = top_node.get("subcategoria") or top_node.get("subcategorias") or top_node.get("subcategories")
                if isinstance(subs, dict):
                    # padrão: top -> categoria -> subcategoria -> produtos
                    for cat_name, cat_node in subs.items():
                        await _process_node([top_key, cat_name], cat_node)
                    continue
            # fallback: processa top_node diretamente (top_key como categoria)
            await _process_node([top_key], top_node)

        return {"ok": True, "msg": "import completo"}
    finally:
        await conn.close()


async def criar_departamento(nome: str, emoji: str = "📦", catalogo_json: str = None):
    """
    Cria um departamento e, se 'catalogo_json' for fornecido, importa categorias/produtos automaticamente.
    Retorna dict com 'ok' e 'id' ou 'msg'.
    """
    conn = await get_conn()
    try:
        dep_id = await conn.fetchval(
            """
            INSERT INTO departamentos (nome, emoji, catalogo_json)
            VALUES ($1, $2, $3)
            ON CONFLICT (nome) DO UPDATE
              SET emoji = EXCLUDED.emoji, catalogo_json = COALESCE(EXCLUDED.catalogo_json, departamentos.catalogo_json)
            RETURNING id
            """,
            nome, emoji, catalogo_json
        )
    finally:
        await conn.close()

    # se tiver catalogo_json, tenta importar (não crítica: loga erro e continua)
    if catalogo_json:
        try:
            await importar_catalogo_para_departamento(dep_id, catalogo_json)
        except Exception as e:
            # opcional: logar
            print(f"[WARN] falha ao importar catálogo para departamento {nome}: {e}")
            # não falhar a criação por causa da import
    return {"ok": True, "id": dep_id}