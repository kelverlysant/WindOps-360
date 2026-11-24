# WindOps 360

**Inteligência para manutenção e performance de parques eólicos.**

O WindOps 360 transforma registros de falhas e manutenções em indicadores operacionais (disponibilidade, MTTR, MTBF) e financeiros (energia não gerada e impacto em R$), e aponta quais turbinas devem receber atenção primeiro.

> ⚠️ Projeto de portfólio. Todos os dados são **sintéticos** e o preço de R$ 250/MWh é uma premissa didática, não uma cotação de mercado.

![Visão geral](docs/01_visao_geral.png)

---

## Perguntas que o sistema responde

| Pergunta | Onde |
|---|---|
| Qual parque tem pior disponibilidade? | `GET /financials/summary?level=farm` · aba *Visão executiva* |
| Quais componentes falham mais? | `GET /overview` · gráfico *Falhas por componente* |
| Quanto tempo a equipe leva para reparar? | MTTR em `GET /kpis/turbines` |
| Quanta energia deixou de ser produzida e quanto isso custou? | `GET /financials/monthly` |
| Quais turbinas devem ser priorizadas? | `GET /ranking` · aba *Priorização* |
| O que precisa de atenção agora? | `GET /alerts` · aba *Alertas* |

---

## Dashboard

| Aba | O que mostra |
|---|---|
| **Visão geral** | Um briefing em uma frase (quanto as paradas custaram e por qual turbina começar), indicadores comparados com o período anterior, energia não gerada mês a mês com a temporada de ventos fortes destacada, disponibilidade por parque contra a meta, mapa de onde está o prejuízo e gráfico de Pareto dos componentes |
| **Raio-X da turbina** | Turbina animada que mostra dados, as turbinas do mesmo parque lado a lado, linha do tempo de todas as paradas, comparação com a média da frota, energia perdida por mês e a decomposição do índice de criticidade ("por que ela é crítica") |
| **Falhas** | Mapa de calor mês × componente, filtros, exportação em CSV, registro de novas falhas e encerramento de falhas abertas |
| **Manutenções** | Preventivas × corretivas por mês, carga de horas por técnico e histórico |
| **Priorização** | Ranking com a contribuição de cada fator, gráfico frequência × tempo de reparo e tabela exportável |
| **Alertas** | Falhas abertas, disponibilidade abaixo da meta, reparos lentos e falhas recorrentes, com regras explícitas |

### Turbinas animadas

A animação do Raio-X carrega informação:

- **Turbina selecionada:** o rotor gira na proporção do vento médio do parque no período (abaixo do *cut-in*, fica parado).
- **Turbinas do mesmo parque:** cada rotor gira conforme a própria disponibilidade. Quanto mais horas parada, mais devagar.
- **Falha em aberto no fim do período:** rotor parado e luz vermelha na nacele. A luz fica âmbar quando a disponibilidade está abaixo da meta e verde quando a turbina opera normalmente.

As turbinas são SVGs com a animação em CSS dentro do próprio arquivo. Quem desativa animações no sistema (`prefers-reduced-motion`) vê as turbinas paradas.

Na barra lateral, o usuário escolhe a empresa, o período, o preço da energia e a meta de disponibilidade.

| Raio-X da turbina | Priorização |
|---|---|
| ![Raio-X](docs/02_raio_x_turbina.png) | ![Priorização](docs/03_priorizacao.png) |

| Alertas | Manutenções |
|---|---|
| ![Alertas](docs/04_alertas.png) | ![Manutenções](docs/05_manutencoes.png) |

---

## Arquitetura

```mermaid
flowchart LR
    G[Gerador de dados sintéticos] -->|seed| DB[(PostgreSQL)]
    DB --> R[Repositório<br/>SQLAlchemy]
    R --> C[Núcleo analítico<br/>KPIs · energia · criticidade]
    C --> API[FastAPI]
    API --> D[Dashboard Streamlit]
```

O **núcleo analítico** (`windops/core`) é Python puro, sem dependência de banco ou framework. A API e o dashboard só consomem esse núcleo, então toda tela mostra números calculados pelas mesmas regras, e as regras podem ser testadas isoladamente.

