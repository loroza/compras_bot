```mermaid
flowchart TB

  A["/start"] --> escolherDept[Escolher Departamento]
  escolherDept --> menuPrincipal{Menu Principal}
  menuPrincipal --> compras[Compras]
  menuPrincipal --> cadastros[Cadastros]
  menuPrincipal --> historico[Histórico]
  menuPrincipal --> orcamentos[Orçamentos]
  menuPrincipal --> trocarDept[Trocar Departamento]