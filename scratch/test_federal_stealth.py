import os
import sys
import time
from playwright.sync_api import sync_playwright
from PIL import Image

def test_federal_stealth():
    cnpj = "09440233000180"
    print("Testando Receita Federal em modo Headless com injeções Stealth...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo"
        )
        
        # Inject stealth properties
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)
        
        page = context.new_page()
        
        try:
            url = "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj"
            print(f"Navegando para {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            cnpj_selector = 'input[name="niContribuinte"]'
            print("Aguardando o campo CNPJ...")
            page.wait_for_selector(cnpj_selector, timeout=20000)
            print("Sucesso! O campo CNPJ foi localizado.")
            
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_selector, cnpj_limpo)
            page.press(cnpj_selector, "Tab")
            print("CNPJ preenchido.")
            time.sleep(1.0)
            
            # Dismiss cookies
            try:
                btn_cookies = 'button:has-text("Aceitar")'
                if page.locator(btn_cookies).is_visible():
                    page.click(btn_cookies)
                    time.sleep(0.5)
            except:
                pass
                
            btn_selector = 'button:has-text("Emitir Certidão")'
            page.wait_for_selector(btn_selector, timeout=10000)
            page.click(btn_selector)
            print("Clicou em Emitir Certidão. Aguardando resultado...")
            
            # Handle potential "Emitir Nova Certidão" dialog
            try:
                btn_xpath = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[2]'
                btn_texto = 'button:has-text("Emitir Nova Certidão")'
                page.wait_for_selector('modal-container', timeout=5000)
                time.sleep(0.5)
                if page.locator(btn_xpath).is_visible():
                    page.click(btn_xpath)
                    print("Clicou em Emitir Nova Certidão (xpath).")
                elif page.locator(btn_texto).is_visible():
                    page.click(btn_texto)
                    print("Clicou em Emitir Nova Certidão (texto).")
            except:
                pass
            
            # Wait for results or error
            sucesso_selector = "iframe:not([src*='hcaptcha']):not([src*='google']), embed, object, [href*='.pdf']"
            erro_selector = ".alert, .error, .message-error, .mensagem-erro, #mensagemErro, .br-message, .feedback, .invalid-feedback"
            
            page.wait_for_selector(f"{sucesso_selector}, {erro_selector}", timeout=25000)
            print("Página respondeu!")
            
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    print("Erro do portal:", el.inner_text().strip())
                    return
            
            if page.query_selector(sucesso_selector):
                print("PDF renderizado em tela! Sucesso total!")
                temp_pdf_path = f"temp_federal_stealth_{cnpj}.pdf"
                page.pdf(path=temp_pdf_path)
                print(f"PDF salvo em {temp_pdf_path}")
            else:
                body_text = page.locator("body").inner_text()
                print("Texto da página:", body_text[:200])
                
        except Exception as e:
            print(f"Erro no modo Headless Stealth: {e}")
            page.screenshot(path="federal_stealth_error.png")
            print("Screenshot de erro salvo em 'federal_stealth_error.png'")
        finally:
            browser.close()

if __name__ == "__main__":
    test_federal_stealth()
