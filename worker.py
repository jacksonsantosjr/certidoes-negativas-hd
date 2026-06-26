import os
import sys
import time
import datetime
import ssl
from dotenv import load_dotenv
from supabase import create_client, Client

# Importa as funções de scraping do test_scrapers.py
import test_scrapers

# Configurações globais para ignorar verificações de SSL se necessário (ambiente corporativo)
try:
    original_create_default_context = ssl.create_default_context
    def custom_create_default_context(*args, **kwargs):
        context = original_create_default_context(*args, **kwargs)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    ssl.create_default_context = custom_create_default_context
    os.environ["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
except Exception:
    pass

# Carrega chaves do .env
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERRO CRÍTICO] SUPABASE_URL ou SUPABASE_KEY não configurados no arquivo .env!")
    sys.exit(1)

# Inicializa cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def log_msg(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def calcular_vencimento(tipo_certidao, emissao_str):
    emissao_dt = datetime.date.fromisoformat(emissao_str)
    if tipo_certidao == "fgts":
        # FGTS geralmente vale por 30 dias
        return (emissao_dt + datetime.timedelta(days=30)).isoformat()
    elif tipo_certidao in ["federal", "cndt", "municipal", "municipal_sp", "estadual", "estadual_sp"]:
        # Certidão Federal, CNDT e Mobiliária de SP geralmente valem por 180 dias (6 meses)
        return (emissao_dt + datetime.timedelta(days=180)).isoformat()
    else:
        # Default de 180 dias para contingência
        return (emissao_dt + datetime.timedelta(days=180)).isoformat()

def processar_tarefa(tarefa):
    tarefa_id = tarefa["id"]
    matriz_id = tarefa["certidao_matriz_id"]
    
    # 1. Busca os dados da certidão matriz e empresa
    try:
        matriz_res = supabase.table("certidoes_matriz").select("*").eq("id", matriz_id).single().execute()
        matriz_item = matriz_res.data
        if not matriz_item:
            raise Exception(f"Certidão Matriz ID {matriz_id} não localizada.")
            
        empresa_id = matriz_item["empresa_id"]
        tipo_certidao = matriz_item["tipo_certidao"].lower()
        
        empresa_res = supabase.table("empresas").select("*").eq("id", empresa_id).single().execute()
        empresa_item = empresa_res.data
        if not empresa_item:
            raise Exception(f"Empresa ID {empresa_id} não localizada.")
            
        cnpj = empresa_item["cnpj"]
        cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
        apelido = empresa_item.get("apelido", cnpj)
        
    except Exception as err:
        log_msg(f"Erro ao recuperar metadados da tarefa {tarefa_id}: {err}")
        supabase.table("fila_execucao").update({
            "status": "falha",
            "log_erro": f"Erro de metadados: {str(err)}",
            "tentativas": tarefa.get("tentativas", 0) + 1
        }).eq("id", tarefa_id).execute()
        return

    log_msg(f"Processando: Empresa '{apelido}' ({cnpj}) | Certidão: {tipo_certidao.upper()}")
    
    # 2. Executa o scraper adequado (Fases 1 e 2)
    resultado = {"status": "erro", "mensagem": "Scraper não implementado ou desabilitado para este tipo de certidão."}
    
    try:
        if tipo_certidao == "fgts":
            resultado = test_scrapers.obter_fgts(cnpj, headless=True)
        elif tipo_certidao == "federal":
            resultado = test_scrapers.obter_federal(cnpj, headless=True)
        elif tipo_certidao == "cndt":
            resultado = test_scrapers.obter_cndt(cnpj, headless=True)
        elif tipo_certidao in ["municipal", "municipal_sp"]:
            resultado = test_scrapers.obter_municipal_sp(cnpj, headless=True)
        elif tipo_certidao in ["estadual", "estadual_sp"]:
            resultado = test_scrapers.obter_estadual(cnpj, headless=True)
        else:
            log_msg(f"Tipo de certidão '{tipo_certidao}' ignorado pelo Worker.")
            
    except Exception as scrap_err:
        resultado = {"status": "erro", "mensagem": f"Exceção no scraper: {str(scrap_err)}"}

    # 3. Trata os resultados obtidos
    if resultado["status"] == "sucesso":
        pdf_path = resultado["pdf_path"]
        log_msg(f"    [SUCESSO] Certidão gerada localmente em: {pdf_path}")
        
        try:
            # 3a. Upload do arquivo para o Supabase Storage
            # Cria um nome único com timestamp para evitar cache e conflitos
            file_name = f"{tipo_certidao}_{int(time.time())}.pdf"
            storage_path = f"{cnpj_limpo}/{file_name}"
            
            with open(pdf_path, "rb") as f:
                supabase.storage.from_("cnds-arquivos").upload(
                    path=storage_path,
                    file=f,
                    file_options={"content-type": "application/pdf"}
                )
            
            # Obtém a URL pública do PDF
            url_pdf = supabase.storage.from_("cnds-arquivos").get_public_url(storage_path)
            log_msg(f"    [STORAGE] Upload concluído. URL: {url_pdf}")
            
            hoje = datetime.date.today().isoformat()
            vencimento = resultado.get("data_vencimento")
            if not vencimento:
                vencimento = calcular_vencimento(tipo_certidao, hoje)
            
            # Atualiza certidoes_matriz
            supabase.table("certidoes_matriz").update({
                "status": "Regular",
                "data_emissao": hoje,
                "data_vencimento": vencimento,
                "url_pdf": url_pdf,
                "ultimo_log": f"Emitida e atualizada com sucesso pelo Worker em {hoje}."
            }).eq("id", matriz_id).execute()
            
            # Marca tarefa como concluída na fila
            supabase.table("fila_execucao").update({
                "status": "sucesso",
                "log_erro": None,
                "tentativas": tarefa.get("tentativas", 0) + 1
            }).eq("id", tarefa_id).execute()
            
            log_msg(f"    [CONCLUÍDO] Fila e certidão atualizadas no Supabase.")
            
            # 3c. Remove o arquivo local temporário
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
                
        except Exception as upload_err:
            log_msg(f"    [ERRO] Falha no upload/atualização do banco: {upload_err}")
            # Se falhar o upload, registra o erro na fila e define status da certidão como erro
            supabase.table("fila_execucao").update({
                "status": "falha",
                "log_erro": f"Erro de upload/banco: {str(upload_err)}",
                "tentativas": tarefa.get("tentativas", 0) + 1
            }).eq("id", tarefa_id).execute()
            
            supabase.table("certidoes_matriz").update({
                "status": "Erro",
                "ultimo_log": f"Erro no pós-processamento: {str(upload_err)}"
            }).eq("id", matriz_id).execute()
            
    else:
        # Se falhar o scraper
        msg_erro = resultado.get("mensagem", "Erro desconhecido no scraper.")
        log_msg(f"    [FALHA] {msg_erro}")
        
        # Atualiza fila de execução
        supabase.table("fila_execucao").update({
            "status": "falha",
            "log_erro": msg_erro,
            "tentativas": tarefa.get("tentativas", 0) + 1
        }).eq("id", tarefa_id).execute()
        
        # Diferencia erro técnico/governamental de pendência fiscal real
        msg_erro_lower = msg_erro.lower()
        status_cnd = "Erro" # Padrão: Erro Governamental / Técnico
        
        keywords_pendencia = [
            "divergência", "débito", "pendência", "regularize", "situação fiscal", 
            "e-cac", "insuficiência", "não cadastrado", "consta como devedor",
            "devedora", "irregular", "restrição", "não possui certificado", "não foi possível emitir",
            "débitos", "pendências", "divergências", "irregularidades"
        ]
        
        if any(kw in msg_erro_lower for kw in keywords_pendencia):
            status_cnd = "Atenção" # Pendência Fiscal Real
            
        # Verifica se a certidão atual na matriz ainda está dentro do prazo de validade
        status_atual = matriz_item.get("status", "")
        vencimento_atual_str = matriz_item.get("data_vencimento")
        
        cnd_valida = False
        # Se a certidão tem vencimento futuro e o status atual não é de pendência ("Atenção"), ela continua válida
        if vencimento_atual_str and status_atual != "Atenção":
            try:
                venc_dt = datetime.date.fromisoformat(vencimento_atual_str)
                hoje_dt = datetime.date.today()
                if venc_dt >= hoje_dt:
                    cnd_valida = True
            except Exception:
                pass

        if status_cnd == "Erro" and cnd_valida:
            # Preserva/restaura o status 'Regular' válido e apenas loga a falha temporária
            log_msg(f"    [AVISO] Mantendo/restaurando status 'Regular' pois a certidão existente ainda é válida até {vencimento_atual_str}.")
            supabase.table("certidoes_matriz").update({
                "status": "Regular",
                "ultimo_log": f"Aviso: Tentativa automática de renovação falhou devido a erro técnico/governamental, mas a certidão atual permanece regular e válida. Detalhes: {msg_erro}"
            }).eq("id", matriz_id).execute()
        else:
            # Atualiza certidoes_matriz para refletir o erro com o status correto (se expirada ou pendência fiscal real)
            supabase.table("certidoes_matriz").update({
                "status": status_cnd,
                "ultimo_log": f"Falha na emissão automática: {msg_erro}"
            }).eq("id", matriz_id).execute()

