-- Script de Carga de Dados Iniciais (Mock / Testes)

-- 1. Inserir Empresas do Grupo (Exemplos de Filiais)
INSERT INTO empresas (cnpj, razao_social, apelido, uf, municipio, inscricao_municipal, inscricao_estadual)
VALUES 
('12345678000199', 'Home Health Care Doctor Servicos Medicos SP Ltda', 'SP-MATRIZ', 'SP', 'São Paulo', '123456-7', '110.220.330.111'),
('12345678000270', 'Home Health Care Doctor Servicos Medicos RJ Ltda', 'RJ-COPACABANA', 'RJ', 'Rio de Janeiro', '765432-1', '220.330.440.222')
ON CONFLICT (cnpj) DO NOTHING;

-- 2. Configurar Certidões para as Empresas
-- SP Matriz: exige Federal, FGTS e Municipal
INSERT INTO certidoes_config (empresa_id, tipo_certidao, periodicidade_dias, obrigatoria)
SELECT id, 'FEDERAL', 28, TRUE FROM empresas WHERE apelido = 'SP-MATRIZ'
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;

INSERT INTO certidoes_config (empresa_id, tipo_certidao, periodicidade_dias, obrigatoria)
SELECT id, 'FGTS', 28, TRUE FROM empresas WHERE apelido = 'SP-MATRIZ'
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;

INSERT INTO certidoes_config (empresa_id, tipo_certidao, periodicidade_dias, obrigatoria)
SELECT id, 'MUNICIPAL', 28, TRUE FROM empresas WHERE apelido = 'SP-MATRIZ'
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;

-- RJ Copacabana: exige Federal e FGTS, Municipal não se aplica (obrigatoria = false)
INSERT INTO certidoes_config (empresa_id, tipo_certidao, periodicidade_dias, obrigatoria)
SELECT id, 'FEDERAL', 28, TRUE FROM empresas WHERE apelido = 'RJ-COPACABANA'
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;

INSERT INTO certidoes_config (empresa_id, tipo_certidao, periodicidade_dias, obrigatoria)
SELECT id, 'FGTS', 28, TRUE FROM empresas WHERE apelido = 'RJ-COPACABANA'
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;

INSERT INTO certidoes_config (empresa_id, tipo_certidao, periodicidade_dias, obrigatoria)
SELECT id, 'MUNICIPAL', 28, FALSE FROM empresas WHERE apelido = 'RJ-COPACABANA'
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;


-- 3. Inicializar a Matriz de Certidões (Com datas antigas ou vazias para disparar renovação)
INSERT INTO certidoes_matriz (empresa_id, tipo_certidao, status, data_emissao, data_vencimento, ultimo_log)
SELECT 
    c.empresa_id, 
    c.tipo_certidao, 
    'Pendente', 
    CURRENT_DATE - INTERVAL '35 days', -- Força expiração/renovação
    CURRENT_DATE - INTERVAL '7 days',  -- Certidão já vencida
    'Carga de dados inicial'
FROM certidoes_config c
WHERE c.obrigatoria = TRUE
ON CONFLICT (empresa_id, tipo_certidao) DO NOTHING;


-- 4. Alimentar a Fila de Execução para as certidões pendentes/vencidas
INSERT INTO fila_execucao (certidao_matriz_id, status, data_agendamento)
SELECT id, 'pendente', now()
FROM certidoes_matriz
WHERE status = 'Pendente' OR data_vencimento <= CURRENT_DATE
ON CONFLICT DO NOTHING;