| Camada | Tecnologia |
|---|---|
| Regras de negócio | Python 3.11+ (dataclasses, enums) |
| Persistência | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| API | FastAPI, Pydantic v2 (documentação OpenAPI em `/docs`) |
| Interface | Streamlit, Plotly, fonte Barlow embutida |
| Qualidade | pytest (78 testes), ruff, GitHub Actions |
| Infraestrutura | Docker, Docker Compose |

---

## Como rodar

### Opção 1 — Docker (recomendado)

```bash
docker compose up --build
```

- Dashboard: http://localhost:8501
- API e documentação interativa: http://localhost:8000/docs

Na primeira subida, o container da API aplica as migrations e carrega os dados sintéticos automaticamente.

### Opção 2 — Local (Windows / PowerShell)

Sem Docker, o projeto usa SQLite por padrão, sem nenhuma configuração.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

alembic upgrade head
python -m windops.db.seed

# terminal 1
uvicorn windops.api.main:app --reload

# terminal 2 (na raiz do projeto, para carregar o tema)
streamlit run windops/dashboard/app.py
```

Para usar PostgreSQL localmente, defina a variável antes dos comandos:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:senha@localhost:5432/windops"
```

### Testes

```powershell
pytest -q
ruff check .
```

---

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/companies` | Empresas (tenants) |
| GET | `/windfarms?company_id=` | Parques |
| GET | `/turbines?company_id=&farm_id=` | Turbinas |
| GET | `/failures?company_id=&turbine_id=&component=&state=open&start=&end=` | Falhas |
| POST | `/failures` | Registrar falha (aberta ou fechada) |
| PATCH | `/failures/{id}/close` | Encerrar falha aberta |
| GET | `/maintenances?company_id=&type=&start=&end=` | Manutenções |
| POST | `/maintenances` | Registrar manutenção (corretiva exige `failure_id` da mesma turbina) |
| GET | `/kpis/turbines` | Disponibilidade, MTTR, MTBF, energia perdida, R$ e criticidade por turbina |
| GET | `/financials/summary?level=company\|farm` | Perdas agregadas |
| GET | `/financials/monthly` | Perdas por mês e empresa |
| GET | `/ranking?by=criticality\|loss&limit=` | Turbinas prioritárias |
| GET | `/overview` | Números da visão executiva |
| GET | `/alerts?availability_target=0.97` | Alertas priorizados (críticos primeiro) |

Os endpoints analíticos aceitam `company_id`, `start`, `end` (janela `[start, end)`) e `price` (R$/MWh).

---

## Regras de negócio

### Indisponibilidade sem contagem dupla
Falhas sobrepostas na mesma turbina são unidas antes de qualquer cálculo:

```
Falha A: 08h ───────── 16h
Falha B:       12h ───────── 18h
Parada real: 10h (não 14h)
```

Falhas que atravessam o fim do período são cortadas na janela. Falhas abertas contam até o fim da janela.

### Indicadores
- **Disponibilidade** = (horas do período − horas paradas) / horas do período. A manutenção preventiva é tratada como parada planejada e fica fora do cálculo.
- **MTTR** = duração média das falhas *encerradas* que começaram no período.
- **MTBF** = horas operando / número de falhas que começaram no período.

### Vento e curva de potência
- O vento é simulado **hora a hora** com uma distribuição de Weibull (k = 2), cuja média segue um perfil sazonal inspirado no Nordeste brasileiro, com pico entre agosto e outubro.
- Aplicar a curva de potência sobre a média mensal subestimaria a energia, porque a relação é cúbica. Por isso a simulação é horária.
- Curva: zero abaixo do *cut-in* (3 m/s), crescimento com v³ até o *rated* (12 m/s), potência nominal até o *cut-out* (25 m/s) e zero acima dele (desligamento por segurança).
- O vento é determinístico por parque e hora: os resultados são reproduzíveis.

### Energia perdida e impacto financeiro
Para cada hora parada: potência esperada × fração da hora em que a turbina estava parada. Uma parada das 10h00 às 10h30 conta meia hora.

```
Impacto (R$) = Energia não gerada (MWh) × Preço (R$/MWh)
```

### Índice de criticidade (0 a 100)
Combina quatro sinais normalizados (min-max) entre as turbinas comparadas:

| Sinal | Peso |
|---|---|
| Impacto financeiro | 40% |
| Número de falhas | 25% |
| Horas paradas | 20% |
| MTTR | 15% |

É uma medida **relativa**: só faz sentido dentro do grupo filtrado. A API devolve também quantos pontos cada fator contribuiu (`criticality_breakdown`), o que torna o índice explicável.

### Alertas

| Alerta | Atenção | Crítico |
|---|---|---|
| Falha aberta | enquanto estiver aberta | após 72 h sem reparo |
| Disponibilidade | abaixo da meta (padrão 97%) | 2 p.p. abaixo da meta |
| Reparo lento | MTTR acima de 1,5× a média da frota | — |
| Falha recorrente | mesmo componente falhando 3 vezes em 90 dias | — |

### Multiempresa
Todas as consultas aceitam `company_id`, e há testes garantindo que dados de uma empresa não aparecem no filtro de outra. Isso **ainda não é** isolamento de segurança: falta autenticação (veja o roadmap).

---

## Dados sintéticos

`python -m windops.db.seed` gera, com semente fixa:

- 2 empresas (AeroVento e Ventus), 2 parques cada e 3 turbinas por parque;
- 24 meses de histórico (jan/2024 a dez/2025);
- turbinas de 2,1 a 4,2 MW com idade entre 1 e 10 anos;
- falhas como processo de Poisson, com taxa que cresce com a idade;
- componente sorteado com pesos, causa coerente com o componente e duração conforme o componente (sensor: 2–12 h; caixa multiplicadora: 72–336 h);
- manutenção corretiva para cada falha encerrada e preventiva a cada ~180 dias.

Todos os horários são considerados no fuso local do parque.

---

## Estrutura

```
windops/
├── core/            # regras de negócio em Python puro
│   ├── entities.py      # Company, WindFarm, Turbine, Failure, Maintenance, Dataset
│   ├── intervals.py     # união e recorte de intervalos
│   ├── kpis.py          # disponibilidade, MTTR, MTBF
│   ├── wind.py          # vento horário e curva de potência
│   ├── financials.py    # energia perdida e R$
│   ├── criticality.py   # índice de criticidade e decomposição
│   ├── alerts.py        # regras de alerta
│   ├── analytics.py     # relatórios consolidados
│   └── generator.py     # dados sintéticos
├── db/              # SQLAlchemy, repositório e seed
├── api/             # FastAPI: rotas, schemas, dependências
└── dashboard/       # Streamlit
    ├── app.py           # filtros e abas
    ├── views.py         # uma função por aba
    ├── charts.py        # gráficos Plotly
    ├── components.py    # briefing, faixa de indicadores, alertas
    ├── theme.py         # paleta, CSS e formatação pt-BR
    └── static/fonts/    # Barlow (SIL Open Font License)
.streamlit/          # tema do dashboard
alembic/             # migrations
tests/               # pytest
```

---

## Roadmap

- [x] Núcleo Python: entidades, dados sintéticos, KPIs, energia, impacto financeiro, criticidade
- [x] PostgreSQL + SQLAlchemy + Alembic
- [x] API FastAPI
- [x] Dashboard Streamlit
- [x] Alertas operacionais
- [x] Docker e CI
- [ ] Autenticação (JWT), perfis e isolamento obrigatório por tenant
- [ ] Notificações de alertas por e-mail ou WhatsApp
- [ ] Importação de dados reais por CSV e preço de energia por cliente
- [ ] Exportação de relatórios em PDF/Excel
- [ ] Deploy em nuvem
- [ ] Detecção de anomalias com dados SCADA (temperatura, vibração, potência)

## Limitações conhecidas
- Dados e vento são simulados. O modelo não considera direção do vento, densidade do ar, esteira entre turbinas ou *curtailment*.
- A curva de potência é simplificada (cúbica entre o *cut-in* e o *rated*), e não a curva certificada de um fabricante.
- A criticidade usa pesos fixos. Numa operação real, eles deveriam ser calibrados com a equipe de O&M.
