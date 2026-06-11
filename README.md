### compras_bot — README

#### Visão geral
Este repositório contém um bot de compras desenvolvido com aiogram (Telegram), usando um catálogo de produtos em JSON e um banco PostgreSQL para persistência. O bot suporta:
- Compra avulsa (adicionar itens livremente ao carrinho)
- Listas de compras (fixas ou temporárias)
- Finalização de compras com histórico
- Gerenciamento de orçamentos (criação/edição)
- Cadastros básicos (listas / itens)

---

### Funcionalidades principais
- Navegação de catálogo (categorias / subcategorias / produtos)
- Adição de itens ao carrinho com quantidade e valor unitário
- Gestão de listas (criar, adicionar itens, remover, iniciar compra a partir da lista)
- Criação e edição de orçamentos
- Histórico de compras persistido no banco de dados

---

### Arquitetura
- aiogram: handlers, FSM e keyboards (`main.py`, `listas.py`, `orcamentos.py`)
- database.py: inicialização e operações CRUD em PostgreSQL
- catalogo.py: carregamento e navegação no catálogo JSON
- arquivos JSON: catálogos por departamento (em ./assets ou pasta configurada)
- Orquestração: bot <-> catálogo <-> banco

---

### Requisitos
- Python 3.10+ (ou conforme requirements.txt)
- PostgreSQL acessível
- Variáveis de ambiente (ver seção abaixo)

---

### Instalação rápida (local)
1. Clone o repositório
2. Crie e ative um virtualenv
3. Instale dependências: pip install -r requirements.txt
4. Configure variáveis de ambiente (TOKEN do bot, string de conexão do PostgreSQL, etc.)
5. Inicialize banco (se houver script de migration) ou deixe o bot criar tabelas automaticamente na primeira execução

---

### Variáveis de ambiente (exemplo)
- BOT_TOKEN — token do Telegram
- DATABASE_URL — string de conexão com PostgreSQL (ex.: postgres://user:pass@host:5432/dbname)
- OUTRAS_VARIAVEIS — conforme usado no seu main.py

---

### Como rodar
No diretório do projeto:
python main.py

Ou use o método que você já tem (systemd, Docker, etc.) dependendo da configuração.

---

### Comandos e teclados principais
- /start — iniciar e escolher departamento
- Teclado principal (após escolher departamento):
  - Compras
  - Cadastros
  - Histórico
  - Orçamentos
  - Trocar Departamento

Teclas internas:
- Menu de Compras: Compra Avulsa, Minhas Listas, Ver Carrinho
- Carrinho: Remover Item, Limpar Carrinho, Finalizar Compra
- Listas: Nova Lista, Adicionar Itens, Remover Item
- Orçamentos: Novo orçamento, Editar orçamento

---

### Fluxograma completo (texto detalhado)
Abaixo segue o fluxograma em formato textual e muito explicado. Cada nó traz:
- O que o usuário vê
- Botões/teclados esperados
- Entrada esperada
- Próxima(s) ação(ões)
- Estado/FSM relacionado
- Ações no banco ou catálogo

#### Legenda rápida
- Nodo: Título (o que o usuário vê)
- Botões: teclados/inline buttons esperados
- Entrada: o que o usuário digita ou seleciona
- Próximo(s): para onde o fluxo vai
- Estado/FSM: nome do State no código
- DB/ação: operações importantes

---

#### 1) Start
- Nodo: `/start`
- Botões: seleção de departamento (botões)
- Entrada: usuário escolhe um departamento
- Próximo: Escolher Departamento -> Menu Principal
- Estado/FSM: MainState.departamento (inicial)
- DB/ação: carregar catálogo do departamento

#### 2) Escolher Departamento
- Nodo: Escolher Departamento
- Botões: botões com nomes dos departamentos
- Entrada: seleção de departamento
- Próximo: Menu Principal
- Estado/FSM: MainState.departamento
- DB/ação: possivelmente criar departamento ou importar catálogo

#### 3) Menu Principal
- Nodo: Menu Principal
- Botões: Compras | Cadastros | Histórico | Orçamentos | Trocar Departamento
- Entrada: escolha do usuário
- Próximo: ramo correspondente
- Estado/FSM: MainState.menu_principal

---

#### 4) Compras (ramo)
- Nodo: Menu de Compras
- Botões: Compra Avulsa | Minhas Listas | Ver Carrinho | Voltar
- Estados: MainState ou ShopState (para Compra Avulsa)

4.1) Compra Avulsa
- Nodo: Navegar catálogo livremente
- Botões/Entrada: navegação de categorias; ao escolher produto -> pergunta quantidade -> pergunta valor unitário
- Próximo: adicionar ao carrinho; mostrar extrato; voltar a navegar ou ver carrinho
- FSM: ShopState (quantidade -> valor)
- DB/ação: identificar produto via catalogo.py; adicionar ao carrinho (sessão/DB)

