/* ==========================================================================
   APP.JS - CONTROLE DE CNDS (SUPABASE REALTIME CONTROLLER)
   ========================================================================== */

let supabaseClient = null;
let empresasData = [];
let certidoesData = [];
let filaData = [];
let editingEmpresaId = null;

// Elementos do DOM
const dom = {
    screenDashboard: document.getElementById('screen-dashboard'),
    screenEmpresas: document.getElementById('screen-empresas'),
    screenFila: document.getElementById('screen-fila'),
    
    btnNavDashboard: document.getElementById('btn-nav-dashboard'),
    btnNavEmpresas: document.getElementById('btn-nav-empresas'),
    btnNavFila: document.getElementById('btn-nav-fila'),
    
    themeToggleBtn: document.getElementById('theme-toggle-btn'),
    
    valTotalEmpresas: document.getElementById('val-total-empresas'),
    valCndRegular: document.getElementById('val-cnd-regular'),
    valCndAtencao: document.getElementById('val-cnd-atencao'),
    valRpaFila: document.getElementById('val-rpa-fila'),
    
    cndTbody: document.getElementById('cnd-tbody'),
    empresasTbody: document.getElementById('empresas-tbody'),
    filaTbody: document.getElementById('fila-tbody'),
    
    filterSearch: document.getElementById('filter-search'),
    filterTipo: document.getElementById('filter-tipo'),
    filterStatus: document.getElementById('filter-status'),
    
    btnTriggerCron: document.getElementById('btn-trigger-cron'),
    btnAddEmpresa: document.getElementById('btn-add-empresa'),
    modalEmpresa: document.getElementById('modal-empresa'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    formEmpresa: document.getElementById('form-empresa'),
    btnCancelarCadastro: document.getElementById('btn-cancelar-cadastro'),
    toastContainer: document.getElementById('toast-container')
};

// ==========================================
// 1. CARREGAMENTO E CONFIGURAÇÃO DO SUPABASE
// ==========================================

async function inicializarSupabase() {
    // 1. Tentar carregar do LocalStorage
    let url = localStorage.getItem('SUPABASE_URL');
    let key = localStorage.getItem('SUPABASE_KEY');
    
    // 2. Se não houver, tentar buscar o arquivo .env no workspace
    if (!url || !key) {
        try {
            const response = await fetch('../.env');
            if (response.ok) {
                const text = await response.text();
                const env = parseEnvText(text);
                url = env.SUPABASE_URL;
                key = env.SUPABASE_KEY;
                
                if (url && key) {
                    localStorage.setItem('SUPABASE_URL', url);
                    localStorage.setItem('SUPABASE_KEY', key);
                    showToast('Configurações carregadas do arquivo .env com sucesso!', 'success');
                }
            }
        } catch (e) {
            console.log('Não foi possível ler o arquivo .env diretamente (CORS/file://).');
        }
    }

    // 3. Se ainda assim não houver chaves, solicitar ao usuário
    if (!url || !key) {
        solicitarCredenciais();
        return false;
    }

    try {
        supabaseClient = supabase.createClient(url, key);
        return true;
    } catch (err) {
        showToast('Erro ao criar cliente Supabase: ' + err.message, 'error');
        localStorage.clear();
        setTimeout(() => location.reload(), 3000);
        return false;
    }
}

function parseEnvText(text) {
    const env = {};
    const lines = text.split('\n');
    lines.forEach(line => {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
            const parts = trimmed.split('=');
            if (parts.length >= 2) {
                const key = parts[0].trim();
                const value = parts.slice(1).join('=').trim().replace(/['"]/g, '');
                env[key] = value;
            }
        }
    });
    return env;
}

function solicitarCredenciais() {
    // Inserir modal de configuração se as chaves do Supabase não forem localizadas
    const setupHtml = `
        <div class="modal-overlay active" id="modal-setup-supabase">
            <div class="modal-card" style="width: 450px;">
                <div class="modal-header">
                    <h3>Conectar ao Supabase</h3>
                </div>
                <form id="form-setup" class="modal-form">
                    <div style="display: flex; flex-direction: column; gap: 14px;">
                        <p style="font-size: 13px; color: var(--text-muted); line-height: 1.4;">
                            Não localizamos as credenciais do seu Supabase no .env ou localmente. Preencha abaixo para conectar o painel:
                        </p>
                        <div class="form-group">
                            <label for="setup-url">URL do Projeto</label>
                            <input type="url" id="setup-url" required placeholder="https://xxxx.supabase.co">
                        </div>
                        <div class="form-group">
                            <label for="setup-key">Chave de Acesso (Anon ou Service Role)</label>
                            <input type="password" id="setup-key" required placeholder="eyJhbGciOiJIUzI1NiIsIn...">
                        </div>
                    </div>
                    <div class="modal-footer" style="margin-top: 20px;">
                        <button type="submit" class="btn btn-primary" style="width: 100%; justify-content: center;">Conectar e Salvar</button>
                    </div>
                </form>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', setupHtml);
    
    document.getElementById('form-setup').addEventListener('submit', (e) => {
        e.preventDefault();
        const url = document.getElementById('setup-url').value.trim();
        const key = document.getElementById('setup-key').value.trim();
        
        localStorage.setItem('SUPABASE_URL', url);
        localStorage.setItem('SUPABASE_KEY', key);
        
        location.reload();
    });
}

// ==========================================
// 2. BUSCA DE DADOS E RENDERIZAÇÃO
// ==========================================

async function carregarDados() {
    if (!supabaseClient) return;

    try {
        // Busca paralela das tabelas
        const [empresasRes, certidoesRes, filaRes] = await Promise.all([
            supabaseClient.from('empresas').select('*').order('apelido'),
            supabaseClient.from('certidoes_matriz').select('*, empresas(*)'),
            supabaseClient.from('fila_execucao').select('*, certidoes_matriz(*, empresas(*))').order('data_agendamento', { ascending: false })
        ]);

        if (empresasRes.error) throw empresasRes.error;
        if (certidoesRes.error) throw certidoesRes.error;
        if (filaRes.error) throw filaRes.error;

        empresasData = empresasRes.data;
        certidoesData = certidoesRes.data;
        filaData = filaRes.data;

        atualizarKPIs();
        renderizarTabelas();
    } catch (err) {
        showToast('Erro ao carregar dados do Supabase: ' + err.message, 'error');
        console.error(err);
    }
}

function atualizarKPIs() {
    dom.valTotalEmpresas.textContent = empresasData.length;
    
    // Certidões Regulares
    const regulares = certidoesData.filter(c => c.status === 'Regular').length;
    dom.valCndRegular.textContent = regulares;
    
    // Exigem atenção ou vencidas
    const atencao = certidoesData.filter(c => c.status === 'Vencida' || c.status === 'Erro' || c.status === 'Atenção').length;
    dom.valCndAtencao.textContent = atencao;
    
    // Fila pendente/processando
    const na_fila = filaData.filter(f => f.status === 'pendente' || f.status === 'processando').length;
    dom.valRpaFila.textContent = na_fila;
    
    // Animação no spinner da fila
    const spinner = dom.valRpaFila.closest('.kpi-card').querySelector('.kpi-icon i');
    if (na_fila > 0) {
        spinner.className = 'fa-solid fa-spinner fa-spin';
    } else {
        spinner.className = 'fa-solid fa-circle-notch';
    }
}

function renderizarTabelas() {
    renderizarDashboardTable();
    renderizarEmpresasTable();
    renderizarFilaTable();
}

function renderizarDashboardTable() {
    const query = dom.filterSearch.value.toLowerCase();
    const tipo = dom.filterTipo.value;
    const status = dom.filterStatus.value;
    
    let filtered = certidoesData.filter(c => {
        const empresa = c.empresas || {};
        const queryClean = query.replace(/\D/g, '');
        const matchQuery = (empresa.razao_social || '').toLowerCase().includes(query) ||
                           (empresa.apelido || '').toLowerCase().includes(query) ||
                           (queryClean && (empresa.cnpj || '').includes(queryClean));
                           
        const matchTipo = tipo === 'ALL' || c.tipo_certidao === tipo;
        const matchStatus = status === 'ALL' || c.status === status;
        
        return matchQuery && matchTipo && matchStatus;
    });

    if (filtered.length === 0) {
        dom.cndTbody.innerHTML = `<tr><td colspan="7" class="loading-state">Nenhuma certidão localizada com os filtros ativos.</td></tr>`;
        return;
    }

    dom.cndTbody.innerHTML = filtered.map(c => {
        const empresa = c.empresas || {};
        const statusBadge = getStatusBadge(c.status);
        const formatDataEmissao = c.data_emissao ? formatarData(c.data_emissao) : '-';
        const formatDataVencimento = c.data_vencimento ? formatarData(c.data_vencimento) : '-';
        
        const isVencida = c.data_vencimento && new Date(c.data_vencimento) <= new Date();
        const dateStyle = isVencida && c.status !== 'Regular' ? 'style="color: var(--color-danger); font-weight: bold;"' : '';
        
        const pdfButton = c.url_pdf 
            ? `<a href="${c.url_pdf}" target="_blank" class="btn-icon" title="Ver CND PDF"><i class="fa-solid fa-file-pdf"></i></a>` 
            : `<button class="btn-icon" disabled style="opacity: 0.3;" title="PDF indisponível"><i class="fa-solid fa-file-pdf"></i></button>`;

        return `
            <tr>
                <td>
                    <div style="font-weight: 600; color: var(--text-active);">${empresa.apelido || 'Sem Apelido'}</div>
                    <div style="font-size: 12px; color: var(--text-muted);">${empresa.razao_social || ''}</div>
                </td>
                <td style="font-family: monospace;">${formatarCNPJ(empresa.cnpj || '')}</td>
                <td><span class="badge" style="background: rgba(255,255,255,0.05); color: var(--text-main);">${c.tipo_certidao}</span></td>
                <td>${statusBadge}</td>
                <td>${formatDataEmissao}</td>
                <td ${dateStyle}>${formatDataVencimento}</td>
                <td class="actions-col">
                    <div class="actions-cell-container">
                        ${pdfButton}
                        <button class="btn-icon btn-force-renew" data-matriz-id="${c.id}" title="Agendar Renovação">
                            <i class="fa-solid fa-arrows-rotate"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    // Adiciona evento aos botões de renovação manual
    document.querySelectorAll('.btn-force-renew').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const matrizId = btn.getAttribute('data-matriz-id');
            await agendarRenovacaoManual(matrizId);
        });
    });
}

