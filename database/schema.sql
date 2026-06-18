-- Script de Criação do Banco de Dados - Controle de Certidões Negativas (Supabase/PostgreSQL)

-- 1. Habilitar extensões necessárias se aplicável
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Tabela de Empresas/Filiais (Cadastro Central)
CREATE TABLE IF NOT EXISTS empresas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cnpj VARCHAR(14) UNIQUE NOT NULL,
    razao_social VARCHAR(255) NOT NULL,
    apelido VARCHAR(100),
    uf CHAR(2) NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    inscricao_estadual VARCHAR(50),
    inscricao_municipal VARCHAR(50),
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Tabela de Configuração de Certidões por Empresa
CREATE TABLE IF NOT EXISTS certidoes_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    tipo_certidao VARCHAR(50) NOT NULL, -- ex: 'FEDERAL', 'FGTS', 'CNDT', 'MUNICIPAL', 'CADIN_ESTADUAL'
    periodicidade_dias INT DEFAULT 28, -- renovação a cada X dias
    obrigatoria BOOLEAN DEFAULT TRUE, -- para controle de 'Não se aplica'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(empresa_id, tipo_certidao)
);

-- 4. Tabela Matriz de Certidões (Guarda o Status Atualizado de cada CND)
CREATE TABLE IF NOT EXISTS certidoes_matriz (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    tipo_certidao VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'Pendente' CHECK (status IN ('Pendente', 'Regular', 'Vencida', 'Em Renovação', 'Atenção', 'Erro')),
    data_emissao DATE,
    data_vencimento DATE,
    url_pdf TEXT,
    ultimo_log TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(empresa_id, tipo_certidao)
);

-- 5. Tabela de Fila de Execução do RPA
CREATE TABLE IF NOT EXISTS fila_execucao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    certidao_matriz_id UUID REFERENCES certidoes_matriz(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'sucesso', 'falha')),
    tentativas INT DEFAULT 0,
    max_tentativas INT DEFAULT 3,
    log_erro TEXT,
    data_agendamento TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Criação de índices para ganho de performance na fila de processamento
CREATE INDEX IF NOT EXISTS idx_fila_pendente 
ON fila_execucao (status, data_agendamento) 
WHERE status = 'pendente';

-- 7. Função PostgreSQL para Controle de Concorrência e Reserva Segura de Tarefas (SELECT FOR UPDATE SKIP LOCKED)
CREATE OR REPLACE FUNCTION obter_proxima_tarefa(worker_id TEXT)
RETURNS TABLE (
    fila_id UUID,
    certidao_matriz_id UUID,
    tipo_certidao VARCHAR,
    cnpj VARCHAR,
    uf CHAR,
    municipio VARCHAR,
    inscricao_municipal VARCHAR,
    inscricao_estadual VARCHAR
) AS $$
DECLARE
    target_id UUID;
BEGIN
    -- Localiza e trava a próxima tarefa pendente de forma atômica
    SELECT f.id INTO target_id
    FROM fila_execucao f
    WHERE f.status = 'pendente'
      AND f.data_agendamento <= now()
      AND f.tentativas < f.max_tentativas
    ORDER BY f.data_agendamento ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF target_id IS NOT NULL THEN
        -- Atualiza imediatamente o status para evitar dupla execução
        UPDATE fila_execucao
        SET status = 'processando',
            tentativas = tentativas + 1,
            updated_at = now(),
            log_erro = 'Processado por: ' || worker_id
        WHERE id = target_id;

        -- Retorna os dados completos da empresa e certidão para o worker rodar
        RETURN QUERY
        SELECT 
            f.id as fila_id,
            f.certidao_matriz_id,
            m.tipo_certidao,
            e.cnpj,
            e.uf,
            e.municipio,
            e.inscricao_municipal,
            e.inscricao_estadual
        FROM fila_execucao f
        JOIN certidoes_matriz m ON f.certidao_matriz_id = m.id
        JOIN empresas e ON m.empresa_id = e.id
        WHERE f.id = target_id;
    END IF;
END;
$$ LANGUAGE plpgsql;
