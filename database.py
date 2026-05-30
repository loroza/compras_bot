import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL)

# ─── INIT ────────────────────────────────────────────────

async def init_db():
    conn = await get_conn()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS carrinho (
            id SERIAL PRIMARY KEY,
            item_nome TEXT,
            quantidade REAL,
            valor_unitario REAL,
            adicionado_por BIGINT
        );
        CREATE TABLE IF NOT EXISTS listas (
            id SERIAL PRIMARY KEY,
            nome TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS lista_itens (
            id SERIAL PRIMARY KEY,
            lista_id INTEGER REFERENCES listas(id) ON DELETE CASCADE,
            item_nome TEXT
        );
        CREATE TABLE IF NOT EXISTS historico_compras (
            id SERIAL PRIMARY KEY,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lista_nome TEXT,
            mercado TEXT,
            total REAL
        );
        CREATE TABLE IF NOT EXISTS historico_itens (
            id SERIAL PRIMARY KEY,
            compra_id INTEGER REFERENCES historico_compras(id),
            item_nome TEXT,
            quantidade REAL,
            valor_unitario REAL
        );
    """)
    await conn.close()

# ─── CARRINHO ────────────────────────────────────────────

async def adicionar_ao_carrinho(user_id, nome, qtd, valor):
    conn = await get_conn()
    await conn.execute(
        "INSERT INTO carrinho (item_nome, quantidade, valor_unitario, adicionado_por) VALUES ($1, $2, $3, $4)",
        nome, qtd, valor, user_id
    )
    await conn.close()

async def pegar_carrinho():
    conn = await get_conn()
    rows = await conn.fetch("SELECT * FROM carrinho")
    await conn.close()
    return rows

async def limpar_carrinho(user_id=None):
    conn = await get_conn()
    await conn.execute("DELETE FROM carrinho")
    await conn.close()

# ─── LISTAS ──────────────────────────────────────────────

async def criar_lista(nome):
    conn = await get_conn()
    try:
        await conn.execute("INSERT INTO listas (nome) VALUES ($1)", nome)
        await conn.close()
        return True
    except Exception:
        await conn.close()
        return False

async def adicionar_item_lista(lista_nome, item_nome):
    conn = await get_conn()
    res = await conn.fetchrow("SELECT id FROM listas WHERE nome = $1", lista_nome)
    if res:
        await conn.execute(
            "INSERT INTO lista_itens (lista_id, item_nome) VALUES ($1, $2)",
            res["id"], item_nome
        )
    await conn.close()

async def pegar_listas_disponiveis():
    conn = await get_conn()
    rows = await conn.fetch("SELECT nome FROM listas")
    await conn.close()
    return [r["nome"] for r in rows]

async def pegar_itens_da_lista(nome_lista):
    conn = await get_conn()
    rows = await conn.fetch("""
        SELECT li.item_nome FROM lista_itens li
        JOIN listas l ON l.id = li.lista_id
        WHERE l.nome = $1
    """, nome_lista)
    await conn.close()
    return [r["item_nome"] for r in rows]

async def remover_item_lista(lista_nome, item_nome):
    conn = await get_conn()
    res = await conn.fetchrow("SELECT id FROM listas WHERE nome = $1", lista_nome)
    if res:
        await conn.execute(
            "DELETE FROM lista_itens WHERE item_nome = $1 AND lista_id = $2",
            item_nome, res["id"]
        )
    await conn.close()

async def deletar_lista(nome):
    conn = await get_conn()
    res = await conn.fetchrow("SELECT id FROM listas WHERE nome = $1", nome)
    if res:
        await conn.execute("DELETE FROM lista_itens WHERE lista_id = $1", res["id"])
        await conn.execute("DELETE FROM listas WHERE id = $1", res["id"])
        await conn.close()
        return True
    await conn.close()
    return False

# ─── HISTÓRICO ───────────────────────────────────────────

async def salvar_historico(lista_nome, mercado, itens_comprados_dict, total):
    conn = await get_conn()
    compra_id = await conn.fetchval(
        "INSERT INTO historico_compras (lista_nome, mercado, total) VALUES ($1, $2, $3) RETURNING id",
        lista_nome, mercado, total
    )
    for item in itens_comprados_dict:
        await conn.execute(
            "INSERT INTO historico_itens (compra_id, item_nome, quantidade, valor_unitario) VALUES ($1, $2, $3, $4)",
            compra_id, item["nome"], item["quantidade"], item["valor_unitario"]
        )
    await conn.close()
    return compra_id