function renderizarEmpresasTable() {
    if (empresasData.length === 0) {
        dom.empresasTbody.innerHTML = `<tr><td colspan="6" class="loading-state">Nenhuma empresa cadastrada.</td></tr>`;
        return;
    }

    dom.empresasTbody.innerHTML = empresasData.map(e => {
        return `
            <tr>
                <td style="font-weight: 600; color: var(--text-active);">${e.apelido}</td>
                <td>${e.razao_social}</td>
                <td style="font-family: monospace;">${formatarCNPJ(e.cnpj)}</td>
                <td>${e.municipio} - ${e.uf}</td>
                <td style="font-size: 13px;">
                    <div>IE: ${e.inscricao_estadual || '-'}</div>
                    <div>IM: ${e.inscricao_municipal || '-'}</div>
                </td>
                <td>
                    <button class="btn-icon btn-edit-empresa" data-id="${e.id}" style="color: var(--color-primary); margin-right: 8px;" title="Editar Empresa">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="btn-icon btn-delete-empresa" data-id="${e.id}" style="color: var(--color-danger);" title="Excluir Empresa">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    // Evento de edição de empresa
    document.querySelectorAll('.btn-edit-empresa').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.getAttribute('data-id');
            abrirModalEdicao(id);
        });
    });

    // Evento de exclusão de empresa
    document.querySelectorAll('.btn-delete-empresa').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            if (confirm('Deseja realmente excluir esta empresa e todo seu histórico de certidões?')) {
                try {
                    const { error } = await supabaseClient.from('empresas').delete().eq('id', id);
                    if (error) throw error;
                    showToast('Empresa excluída com sucesso!', 'success');
                    carregarDados();
                } catch (err) {
                    showToast('Erro ao excluir empresa: ' + err.message, 'error');
                }
            }
        });
    });
}

function renderizarFilaTable() {
    if (filaData.length === 0) {
        dom.filaTbody.innerHTML = `<tr><td colspan="6" class="loading-state">Fila de execução vazia no momento.</td></tr>`;
        return;
    }

    dom.filaTbody.innerHTML = filaData.map(f => {
        const matriz = f.certidoes_matriz || {};
        const empresa = matriz.empresas || {};
        const statusBadge = getFilaStatusBadge(f.status);
        const dataAgendada = formatarDataHora(f.data_agendamento);
        const erroLog = f.log_erro ? `<span style="font-family: monospace; font-size: 12px; color: var(--color-danger); display: block; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${f.log_erro}">${f.log_erro}</span>` : '<span style="color: var(--text-muted); font-size: 12px;">Nenhum erro</span>';

        return `
            <tr>
                <td style="font-family: monospace; font-size: 13px;">${dataAgendada}</td>
                <td>
                    <div style="font-weight: 500; color: var(--text-active);">${empresa.apelido || '-'}</div>
                    <div style="font-size: 11px; color: var(--text-muted);">${matriz.tipo_certidao || ''}</div>
                </td>
                <td>${statusBadge}</td>
                <td style="text-align: center;">${f.tentativas} / ${f.max_tentativas}</td>
                <td>${erroLog}</td>
                <td>
                    <button class="btn-icon btn-reset-fila" data-id="${f.id}" title="Re-processar (Pendente)" ${f.status === 'pendente' || f.status === 'processando' ? 'disabled style="opacity: 0.3;"' : ''}>
                        <i class="fa-solid fa-redo"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    // Evento de reset da fila
    document.querySelectorAll('.btn-reset-fila').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            try {
                const { error } = await supabaseClient.from('fila_execucao').update({
                    status: 'pendente',
                    tentativas: 0,
                    log_erro: 'Reiniciado manualmente via Dashboard.'
                }).eq('id', id);
                
                if (error) throw error;
                showToast('Fila reiniciada! Robô re-processará esta certidão.', 'success');
                carregarDados();
            } catch (err) {
                showToast('Erro ao reiniciar fila: ' + err.message, 'error');
            }
        });
    });
}

