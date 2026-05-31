import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def get_conn():
    return await asyncpg.connect(DATABASE_URL)

# ─── DEPARTAMENTOS ────

async def listar_departamentos():
    conn = await get_conn()
    rows = await conn.fetch("SELECT * FROM departamentos WHERE ativo = TRUE ORDER BY id")
    await conn.close()
    return rows

async def buscar_departamento(id_dep):
    conn = await get_conn()
    row = await conn.fetchrow("SELECT * FROM departamentos WHERE id = $1", id_dep)
    await conn.close()
    return row

# ─── CATEGORIAS ────

async def criar_categoria(dep_id, nome, emoji='🏷️'):
    conn = await get_conn()
    try:
        await conn.execute(
            "INSERT INTO categorias (departamento_id, nome, emoji) VALUES ($1, $2, $3)",
            dep_id, nome, emoji
        )
        return True
    except:
        return False
    finally:
        await conn.close()

async def listar_categorias(dep_id):
    conn = await get_conn()
    rows = await conn.fetch("SELECT * FROM categorias WHERE departamento_id = $1 ORDER BY nome", dep_id)
    await conn.close()
    return rows

async def deletar_categoria(cat_id):
    conn = await get_conn()
    await conn.execute("DELETE FROM categorias WHERE id = $1", cat_id)
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
    except:
        return False
    finally:
        await conn.close()

async def listar_produtos(dep_id):
    conn = await get_conn()
    rows = await conn.fetch("SELECT * FROM produtos WHERE departamento_id = $1 ORDER BY nome", dep_id)
    await conn.close()
    return rows

async def deletar_produto(prod_id):
    conn = await get_conn()
    await conn.execute("DELETE FROM produtos WHERE id = $1", prod_id)
    await conn.close()

# ─── CARRINHO ────

async def adicionar_ao_carrinho(user_id, dep_id, nome, qtd, valor):
    conn = await get_conn()
    await conn.execute(
        "INSERT INTO carrinho (adicionado_por, departamento_id, item_nome, quantidade, valor_unitario) VALUES ($1, $2, $3, $4, $5)",
        user_id, dep_id, nome, qtd, valor
    )
    await conn.close()

async def pegar_carrinho(user_id, dep_id):
    conn = await get_conn()
    rows = await conn.fetch("SELECT * FROM carrinho WHERE adicionado_por = $1 AND departamento_id = $2", user_id, dep_id)
    await conn.close()
    return rows

async def limpar_carrinho(user_id, dep_id):
    conn = await get_conn()
    await conn.execute("DELETE FROM carrinho WHERE adicionado_por = $1 AND departamento_id = $2", user_id, dep_id)
    await conn.close()

# ─── LISTAS ────

async def criar_lista(dep_id, nome, tipo='avulsa'):
    conn = await get_conn()
    try:
        await conn.execute("INSERT INTO listas (departamento_id, nome, tipo) VALUES ($1, $2, $3)", dep_id, nome, tipo)
        return True
    except:
        return False
    finally:
        await conn.close()

async def adicionar_item_lista(lista_id, item_nome):
    conn = await get_conn()
    await conn.execute("INSERT INTO lista_itens (lista_id, item_nome) VALUES ($1, $2)", lista_id, item_nome)
    await conn.close()

async def pegar_listas_disponiveis(dep_id):
    conn = await get_conn()
    rows = await conn.fetch("SELECT * FROM listas WHERE departamento_id = $1", dep_id)
    await conn.close()
    return rows

async def pegar_itens_da_lista(lista_id):
    conn = await get_conn()
    rows = await conn.fetch("SELECT item_nome FROM lista_itens WHERE lista_id = $1", lista_id)
    await conn.close()
    return [r["item_nome"] for r in rows]

async def remover_item_lista(lista_id, item_nome):
    conn = await get_conn()
    await conn.execute("DELETE FROM lista_itens WHERE item_nome = $1 AND lista_id = $2", item_nome, lista_id)
    await conn.close()

async def deletar_lista(lista_id):
    conn = await get_conn()
    await conn.execute("DELETE FROM listas WHERE id = $1", lista_id)
    await conn.close()

# ─── HISTÓRICO ────

async def salvar_historico(dep_id, lista_nome, mercado, itens_detalhe, total):
    conn = await get_conn()
    compra_id = await conn.fetchval(
        "INSERT INTO historico_compras (departamento_id, lista_nome, mercado, total) VALUES ($1, $2, $3, $4) RETURNING id",
        dep_id, lista_nome, mercado, total
    )
    for item in itens_detalhe:
        await conn.execute(
            "INSERT INTO historico_itens (compra_id, item_nome, quantidade, valor_unitario) VALUES ($1, $2, $3, $4)",
            compra_id, item["nome"], item["quantidade"], item["valor_unitario"]
        )
    await conn.close()