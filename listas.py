from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import database
import catalogo

router = Router()

class ListaState(StatesGroup):
    escolhendo_tipo_lista = State()   # ← novo: padrão ou avulsa
    criando_nome = State()
    escolhendo_lista = State()
    navegando_catalogo = State()
    compra_navegando = State()
    compra_quantidade = State()
    compra_valor = State()
    compra_nome_mercado = State()
    removendo_item = State()
    escolhendo_lista_remover = State()
    removendo_lista = State()         # ← novo: remover lista inteira

def kb_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
        [KeyboardButton(text="📦 Ver Carrinho"), KeyboardButton(text="🏁 Finalizar")]
    ], resize_keyboard=True)

def kb_listas_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Nova Lista"), KeyboardButton(text="🗑️ Remover Lista")],
        [KeyboardButton(text="📝 Adicionar Itens"), KeyboardButton(text="🚀 Iniciar Compra")],
        [KeyboardButton(text="🗑️ Remover Item"), KeyboardButton(text="⬅️ Menu Principal")]
    ], resize_keyboard=True)

def kb_opcoes(lista, voltar=True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar:
        btns.append([KeyboardButton(text="⬅️ Voltar")])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def kb_lista_escolha(listas):
    btns = [[KeyboardButton(text=nome)] for nome in listas]
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def obter_opcoes_nivel(caminho):
    if not caminho:
        return list(catalogo.CATALOGO.keys())
    return catalogo.obter_opcoes(caminho)

def is_lista_padrao(nome):
    return "(padrão)" in nome.lower()

async def extrato_carrinho(message: types.Message):
    itens = await database.pegar_carrinho()
    if not itens:
        return
    texto = "🛒 *Carrinho atual:*\n\n"
    total = 0
    for item in itens:
        sub = item['quantidade'] * item['valor_unitario']
        total += sub
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
    texto += f"\n💰 *Total: R${total:.2f}*"
    await message.answer(texto, parse_mode="Markdown")


# ─── MENU LISTAS ────

@router.message(F.text == "📋 Minhas Listas")
async def menu_listas(message: types.Message):
    await message.answer("📋 Gerenciador de Listas:", reply_markup=kb_listas_menu())

@router.message(F.text == "⬅️ Menu Principal")
async def voltar_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Menu Principal:", reply_markup=kb_menu())


# ─── CRIAR LISTA ────

@router.message(F.text == "➕ Nova Lista")
async def nova_lista(message: types.Message, state: FSMContext):
    await state.set_state(ListaState.escolhendo_tipo_lista)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📌 Padrão"), KeyboardButton(text="🛒 Avulsa")],
        [KeyboardButton(text="❌ Cancelar")]
    ], resize_keyboard=True)
    await message.answer(
        "Qual o tipo da lista?\n\n"
        "📌 *Padrão* — fica salva após a compra (ex: Lista Mensal)\n"
        "🛒 *Avulsa* — é deletada automaticamente ao finalizar",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.message(ListaState.escolhendo_tipo_lista)
async def escolher_tipo_lista(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    if message.text == "📌 Padrão":
        await state.update_data(tipo_lista="padrao")
    elif message.text == "🛒 Avulsa":
        await state.update_data(tipo_lista="avulsa")
    else:
        return await message.answer("Escolha uma opção válida.")

    await state.set_state(ListaState.criando_nome)
    await message.answer("Digite o nome da lista:", reply_markup=ReplyKeyboardRemove())

@router.message(ListaState.criando_nome)
async def salvar_nome_lista(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tipo = data.get("tipo_lista", "avulsa")
    nome_base = message.text.strip()
    nome = f"{nome_base} (padrão)" if tipo == "padrao" else nome_base

    criado = await database.criar_lista(nome)
    await state.clear()
    if criado:
        await message.answer(f"✅ Lista *{nome}* criada com sucesso!", reply_markup=kb_listas_menu(), parse_mode="Markdown")
    else:
        await message.answer(f"⚠️ Já existe uma lista com o nome *{nome}*.", reply_markup=kb_listas_menu(), parse_mode="Markdown")


# ─── REMOVER LISTA INTEIRA ────

@router.message(F.text == "🗑️ Remover Lista")
async def cmd_remover_lista(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.removendo_lista)
    await message.answer("Qual lista deseja remover?", reply_markup=kb_lista_escolha(listas))

@router.message(ListaState.removendo_lista)
async def confirmar_remocao_lista(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    listas = await database.pegar_listas_disponiveis()
    if message.text not in listas:
        return await message.answer("Lista não encontrada. Tente novamente.", reply_markup=kb_lista_escolha(listas))

    await database.deletar_lista(message.text)
    await state.clear()
    await message.answer(f"🗑️ Lista *{message.text}* removida!", reply_markup=kb_listas_menu(), parse_mode="Markdown")


# ─── ADICIONAR ITENS À LISTA ────

@router.message(F.text == "📝 Adicionar Itens")
async def adicionar_itens(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda. Crie uma primeiro!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(modo="adicionar")
    await message.answer("Qual lista você quer editar?", reply_markup=kb_lista_escolha(listas))

@router.message(ListaState.escolhendo_lista)
async def lista_escolhida(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    data = await state.get_data()
    modo = data.get("modo")
    listas = await database.pegar_listas_disponiveis()

    if message.text not in listas:
        return await message.answer("Lista não encontrada. Tente novamente.", reply_markup=kb_lista_escolha(listas))

    if modo == "adicionar":
        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(lista_atual=message.text, caminho=[])
        opts = list(catalogo.CATALOGO.keys())
        await message.answer(
            f"📝 Adicionando itens em *{message.text}*\nEscolha a categoria:",
            reply_markup=kb_opcoes(opts, False),
            parse_mode="Markdown"
        )

    elif modo == "compra":
        itens = await database.pegar_itens_da_lista(message.text)
        if not itens:
            await state.clear()
            return await message.answer("Essa lista está vazia! Adicione itens primeiro.", reply_markup=kb_listas_menu())

        await database.limpar_carrinho(message.from_user.id)
        await state.set_state(ListaState.compra_navegando)
        cats_filtradas = catalogo.categorias_dos_itens(itens)

        await state.update_data(
            lista_atual=message.text,
            itens_lista=itens,
            itens_comprados=[],
            itens_comprados_detalhe=[],
            caminho_compra=[],
            cats_filtradas=cats_filtradas
        )

        btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in cats_filtradas]
        btns.append([KeyboardButton(text="✅ Finalizar Compra")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

        await message.answer(
            f"🛒 Compra da lista *{message.text}* iniciada!\n"
            f"📋 {len(itens)} itens pendentes\n\n"
            f"Categorias disponíveis:",
            reply_markup=kb,
            parse_mode="Markdown"
        )


# ─── INICIAR COMPRA ────

@router.message(F.text == "🚀 Iniciar Compra")
async def iniciar_compra(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(modo="compra")
    await message.answer("Qual lista você quer usar?", reply_markup=kb_lista_escolha(listas))


# ─── NAVEGAÇÃO DURANTE A COMPRA ────

@router.message(ListaState.compra_navegando)
async def compra_navegar(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho_compra", [])
    itens_lista = data.get("itens_lista", [])
    itens_comprados = data.get("itens_comprados", [])
    cats_filtradas = data.get("cats_filtradas", [])

    if message.text == "✅ Finalizar Compra":
        pendentes = [i for i in itens_lista if i not in itens_comprados]
        if pendentes:
            texto = "⚠️ *Itens ainda não comprados:*\n" + "\n".join(f"• {i}" for i in pendentes)
            texto += "\n\nO que deseja fazer?"
            kb = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="🏪 Finalizar e continuar em outro mercado")],
                [KeyboardButton(text="✅ Finalizar e encerrar")],
                [KeyboardButton(text="🔙 Voltar")]
            ], resize_keyboard=True)
            return await message.answer(texto, reply_markup=kb, parse_mode="Markdown")

        await state.set_state(ListaState.compra_nome_mercado)
        await state.update_data(continuar_depois=False)
        return await message.answer("🏪 Qual o nome do mercado desta compra?", reply_markup=ReplyKeyboardRemove())

    if message.text == "✅ Finalizar e encerrar":
        await state.set_state(ListaState.compra_nome_mercado)
        await state.update_data(continuar_depois=False)
        return await message.answer("🏪 Qual o nome do mercado desta compra?", reply_markup=ReplyKeyboardRemove())

    if message.text == "🏪 Finalizar e continuar em outro mercado":
        await state.set_state(ListaState.compra_nome_mercado)
        await state.update_data(continuar_depois=True)
        return await message.answer("🏪 Qual o nome do mercado desta compra?", reply_markup=ReplyKeyboardRemove())

    if message.text == "🔙 Voltar":
        if caminho:
            caminho.pop()
        await state.update_data(caminho_compra=caminho)
        return await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados, cats_filtradas)

    tipo, chave = catalogo.identificar_escolha(caminho, message.text)

    if tipo == "categoria":
        caminho.append(chave)
        await state.update_data(caminho_compra=caminho)
        return await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados, cats_filtradas)

    elif tipo == "produto":
        pendentes = [i for i in itens_lista if i not in itens_comprados]
        if chave not in pendentes:
            return await message.answer("Este item já foi comprado ou não está na lista.")
        await state.update_data(item_atual=chave)
        await state.set_state(ListaState.compra_quantidade)
        return await message.answer(f"🛍️ *{chave}*\nQual a quantidade?", parse_mode="Markdown")

    else:
        await message.answer("Opção inválida. Use o teclado do bot.")


# ─── NOME DO MERCADO + FINALIZAÇÃO ────

@router.message(ListaState.compra_nome_mercado)
async def salvar_nome_mercado(message: types.Message, state: FSMContext):
    mercado = message.text.strip()
    data = await state.get_data()
    lista_atual = data.get("lista_atual", "")
    itens_comprados = data.get("itens_comprados", [])
    itens_comprados_detalhe = data.get("itens_comprados_detalhe", [])
    itens_lista = data.get("itens_lista", [])
    continuar_depois = data.get("continuar_depois", False)

    total = sum(i["quantidade"] * i["valor_unitario"] for i in itens_comprados_detalhe)
    await database.salvar_historico(lista_atual, mercado, itens_comprados_detalhe, total)
    await database.limpar_carrinho(message.from_user.id)

    pendentes = [i for i in itens_lista if i not in itens_comprados]

    # ✅ Regra: deleta lista se não for padrão e todos os itens foram comprados (ou encerrou)
    lista_deletada = False
    if not continuar_depois and not is_lista_padrao(lista_atual):
        await database.deletar_lista(lista_atual)
        lista_deletada = True

    texto = f"✅ *Compra no {mercado} finalizada!*\n"
    texto += f"💰 Total: R${total:.2f}\n"
    texto += f"📦 {len(itens_comprados)} itens comprados"
    if pendentes:
        texto += f"\n⚠️ {len(pendentes)} itens não comprados"
    if lista_deletada:
        texto += f"\n🗑️ Lista *{lista_atual}* removida automaticamente"
    await message.answer(texto, parse_mode="Markdown")

    if continuar_depois and pendentes:
        cats_filtradas = catalogo.categorias_dos_itens(pendentes)
        await state.set_state(ListaState.compra_navegando)
        await state.update_data(
            itens_lista=pendentes,
            itens_comprados=[],
            itens_comprados_detalhe=[],
            caminho_compra=[],
            cats_filtradas=cats_filtradas,
            continuar_depois=False
        )

        btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in cats_filtradas]
        btns.append([KeyboardButton(text="✅ Finalizar Compra")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

        await message.answer(
            f"🛒 Continuando compra da lista *{lista_atual}*\n"
            f"📋 {len(pendentes)} itens restantes\n\nEscolha a categoria:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    else:
        # ✅ Se for padrão e continuar_depois, deleta após o segundo mercado também
        if not is_lista_padrao(lista_atual) and not lista_deletada:
            await database.deletar_lista(lista_atual)
        await state.clear()
        await message.answer("Voltando ao menu de listas.", reply_markup=kb_listas_menu())


async def _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados, cats_filtradas):
    pendentes = [i for i in itens_lista if i not in itens_comprados]

    if not caminho:
        cats_com_pendentes = catalogo.categorias_dos_itens(pendentes)
        if not cats_com_pendentes:
            await state.set_state(ListaState.compra_nome_mercado)
            await state.update_data(continuar_depois=False)
            return await message.answer(
                "🎉 Todos os itens foram comprados!\n\n🏪 Qual o nome do mercado?",
                reply_markup=ReplyKeyboardRemove()
            )
        btns = [[KeyboardButton(text=catalogo.formatar(c))] for c in cats_com_pendentes]
        btns.append([KeyboardButton(text="✅ Finalizar Compra")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        return await message.answer("Escolha a categoria:", reply_markup=kb)

    opcoes = catalogo.obter_opcoes(caminho)
    if not opcoes:
        return await message.answer("Categoria vazia.", reply_markup=kb_listas_menu())

    primeira = opcoes[0]
    no_teste = catalogo.obter_no(caminho + [primeira])

    if no_teste is None:
        itens_aqui = [p for p in opcoes if p in pendentes]
        if not itens_aqui:
            await message.answer("✅ Todos os itens desta categoria já foram comprados!")
            caminho.pop()
            await state.update_data(caminho_compra=caminho)
            return await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados, cats_filtradas)

        btns = [[KeyboardButton(text=item)] for item in itens_aqui]
        btns.append([KeyboardButton(text="🔙 Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await message.answer(f"📋 Itens pendentes ({len(itens_aqui)}):", reply_markup=kb)
    else:
        subs_com_pendentes = []
        for sub in opcoes:
            produtos_sub = catalogo.obter_opcoes(caminho + [sub])
            if any(p in pendentes for p in produtos_sub):
                subs_com_pendentes.append(sub)

        if not subs_com_pendentes:
            await message.answer("✅ Todos os itens desta subcategoria já foram comprados!")
            caminho.pop()
            await state.update_data(caminho_compra=caminho)
            return await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados, cats_filtradas)

        btns = [[KeyboardButton(text=catalogo.formatar(s))] for s in subs_com_pendentes]
        btns.append([KeyboardButton(text="🔙 Voltar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await message.answer("Selecione a subcategoria:", reply_markup=kb)


# ─── QUANTIDADE E VALOR DURANTE COMPRA ────

@router.message(ListaState.compra_quantidade)
async def compra_qtd(message: types.Message, state: FSMContext):
    try:
        qtd = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Digite um número válido. Ex: 2 ou 1.5")
    await state.update_data(qtd_atual=qtd)
    await state.set_state(ListaState.compra_valor)
    await message.answer("💰 Qual o valor unitário? (Ex: 12.90)")

@router.message(ListaState.compra_valor)
async def compra_val(message: types.Message, state: FSMContext):
    try:
        valor = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Digite um valor válido. Ex: 12.90")

    data = await state.get_data()
    item = data["item_atual"]
    qtd = data["qtd_atual"]
    caminho = data.get("caminho_compra", [])
    itens_lista = data.get("itens_lista", [])
    itens_comprados = data.get("itens_comprados", [])
    itens_comprados_detalhe = data.get("itens_comprados_detalhe", [])
    cats_filtradas = data.get("cats_filtradas", [])

    await database.adicionar_ao_carrinho(message.from_user.id, item, qtd, valor)
    itens_comprados.append(item)
    itens_comprados_detalhe.append({"nome": item, "quantidade": qtd, "valor_unitario": valor})

    await state.update_data(
        itens_comprados=itens_comprados,
        itens_comprados_detalhe=itens_comprados_detalhe
    )
    await state.set_state(ListaState.compra_navegando)

    pendentes = [i for i in itens_lista if i not in itens_comprados]
    await extrato_carrinho(message)
    await message.answer(f"📋 Ainda faltam *{len(pendentes)}* itens da lista.", parse_mode="Markdown")

    await _mostrar_nivel_compra(message, state, caminho, itens_lista, itens_comprados, cats_filtradas)


# ─── NAVEGAÇÃO NO CATÁLOGO PARA ADICIONAR ITEM À LISTA ────

@router.message(ListaState.navegando_catalogo)
async def navegar_catalogo_lista(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])
    lista_atual = data.get("lista_atual")

    if message.text == "⬅️ Voltar":
        if not caminho:
            await state.set_state(ListaState.escolhendo_lista)
            listas = await database.pegar_listas_disponiveis()
            return await message.answer("Escolha a lista:", reply_markup=kb_lista_escolha(listas))
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = obter_opcoes_nivel(caminho)
        return await message.answer("Voltando...", reply_markup=kb_opcoes(opts, len(caminho) > 0))

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer(f"✅ Itens salvos em *{lista_atual}*!", reply_markup=kb_listas_menu(), parse_mode="Markdown")

    tipo, valor = catalogo.identificar_escolha(caminho, message.text)

    if tipo == "produto":
        await database.adicionar_item_lista(lista_atual, valor)
        opts = obter_opcoes_nivel(caminho)
        await message.answer(f"✅ *{valor}* adicionado!", reply_markup=kb_opcoes(opts, len(caminho) > 0), parse_mode="Markdown")

    elif tipo == "categoria":
        caminho.append(valor)
        await state.update_data(caminho=caminho)
        novas_opts = obter_opcoes_nivel(caminho)
        await message.answer(f"📂 {message.text}:", reply_markup=kb_opcoes(novas_opts))

    else:
        await message.answer("Opção inválida. Use o teclado do bot.")


# ─── REMOVER ITEM DA LISTA ────

@router.message(F.text == "🗑️ Remover Item")
async def cmd_remover(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas_disponiveis()
    if not listas:
        return await message.answer("Nenhuma lista criada ainda!", reply_markup=kb_listas_menu())
    await state.set_state(ListaState.escolhendo_lista_remover)
    await message.answer("De qual lista você quer remover um item?", reply_markup=kb_lista_escolha(listas))

@router.message(ListaState.escolhendo_lista_remover)
async def lista_para_remover(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    itens = await database.pegar_itens_da_lista(message.text)
    if not itens:
        await state.clear()
        return await message.answer("Essa lista está vazia!", reply_markup=kb_listas_menu())

    await state.set_state(ListaState.removendo_item)
    await state.update_data(lista_atual=message.text)

    btns = [[KeyboardButton(text=item)] for item in itens]
    btns.append([KeyboardButton(text="❌ Cancelar")])
    kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
    await message.answer(f"📋 *{message.text}* — Qual item deseja remover?", reply_markup=kb, parse_mode="Markdown")

@router.message(ListaState.removendo_item)
async def confirmar_remocao(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    data = await state.get_data()
    lista_atual = data.get("lista_atual")
    await database.remover_item_lista(lista_atual, message.text)

    itens = await database.pegar_itens_da_lista(lista_atual)
    if not itens:
        await state.clear()
        await message.answer(f"🗑️ *{message.text}* removido!\n\nA lista ficou vazia.", reply_markup=kb_listas_menu(), parse_mode="Markdown")
    else:
        btns = [[KeyboardButton(text=item)] for item in itens]
        btns.append([KeyboardButton(text="❌ Cancelar")])
        kb = ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)
        await message.answer(
            f"🗑️ *{message.text}* removido!\n\nRemova outro ou clique em ❌ Cancelar:",
            reply_markup=kb,
            parse_mode="Markdown"
        )