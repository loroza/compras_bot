import asyncio
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

import database
import catalogo

load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

class ShopState(StatesGroup):
    navegando = State()
    quantidade = State()
    valor = State()

# --- AUXILIARES ---
def kb_opcoes(lista, voltar=True):
    btns = [[KeyboardButton(text=catalogo.formatar(opt))] for opt in lista]
    if voltar: btns.append([KeyboardButton(text="⬅️ Voltar")])
    btns.append([KeyboardButton(text="❌ Cancelar")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def kb_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Compra Avulsa"), KeyboardButton(text="📋 Minhas Listas")],
        [KeyboardButton(text="📦 Ver Carrinho"), KeyboardButton(text="🏁 Finalizar")]
    ], resize_keyboard=True)

# --- HANDLERS ---
@dp.message(CommandStart())
async def start(message: types.Message):
    await database.init_db()
    await message.answer("🛒 Bot de Compras pronto!", reply_markup=kb_menu())

@dp.message(F.text == "🛒 Compra Avulsa")
async def start_buy(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.navegando)
    await state.update_data(caminho=[])
    opts = list(catalogo.CATALOGO.keys())
    await message.answer("Escolha a categoria:", reply_markup=kb_opcoes(opts, False))

@dp.message(ShopState.navegando)
async def navegar(message: types.Message, state: FSMContext):
    data = await state.get_data()
    caminho = data.get("caminho", [])

    if message.text == "⬅️ Voltar":
        if not caminho:
            await state.clear()
            return await message.answer("Menu Principal:", reply_markup=kb_menu())
        caminho.pop()
        await state.update_data(caminho=caminho)
        opts = list(catalogo.CATALOGO.keys()) if not caminho else catalogo.obter_opcoes(caminho)
        return await message.answer("Voltando...", reply_markup=kb_opcoes(opts, len(caminho) > 0))

    if message.text == "❌ Cancelar":
        await state.clear()
        return await message.answer("Operação cancelada.", reply_markup=kb_menu())

    escolha = message.text.lower().replace(" ", "_")
    nova_lista = catalogo.obter_opcoes(caminho + [escolha])

    if not nova_lista: 
        await state.update_data(produto=message.text)
        await state.set_state(ShopState.quantidade)
        await message.answer(f"Quanto de {message.text}?", reply_markup=types.ReplyKeyboardRemove())
    else:
        caminho.append(escolha)
        await state.update_data(caminho=caminho)
        await message.answer("Selecione:", reply_markup=kb_opcoes(nova_lista))

@dp.message(ShopState.quantidade)
async def set_qtd(message: types.Message, state: FSMContext):
    try:
        qtd = float(message.text.replace(",", "."))
        await state.update_data(qtd=qtd)
        await state.set_state(ShopState.valor)
        await message.answer("Qual o valor unitário? (Ex: 5.50)")
    except:
        await message.answer("Por favor, digite um número.")

@dp.message(ShopState.valor)
async def set_valor(message: types.Message, state: FSMContext):
    try:
        valor = float(message.text.replace(",", "."))
        data = await state.get_data()
        await database.adicionar_ao_carrinho(data['produto'], data['qtd'], valor, message.from_user.id)
        await state.clear()
        await message.answer(f"✅ {data['produto']} adicionado!", reply_markup=kb_menu())
    except:
        await message.answer("Valor inválido.")

@dp.message(F.text == "📦 Ver Carrinho")
async def ver_carrinho(message: types.Message):
    itens = await database.pegar_carrinho()
    if not itens:
        return await message.answer("Carrinho vazio!")
    
    texto = "🛒 **Carrinho Atual:**\n\n"
    total_geral = 0
    for item in itens:
        sub = item['quantidade'] * item['valor_unitario']
        total_geral += sub
        texto += f"• {item['item_nome']}: {item['quantidade']}x R${item['valor_unitario']:.2f} = R${sub:.2f}\n"
    
    texto += f"\n💰 **TOTAL: R${total_geral:.2f}**"
    await message.answer(texto)

async def main():
    # Importação dentro da função para evitar loops de importação
    from listas import router as listas_router
    dp.include_router(listas_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())