// ==========================================
// 3. EVENTOS DO SISTEMA E AUTOMAÇÕES
// ==========================================

async function agendarRenovacaoManual(matrizId) {
    try {
        // Verifica se a certidão já está na fila ativa
        const { data: existente, error: errExistente } = await supabaseClient
            .from('fila_execucao')
            .select('id, status')
            .eq('certidao_matriz_id', matrizId)
            .in('status', ['pendente', 'processando'])
            .maybeSingle();

        if (errExistente) throw errExistente;
        
        if (existente) {
            showToast('Esta certidão já está na fila com status ' + existente.status.toUpperCase(), 'info');
            return;
        }

        // Insere na fila de execução
        const { error } = await supabaseClient.from('fila_execucao').insert({
            certidao_matriz_id: matrizId,
            status: 'pendente',
            data_agendamento: new Date().toISOString()
        });

        if (error) throw error;
        
        // Atualiza a matriz para "Em Renovação"
        await supabaseClient.from('certidoes_matriz').update({
            status: 'Em Renovação',
            ultimo_log: 'Agendamento manual solicitado via Dashboard.'
        }).eq('id', matrizId);

        showToast('Sucesso! Job agendado para o worker RPA.', 'success');
        carregarDados();
    } catch (err) {
        showToast('Erro ao agendar renovação: ' + err.message, 'error');
    }
}