def main():
    log_msg("=" * 70)
    log_msg(" CONTROLE DE CERTIDÕES - WORKER LOCAL PYTHON (FASES 1 E 2) ")
    log_msg("=" * 70)
    log_msg("Aguardando tarefas com status 'pendente' na fila do Supabase...")
    
    while True:
        try:
            # Consulta tarefas pendentes ordenadas por agendamento (mais antigo primeiro)
            res = supabase.table("fila_execucao")\
                .select("*")\
                .eq("status", "pendente")\
                .order("data_agendamento", desc=False)\
                .execute()
                
            tarefas = res.data
            
            if tarefas:
                tarefa = tarefas[0] # Pega a primeira tarefa pendente
                tarefa_id = tarefa["id"]
                
                log_msg(f"Nova tarefa pendente encontrada (ID: {tarefa_id}). Reservando...")
                
                # Transiciona o status para 'processando' imediatamente para evitar concorrência/duplicações
                update_res = supabase.table("fila_execucao")\
                    .update({"status": "processando"})\
                    .eq("id", tarefa_id)\
                    .eq("status", "pendente")\
                    .execute()
                
                # Se alterou com sucesso (garante que outro worker não pegou no mesmo milissegundo)
                if update_res.data:
                    processar_tarefa(tarefa)
                else:
                    log_msg("Tarefa já reservada por outra instância do Worker. Pulando.")
            
        except Exception as poll_err:
            log_msg(f"[AVISO] Erro no polling de tarefas (tentando novamente em 5s): {poll_err}")
            time.sleep(5)
            continue
            
        # Espera 3 segundos antes de consultar novamente a fila
        time.sleep(3)

if __name__ == "__main__":
    main()
