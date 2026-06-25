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

def inspect():
    empresa_id = "3f5ffd0c-6b4e-4257-8e6b-a1b80b38d9fe"
    
    # Find CND Municipal
    res = supabase.table("certidoes_matriz").select("*").eq("empresa_id", empresa_id).eq("tipo_certidao", "MUNICIPAL").execute()
    print("=== certidoes_matriz row ===")
    for row in res.data:
        print("ID:", row["id"])
        print("Status:", row["status"])
        print("Data Emissão:", row["data_emissao"])
        print("Data Vencimento:", row["data_vencimento"])
        print("URL PDF:", row["url_pdf"])
        print("Último Log:", row["ultimo_log"])
        print("-" * 50)
        
    # Let's also look at all fila_execucao jobs for this certidao_matriz
    if res.data:
        matriz_id = res.data[0]["id"]
        jobs = supabase.table("fila_execucao").select("*").eq("certidao_matriz_id", matriz_id).order("id", desc=True).limit(5).execute()
        print("=== fila_execucao jobs ===")
        for job in jobs.data:
            print(f"Job ID: {job['id']} | Status: {job['status']} | Tentativas: {job['tentativas']} | Agendamento: {job['data_agendamento']}")
            print(f"  Log erro: {job['log_erro']}")

if __name__ == "__main__":
    inspect()