async function verificarVencimentos() {
    showToast('Executando verificação SQL de expiração...', 'info');
    try {
        // Força a inserção na fila de qualquer certidão vencida ou a expirar em 5 dias que não esteja na fila ativa
        // Replicando a lógica do Orquestrador de 28 dias
        const { data: pendentes, error: errP } = await supabaseClient
            .from('certidoes_matriz')
            .select('id, tipo_certidao, status, data_vencimento')
            .not('status', 'eq', 'Em Renovação');
            
        if (errP) throw errP;

        let inseridosCount = 0;
        for (const cnd of pendentes) {
            let expiraLogo = false;
            if (cnd.data_vencimento) {
                const diffTime = new Date(cnd.data_vencimento) - new Date();
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                // Dispara se expirar em até 5 dias, ou se estiver com erro/vencida
                if (diffDays <= 5 || cnd.status === 'Vencida' || cnd.status === 'Pendente') {
                    expiraLogo = true;
                }
            } else {
                expiraLogo = true; // Força geração se nunca foi emitida
            }

            if (expiraLogo) {
                // Checa se já está na fila pendente
                const { data: naFila } = await supabaseClient
                    .from('fila_execucao')
                    .select('id')
                    .eq('certidao_matriz_id', cnd.id)
                    .in('status', ['pendente', 'processando'])
                    .maybeSingle();

                if (!naFila) {
                    await supabaseClient.from('fila_execucao').insert({
                        certidao_matriz_id: cnd.id,
                        status: 'pendente'
                    });
                    
                    await supabaseClient.from('certidoes_matriz').update({
                        status: 'Pendente',
                        ultimo_log: 'Fila forçada devido a proximidade de expiração.'
                    }).eq('id', cnd.id);
                    
                    inseridosCount++;
                }
            }
        }

        if (inseridosCount > 0) {
            showToast(`${inseridosCount} renovações inseridas na fila de execução!`, 'success');
        } else {
            showToast('Nenhuma certidão precisa de renovação no momento.', 'info');
        }
        carregarDados();
    } catch (err) {
        showToast('Erro ao varrer vencimentos: ' + err.message, 'error');
    }
}

// ==========================================
// 4. SUPABASE REALTIME (TEMPO REAL)
// ==========================================

