import os
import ssl
import httpx

# Disable SSL verification globally for httpx (used by supabase-py)
original_init = httpx.Client.__init__
def custom_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_init(self, *args, **kwargs)
httpx.Client.__init__ = custom_init

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def run_correction():
    empresa_id = "3f5ffd0c-6b4e-4257-8e6b-a1b80b38d9fe"
    print(f"Iniciando correção da PEDIATRIA (ID: {empresa_id})...")
    
    # 1. Corrige CND Municipal
    print("Atualizando CND Municipal...")
    res_mun = supabase.table("certidoes_matriz").update({
        "status": "Regular",
        "data_emissao": "2026-06-23",
        "data_vencimento": "2026-12-20",
        "ultimo_log": "Correção de data efetuada manualmente de acordo com a liberação contida no PDF."
    }).eq("id", "79755429-c2ea-42ec-bbde-74b55a38ebb4").execute()
    print("Resultado Municipal:", res_mun.data)
    
    # 2. Restaura CND FGTS
    print("Restaurando CND FGTS...")
    res_fgts = supabase.table("certidoes_matriz").update({
        "status": "Regular",
        "ultimo_log": "Status restaurado manualmente (certidão emitida em 23/06/2026 é válida até 23/07/2026)."
    }).eq("id", "cd5bde12-c59b-452f-8896-d68fdf26bc2b").execute()
    print("Resultado FGTS:", res_fgts.data)
    
    # 3. Restaura CND Federal
    print("Restaurando CND Federal...")
    res_fed = supabase.table("certidoes_matriz").update({
        "status": "Regular",
        "ultimo_log": "Status restaurado manualmente (certidão emitida em 23/06/2026 é válida até 20/12/2026)."
    }).eq("id", "909b9866-034a-4afc-8174-62c00a76759c").execute()
    print("Resultado Federal:", res_fed.data)
    
    # 4. Limpa jobs pendentes/com falha recentes na fila de execução para evitar novas tentativas erradas imediatas
    print("Limpando status das execuções pendentes recentes para PEDIATRIA...")
    res_fila = supabase.table("fila_execucao")\
        .update({"status": "sucesso", "log_erro": "Status e data corrigidos manualmente no banco."})\
        .eq("certidao_matriz_id", "79755429-c2ea-42ec-bbde-74b55a38ebb4")\
        .in_("status", ["pendente", "processando", "falha"])\
        .execute()
    print("Resultado fila Municipal:", len(res_fila.data), "linhas atualizadas.")
    
    res_fila_fgts = supabase.table("fila_execucao")\
        .update({"status": "sucesso", "log_erro": "Status restaurado manualmente."})\
        .eq("certidao_matriz_id", "cd5bde12-c59b-452f-8896-d68fdf26bc2b")\
        .in_("status", ["pendente", "processando", "falha"])\
        .execute()
    print("Resultado fila FGTS:", len(res_fila_fgts.data), "linhas atualizadas.")

    res_fila_fed = supabase.table("fila_execucao")\
        .update({"status": "sucesso", "log_erro": "Status restaurado manualmente."})\
        .eq("certidao_matriz_id", "909b9866-034a-4afc-8174-62c00a76759c")\
        .in_("status", ["pendente", "processando", "falha"])\
        .execute()
    print("Resultado fila Federal:", len(res_fila_fed.data), "linhas atualizadas.")
    
    print("Correções concluídas com sucesso!")

if __name__ == "__main__":
    run_correction()
