import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from test_scrapers import obter_fgts

def test():
    cnpj = "09440233000180"
    print("Testando obter_fgts com native Chrome e headless=True...")
    res = obter_fgts(cnpj, headless=True)
    print("Resultado:", res)

if __name__ == "__main__":
    test()