function configurarRealtime() {
    if (!supabaseClient) return;

    // Escuta alterações na Fila de Execução e atualiza tela instantaneamente
    supabaseClient
        .channel('db-fila-changes')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'fila_execucao' }, payload => {
            console.log('Alteração na fila recebida em realtime:', payload);
            carregarDados();
            
            if (payload.eventType === 'UPDATE') {
                const row = payload.new;
                if (row.status === 'sucesso') {
                    showToast('Processamento finalizado com sucesso pelo robô!', 'success');
                } else if (row.status === 'falha') {
                    showToast('Ocorreu um erro no processamento do robô.', 'error');
                }
            }
        })
        .subscribe();

    // Escuta alterações na Matriz de Certidões
    supabaseClient
        .channel('db-matriz-changes')
        .on('postgres_changes', { event: '*', schema: 'public', table: 'certidoes_matriz' }, payload => {
            console.log('Alteração na matriz recebida em realtime:', payload);
            carregarDados();
        })
        .subscribe();
}

// ==========================================
// 5. AUXILIARES DE FORMATAÇÃO E ELA-TELA
// ==========================================

function getStatusBadge(status) {
    switch (status) {
        case 'Regular':
            return `<span class="badge badge-regular"><i class="fa-solid fa-circle-check"></i> Regular</span>`;
        case 'Vencida':
            return `<span class="badge badge-vencida"><i class="fa-solid fa-triangle-exclamation"></i> Vencida</span>`;
        case 'Em Renovação':
            return `<span class="badge badge-renovacao"><i class="fa-solid fa-spinner fa-spin"></i> Em Renovação</span>`;
        case 'Erro':
            return `<span class="badge badge-erro"><i class="fa-solid fa-circle-xmark"></i> Erro Governamental</span>`;
        case 'Atenção':
            return `<span class="badge badge-erro"><i class="fa-solid fa-triangle-exclamation"></i> Pendência Fiscal</span>`;
        default:
            return `<span class="badge badge-pendente"><i class="fa-solid fa-clock"></i> Pendente</span>`;
    }
}

function getFilaStatusBadge(status) {
    switch (status) {
        case 'sucesso':
            return `<span class="badge badge-regular"><i class="fa-solid fa-check"></i> Sucesso</span>`;
        case 'falha':
            return `<span class="badge badge-vencida"><i class="fa-solid fa-xmark"></i> Falha</span>`;
        case 'processando':
            return `<span class="badge badge-renovacao"><i class="fa-solid fa-spinner fa-spin"></i> Processando</span>`;
        default:
            return `<span class="badge badge-pendente"><i class="fa-solid fa-clock"></i> Aguardando Fila</span>`;
    }
}

function formatarData(dataStr) {
    if (!dataStr) return '';
    const date = new Date(dataStr + 'T00:00:00');
    return date.toLocaleDateString('pt-BR');
}

function formatarDataHora(dataStr) {
    if (!dataStr) return '';
    const date = new Date(dataStr);
    return date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function formatarCNPJ(cnpj) {
    const limpo = cnpj.replace(/\D/g, '');
    if (limpo.length !== 14) return cnpj;
    return limpo.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = '<i class="fa-solid fa-info"></i>';
    if (type === 'success') icon = '<i class="fa-solid fa-circle-check"></i>';
    if (type === 'error') icon = '<i class="fa-solid fa-triangle-exclamation"></i>';
    
    toast.innerHTML = `
        ${icon}
        <span style="font-size: 13px; font-weight: 500;">${message}</span>
    `;
    
    dom.toastContainer.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ==========================================
// 6. INICIALIZAÇÃO E NAVEGAÇÃO
// ==========================================

function configurarNavegacao() {
    const screens = [
        { btn: dom.btnNavDashboard, screen: dom.screenDashboard, title: 'Painel Geral de CNDs', subtitle: 'Monitoramento em tempo real das certidões negativas do grupo empresarial.' },
        { btn: dom.btnNavEmpresas, screen: dom.screenEmpresas, title: 'Cadastro de Empresas/Filiais', subtitle: 'Gerenciamento dos CNPJs e cadastros das filiais do grupo de saúde.' },
        { btn: dom.btnNavFila, screen: dom.screenFila, title: 'Fila de Automação do RPA', subtitle: 'Acompanhamento em tempo real dos robôs de busca e agendamentos.' }
    ];

    screens.forEach(s => {
        s.btn.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Toggle active classes
            screens.forEach(x => {
                x.btn.classList.remove('active');
                x.screen.classList.remove('active');
            });
            
            s.btn.classList.add('active');
            s.screen.classList.add('active');
            
            document.getElementById('page-title').textContent = s.title;
            document.getElementById('page-subtitle').textContent = s.subtitle;
        });
    });
}