Fluxo detalhe:
- Selecionar produto -> Digite quantidade (validar inteiro>0) -> Digite valor unitário (validar decimal>0) -> Adicionar ao carrinho -> Mostrar extrato -> voltar ou finalizar

4.2) Minhas Listas
- Nodo: Listas do usuário
- Botões: selecionar lista | criar nova | voltar
- FSM: ListaState (criar, editar, iniciar compra)
- Operações:
  - Criar nova: tipo (fixa/temporária) -> nome -> salvar no DB
  - Adicionar itens: navegar catálogo modo "adicionar à lista" -> gravar item em lista
  - Iniciar compra: para cada item da lista, pedir quantidade e valor e adicionar ao carrinho

4.3) Ver Carrinho
- Nodo: Exibir carrinho
- Botões: Remover Item | Limpar Carrinho | Finalizar Compra | Voltar
- Operações:
  - Remover item: seleção -> remover
  - Limpar carrinho: confirmar -> limpar
  - Finalizar compra: pedir nome do mercado -> confirmar -> salvar em histórico -> limpar carrinho
- DB/ação: salvar_historico(), gravar itens e total

---

#### 5) Cadastros
- Nodo: Cadastros
- Botões: Gerenciar Listas (principal)
- Ações:
  - Nova lista: selecionar tipo -> nome -> salvar no DB
  - Adicionar itens: navegar catálogo -> adicionar à lista
  - Remover item: selecionar item -> confirmar -> remover
- FSM: ListaState
- DB/ação: tabelas de listas + itens

---

#### 6) Orçamentos
- Nodo: Menu de Orçamentos
- Botões: Novo orçamento | Editar orçamento | Ver histórico
- FSM: OrcState

Criar novo orçamento:
1. Tipo loja (Física / E-commerce)
2. Nome loja
3. Descrição/link
4. Selecionar lista ou navegar catálogo
5. Selecionar categoria/subcategoria/produto
6. Quantidade
7. Valor unitário
8. Adicionar outro / finalizar
9. Ao finalizar -> criar_orcamento() salva orçamento + itens no DB

Editar orçamento:
- Incluir item | Excluir item | Editar item (cada ação atualiza DB)

---

#### 7) Histórico
- Nodo: Histórico de compras
- Botões: listar compras por data | ver detalhes
- Ação: selecionar compra -> ver itens e total
- FSM: MainState.historico
- DB/ação: leitura da tabela histórico

---

#### 8) Trocar Departamento
- Nodo: Trocar Departamento
- Ação: reabre seleção de departamento, recarrega catálogo
- Observação: sempre recarregar catálogo associado ao novo departamento

---

#### 9) Utilitários e comportamentos comuns
- Voltar ao menu: botão presente em vários pontos
- Confirmações: antes de operações destrutivas (limpar carrinho, excluir item, finalizar)
- Validações: quantidade e valor obrigatoriamente numéricos e positivos
- Timeout/estado inconsistente: limpar estado e retornar ao menu principal

---

### Mapeamento dos FSMs / Handlers por arquivo
- main.py
  - MainState: seleção de departamento, menu, carrinho, histórico
  - ShopState: compra avulsa
  - Keyboards: kb_menu, kb_departamentos, kb_carrinho
- listas.py
  - ListaState: criação/edição/iniciar compra de listas
  - Keyboards: kb_listas_menu, kb_tipo_lista, kb_opcoes
- catalogo.py
  - carregar_catalogo_dep, obter_opcoes, identificar_escolha, formatar_extrato
- orcamentos.py
  - OrcState: criação/edição de orçamentos
  - Funções DB locais: criar_orcamento, adicionar_item_orc, listar_orcamentos
- database.py
  - Inicialização das tabelas e operações CRUD (departamentos, categorias, produtos, listas, itens, carrinho, histórico)
  - importar_catalogo_para_departamento()

---
