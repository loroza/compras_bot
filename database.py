import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


async def get_conn():
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

        # Se o departamento padrão ainda não existir, cria.
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
        rows = await conn.fetch("SELECT * FROM departamentos WHERE ativo = TRUE ORDER BY id")
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

async def adicionar_ao_carrinho(user_id, dep_id, nome, qtd, valor):
    conn = await get_conn()
    try:
        await conn.execute(
            """
            INSERT INTO carrinho
            (adicionado_por, departamento_id, item_nome, quantidade, valor_unitario)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id, dep_id, nome, qtd, valor
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