function configurarTema() {
    // Carregar tema preferido
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'light') {
        document.body.classList.remove('dark-mode');
        document.body.classList.add('light-mode');
        dom.themeToggleBtn.innerHTML = '<i class="fa-solid fa-moon"></i> <span>Modo Escuro</span>';
    }
    
    dom.themeToggleBtn.addEventListener('click', () => {
        if (document.body.classList.contains('dark-mode')) {
            document.body.classList.remove('dark-mode');
            document.body.classList.add('light-mode');
            dom.themeToggleBtn.innerHTML = '<i class="fa-solid fa-moon"></i> <span>Modo Escuro</span>';
            localStorage.setItem('theme', 'light');
        } else {
            document.body.classList.remove('light-mode');
            document.body.classList.add('dark-mode');
            dom.themeToggleBtn.innerHTML = '<i class="fa-solid fa-sun"></i> <span>Modo Claro</span>';
            localStorage.setItem('theme', 'dark');
        }
    });
}

function configurarSidebarToggle() {
    const btnToggle = document.getElementById('btn-sidebar-toggle');
    const container = document.querySelector('.app-container');
    const icon = btnToggle.querySelector('i');
    
    // Recupera o estado anterior do LocalStorage
    const collapsed = localStorage.getItem('sidebar-collapsed') === 'true';
    if (collapsed) {
        container.classList.add('collapsed');
        icon.className = 'fa-solid fa-chevron-right';
    }
    
    btnToggle.addEventListener('click', () => {
        const isCollapsed = container.classList.toggle('collapsed');
        localStorage.setItem('sidebar-collapsed', isCollapsed);
        
        // Altera o ícone da filipeta
        if (isCollapsed) {
            icon.className = 'fa-solid fa-chevron-right';
        } else {
            icon.className = 'fa-solid fa-chevron-left';
        }
    });
}
function abrirModalEdicao(id) {
    const empresa = empresasData.find(e => e.id == id);
    if (!empresa) return;

    editingEmpresaId = id;
    
    // Altera título e botão
    document.querySelector('#modal-empresa h3').textContent = 'Editar Empresa/Filial';
    document.querySelector('#modal-empresa button[type="submit"]').textContent = 'Salvar Alterações';
    
    // Preenche os campos
    document.getElementById('empresa-cnpj').value = empresa.cnpj;
    document.getElementById('empresa-cnpj').disabled = true; // Impede alterar o CNPJ de uma empresa existente
    document.getElementById('empresa-apelido').value = empresa.apelido;
    document.getElementById('empresa-razaosocial').value = empresa.razao_social;
    document.getElementById('empresa-uf').value = empresa.uf;
    document.getElementById('empresa-municipio').value = empresa.municipio;
    document.getElementById('empresa-ie').value = empresa.inscricao_estadual || '';
    document.getElementById('empresa-im').value = empresa.inscricao_municipal || '';
    
    // Configura os checkboxes baseados nas certidões ativas atualmente
    const activeTypes = certidoesData.filter(c => c.empresa_id === id).map(c => c.tipo_certidao);
    document.getElementById('cert-federal').checked = activeTypes.includes('FEDERAL');
    document.getElementById('cert-fgts').checked = activeTypes.includes('FGTS');
    document.getElementById('cert-cndt').checked = activeTypes.includes('CNDT');
    document.getElementById('cert-estadual').checked = activeTypes.includes('ESTADUAL');
    document.getElementById('cert-municipal').checked = activeTypes.includes('MUNICIPAL');
    
    dom.modalEmpresa.classList.add('active');
}

