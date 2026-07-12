import asyncpg
import os
from dotenv import load_dotenv
import json

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não está definida. Configure a variável de ambiente DATABASE_URL.")
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

            -- NOVAS TABELAS PARA ORÇAMENTOS
            CREATE TABLE IF NOT EXISTS orcamentos (
                id SERIAL PRIMARY KEY,
                departamento_id INTEGER REFERENCES departamentos(id) ON DELETE CASCADE,
                nome_orcamento TEXT NOT NULL,
                criado_por BIGINT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orcamento_itens (
                id SERIAL PRIMARY KEY,
                orcamento_id INTEGER REFERENCES orcamentos(id) ON DELETE CASCADE,
                item_nome TEXT NOT NULL,
                quantidade REAL DEFAULT 1,
                valor_unitario REAL DEFAULT 0,
                loja_tipo TEXT,
                loja_nome TEXT,
                loja_link TEXT,
                unidade TEXT
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
            "INSERT INTO categorias (departamento_id, nome, emoji) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
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
            updates.append(f"nome = ${idx}"); valores.append(nome); idx += 1
        if emoji is not None:
            updates.append(f"emoji = ${idx}"); valores.append(emoji); idx += 1
        if not updates: return False
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
            "INSERT INTO produtos (departamento_id, nome, categoria_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
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
            updates.append(f"nome = ${idx}"); valores.append(nome); idx += 1
        if cat_id is not None:
            updates.append(f"categoria_id = ${idx}"); valores.append(cat_id); idx += 1
        if not updates: return False
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
    if valor is None:
        valor = 0.0
    try:
        qtd_val = float(qtd)
    except:
        qtd_val = 1.0
    try:
        valor_val = float(valor)
    except:
        valor_val = 0.0

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
            return await conn.fetch("SELECT * FROM carrinho WHERE adicionado_por = $1 AND departamento_id = $2", user_id, dep_id)
        elif dep_id is not None:
            return await conn.fetch("SELECT * FROM carrinho WHERE departamento_id = $1", dep_id)
        return await conn.fetch("SELECT * FROM carrinho")
    finally:
        await conn.close()


async def remover_item_carrinho(user_id, dep_id, item_nome):
    conn = await get_conn()
    try:
        row = await conn.fetchrow(
            "SELECT id FROM carrinho WHERE adicionado_por=$1 AND departamento_id=$2 AND item_nome=$3 LIMIT 1",
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
            await conn.execute("DELETE FROM carrinho WHERE adicionado_por = $1 AND departamento_id = $2", user_id, dep_id)
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
            "INSERT INTO listas (departamento_id, nome, tipo) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
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
        return await conn.fetch("SELECT * FROM listas WHERE departamento_id = $1 ORDER BY id", dep_id)
    finally:
        await conn.close()


async def buscar_lista(lista_id):
    conn = await get_conn()
    try:
        return await conn.fetchrow("SELECT * FROM listas WHERE id = $1", lista_id)
    finally:
        await conn.close()


async def buscar_lista_por_nome(dep_id, nome):
    conn = await get_conn()
    try:
        return await conn.fetchrow("SELECT * FROM listas WHERE departamento_id=$1 AND LOWER(nome)=LOWER($2)", dep_id, nome)
    finally:
        await conn.close()


async def adicionar_item_lista(lista_id, item_nome):
    conn = await get_conn()
    try:
        await conn.execute("INSERT INTO lista_itens (lista_id, item_nome) VALUES ($1, $2)", lista_id, item_nome)
    finally:
        await conn.close()


async def pegar_itens_da_lista(lista_id):
    conn = await get_conn()
    try:
        rows = await conn.fetch("SELECT item_nome FROM lista_itens WHERE lista_id = $1 ORDER BY id", lista_id)
        return [r["item_nome"] for r in rows]
    finally:
        await conn.close()

async def pegar_itens_da_lista_com_categoria(lista_id):
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT li.item_nome, c.nome AS categoria
            FROM lista_itens li
            INNER JOIN listas l ON l.id = li.lista_id
            LEFT JOIN produtos p ON p.departamento_id = l.departamento_id 
                AND LOWER(TRIM(p.nome)) = LOWER(TRIM(li.item_nome))
            LEFT JOIN categorias c ON c.id = p.categoria_id
            WHERE li.lista_id = $1
            ORDER BY li.id
            """,
            lista_id
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def remover_item_lista(lista_id, item_nome):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM lista_itens WHERE item_nome = $1 AND lista_id = $2", item_nome, lista_id)
    finally:
        await conn.close()


async def deletar_lista(lista_id):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM listas WHERE id = $1", lista_id)
        return True
    except:
        return False
    finally:
        await conn.close()


# ─── HISTÓRICO ────

async def salvar_historico(dep_id, lista_nome, mercado, itens_comprados_dict, total):
    conn = await get_conn()
    try:
        compra_id = await conn.fetchval(
            "INSERT INTO historico_compras (departamento_id, lista_nome, mercado, total) VALUES ($1, $2, $3, $4) RETURNING id",
            dep_id, lista_nome, mercado, total
        )
        for item in itens_comprados_dict:
            await conn.execute(
                "INSERT INTO historico_itens (compra_id, item_nome, quantidade, valor_unitario) VALUES ($1, $2, $3, $4)",
                compra_id, item["nome"], item["quantidade"], item["valor_unitario"]
            )
        return compra_id
    finally:
        await conn.close()


async def listar_historico(dep_id, limite=20):
    conn = await get_conn()
    try:
        return await conn.fetch(
            "SELECT id, mercado, total, data, lista_nome FROM historico_compras WHERE departamento_id=$1 ORDER BY data DESC LIMIT $2",
            dep_id, limite
        )
    finally:
        await conn.close()


async def listar_itens_historico(compra_id):
    conn = await get_conn()
    try:
        return await conn.fetch("SELECT item_nome, quantidade, valor_unitario FROM historico_itens WHERE compra_id=$1 ORDER BY item_nome", compra_id)
    finally:
        await conn.close()


# ─── ORÇAMENTOS ────

async def criar_orcamento(dep_id, nome_orcamento, user_id):
    conn = await get_conn()
    try:
        return await conn.fetchval(
            "INSERT INTO orcamentos (departamento_id, nome_orcamento, criado_por) VALUES ($1, $2, $3) RETURNING id",
            dep_id, nome_orcamento, user_id
        )
    finally:
        await conn.close()

async def listar_orcamentos(dep_id):
    conn = await get_conn()
    try:
        return await conn.fetch("SELECT * FROM orcamentos WHERE departamento_id=$1 ORDER BY criado_em DESC", dep_id)
    finally:
        await conn.close()

async def buscar_orcamento_por_id(orc_id):
    conn = await get_conn()
    try:
        return await conn.fetchrow("SELECT * FROM orcamentos WHERE id=$1", orc_id)
    finally:
        await conn.close()

async def adicionar_item_orc_completo(orc_id, item_nome, qtd=1, valor=0, loja_tipo=None, loja_nome=None, link=None, unidade=None):
    conn = await get_conn()
    try:
        return await conn.fetchval(
            """INSERT INTO orcamento_itens (orcamento_id, item_nome, quantidade, valor_unitario, loja_tipo, loja_nome, loja_link, unidade) 
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
            orc_id, item_nome, qtd, valor, loja_tipo, loja_nome, link, unidade
        )
    finally:
        await conn.close()

async def listar_itens_orcamento(orc_id):
    conn = await get_conn()
    try:
        return await conn.fetch("SELECT * FROM orcamento_itens WHERE orcamento_id=$1 ORDER BY id", orc_id)
    finally:
        await conn.close()

async def deletar_orcamento(orc_id):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM orcamentos WHERE id=$1", orc_id)
    finally:
        await conn.close()

async def excluir_item_orc_por_id(item_id):
    conn = await get_conn()
    try:
        await conn.execute("DELETE FROM orcamento_itens WHERE id=$1", item_id)
    finally:
        await conn.close()

async def contar_itens_orcamento(orc_id):
    conn = await get_conn()
    try:
        return await conn.fetchval("SELECT COUNT(*) FROM orcamento_itens WHERE orcamento_id=$1", orc_id)
    finally:
        await conn.close()


# --- IMPORTAÇÃO DE CATÁLOGO JSON PARA DB ---

async def importar_catalogo_para_departamento(dep_id: int, arquivo_json: str):
    if not arquivo_json:
        return {"ok": False, "msg": "arquivo_json vazio"}

    if not os.path.isfile(arquivo_json):
        return {"ok": False, "msg": f"arquivo não encontrado na raiz: {arquivo_json}"}

    try:
        with open(arquivo_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"ok": False, "msg": f"erro ao ler JSON: {e}"}

    conn = await get_conn()
    try:
        async def _ensure_categoria(path_parts):
            nome = " / ".join([p.strip() for p in path_parts if p and str(p).strip()])
            if not nome: nome = "Sem categoria"
            return await conn.fetchval(
                """
                INSERT INTO categorias (departamento_id, nome)
                VALUES ($1, $2)
                ON CONFLICT (departamento_id, nome) DO UPDATE SET nome = EXCLUDED.nome
                RETURNING id
                """,
                dep_id, nome
            )

        def _normalize_produtos(node):
            if isinstance(node, list): return [str(p).strip() for p in node if p]
            if isinstance(node, dict):
                p_list = node.get("produtos") or []
                return [p.get("nome") if isinstance(p, dict) else str(p).strip() for p in p_list if p]
            return []

        async def _process_node(path_parts, node):
            if isinstance(node, list):
                prods = _normalize_produtos(node)
                if prods:
                    cat_id = await _ensure_categoria(path_parts)
                    for p in prods:
                        await conn.execute("INSERT INTO produtos (departamento_id, categoria_id, nome) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", dep_id, cat_id, p)
                return

            if isinstance(node, dict):
                if "produtos" in node and isinstance(node["produtos"], list):
                    prods = _normalize_produtos(node)
                    cat_id = await _ensure_categoria(path_parts)
                    for p in prods:
                        await conn.execute("INSERT INTO produtos (departamento_id, categoria_id, nome) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", dep_id, cat_id, p)
                
                subs = node.get("subcategoria") or node.get("subcategorias") or node.get("subcategories")
                if isinstance(subs, dict):
                    for k, v in subs.items():
                        await _process_node(path_parts + [k], v)
                else:
                    for k, v in node.items():
                        if k not in ["emoji", "produtos"]:
                            await _process_node(path_parts + [k], v)

        for top_key, top_node in data.items():
            await _process_node([top_key], top_node)

        return {"ok": True, "msg": "import completo"}
    finally:
        await conn.close()

async def criar_departamento_com_import(nome, emoji="📦", catalogo_json=None):
    conn = await get_conn()
    try:
        dep_id = await conn.fetchval(
            "INSERT INTO departamentos (nome, emoji, catalogo_json) VALUES ($1, $2, $3) ON CONFLICT (nome) DO UPDATE SET emoji=EXCLUDED.emoji RETURNING id",
            nome, emoji, catalogo_json
        )
        if catalogo_json:
            await importar_catalogo_para_departamento(dep_id, catalogo_json)
        return {"ok": True, "id": dep_id}
    finally:
        await conn.close()