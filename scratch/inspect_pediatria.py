import os
import ssl
from dotenv import load_dotenv

# Bypass SSL para redes corporativas
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

from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def main():
    print("Buscando a empresa PEDIATRIA...")
    # Busca empresa cujo apelido ou nome contenha 'PEDIATRIA' (case-insensitive)
    empresas_res = supabase.table("empresas").select("*").execute()
    empresas = empresas_res.data
    
    pediatria = None
    for emp in empresas:
        apelido = emp.get("apelido") or ""
        razao = emp.get("razao_social") or ""
        if "pediatria" in apelido.lower() or "pediatria" in razao.lower():
            pediatria = emp
            print(f"Empresa encontrada: ID={emp['id']} | CNPJ={emp['cnpj']} | Apelido={emp['apelido']} | Razão={emp['razao_social']}")
            break
            
    if not pediatria:
        print("Empresa PEDIATRIA não encontrada! Todas as empresas:")
        for emp in empresas:
            print(f" - ID={emp['id']} | CNPJ={emp['cnpj']} | Apelido={emp.get('apelido')} | Razão={emp.get('razao_social')}")
        return
        
    print("\nBuscando as certidões matriz associadas...")
    matriz_res = supabase.table("certidoes_matriz").select("*").eq("empresa_id", pediatria["id"]).execute()
    certidoes = matriz_res.data
    
    print(f"Encontradas {len(certidoes)} certidões matriz:")
    for cert in certidoes:
        print(f" - ID: {cert['id']} | Tipo: {cert['tipo_certidao']} | Status: {cert['status']} | Última Emissão: {cert.get('data_emissao')} | Vencimento: {cert.get('data_vencimento')}")

if __name__ == "__main__":
    main()