function configurarModais() {
    // Abertura
    dom.btnAddEmpresa.addEventListener('click', () => {
        editingEmpresaId = null;
        document.querySelector('#modal-empresa h3').textContent = 'Cadastrar Nova Empresa/Filial';
        document.querySelector('#modal-empresa button[type="submit"]').textContent = 'Salvar Empresa';
        document.getElementById('empresa-cnpj').disabled = false;
        
        // Reset checkboxes para default (ativo)
        document.getElementById('cert-federal').checked = true;
        document.getElementById('cert-fgts').checked = true;
        document.getElementById('cert-cndt').checked = true;
        document.getElementById('cert-estadual').checked = true;
        document.getElementById('cert-municipal').checked = true;
        
        dom.modalEmpresa.classList.add('active');
    });

    // Auto-preenchimento via CNPJ (BrasilAPI)
    const cnpjInput = document.getElementById('empresa-cnpj');
    let cnpjLookupTimeout = null;

    cnpjInput.addEventListener('input', () => {
        // Só busca em modo cadastro (não edição)
        if (editingEmpresaId) return;

        const cnpjLimpo = cnpjInput.value.replace(/\D/g, '');

        // Cancela qualquer busca anterior pendente
        if (cnpjLookupTimeout) {
            clearTimeout(cnpjLookupTimeout);
            cnpjLookupTimeout = null;
        }

        if (cnpjLimpo.length === 14) {
            // Pequeno debounce de 300ms para evitar chamadas desnecessárias
            cnpjLookupTimeout = setTimeout(() => buscarDadosCNPJ(cnpjLimpo), 300);
        }
    });

    async function buscarDadosCNPJ(cnpj) {
        const razaoInput = document.getElementById('empresa-razaosocial');
        const ufInput = document.getElementById('empresa-uf');
        const municipioInput = document.getElementById('empresa-municipio');

        // Feedback visual: indica que está buscando
        razaoInput.value = 'Buscando...';
        ufInput.value = '...';
        municipioInput.value = '...';
        razaoInput.disabled = true;
        ufInput.disabled = true;
        municipioInput.disabled = true;

        try {
            const response = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpj}`);
            
            if (!response.ok) {
                throw new Error(`CNPJ não encontrado (HTTP ${response.status})`);
            }
            
            const dados = await response.json();

            // Preenche os campos com os dados retornados
            razaoInput.value = dados.razao_social || '';
            ufInput.value = dados.uf || '';
            municipioInput.value = dados.municipio || '';

            showToast('Dados do CNPJ preenchidos automaticamente!', 'success');
        } catch (err) {
            console.warn('Erro ao buscar CNPJ na BrasilAPI:', err);
            razaoInput.value = '';
            ufInput.value = '';
            municipioInput.value = '';
            showToast('Não foi possível buscar os dados do CNPJ automaticamente. Preencha manualmente.', 'info');
        } finally {
            razaoInput.disabled = false;
            ufInput.disabled = false;
            municipioInput.disabled = false;
        }
    }
    
    // Fechamento
    const fecharModal = () => {
        dom.modalEmpresa.classList.remove('active');
        dom.formEmpresa.reset();
        document.getElementById('empresa-cnpj').disabled = false;
        editingEmpresaId = null;
        
        // Reset checkboxes
        document.getElementById('cert-federal').checked = true;
        document.getElementById('cert-fgts').checked = true;
        document.getElementById('cert-cndt').checked = true;
        document.getElementById('cert-estadual').checked = true;
        document.getElementById('cert-municipal').checked = true;
    };
    
    dom.btnCloseModal.addEventListener('click', fecharModal);
    dom.btnCancelarCadastro.addEventListener('click', fecharModal);
    
    // Envio do Formulário de Empresa
    dom.formEmpresa.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const cnpj = document.getElementById('empresa-cnpj').value.trim();
        const apelido = document.getElementById('empresa-apelido').value.trim();
        const razao_social = document.getElementById('empresa-razaosocial').value.trim();
        const uf = document.getElementById('empresa-uf').value.trim().toUpperCase();
        const municipio = document.getElementById('empresa-municipio').value.trim();
        const ie = document.getElementById('empresa-ie').value.trim();
        const im = document.getElementById('empresa-im').value.trim();

        if (cnpj.length !== 14) {
            showToast('CNPJ inválido! Precisa conter 14 dígitos.', 'error');
            return;
        }

        // Obter tipos de certidões selecionadas
        const tiposSelecionados = [];
        if (document.getElementById('cert-federal').checked) tiposSelecionados.push('FEDERAL');
        if (document.getElementById('cert-fgts').checked) tiposSelecionados.push('FGTS');
        if (document.getElementById('cert-cndt').checked) tiposSelecionados.push('CNDT');
        if (document.getElementById('cert-estadual').checked) tiposSelecionados.push('ESTADUAL');
        if (document.getElementById('cert-municipal').checked) tiposSelecionados.push('MUNICIPAL');

        if (tiposSelecionados.length === 0) {
            showToast('Selecione pelo menos uma certidão para monitorar!', 'error');
            return;
        }

        try {
            if (editingEmpresaId) {
                // Atualiza Empresa Existente
                const { error: errEmpresa } = await supabaseClient
                    .from('empresas')
                    .update({
                        apelido, razao_social, uf, municipio,
                        inscricao_estadual: ie || null,
                        inscricao_municipal: im || null
                    })
                    .eq('id', editingEmpresaId);

                if (errEmpresa) throw errEmpresa;

                // Gerencia certidões (Adiciona novas e remove desmarcadas)
                const activeTypes = certidoesData.filter(c => c.empresa_id === editingEmpresaId).map(c => c.tipo_certidao);
                const aAdicionar = tiposSelecionados.filter(t => !activeTypes.includes(t));
                const aRemover = activeTypes.filter(t => !tiposSelecionados.includes(t));

                // Adiciona novas selecionadas
                if (aAdicionar.length > 0) {
                    const configsAdicionar = aAdicionar.map(tipo => ({
                        empresa_id: editingEmpresaId,
                        tipo_certidao: tipo,
                        periodicidade_dias: 28,
                        obrigatoria: true
                    }));
                    const { error: errAddConfigs } = await supabaseClient.from('certidoes_config').insert(configsAdicionar);
                    if (errAddConfigs) throw errAddConfigs;

                    const matrizAdicionar = configsAdicionar.map(cfg => ({
                        empresa_id: cfg.empresa_id,
                        tipo_certidao: cfg.tipo_certidao,
                        status: 'Pendente',
                        ultimo_log: 'Adicionado via edição da empresa.'
                    }));
                    const { data: matrizInserida, error: errAddMatriz } = await supabaseClient
                        .from('certidoes_matriz')
                        .insert(matrizAdicionar)
                        .select();
                    if (errAddMatriz) throw errAddMatriz;

                    const filaAdicionar = matrizInserida.map(m => ({
                        certidao_matriz_id: m.id,
                        status: 'pendente'
                    }));
                    const { error: errAddFila } = await supabaseClient.from('fila_execucao').insert(filaAdicionar);
                    if (errAddFila) throw errAddFila;
                }

                // Remove desmarcadas
                if (aRemover.length > 0) {
                    const { error: errDelConfigs } = await supabaseClient
                        .from('certidoes_config')
                        .delete()
                        .eq('empresa_id', editingEmpresaId)
                        .in('tipo_certidao', aRemover);
                    if (errDelConfigs) throw errDelConfigs;

                    const { error: errDelMatriz } = await supabaseClient
                        .from('certidoes_matriz')
                        .delete()
                        .eq('empresa_id', editingEmpresaId)
                        .in('tipo_certidao', aRemover);
                    if (errDelMatriz) throw errDelMatriz;
                }

                showToast('Empresa atualizada com sucesso!', 'success');
                fecharModal();
                carregarDados();
            } else {
                // 1. Cadastra a Empresa
                const { data: novaEmpresa, error: errEmpresa } = await supabaseClient
                    .from('empresas')
                    .insert({
                        cnpj, apelido, razao_social, uf, municipio,
                        inscricao_estadual: ie || null,
                        inscricao_municipal: im || null
                    })
                    .select()
                    .single();

                if (errEmpresa) throw errEmpresa;

                // 2. Cria as configurações para as certidões selecionadas
                const configs = tiposSelecionados.map(tipo => ({
                    empresa_id: novaEmpresa.id,
                    tipo_certidao: tipo,
                    periodicidade_dias: 28,
                    obrigatoria: true
                }));
                
                const { error: errConfigs } = await supabaseClient.from('certidoes_config').insert(configs);
                if (errConfigs) throw errConfigs;

                // 3. Inicializa a Matriz com status 'Pendente'
                const matriz = configs.map(cfg => ({
                    empresa_id: cfg.empresa_id,
                    tipo_certidao: cfg.tipo_certidao,
                    status: 'Pendente',
                    ultimo_log: 'Inicializado via cadastro da empresa.'
                }));
                
                const { data: matrizInserida, error: errMatriz } = await supabaseClient
                    .from('certidoes_matriz')
                    .insert(matriz)
                    .select();
                    
                if (errMatriz) throw errMatriz;

                // 4. Insere na fila de execução automática para processar imediatamente
                const fila = matrizInserida.map(m => ({
                    certidao_matriz_id: m.id,
                    status: 'pendente'
                }));
                
                const { error: errFila } = await supabaseClient.from('fila_execucao').insert(fila);
                if (errFila) throw errFila;

                showToast('Empresa cadastrada e certidões agendadas!', 'success');
                fecharModal();
                carregarDados();
            }
            
        } catch (err) {
            showToast('Erro ao salvar empresa: ' + err.message, 'error');
            console.error(err);
        }
    });
}

// Configuração dos filtros de tabela em tempo real
function configurarFiltros() {
    dom.filterSearch.addEventListener('keyup', renderizarDashboardTable);
    dom.filterTipo.addEventListener('change', renderizarDashboardTable);
    dom.filterStatus.addEventListener('change', renderizarDashboardTable);
    
    dom.btnTriggerCron.addEventListener('click', verificarVencimentos);
}

// Inicializa o APP
async function init() {
    configurarTema();
    configurarSidebarToggle();
    configurarNavegacao();
    
    const conectado = await inicializarSupabase();
    if (conectado) {
        configurarModais();
        configurarFiltros();
        await carregarDados();
        configurarRealtime();
        
        // Polling de segurança a cada 20 segundos (caso o realtime oscile)
        setInterval(carregarDados, 20000);
    }
}

document.addEventListener('DOMContentLoaded', init);
