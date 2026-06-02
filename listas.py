from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import catalogo
import database

router = Router()

class ListaState(StatesGroup):
    criando_nome = State()
    escolhendo_lista = State()
    navegando_catalogo = State()
    compra_navegando = State()
    compra_quantidade = State()
    compra_valor = State()
    removendo_item = State()
    escolhendo_lista_remover = State()

def kb_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
        [KeyboardButton(text="📦 Ver Carrinho"), KeyboardButton(text="🏁 Finalizar")]
    ], resize_keyboard=True)

def kb_listas_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Nova Lista")],
        [KeyboardButton(text="📝 Adicionar Itens"), KeyboardButton(text="🚀 Iniciar Compra")],
        [KeyboardButton(text="🗑️ Remover Item"), KeyboardButton(text="⬅️ Menu Principal")]
    ], resize_keyboard=True)

def kb_opcoes(lista, voltar=True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar: btns.append([KeyboardButton(text="⬅️ Voltar")])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def kb_lista_escolha(listas):
    btns = [[KeyboardButton(text=l['nome'])] for l in listas]
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# --- HANDLERS ---
@router.message(F.text == "📋 Minhas Listas")
async def listas_main(message: types.Message):
    await message.answer("Gerenciar Listas:", reply_markup=kb_listas_menu())

@router.message(F.text == "⬅️ Menu Principal")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Menu Principal:", reply_markup=kb_menu())

@router.message(F.text == "➕ Nova Lista")
async def new_list(message: types.Message, state: FSMContext):
    await state.set_state(ListaState.criando_nome)
    await message.answer("Nome da lista:", reply_markup=ReplyKeyboardRemove())

@router.message(ListaState.criando_nome)
async def save_list(message: types.Message, state: FSMContext):
    await database.criar_lista(message.text)
    await state.clear()
    await message.answer(f"✅ Lista {message.text} criada!", reply_markup=kb_listas_menu())

@router.message(F.text == "📝 Adicionar Itens")
async def add_item_start(message: types.Message, state: FSMContext):
    listas = await database.pegar_listas()
    if not listas: return await message.answer("Crie uma lista primeiro!")
    await state.set_state(ListaState.escolhendo_lista)
    await state.update_data(acao="adicionar")
    await message.answer("Selecione a lista:", reply_markup=kb_lista_escolha(listas))

@router.message(ListaState.escolhendo_lista)
async def list_chosen(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Cancelado.", reply_markup=kb_listas_menu())

    await state.update_data(lista_nome=message.text)
    if data.get("acao") == "adicionar":
        await state.set_state(ListaState.navegando_catalogo)
        await state.update_data(caminho=[])
        opts = list(catalogo.CATALOGO.keys())
        await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, False))
    else:
        # Iniciar Compra
        itens = await database.pegar_itens_lista(message.text)
        if not itens: 
            await state.clear()
            return await message.answer("Lista vazia!", reply_markup=kb_listas_menu())
        await state.set_state(ListaState.compra_navegando)
        await state.update_data(itens_pendentes=itens, caminho=[])
        await message.answer(f"Iniciando compra: {message.text}", reply_markup=kb_opcoes(list(catalogo.CATALOGO.keys()), False))

@router.message(ListaState.navegando_catalogo)
async def nav_add(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])

    if message.text == "⬅️ Voltar":
        if not caminho:
            await state.set_state(ListaState.escolhendo_lista)
            l = await database.pegar_listas()
            return await message.answer("Escolha a lista:", reply_markup=kb_lista_escolha(l))
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = list(catalogo.CATALOGO.keys()) if not caminho else catalogo.obter_opcoes(caminho)
        return await message.answer("Selecione:", reply_markup=kb_opcoes(opts, len(caminho)>0))

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Finalizado.", reply_markup=kb_listas_menu())

    escolha = message.text.lower().replace(" ", "_")
    nova_lista = catalogo.obter_opcoes(caminho + [escolha])

    if not nova_lista: 
        await database.adicionar_item_lista(data['lista_nome'], message.text)
        await message.answer(f"✅ {message.text} adicionado à lista!")
    else:
        caminho.append(escolha)
        await state.update_data(caminho=caminho)
        await message.answer("Selecione:", reply_markup=kb_opcoes(nova_lista))