import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ssl
import time
from playwright.sync_api import sync_playwright
import ddddocr

def test_municipal_stealth():
    cnpj = "09440233000180"
    print("Testando Municipal SP em modo Headless com injeções Stealth...")
    
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
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
            url = "https://duc.prefeitura.sp.gov.br/certidoes/forms_anonimo/frmConsultaEmissaoCertificado.aspx"
            print(f"Navegando para {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Close cookie popup by authorizing all cookies
            try:
                cookie_btn = page.locator('.cc__button__autorizacao--all')
                if cookie_btn.count() > 0:
                    cookie_btn.click()
                    time.sleep(0.5)
            except:
                pass
                
            # Wait for dropdown
            dropdown_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_ddlTipoCertidao"]'
            page.wait_for_selector(dropdown_xpath, timeout=15000)
            page.select_option(dropdown_xpath, label="Certidão Tributária Mobiliária")
            print("Dropdown selecionado.")
            time.sleep(2)
            
            cnpj_input_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_txtCNPJ"]'
            page.wait_for_selector(cnpj_input_xpath, timeout=15000)
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_input_xpath, cnpj_limpo)
            print("CNPJ preenchido.")
            
            captcha_img_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_imgCaptcha"]'
            captcha_input_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_txtValorCaptcha"]'
            emitir_btn_xpath = 'xpath=//*[@id="ctl00_ConteudoPrincipal_btnEmitir"]'
            
            page.wait_for_selector(captcha_img_xpath, timeout=10000)
            img_el = page.locator(captcha_img_xpath)
            
            # Instead of screenshot wait_for_visible, get screenshot bytes directly or try screenshot
            img_bytes = img_el.screenshot()
            
            captcha_val = ocr.classification(img_bytes)
            captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
            print(f"ddddocr decodificou o CAPTCHA como: '{captcha_val}'")
            
            page.fill(captcha_input_xpath, captcha_val)
            print("Enviando formulário...")
            
            # Expect download
            try:
                with page.expect_download(timeout=15000) as download_info:
                    page.click(emitir_btn_xpath)
                download = download_info.value
                temp_pdf_path = f"temp_municipal_stealth_{cnpj}.pdf"
                download.save_as(temp_pdf_path)
                print(f"PDF baixado com sucesso em: {temp_pdf_path}")
            except Exception as e:
                # Check for errors on page
                erro_selector = "#ctl00_ConteudoPrincipal_lblMensagem, .alert, .erro, .mensagem-erro"
                erro_msg = ""
                elementos_erro = page.query_selector_all(erro_selector)
                for el in elementos_erro:
                    if el.is_visible():
                        erro_msg = el.inner_text().strip()
                        break
                if erro_msg:
                    print(f"Erro reportado no portal: {erro_msg}")
                else:
                    print(f"Falha ou timeout no download: {e}")
                    page.screenshot(path="municipal_stealth_error.png")
                    print("Screenshot salvo em 'municipal_stealth_error.png'")
                
        except Exception as e:
            print(f"Exceção: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    test_municipal_stealth()
